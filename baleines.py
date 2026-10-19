"""
Baleines Fomo : tu donnes au bot les wallets des meilleurs traders du classement Fomo, il surveille
leurs achats et repère quand PLUSIEURS d'entre eux achètent le même token en peu de temps.

Liste automatique : baleines_liste.txt (une baleine par ligne : NOM ADRESSE). Le bot la relit à
chaque lancement ; une baleine retirée avec /retire n'est pas rajoutée ensuite.

Ajouter / gérer les baleines depuis Telegram :
  /baleine NOM ADRESSE [ADRESSE2]   (adresse Solana et/ou EVM 0x…, l'ordre n'a pas d'importance)
  /baleines                          (la liste)
  /retire NOM

Comment on récupère les adresses : le profil Fomo affiche les stats mais pas l'adresse ; des outils
de type « FOMO Wallet Finder » donnent l'adresse Solana et l'adresse EVM d'un profil.

Ce que le bot lit (gratuit) :
  - Solana : les dernières transactions du wallet (RPC public, ou SOLANA_RPC_URL si tu ajoutes un
    secret avec une clé gratuite type Helius, plus fiable) ;
  - Base et Robinhood Chain : les tokens reçus par le wallet (explorateurs Blockscout ; pour
    Robinhood, un secret BLOCKSCOUT_API_KEY gratuit peut être nécessaire) ;
  - BNB : pas de source gratuite sans clé, non couvert pour l'instant.

EN_DIRECT = False : observation. Les signaux sont enregistrés et suivis dans le bilan quotidien
(gain simulé), sans alerte Telegram. On passe à True si le bilan montre que ça marche.
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

import outils as v

FICHIER = Path("alertes/baleines.json")
LISTE = Path("baleines_liste.txt")
EN_DIRECT = False
BALEINES_MIN = 3              # au moins 3 baleines différentes sur le même token…
FENETRE_H = 3                 # …en moins de 3 heures
LIQ_MIN = 10_000              # token sans liquidité = spam envoyé au wallet, ignoré
SIG_PAR_WALLET = 8            # transactions Solana lues par wallet et par cycle
BUDGET_S = 110                # temps max passé sur les baleines à chaque cycle (le reste continue)
PAUSE_RPC = 0.15              # pause entre deux appels au RPC Solana public (limite de débit)
ACHATS_JOURS = 3
SOL_RPC = os.getenv("SOLANA_RPC_URL", "").strip() or "https://api.mainnet-beta.solana.com"
BLOCKSCOUT = {"base": "https://base.blockscout.com",
              "robinhood": "https://robinhoodchain.blockscout.com"}
BLOCKSCOUT_PRO = {"robinhood": "4663"}   # API Blockscout « PRO » (clé gratuite) en secours
# jetons « monnaie » à ignorer : recevoir de l'USDC ou du SOL n'est pas acheter un memecoin
IGNORES = {
    "So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "0x4200000000000000000000000000000000000006", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "0x50c5725949a6f0c72e6c4a641f24049a917db0cb", "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",
}
IGNORES_BAS = {x.lower() for x in IGNORES}

_etat = {"baleines": {}, "curseurs": {}, "achats": [], "signales": {}, "retirees": [], "tour": 0}


# ---------------------------------------------------------------- état
def charger():
    global _etat
    if FICHIER.exists():
        try:
            _etat = json.loads(FICHIER.read_text())
        except json.JSONDecodeError:
            pass
    for k, d in (("baleines", {}), ("curseurs", {}), ("achats", []), ("signales", {}),
                 ("retirees", []), ("tour", 0)):
        _etat.setdefault(k, d)
    charger_liste()
    return _etat


def charger_liste():
    """Ajoute les baleines de baleines_liste.txt (sauf celles retirées avec /retire)."""
    if not LISTE.exists():
        return
    ajoutees = 0
    for ligne in LISTE.read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].split()
        if len(ligne) < 2:
            continue
        nom = re.sub(r"[^\w.-]", "", ligne[0])[:24]
        sol = next((a for a in ligne[1:] if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", a)), None)
        evm = next((a.lower() for a in ligne[1:] if re.fullmatch(r"0x[a-fA-F0-9]{40}", a)), None)
        if not nom or not (sol or evm) or nom in _etat["retirees"] or nom in _etat["baleines"]:
            continue
        b = _etat["baleines"][nom] = {"ajout": time.time(), "liste": True}
        if sol:
            b["sol"] = sol
        if evm:
            b["evm"] = evm
        ajoutees += 1
    if ajoutees:
        print(f"baleines : {ajoutees} ajoutée(s) depuis {LISTE}")


def sauver():
    now = time.time()
    _etat["achats"] = [a for a in _etat["achats"] if now - a["ts"] < ACHATS_JOURS * 86400]
    _etat["signales"] = {k: ts for k, ts in _etat["signales"].items() if now - ts < 24 * 3600}
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(_etat, separators=(",", ":")))


def stats():
    now = time.time()
    return len(_etat["baleines"]), sum(1 for a in _etat["achats"] if now - a["ts"] < 86400)


# ---------------------------------------------------------------- commandes Telegram
def cmd_baleine(args, envoyer):
    """/baleine NOM ADRESSE [ADRESSE2]"""
    if len(args) < 2:
        envoyer("Exemple : <code>/baleine Jamjam ADRESSE_SOLANA 0xADRESSE_EVM</code> "
                "(une adresse Solana et/ou une adresse 0x…)")
        return
    nom = re.sub(r"[^\w.-]", "", args[0])[:24] or "baleine"
    sol = next((a for a in args[1:] if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", a)), None)
    evm = next((a.lower() for a in args[1:] if re.fullmatch(r"0x[a-fA-F0-9]{40}", a)), None)
    if not sol and not evm:
        envoyer("😕 Je ne reconnais pas d'adresse : il faut une adresse Solana ou une adresse 0x… (EVM).")
        return
    if nom in _etat["retirees"]:
        _etat["retirees"].remove(nom)
    b = _etat["baleines"].setdefault(nom, {"ajout": time.time()})
    if sol:
        b["sol"] = sol
    if evm:
        b["evm"] = evm
    envoyer(f"🐳 Baleine « {nom} » ajoutée ({'Solana' if b.get('sol') else ''}"
            f"{' + ' if b.get('sol') and b.get('evm') else ''}{'EVM' if b.get('evm') else ''}). "
            f"{len(_etat['baleines'])} baleine(s) suivie(s). Je note ses achats à partir de maintenant.")


def cmd_liste(envoyer):
    if not _etat["baleines"]:
        envoyer("Aucune baleine suivie. Ajoute-en une : <code>/baleine NOM ADRESSE</code>")
        return
    now = time.time()
    actifs = {}
    for a in _etat["achats"]:
        if now - a["ts"] < 86400:
            actifs[a["baleine"]] = actifs.get(a["baleine"], 0) + 1
    nb_liste = sum(1 for b in _etat["baleines"].values() if b.get("liste"))
    lignes = [f"🐳 <b>{len(_etat['baleines'])} baleine(s) suivie(s)</b> "
              f"({nb_liste} de la liste, {len(_etat['baleines']) - nb_liste} ajoutée(s) à la main)",
              f"{len(actifs)} ont acheté quelque chose dans les dernières 24 h."]
    if len(_etat["baleines"]) <= 30:
        for nom, b in sorted(_etat["baleines"].items()):
            chaines = "/".join(x for x, k in (("Sol", "sol"), ("EVM", "evm")) if b.get(k))
            lignes.append(f"• {nom} ({chaines}) : {actifs.get(nom, 0)} achat(s) vu(s) en 24 h")
    else:
        lignes.append("Les plus actives (achats en 24 h) :")
        for nom, n in sorted(actifs.items(), key=lambda x: -x[1])[:15]:
            lignes.append(f"• {nom} : {n}")
        mains = [n for n, b in sorted(_etat["baleines"].items()) if not b.get("liste")]
        if mains:
            lignes.append("Ajoutées à la main : " + ", ".join(mains))
    envoyer("\n".join(lignes))


def cmd_retire(args, envoyer):
    nom = args[0] if args else ""
    if _etat["baleines"].pop(nom, None) is not None:
        if nom not in _etat["retirees"]:
            _etat["retirees"].append(nom)     # pour ne pas la rajouter depuis baleines_liste.txt
        envoyer(f"🗑️ Baleine « {nom} » retirée.")
    else:
        envoyer(f"😕 Pas de baleine « {nom[:24]} ». Tape /baleines pour la liste.")


# ---------------------------------------------------------------- lecture des achats
def _rpc(methode, params):
    try:
        r = requests.post(SOL_RPC, json={"jsonrpc": "2.0", "id": 1, "method": methode, "params": params},
                          timeout=20)
        if r.status_code != 200:
            return None
        return r.json().get("result")
    except (requests.RequestException, ValueError):
        return None


def achats_solana(nom, adresse):
    cle = f"sol:{adresse}"
    sigs = _rpc("getSignaturesForAddress", [adresse, {"limit": SIG_PAR_WALLET}]) or []
    time.sleep(PAUSE_RPC)
    if not sigs:
        return []
    dernier = _etat["curseurs"].get(cle)
    _etat["curseurs"][cle] = sigs[0]["signature"]
    if dernier is None:
        return []                          # première lecture : on prend juste le point de départ
    nouveaux = []
    for s in sigs:
        if s["signature"] == dernier:
            break
        if not s.get("err"):
            nouveaux.append(s)
    achats = []
    for s in nouveaux:
        tx = _rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed",
                                                       "maxSupportedTransactionVersion": 0}])
        meta = (tx or {}).get("meta") or {}
        avant = {(b.get("mint"), b.get("owner")): float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
                 for b in meta.get("preTokenBalances") or []}
        for b in meta.get("postTokenBalances") or []:
            mint, owner = b.get("mint"), b.get("owner")
            if owner != adresse or mint in IGNORES:
                continue
            apres = float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
            if apres > avant.get((mint, owner), 0) * 1.0001:
                achats.append({"ts": (tx or {}).get("blockTime") or time.time(), "baleine": nom,
                               "chain": "solana", "token": mint})
        time.sleep(PAUSE_RPC)
    return achats


def _ts_iso(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def achats_evm(nom, adresse, chain):
    cle = f"{chain}:{adresse}"
    items = []
    base = BLOCKSCOUT.get(chain)
    d = v.get_json(f"{base}/api/v2/addresses/{adresse}/token-transfers",
                   params={"type": "ERC-20", "filter": "to"}) if base else None
    if d and isinstance(d.get("items"), list):
        for it in d["items"]:
            items.append((_ts_iso(it.get("timestamp")), ((it.get("token") or {}).get("address") or "").lower()))
    elif chain in BLOCKSCOUT_PRO and os.getenv("BLOCKSCOUT_API_KEY"):
        d = v.get_json("https://api.blockscout.com/v2/api",
                       params={"chainid": BLOCKSCOUT_PRO[chain], "module": "account", "action": "tokentx",
                               "address": adresse, "sort": "desc",
                               "apikey": os.getenv("BLOCKSCOUT_API_KEY").strip()}) or {}
        for it in d.get("result") or [] if isinstance(d.get("result"), list) else []:
            if (it.get("to") or "").lower() == adresse:
                items.append((float(it.get("timeStamp") or 0), (it.get("contractAddress") or "").lower()))
    if not items:
        return []
    dernier = _etat["curseurs"].get(cle)
    _etat["curseurs"][cle] = max(ts for ts, _ in items if ts) if any(ts for ts, _ in items) else dernier
    if dernier is None:
        return []
    return [{"ts": ts, "baleine": nom, "chain": chain, "token": tok}
            for ts, tok in items if ts and ts > dernier and tok and tok not in IGNORES_BAS]


# ---------------------------------------------------------------- signal
def surveiller(st, sv, ajouter_suivi, envoyer=None):
    """À appeler à chaque cycle : lit les achats des baleines et enregistre les signaux."""
    if not _etat["baleines"]:
        return
    # avec beaucoup de baleines, on tourne : chaque cycle reprend là où le précédent s'est arrêté
    noms = sorted(_etat["baleines"])
    depart = _etat.get("tour", 0) % max(len(noms), 1)
    debut = time.time()
    vus = 0
    for nom in noms[depart:] + noms[:depart]:
        if time.time() - debut > BUDGET_S:
            break
        b = _etat["baleines"][nom]
        vus += 1
        nouveaux = []
        if b.get("sol"):
            nouveaux += achats_solana(nom, b["sol"])
        if b.get("evm"):
            for chain in BLOCKSCOUT:
                nouveaux += achats_evm(nom, b["evm"], chain)
        _etat["achats"] += nouveaux
    _etat["tour"] = (depart + vus) % max(len(noms), 1)
    if vus < len(noms):
        print(f"baleines : {vus}/{len(noms)} lues ce cycle (la suite au prochain)")
    now = time.time()
    par_token = {}
    for a in _etat["achats"]:
        if now - a["ts"] <= FENETRE_H * 3600:
            par_token.setdefault((a["chain"], a["token"]), {}).setdefault(a["baleine"], a["ts"])
    cands = {}
    for (chain, tok), qui in par_token.items():
        k = v.key_of(chain, tok)
        if len(qui) >= BALEINES_MIN and k not in _etat["signales"]:
            cands[k] = {"chain": chain, "address": tok, "sources": ["baleines"], "boost": 0, "qui": qui}
    if not cands:
        return
    for t in v.enrich(cands):
        if t["liq"] < LIQ_MIN or not t["price"]:
            continue                        # spam ou token mort
        qui = cands[t["key"]]["qui"]
        _etat["signales"][t["key"]] = now
        st["alerts"].append({"ts": now, "type": "baleines", "observation": not EN_DIRECT,
                             "key": t["key"], "symbol": t["symbol"], "chain": t["chain"],
                             "address": t["address"], "price": t["price"], "mcap": t["mcap"],
                             "url": t["dexscreener"], "baleines": sorted(qui)})
        ajouter_suivi(t)
        print(f"signal baleines : {len(qui)} baleines sur un même token"
              f"{'' if EN_DIRECT else ' (observation)'}")
        if EN_DIRECT and envoyer:
            il_y_a = " · ".join(f"{n} (il y a {int((now - ts) / 60)} min)" for n, ts in sorted(qui.items()))
            envoyer(f"🐳 <b>{len(qui)} baleines ont acheté ${t['symbol']}</b> ({t['chain']})\n"
                    f"{il_y_a}\nmcap {t['mcap'] / 1e3:.0f} k$ · liq {t['liq'] / 1e3:.0f} k$ · "
                    f"prix {t['chg_1h']:+.0f} % sur 1 h\n"
                    f"<a href=\"{t['dexscreener']}\">Voir sur DexScreener</a>\n"
                    f"<i>Tu arrives après elles : vérifie que le prix n'a pas déjà décollé. Petite mise.</i>")
