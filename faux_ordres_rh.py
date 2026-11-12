"""
Achats fictifs au vrai prix sur Robinhood Chain (12/11/2026). Aucun argent, aucun wallet.

Même idée que faux_ordres.py (Jupiter, Solana), pour les alertes 🐋 « wallets gagnants » : pour chaque
signal à temps de 5 wallets ou plus, le bot demande à 0x le VRAI prix d'un achat de 5 € en ETH (devis
seulement, aucune transaction), suit la position avec la vente automatique (x1,5 / −30 % / 12 h, sortie si
la liquidité fond), puis redemande le vrai prix de vente.

Deux questions : le gain des wallets gagnants tient-il au vrai prix ? Et 0x trouve-t-il toujours un chemin
pour revendre ? (Aucun chemin, ou une taxe de vente, = signal d'alarme sur le token.)
Sans secret ZEROX_API_KEY, le module ne fait rien.
"""
import os
import time

import requests

import outils as v

API = "https://api.0x.org/swap/allowance-holder/price"
CHAINE_ID = 4663              # Robinhood Chain (le même identifiant marche chez GoPlus)
ETH = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
MISE_USD = 5.75               # ≈ 5 €
TP, STOP, DUREE_H, RUG_LIQ = 1.5, 0.70, 12, 0.70
MIN_WALLETS = 5
MAX_OUVERTES = 40


def cle():
    return os.getenv("ZEROX_API_KEY", "").strip()


def devis(vend, achete, montant):
    """Devis 0x (sans transaction) : (quantité reçue, frais réseau en wei, taxe de vente en %) ou None."""
    try:
        r = requests.get(API, timeout=20, params={"chainId": CHAINE_ID, "sellToken": vend, "buyToken": achete,
                                                  "sellAmount": str(int(montant))},
                         headers={"0x-api-key": cle(), "0x-version": "v2", **v.UA})
        d = r.json() if r.ok else {}
    except (requests.RequestException, ValueError):
        return None
    if not d.get("liquidityAvailable") or not d.get("buyAmount"):
        return None
    meta = (d.get("tokenMetadata") or {})
    taxe = max(int((meta.get("buyToken") or {}).get("buyTaxBps") or 0),
               int((meta.get("sellToken") or {}).get("sellTaxBps") or 0)) / 100
    return int(d["buyAmount"]), int(d.get("totalNetworkFee") or 0), taxe


def _prix(adresses):
    """Prix, liquidité, mcap et prix de l'ETH (DexScreener) des tokens suivis."""
    res, adresses = {}, list(adresses)
    for i in range(0, len(adresses), 30):
        for p in v.get_json(f"{v.DS}/tokens/v1/robinhood/{','.join(adresses[i:i + 30])}") or []:
            a = ((p.get("baseToken") or {}).get("address") or "").lower()
            liq = (p.get("liquidity") or {}).get("usd") or 0
            try:
                pu, pn = float(p.get("priceUsd") or 0), float(p.get("priceNative") or 0)
            except (TypeError, ValueError):
                continue
            if a and pu and liq >= res.get(a, (0, -1))[1]:
                res[a] = (pu, liq, p.get("marketCap") or p.get("fdv") or 0, pu / pn if pn else None)
    return res


def ouvrir(fo, s, px):
    pu, liq, mc, eth_usd = px
    if not eth_usd:
        fo["refus"] = fo.get("refus", 0) + 1
        return
    wei = MISE_USD / eth_usd * 1e18
    d = devis(ETH, s["address"], wei)
    if not d:
        fo["sans_chemin_achat"] = fo.get("sans_chemin_achat", 0) + 1
        return
    recu, frais, taxe = d
    fo["ouvertes"][f"{s['key']}:{int(s['ts'])}"] = {
        "symbol": s["symbol"], "address": s["address"], "ts": time.time(), "ts_signal": s["ts"],
        "prix_affiche": s["price"], "mcap0": s.get("mcap"), "eth_depense": wei + frais, "eth_usd": eth_usd,
        "quantite": recu, "taxe_achat": taxe, "liq0": liq, "haut": 1.0, "wallets": s["wallets"]}


def _x_reel(pos):
    d = devis(pos["address"], ETH, pos["quantite"])
    if not d:
        return None, None
    recu, frais, taxe = d
    return (recu - frais) / pos["eth_depense"], taxe


def fermer(fo, k, pos, raison, prix_sortie):
    xr, taxe = _x_reel(pos)
    papier = prix_sortie / pos["prix_affiche"] - 1 if pos["prix_affiche"] and prix_sortie else None
    fo["fermees"].append({"symbol": pos["symbol"], "ts": pos["ts"], "fin": time.time(), "raison": raison,
                          "res": round(xr - 1, 4) if xr is not None else None, "revente_ok": xr is not None,
                          "taxe_vente": taxe, "papier": round(papier, 4) if papier is not None else None,
                          "reaction_min": round((pos["ts"] - pos["ts_signal"]) / 60, 1), "wallets": pos["wallets"]})
    v.archiver("faux_ordres_rh", [x for x in fo["fermees"] if time.time() - x["fin"] >= 60 * 86400])
    fo["fermees"] = [x for x in fo["fermees"] if time.time() - x["fin"] < 60 * 86400]
    del fo["ouvertes"][k]
    print(f"faux ordres Robinhood : {pos['symbol']} fermé ({raison}) : "
          + (f"réel {(xr - 1) * 100:+.1f} %" if xr is not None else "AUCUN CHEMIN DE REVENTE"))


def tick(st, pf):
    if not cle():
        return
    fo = st.setdefault("faux_ordres_rh", {"ouvertes": {}, "fermees": [], "vu_jusqua": time.time(), "refus": 0})
    now = time.time()
    nouveaux = [s for s in pf.get("signaux", []) if s["ts"] > fo["vu_jusqua"] and s.get("chain") == "robinhood"
                and not s.get("trop_tard") and s.get("wallets", 0) >= MIN_WALLETS]
    if nouveaux:
        fo["vu_jusqua"] = max(s["ts"] for s in nouveaux)
    adresses = {p["address"].lower() for p in fo["ouvertes"].values()} | {s["address"].lower() for s in nouveaux}
    if not adresses:
        return
    prix = _prix(adresses)
    for s in nouveaux:
        if len(fo["ouvertes"]) < MAX_OUVERTES and prix.get(s["address"].lower()):
            ouvrir(fo, s, prix[s["address"].lower()])
    for k, pos in list(fo["ouvertes"].items()):
        pa = prix.get(pos["address"].lower())
        if not pa:
            if now - pos["ts"] > DUREE_H * 3600:
                fermer(fo, k, pos, "plus de prix affiché (token mort ?)", 0)
            continue
        p, liq, mc, _ = pa
        x = p / pos["prix_affiche"] if pos["prix_affiche"] else 1
        x_mc = mc / pos["mcap0"] if pos.get("mcap0") and mc else None
        if x > 10 or (x_mc and max(x, x_mc) / max(min(x, x_mc), 1e-9) > 1.5):
            continue                                   # prix affiché aberrant
        pos["haut"] = max(pos["haut"], x)
        raison = None
        if liq < RUG_LIQ * pos["liq0"]:
            raison = "liquidité qui fond"
        elif x <= STOP:
            raison = "stop −30 %"
        elif x >= TP:
            raison = "objectif x1,5"
        elif now - pos["ts"] >= DUREE_H * 3600:
            raison = "12 h écoulées"
        pos["liq0"] = max(pos["liq0"], liq)
        if raison in ("objectif x1,5", "stop −30 %"):    # le vrai prix doit confirmer
            xr, _ = _x_reel(pos)
            if xr is not None and ((raison == "objectif x1,5" and xr < 1.2) or (raison == "stop −30 %" and xr > 0.85)):
                continue
        if raison:
            fermer(fo, k, pos, raison, p)


def bilan(st):
    if not cle():
        return ["🧾 Achats fictifs Robinhood Chain (0x) : en attente de la clé ZEROX_API_KEY"]
    fo = st.get("faux_ordres_rh") or {}
    f, n_o = fo.get("fermees") or [], len(fo.get("ouvertes") or {})
    sans = fo.get("sans_chemin_achat", 0)
    if not f:
        return [f"🧾 Achats fictifs Robinhood Chain (0x) : aucun fermé pour l'instant ({n_o} en cours, "
                f"{sans} sans chemin d'achat)"]
    ok = [x for x in f if x.get("revente_ok")]
    m = sum(x["res"] for x in ok) / len(ok) if ok else 0
    ec = [x["res"] - x["papier"] for x in ok if x.get("papier") is not None and -1 <= x["papier"] <= 9
          and abs(x["res"] - x["papier"]) <= 0.5]
    taxes = sum(1 for x in ok if (x.get("taxe_vente") or 0) > 0)
    return [f"🧾 <b>Achats fictifs Robinhood Chain</b> (vrai prix de 0x, rien acheté ; vente automatique x1,5 / −30 % / 12 h) : "
            f"{len(f)} fermés, {n_o} en cours · résultat réel moyen <b>{m * 100:+.1f} %</b>"
            + (f" (écart avec les prix affichés {sum(ec) / len(ec) * 100:+.1f} points)" if ec else "")
            + f" · ⚠️ revente impossible : {len(f) - len(ok)} · taxe de vente : {taxes} · sans chemin d'achat : {sans}"]
