"""
Suivi des tokens sur 7 jours (un relevé toutes les 30 min) et détection des « survivants ».

Pourquoi : les gros gains de la semaine (CLAUDIA, WangChai, QT…) ne se sont pas faits
dans les premières minutes, mais sur des tokens qui avaient déjà SURVÉCU et qui repartaient.
Ce module garde l'historique des tokens vus par le bot pour repérer ce moment-là.

Deux formes de « survivant » :
  1. rebond sur plancher : grosse correction après le sommet, puis un plancher qui tient
     depuis au moins 3 h, puis le prix casse le haut de sa zone des dernières heures ;
  2. montée régulière : sur 12-18 h, des creux de plus en plus hauts et des sommets de plus
     en plus hauts, sans chute de plus de 35 % (le profil WangChai).

Sert aussi au bilan : plus haut atteint et prix actuel de chaque alerte envoyée.
"""
import json
import time
from pathlib import Path

import outils as v

FICHIER = Path("alertes/suivi.json")
RELEVE_MIN = 30               # un relevé de prix toutes les 30 min
SUIVI_MAX = 500               # nombre max de tokens suivis en même temps
SUIVI_JOURS = 7
ENTREE_LIQ_MIN = 15_000       # pour entrer dans le suivi
ENTREE_MCAP_MIN = 60_000
MORT_LIQ = 5_000              # liquidité sous 5 k$ = mort
MORT_CHUTE = 0.10             # prix sous 10 % de son plus haut (après 12 h) = mort

# --- Alerte « survivant »
SURV_AGE_MIN_H, SURV_AGE_MAX_H = 12, 168     # entre 12 h et 7 jours
SURV_MCAP_MIN, SURV_MCAP_MAX = 300_000, 10_000_000
SURV_LIQ_MIN = 40_000
SURV_LIQ_STABLE = 0.85        # liquidité ≥ 85 % de celle d'il y a 12 h (personne ne la retire)
SURV_COUVERTURE_H = 6         # il faut au moins 6 h d'historique pour juger
SURV_CORRECTION_MIN = 0.30    # rebond : il faut avoir corrigé d'au moins 30 % depuis le sommet…
SURV_CORRECTION_MAX = 0.80    # …mais pas plus de 80 % (au-delà, c'est un cadavre)
SURV_PLANCHER_H = 3           # pas de nouveau plus bas depuis au moins 3 h
SURV_REBOND_MIN = 1.25        # prix ≥ plancher +25 %
SURV_HAUSSE_1H_MIN = 5        # et ça monte encore sur 1 h
SURV_MONTEE_X = 1.4           # montée régulière : +40 % au moins sur la fenêtre
SURV_MONTEE_REPLI_MAX = 0.35  # sans repli de plus de 35 %
SURV_VOL_6H_MIN = 50_000
SURV_ACHATS_6H_RATIO = 1.1    # plus d'achats que de ventes sur 6 h
CHUTE_5M_MAX = -10


def charger():
    if FICHIER.exists():
        try:
            s = json.loads(FICHIER.read_text())
            s.setdefault("tokens", {})
            s.setdefault("dernier_releve", 0)
            return s
        except json.JSONDecodeError:
            pass
    return {"tokens": {}, "dernier_releve": 0}


def sauver(s):
    now = time.time()
    for e in s["tokens"].values():
        garde, vues = [], set()
        for p in e["serie"]:
            if now - p[0] > SUIVI_JOURS * 86400:
                continue
            if now - p[0] > 48 * 3600:        # au-delà de 48 h : un point par heure suffit
                h = int(p[0] // 3600)
                if h in vues:
                    continue
                vues.add(h)
            garde.append(p)
        e["serie"] = garde or e["serie"][-1:]
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(s, separators=(",", ":")))


def _point(t, now):
    return [round(now), float(f"{t['price']:.6g}"), round(t["mcap"]), round(t["liq"])]


def ajouter(s, t, garder=False):
    """Ajoute un token au suivi (garder=True : token alerté, suivi 7 jours quoi qu'il arrive)."""
    now = time.time()
    e = s["tokens"].get(t["key"])
    if e is None:
        if not garder and (t["age_h"] > SUIVI_JOURS * 24 or t["liq"] < ENTREE_LIQ_MIN
                           or t["mcap"] < ENTREE_MCAP_MIN or len(s["tokens"]) >= SUIVI_MAX
                           or not t["price"]):
            return None
        e = s["tokens"][t["key"]] = {
            "chain": t["chain"], "address": t["address"], "pair": t.get("pair"),
            "symbol": t["symbol"], "url": t.get("dexscreener"),
            "created": now - t["age_h"] * 3600, "ajoute": now,
            "serie": [_point(t, now)], "ath": t["price"], "ath_ts": now}
    if garder:
        e["garder_jusqua"] = now + SUIVI_JOURS * 86400
    return e


def ajouter_lot(s, tokens):
    for t in tokens:
        ajouter(s, t)


def plus_haut_apres(e, ts):
    """Plus haut prix relevé à partir de l'instant ts (None si aucun relevé)."""
    prix = [p[1] for p in e["serie"] if p[0] >= ts - 60]
    return max(prix) if prix else None


def rafraichir(s, listes_suivies):
    """Relevé de prix (toutes les 30 min). Renvoie (tokens frais, clés à retirer) ou None."""
    now = time.time()
    if now - s["dernier_releve"] < RELEVE_MIN * 60 or not s["tokens"]:
        return None
    s["dernier_releve"] = now
    cands = {k: {"chain": e["chain"], "address": e["address"], "sources": ["suivi"], "boost": 0}
             for k, e in s["tokens"].items()}
    frais = v.enrich(cands)
    by_key = {t["key"]: t for t in frais}
    morts, fins = [], []
    for k, e in s["tokens"].items():
        t = by_key.get(k)
        if t is None:
            e["absent"] = e.get("absent", 0) + 1
            if e["absent"] >= 3:                      # disparu de DexScreener 3 relevés de suite
                morts.append(k)
            continue
        e["absent"] = 0
        e["serie"].append(_point(t, now))
        if t["price"] > e["ath"]:
            e["ath"], e["ath_ts"] = t["price"], now
        e.update(pair=t.get("pair"), url=t.get("dexscreener"), symbol=t["symbol"])
        if t["liq"] < MORT_LIQ or (t["price"] < MORT_CHUTE * e["ath"] and now - e["created"] > 12 * 3600):
            morts.append(k)
        elif now - e["ajoute"] > SUIVI_JOURS * 86400 and now > e.get("garder_jusqua", 0):
            fins.append(k)
    # plus haut et prix actuel des alertes / signaux envoyés (pour le bilan)
    for lst in listes_suivies:
        for a in lst:
            if now - a["ts"] > SUIVI_JOURS * 86400:
                continue
            t = by_key.get(a["key"])
            if t:
                a["last"], a["last_mcap"] = t["price"], t["mcap"]
                a["peak"] = max(a.get("peak") or a["price"], t["price"])
            if a["key"] in morts:
                a["mort"] = True
    return frais, morts, fins


def retirer(s, keys):
    for k in keys:
        s["tokens"].pop(k, None)


# ---------------------------------------------------------------- survivants
def motif_survivant(e, t, now=None):
    """Renvoie (motif, détails) si le token a une forme de survivant, sinon None."""
    now = now or time.time()
    if not (SURV_AGE_MIN_H <= t["age_h"] <= SURV_AGE_MAX_H
            and SURV_MCAP_MIN <= t["mcap"] <= SURV_MCAP_MAX and t["liq"] >= SURV_LIQ_MIN):
        return None
    serie = e["serie"]
    if len(serie) < 8 or serie[0][0] > now - SURV_COUVERTURE_H * 3600:
        return None
    ref = next((p for p in serie if p[0] >= now - 12 * 3600), serie[0])
    if t["liq"] < SURV_LIQ_STABLE * ref[3]:
        return None                                   # de la liquidité a été retirée
    if t["vol_6h"] < SURV_VOL_6H_MIN or t["buys_6h"] < SURV_ACHATS_6H_RATIO * max(t["sells_6h"], 1):
        return None
    if t.get("chg_5m", 0) <= CHUTE_5M_MAX:
        return None
    prix, ath, ath_ts = t["price"], e["ath"], e["ath_ts"]
    ratio_mcap = t["mcap"] / prix if prix else 0

    # 1. rebond sur plancher
    apres = [p for p in serie if p[0] >= ath_ts]
    if apres:
        bas = min(apres, key=lambda p: p[1])
        corr = 1 - bas[1] / ath if ath else 0
        zone = [p[1] for p in serie if now - 6 * 3600 <= p[0] <= now - 3600]
        if (SURV_CORRECTION_MIN <= corr <= SURV_CORRECTION_MAX
                and bas[0] <= now - SURV_PLANCHER_H * 3600
                and prix >= bas[1] * SURV_REBOND_MIN
                and zone and prix > max(zone)
                and t["chg_1h"] >= SURV_HAUSSE_1H_MIN):
            return "rebond", {
                "sommet_mcap": ath * ratio_mcap, "correction_pct": round(corr * 100),
                "plancher_mcap": bas[1] * ratio_mcap, "plancher_h": round((now - bas[0]) / 3600, 1),
                "rebond_pct": round((prix / bas[1] - 1) * 100)}

    # 2. montée régulière (creux et sommets de plus en plus hauts)
    fen = [p for p in serie if p[0] >= now - 18 * 3600]
    if fen and fen[0][0] <= now - 12 * 3600:
        debut = fen[0][0]
        duree = now - debut + 1
        tiers = [[p[1] for p in fen if debut + i * duree / 3 <= p[0] < debut + (i + 1) * duree / 3]
                 for i in range(3)]
        if all(tiers):
            creux = [min(x) for x in tiers]
            sommets = [max(x) for x in tiers]
            plus_haut, repli = 0, 0
            for p in fen:
                plus_haut = max(plus_haut, p[1])
                repli = max(repli, 1 - p[1] / plus_haut)
            if (creux[0] < creux[1] < creux[2] and sommets[0] < sommets[1] < sommets[2]
                    and prix >= SURV_MONTEE_X * fen[0][1] and repli <= SURV_MONTEE_REPLI_MAX
                    and t["chg_1h"] >= 0 and prix >= 0.9 * ath):
                return "montee", {
                    "x_fenetre": round(prix / fen[0][1], 1),
                    "fenetre_h": round(duree / 3600), "repli_max_pct": round(repli * 100),
                    "dernier_creux_mcap": creux[2] * ratio_mcap}
    return None
