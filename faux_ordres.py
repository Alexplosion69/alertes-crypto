"""
Faux ordres (options 12 et 13 en répétition, 02/11/2026). Aucun argent, aucun wallet.

Pour chaque zone d'entrée de la liste d'attente et chaque token du témoin (Solana), le bot demande à
Jupiter le VRAI prix d'un achat de 5 € (sans « taker » : Jupiter renvoie un devis, pas de
transaction). Il suit ensuite la position comme le ferait le garde-fou, avec la règle de sortie
gagnante du test du 01/11 :
    tout vendu à x1,5 · stop à −30 % · sortie au bout de 12 h · sortie immédiate si la liquidité
    perd 30 % d'un relevé à l'autre (signe de rug).
À la sortie, il redemande à Jupiter le vrai prix de vente de la quantité « achetée ».

Ce que ça mesure : l'écart entre le prix affiché (DexScreener) et le prix réellement obtenu
(glissement), le temps de réaction, et le résultat qu'aurait eu le garde-fou avec un wallet perso.
"""
import time

import requests

import outils as v

API = "https://api.jup.ag/swap/v2/order"
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
MISE_USD = 5.75               # ≈ 5 €
TP, STOP, DUREE_H, RUG_LIQ = 1.5, 0.70, 12, 0.70
FRAIS_RESEAU_SOL = 0.0002     # frais Solana + priorité, par ordre (estimation large)
TYPES = ("attente", "temoin", "temoin_apparie")
MAX_OUVERTES = 40


def devis(entree, sortie, montant):
    """Devis Jupiter (sans transaction). Renvoie la quantité reçue (unités brutes) ou None."""
    try:
        r = requests.get(API, params={"inputMint": entree, "outputMint": sortie, "amount": int(montant)},
                         headers={"Accept": "application/json", **v.UA}, timeout=20)
        d = r.json() if r.ok else {}
    except (requests.RequestException, ValueError):
        return None
    try:
        out = int(d.get("outAmount") or 0)
    except (TypeError, ValueError):
        return None
    return out or None


def prix_sol():
    """Prix du SOL en dollars, via un devis 1 SOL → USDC."""
    out = devis(SOL, USDC, 1e9)
    return out / 1e6 if out else None


def _prix_actuels(adresses):
    """Prix et liquidité DexScreener des tokens suivis (30 par appel)."""
    res = {}
    adresses = list(adresses)
    for i in range(0, len(adresses), 30):
        d = v.get_json(f"{v.DS}/tokens/v1/solana/{','.join(adresses[i:i + 30])}") or []
        for p in d:
            a = (p.get("baseToken") or {}).get("address")
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if a and p.get("priceUsd") and liq >= res.get(a, (0, -1))[1]:
                res[a] = (float(p["priceUsd"]), liq)
    return res


def ouvrir(fo, a, sol_usd):
    lamports = MISE_USD / sol_usd * 1e9
    recu = devis(SOL, a["address"], lamports)
    if not recu:
        fo["refus"] = fo.get("refus", 0) + 1
        return
    fo["ouvertes"][f"{a['key']}:{int(a['ts'])}"] = {
        "symbol": a["symbol"], "address": a["address"], "type": a["type"], "ts": time.time(),
        "ts_alerte": a["ts"], "prix_affiche": a["price"], "sol_depense": lamports / 1e9 + FRAIS_RESEAU_SOL,
        "sol_usd": sol_usd, "quantite": recu, "liq0": None, "haut": 1.0}


def fermer(fo, k, pos, raison, prix_affiche_sortie):
    sol_recu = (devis(pos["address"], SOL, pos["quantite"]) or 0) / 1e9 - FRAIS_RESEAU_SOL
    res = sol_recu / pos["sol_depense"] - 1
    # résultat « sur le papier » avec les prix affichés, pour mesurer l'écart avec la réalité
    papier = prix_affiche_sortie / pos["prix_affiche"] - 1 if pos["prix_affiche"] else None
    fo["fermees"].append({"symbol": pos["symbol"], "type": pos["type"], "ts": pos["ts"], "fin": time.time(),
                          "raison": raison, "res": round(res, 4),
                          "papier": round(papier, 4) if papier is not None else None,
                          "reaction_min": round((pos["ts"] - pos["ts_alerte"]) / 60, 1)})
    v.archiver("faux_ordres", [x for x in fo["fermees"] if time.time() - x["fin"] >= 60 * 86400])
    fo["fermees"] = [x for x in fo["fermees"] if time.time() - x["fin"] < 60 * 86400]
    del fo["ouvertes"][k]
    print(f"faux ordres : {pos['symbol']} fermé ({raison}) : réel {res * 100:+.1f} %"
          + (f", affiché {papier * 100:+.1f} %" if papier is not None else ""))


def tick(st):
    fo = st.setdefault("faux_ordres", {"ouvertes": {}, "fermees": [], "vu_jusqua": time.time(), "refus": 0})
    now = time.time()
    nouvelles = [a for a in st.get("alerts", []) if a.get("type") in TYPES and a.get("chain") == "solana"
                 and a["ts"] > fo["vu_jusqua"]]
    if nouvelles:
        fo["vu_jusqua"] = max(a["ts"] for a in nouvelles)
        sol_usd = prix_sol()
        if sol_usd:
            for a in nouvelles:
                if len(fo["ouvertes"]) < MAX_OUVERTES:
                    ouvrir(fo, a, sol_usd)
    if nouvelles:
        print(f"faux ordres : {len(fo['ouvertes'])} en cours, {len(fo['fermees'])} fermés, "
              f"{fo.get('refus', 0)} devis refusés")
    if not fo["ouvertes"]:
        return
    prix = _prix_actuels({p["address"] for p in fo["ouvertes"].values()})
    for k, pos in list(fo["ouvertes"].items()):
        pa = prix.get(pos["address"])
        if not pa:
            if now - pos["ts"] > DUREE_H * 3600:
                fermer(fo, k, pos, "plus de prix affiché (token mort ?)", 0)
            continue
        p, liq = pa
        x = p / pos["prix_affiche"] if pos["prix_affiche"] else 1
        pos["haut"] = max(pos["haut"], x)
        raison = None
        if pos["liq0"] and liq < RUG_LIQ * pos["liq0"]:
            raison = "liquidité qui fond"
        elif x <= STOP:
            raison = "stop −30 %"
        elif x >= TP:
            raison = "objectif x1,5"
        elif now - pos["ts"] >= DUREE_H * 3600:
            raison = "12 h écoulées"
        pos["liq0"] = max(pos["liq0"] or 0, liq)
        if raison:
            fermer(fo, k, pos, raison, p)


def bilan(st):
    fo = st.get("faux_ordres") or {}
    f = fo.get("fermees") or []
    n_o = len(fo.get("ouvertes") or {})
    if not f:
        return [f"🧾 Achats fictifs au vrai prix (Jupiter) : aucun fermé pour l'instant ({n_o} en cours)"]
    lignes = []
    for typ, nom in (("attente", "signaux Repli"), ("temoin", "tirages au hasard"), ("temoin_apparie", "jumeaux")):
        g = [x for x in f if x["type"] == typ]
        if not g:
            continue
        m = sum(x["res"] for x in g) / len(g)
        pap = [x["papier"] for x in g if x.get("papier") is not None]
        ecart = (m - sum(pap) / len(pap)) * 100 if pap else 0
        raisons = {}
        for x in g:
            raisons[x["raison"]] = raisons.get(x["raison"], 0) + 1
        lignes.append(f"   · {nom} : {len(g)} · résultat réel moyen <b>{m * 100:+.1f} %</b> "
                      f"(écart avec les prix affichés {ecart:+.1f} points) · sorties : "
                      + ", ".join(f"{r} {n}" for r, n in raisons.items()))
    return [f"🧾 <b>Achats fictifs au vrai prix</b> (prix réellement proposé par Jupiter, rien acheté ; "
            f"vente automatique x1,5 / −30 % / 12 h) : {len(f)} fermés, {n_o} en cours"] + lignes
