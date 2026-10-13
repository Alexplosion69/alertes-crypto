"""
Filtre sur le créateur (le « dev ») d'un token.

On ne SUIT pas les devs : ce sont eux qui vendent quand la communauté achète.
On s'en sert comme filtre de sécurité, pour écarter :
  - le dev qui détient encore une grosse part (il peut tout vendre d'un coup) ;
  - les wallets « initiés » liés entre eux qui tiennent une grosse part ;
  - le dev en série (beaucoup de tokens lancés) ou récidiviste (ses tokens précédents sont morts).

Sources gratuites : RugCheck (rapport complet, Solana), GoPlus (Base/BNB),
et notre propre mémoire des devs déjà croisés (alertes/devs.json).
"""
import json
import time
from pathlib import Path

import outils as v

DEV_DETIENT_MAX = 5      # % de l'offre encore détenu par le dev
INITIES_MAX = 15         # % détenu par des wallets initiés (liés) dans le top 20
DEV_SERIE_MAX = 5        # le dev a déjà créé 5 autres tokens ou plus (RugCheck ou notre mémoire)
DEV_MORTS_MAX = 2        # 2 tokens de ce dev déjà morts sous nos yeux : récidiviste
PLATEFORME_MIN = 30      # « créateur » vu sur 30 tokens ou plus : c'est une plateforme, pas un dev
MEMOIRE_JOURS = 30

FICHIER = Path("alertes/devs.json")
_mem = {"devs": {}, "par_token": {}}


# ---------------------------------------------------------------- mémoire
def charger():
    global _mem
    if FICHIER.exists():
        try:
            _mem = json.loads(FICHIER.read_text())
        except json.JSONDecodeError:
            pass
    _mem.setdefault("devs", {})
    _mem.setdefault("par_token", {})
    return _mem


def sauver():
    now = time.time()
    for ck in list(_mem["devs"]):
        toks = {tk: x for tk, x in _mem["devs"][ck].items() if now - x["ts"] < MEMOIRE_JOURS * 86400}
        if toks:
            _mem["devs"][ck] = toks
        else:
            del _mem["devs"][ck]
    _mem["par_token"] = {tk: ck for tk, ck in _mem["par_token"].items()
                         if ck in _mem["devs"] and tk in _mem["devs"][ck]}
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(_mem))


def noter(chain, createur, token_key):
    if not createur:
        return
    ck = v.key_of(chain, createur)
    _mem["devs"].setdefault(ck, {}).setdefault(token_key, {"ts": time.time(), "mort": False})
    _mem["par_token"][token_key] = ck


def marquer_mort(token_key):
    """Appelé par le suivi quand un token meurt (liquidité retirée, prix effondré)."""
    ck = _mem["par_token"].get(token_key)
    if ck and token_key in _mem["devs"].get(ck, {}):
        _mem["devs"][ck][token_key]["mort"] = True


def historique(chain, createur, token_key):
    """(autres tokens de ce dev vus par nous, dont morts)"""
    toks = _mem["devs"].get(v.key_of(chain, createur), {})
    autres = {k: x for k, x in toks.items() if k != token_key}
    return len(autres), sum(1 for x in autres.values() if x["mort"])


# ---------------------------------------------------------------- RugCheck complet (Solana)
def rugcheck(address):
    """Rapport complet RugCheck, résumé en ce qui nous intéresse. None si indisponible."""
    d = v.get_json(f"https://api.rugcheck.xyz/v1/tokens/{address}/report")
    if not d:
        return None
    risks = d.get("risks") or []
    createur = d.get("creator")
    top = d.get("topHolders") or []
    dev_pct = next((float(h.get("pct") or 0) for h in top
                    if createur and (h.get("owner") == createur or h.get("address") == createur)), 0.0)
    inities = sum(float(h.get("pct") or 0) for h in top if h.get("insider"))
    # liquidité verrouillée du marché principal
    lp = None
    best = -1
    for m in d.get("markets") or []:
        l = m.get("lp") or {}
        taille = float(l.get("quoteUSD") or 0) + float(l.get("baseUSD") or 0)
        if taille > best and l.get("lpLockedPct") is not None:
            best, lp = taille, float(l["lpLockedPct"])
    ct = d.get("creatorTokens")
    return {
        "dangers": [r.get("name") for r in risks if r.get("level") == "danger"],
        "warns": [r.get("name") for r in risks if r.get("level") == "warn"],
        "lp": lp,
        "rugged": bool(d.get("rugged")),
        "createur": createur,
        "dev_pct": round(dev_pct, 1),
        "inities_pct": round(inities, 1),
        "reseaux_inities": int(d.get("graphInsidersDetected") or 0),
        "nb_tokens_dev": len(ct) if isinstance(ct, list) else None,
    }


# ---------------------------------------------------------------- verdict
def verdict(t, createur, dev_pct=None, inities_pct=None, nb_tokens_dev=None):
    """Renvoie (ok, texte court). Inconnu ≠ dangereux : un dev non identifié n'est pas rejeté."""
    if dev_pct is not None and dev_pct > DEV_DETIENT_MAX:
        return False, f"le dev détient encore {dev_pct:.0f} % de l'offre"
    if inities_pct is not None and inities_pct > INITIES_MAX:
        return False, f"des wallets initiés liés détiennent {inities_pct:.0f} %"
    if not createur:
        return True, "dev non identifié"
    if t["chain"] != "solana":
        # Base/BNB : le « créateur » est souvent le contrat de la plateforme de lancement
        # (four.meme, Clanker…) ; on ne juge que la part qu'il détient
        txt = f"créateur détient {dev_pct:.0f} %" if dev_pct is not None else "part du créateur inconnue"
        return True, txt
    noter(t["chain"], createur, t["key"])
    vus, morts = historique(t["chain"], createur, t["key"])
    if vus >= PLATEFORME_MIN:
        return True, "créateur = plateforme de lancement (historique non pertinent)"
    if morts >= DEV_MORTS_MAX:
        return False, f"dev récidiviste : {morts} de ses tokens précédents sont morts"
    serie = max(nb_tokens_dev or 0, vus)
    if serie >= DEV_SERIE_MAX:
        return False, f"dev en série : {serie} autres tokens créés"
    parts = []
    if dev_pct is not None:
        parts.append(f"dev détient {dev_pct:.0f} %")
    if serie:
        parts.append(f"{serie} autre(s) token(s) du même dev, {morts} mort(s)")
    else:
        parts.append("pas d'autre token connu de ce dev")
    return True, "dev : " + ", ".join(parts)
