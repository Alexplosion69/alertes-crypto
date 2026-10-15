"""
Smart wallets : repérer les wallets qui achètent tôt les tokens qui font x3, puis surveiller
quand plusieurs d'entre eux achètent le même nouveau token.

Comment la liste se construit (automatiquement, gratuitement) :
  1. pour chaque token jeune suivi par le bot, on lit les 300 dernières transactions
     (GeckoTerminal, gratuit) et on note qui a acheté, à quel prix, pour combien ;
  2. si le token monte ensuite à 3x le prix d'achat d'un wallet : un « bon coup » pour lui ;
     si le token meurt ou ne fait pas x3 en 72 h : un coup raté ;
  3. un wallet devient « smart » quand il a au moins 2 bons coups ET au moins 40 % de réussite.
     Les bots qui achètent tout (snipers) ont un taux de réussite très bas : ils sont écartés.

Le signal : au moins 3 smart wallets ont acheté le même token (pas forcément en même temps),
et le prix n'est pas déjà à plus de 2x leur prix d'entrée moyen (sinon on arrive trop tard,
exactement le problème des alertes « baleine » de Fomo).

EN_DIRECT = False : mode observation. Les signaux sont enregistrés et apparaissent dans le
bilan quotidien avec ce qu'ils sont devenus, mais ne sont pas envoyés en alerte. On passe à
True quand le bilan montre que ça marche.

Tu peux ajouter des wallets à la main dans portefeuilles_manuels.txt (toujours considérés smart).
"""
import json
import time
from datetime import datetime
from pathlib import Path

import outils as v
import suivi

FICHIER = Path("alertes/portefeuilles.json")
MANUELS = Path("portefeuilles_manuels.txt")

EN_DIRECT = False             # False = observation (bilan quotidien seulement)
TRADES_PAR_CYCLE = 8          # pools lus par cycle (GeckoTerminal gratuit : on reste raisonnable)
COLLECTE_AGE_MAX_H = 24       # on lit les acheteurs des tokens de moins de 24 h
COLLECTE_LIQ_MIN = 15_000
RELECTURE_MIN = 20            # pas deux lectures du même pool en moins de 20 min
ACHAT_MIN_USD = 50            # achats plus petits ignorés (poussière, bots)
ACHETEURS_MAX_PAR_TOKEN = 400
BON_COUP_X = 3                # le token a fait x3 après l'achat = bon coup
RESOLUTION_H = 72             # au bout de 72 h sans x3 : coup raté
SMART_MIN_BONS_COUPS = 3       # 2 au départ : trop facile avec une base de 2 jours (−45 % au bilan)
SMART_MIN_TAUX = 0.40
SMART_MIN_TOKENS = 5           # il faut avoir vu le wallet sur au moins 5 tokens
SIGNAL_MIN_WALLETS = 3        # 2 wallets, ce n'est pas assez
SIGNAL_TROP_TARD_X = 2        # prix déjà à 2x leur entrée moyenne : trop tard
SIGNAL_REALERTE_H = 24


def charger():
    if FICHIER.exists():
        try:
            pf = json.loads(FICHIER.read_text())
            for k, d in (("obs", {}), ("w", {}), ("signaux", []), ("signales", {})):
                pf.setdefault(k, d)
            return pf
        except json.JSONDecodeError:
            pass
    return {"obs": {}, "w": {}, "signaux": [], "signales": {}}


def sauver(pf):
    now = time.time()
    # on oublie les wallets vus une seule fois sans succès (3 j) et ceux inactifs depuis 30 j
    pf["w"] = {k: x for k, x in pf["w"].items()
               if not (x[1] == 0 and x[0] <= 1 and now - x[2] > 3 * 86400)
               and now - x[2] < 30 * 86400}
    pf["signaux"] = [s for s in pf["signaux"] if now - s["ts"] < 30 * 86400]
    pf["signales"] = {k: ts for k, ts in pf["signales"].items() if now - ts < SIGNAL_REALERTE_H * 3600}
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(pf, separators=(",", ":")))


def manuels():
    """Wallets ajoutés à la main : une adresse par ligne, texte après # ignoré."""
    res = set()
    if not MANUELS.exists():
        return res
    for ligne in MANUELS.read_text(encoding="utf-8").splitlines():
        addr = ligne.split("#", 1)[0].strip().split(" ")[0] if ligne.strip() else ""
        if not addr:
            continue
        if addr.lower().startswith("0x"):
            res |= {v.key_of("base", addr), v.key_of("bsc", addr)}
        else:
            res.add(v.key_of("solana", addr))
    return res


def smart(pf):
    auto = {k for k, (n, w, _) in pf["w"].items()
            if w >= SMART_MIN_BONS_COUPS and n >= SMART_MIN_TOKENS and w / n >= SMART_MIN_TAUX}
    return auto | manuels()


def stats(pf):
    return len(pf["w"]), len(smart(pf))


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _compter(pf, chain, wallet, bon):
    k = v.key_of(chain, wallet)
    n, w, _ = pf["w"].get(k, [0, 0, 0])
    pf["w"][k] = [n + 1, w + (1 if bon else 0), round(time.time())]


# ---------------------------------------------------------------- collecte des acheteurs
def collecter(pf, sv, verifier, envoyer):
    now = time.time()
    cands = [(k, e) for k, e in sv["tokens"].items()
             if e.get("pair") and e["chain"] in v.GT_NETWORKS
             and now - e["created"] <= COLLECTE_AGE_MAX_H * 3600
             and e["serie"][-1][3] >= COLLECTE_LIQ_MIN
             and now - pf["obs"].get(k, {}).get("last_fetch", 0) > RELECTURE_MIN * 60]
    cands.sort(key=lambda x: pf["obs"].get(x[0], {}).get("last_fetch", 0))
    for k, e in cands[:TRADES_PAR_CYCLE]:
        chain = e["chain"]
        o = pf["obs"].setdefault(k, {"chain": chain, "debut": now, "buys": {}, "sells": {},
                                     "done": [], "last_fetch": 0, "vu_jusqua": 0})
        o["last_fetch"] = now
        data = v.gt_get(f"/networks/{v.GT_NETWORKS[chain]}/pools/{e['pair']}/trades")
        if not data:
            continue
        base = e["address"].lower()
        vu = o["vu_jusqua"]
        dernier = (0, None)
        for item in data.get("data") or []:
            a = item.get("attributes") or {}
            ts = _ts(a.get("block_timestamp"))
            w = a.get("tx_from_address")
            if ts is None or not w or ts <= o["vu_jusqua"]:
                continue                         # déjà compté lors d'une lecture précédente
            vu = max(vu, ts)
            kind = a.get("kind")
            if (a.get("to_token_address") or "").lower() == base:
                prix = a.get("price_to_in_usd")
            elif (a.get("from_token_address") or "").lower() == base:
                prix = a.get("price_from_in_usd")
            else:
                prix = a.get("price_to_in_usd") if kind == "buy" else a.get("price_from_in_usd")
            try:
                prix, usd = float(prix or 0), float(a.get("volume_in_usd") or 0)
            except (TypeError, ValueError):
                continue
            if prix and ts > dernier[0]:
                dernier = (ts, prix)
            wk = w if chain == "solana" else w.lower()
            if kind == "buy":
                if usd < ACHAT_MIN_USD or not prix:
                    continue
                b = o["buys"].get(wk)
                if b:
                    b[2] = round(b[2] + usd, 2)
                    if ts < b[0]:
                        b[0], b[1] = ts, prix
                elif len(o["buys"]) < ACHETEURS_MAX_PAR_TOKEN:
                    o["buys"][wk] = [ts, prix, round(usd, 2)]
            elif kind == "sell":
                o["sells"][wk] = round(o["sells"].get(wk, 0) + usd, 2)
        o["vu_jusqua"] = vu
        if dernier[1] and dernier[0] >= o.get("dernier_prix_ts", 0):
            o["dernier_prix"], o["dernier_prix_ts"] = dernier[1], dernier[0]
        detecter(pf, k, e, o, verifier, envoyer)


# ---------------------------------------------------------------- bons / mauvais coups
def resoudre(pf, sv):
    """À appeler après chaque relevé de prix du suivi."""
    now = time.time()
    for k, o in list(pf["obs"].items()):
        e = sv["tokens"].get(k)
        done = set(o["done"])
        if e:
            for w, (ts, prix, _) in o["buys"].items():
                if w in done or not prix:
                    continue
                haut = suivi.plus_haut_apres(e, ts)
                if haut and haut >= BON_COUP_X * prix:
                    _compter(pf, o["chain"], w, True)
                    done.add(w)
            o["done"] = list(done)
        if e is None or now - o["debut"] > RESOLUTION_H * 3600:
            for w in o["buys"]:
                if w not in done:
                    _compter(pf, o["chain"], w, False)
            del pf["obs"][k]


# ---------------------------------------------------------------- signal
def fmt_usd(x):
    return f"{x / 1e6:.2f} M$" if x >= 1e6 else f"{x / 1e3:.0f} k$"


def detecter(pf, k, e, o, verifier, envoyer):
    now = time.time()
    if now - pf["signales"].get(k, 0) < SIGNAL_REALERTE_H * 3600:
        return
    s = smart(pf)
    presents = [w for w in o["buys"] if v.key_of(o["chain"], w) in s]
    if len(presents) < SIGNAL_MIN_WALLETS:
        return
    entree = sum(o["buys"][w][1] for w in presents) / len(presents)
    dernier = e["serie"][-1]
    # prix le plus récent : dernière transaction lue ou dernier relevé du suivi
    prix = (o["dernier_prix"] if o.get("dernier_prix") and o.get("dernier_prix_ts", 0) > dernier[0]
            else dernier[1])
    ratio_mcap = dernier[2] / dernier[1] if dernier[1] else 0
    mcap, mcap_entree = prix * ratio_mcap, entree * ratio_mcap
    trop_tard = prix > SIGNAL_TROP_TARD_X * entree
    t = {"key": k, "chain": e["chain"], "address": e["address"], "symbol": e["symbol"]}
    ok, sec = (False, "non vérifié (trop tard)") if trop_tard else verifier(t)
    records = []
    for w in presents:
        n, bons, _ = pf["w"].get(v.key_of(o["chain"], w), [0, 0, 0])
        records.append(f"{bons}/{n}" if n else "manuel")
    vendu = sum(1 for w in presents if o["sells"].get(w))
    sig = {"ts": now, "key": k, "symbol": e["symbol"], "chain": e["chain"],
           "address": e["address"], "url": e.get("url"), "price": prix, "mcap": mcap,
           "wallets": len(presents), "entree_moy": entree, "trop_tard": trop_tard,
           "securite_ok": ok, "envoye": False}
    if EN_DIRECT and ok and not trop_tard:
        lignes = [
            f"🐋 <b>${e['symbol']}</b> ({e['chain']}) — {len(presents)} smart wallets ont acheté",
            f"Leurs bons coups (x3 ou plus) : {', '.join(records)}",
            f"💰 leur entrée moyenne : mcap {fmt_usd(mcap_entree)} · maintenant {fmt_usd(mcap)} "
            f"({(prix / entree - 1) * 100:+.0f} %)",
            f"↩️ {vendu} d'entre eux ont déjà vendu une partie" if vendu else "↩️ aucun n'a encore vendu",
            f"🛡️ {sec}",
            f"<a href=\"{e.get('url')}\">Voir sur DexScreener</a>",
            "<i>Signal automatique, pas un conseil. Petite mise seulement.</i>",
        ]
        sig["envoye"] = bool(envoyer("\n".join(lignes)))
    pf["signaux"].append(sig)
    pf["signales"][k] = now
    e["garder_jusqua"] = now + 7 * 86400   # on suit ce token 7 jours pour le bilan
    print(f"signal smart wallets {e['symbol']} : {len(presents)} wallets, "
          f"{'trop tard' if trop_tard else 'à temps'}, sécurité {'OK' if ok else 'non'}")
