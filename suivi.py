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

# --- Force relative : un token qui tient quand le marché des memecoins baisse
FORCE_MARCHE_BAISSE = -3      # médiane des memecoins suivis sur 6 h ≤ −3 % = marché en baisse
FORCE_MIN_TOKENS = 20         # il faut au moins 20 tokens suivis pour calculer une médiane fiable


def charger():
    if FICHIER.exists():
        try:
            s = json.loads(FICHIER.read_text())
            s.setdefault("tokens", {})
            s.setdefault("dernier_releve", 0)
            s.setdefault("marche", {})
            return s
        except json.JSONDecodeError:
            pass
    return {"tokens": {}, "dernier_releve": 0, "marche": {}}


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
    # humeur du marché : médiane des variations des memecoins suivis
    # seulement les tokens encore échangés : les tokens morts (0 % faute d'échanges) faussaient la
    # médiane, qui affichait toujours +0 %
    actifs = [t for t in frais if t["vol_6h"] >= 5_000]
    ch6 = sorted(t["chg_6h"] for t in actifs)
    ch24 = sorted(t["chg_24h"] for t in actifs if t["vol_24h"] >= 5_000)
    if len(ch6) >= FORCE_MIN_TOKENS:
        s["marche"] = {"med_6h": round(ch6[len(ch6) // 2], 1),
                       "med_24h": round(ch24[len(ch24) // 2], 1) if ch24 else 0.0,
                       "n": len(ch6), "ts": round(now)}
    # plus haut, prix actuel et gain simulé des alertes / signaux envoyés (pour le bilan)
    for lst in listes_suivies:
        for a in lst:
            if now - a["ts"] > SUIVI_JOURS * 86400 or not a.get("price"):
                continue
            t = by_key.get(a["key"])
            if t and not releve_coherent(a, t["price"], t["mcap"]):
                t = None                    # prix aberrant (changement de paire, bug de cotation) : ignoré
            if t:
                a["last"], a["last_mcap"] = t["price"], t["mcap"]
                a["peak"] = max(a.get("peak") or a["price"], t["price"])
                simuler(a, t["price"] / a["price"])
            if a["key"] in morts:
                a["mort"] = True
                simuler(a, (a.get("last") or 0) / a["price"], fin=True)
    return frais, morts, fins


X_MAX = 500          # au-delà, un « x » mesuré en 7 jours est presque toujours un bug de prix


def releve_coherent(a, prix, mcap):
    """Un relevé n'est gardé que si le prix et la capitalisation racontent la même histoire.
    Quand DexScreener change de paire de référence (paire en MUSK4, BNCB, WBTC…), le prix en $
    peut être faux d'un facteur 1000 alors que la capitalisation, elle, reste cohérente."""
    if not a.get("price") or not prix:
        return False
    x_prix = prix / a["price"]
    if x_prix > X_MAX:
        return False
    if a.get("mcap") and mcap:
        ecart = x_prix / (mcap / a["mcap"])
        if ecart > 3 or ecart < 1 / 3:
            return False
    return True


def simuler(a, x, fin=False):
    """Gain simulé d'1 € misé sur l'alerte, avec ta règle :
    - la moitié vendue à x2 ;
    - tant que la moitié n'est pas vendue : tout est coupé si on tombe à −50 % ;
    - après x2, le reste est vendu s'il retombe à x1 (on ne perd plus) ou à −50 % de son plus haut.
    Relevés toutes les 30 min : les stops sont comptés au prix relevé (prudent)."""
    s = a.setdefault("sim", {"cash": 0.0, "reste": 1.0, "haut": 1.0, "moitie": False})
    if s["reste"] <= 0:
        return
    x = min(x, X_MAX)
    s["haut"] = max(s["haut"], x)
    if not s["moitie"]:
        if s["haut"] >= 2:
            s["cash"] += 1.0            # 0,5 € de mise revendus à x2
            s["reste"], s["moitie"] = 0.5, True
        elif x <= 0.5 or fin:
            s["cash"] += s["reste"] * x
            s["reste"] = 0.0
            return
    if s["moitie"] and s["reste"] > 0 and (x <= max(1.0, 0.5 * s["haut"]) or fin):
        s["cash"] += s["reste"] * x
        s["reste"] = 0.0


MISE_SIM = 5.0         # mise simulée en € : à 5 €, la coupure à −50 % reste vendable (minimum ~2 $)
FRAIS_PCT = 0.005      # frais Fomo par ordre (0,45 % constaté, arrondi par prudence)…
FRAIS_MIN = 0.10       # …avec un minimum de 0,10 € par ordre (achat comme vente)


def _frais(valeur):
    """Frais d'un ordre, en fraction de la mise, pour un ordre valant `valeur` mises."""
    return max(FRAIS_PCT * valeur * MISE_SIM, FRAIS_MIN) / MISE_SIM


def resultat_sim_net(a):
    """Comme resultat_sim, mais après frais : achat, vente de la moitié à x2, vente du reste.
    Un reste qui ne vaut plus rien n'est pas vendu (pas de frais dessus). Pour 1 € de mise."""
    s = a.get("sim")
    if not s:
        return 0.0
    x = min((a.get("last") or a["price"]) / a["price"], X_MAX) if a.get("price") else 0
    frais = _frais(1.0)                                   # achat
    if s["moitie"]:
        frais += _frais(1.0)                              # moitié vendue à x2 (vaut 1 mise)
        final = s["reste"] * x if s["reste"] > 0 else s["cash"] - 1.0
    else:
        final = s["reste"] * x if s["reste"] > 0 else s["cash"]
    if final * MISE_SIM > FRAIS_MIN:                      # sinon on ne prend pas la peine de vendre
        frais += _frais(final)
    return round(resultat_sim(a) - frais, 2)


def resultat_sim(a):
    """Gain (ou perte) en € pour 1 € misé, positions encore ouvertes comptées au dernier prix."""
    s = a.get("sim")
    if not s:
        return 0.0
    x = min((a.get("last") or a["price"]) / a["price"], X_MAX) if a.get("price") else 0
    return round(s["cash"] + s["reste"] * x - 1, 2)


def force_relative(s, t):
    """Renvoie (fort, texte) : le token tient-il quand le marché baisse ?"""
    m = s.get("marche") or {}
    if not m or time.time() - m.get("ts", 0) > 3 * 3600:
        return False, ""
    med, chg = m["med_6h"], t["chg_6h"]
    if med <= FORCE_MARCHE_BAISSE and chg >= 0:
        return True, (f"💪 tient malgré le marché : memecoins suivis {med:+.0f} % sur 6 h (médiane), "
                      f"lui {chg:+.0f} %")
    if med >= 3:
        return False, (f"🌊 marché porteur : memecoins suivis {med:+.0f} % sur 6 h, une partie de la hausse "
                       f"vient de tout le marché")
    return False, f"📊 marché : memecoins suivis {med:+.0f} % sur 6 h (médiane), lui {chg:+.0f} %"


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


# ---------------------------------------------------------------- momentum confirmé (observation)
MOM_AGE_MIN_H, MOM_AGE_MAX_H = 6, 168
MOM_MCAP_MIN, MOM_MCAP_MAX = 300_000, 3_000_000   # là où tu as repéré DOPE, Pepper, CLAUDIA…
MOM_LIQ_MIN = 50_000
MOM_LIQ_SUR_MCAP = 0.03       # liquidité ≥ 3 % du mcap (DOPE : ~200 k$ pour ~4,8 M$)
MOM_DEPUIS_HAUT = 0.5         # prix ≥ 50 % de son plus haut connu


def motif_momentum(e, t, now=None):
    """Version large des survivants : token déjà installé (6 h+, 300 k$-3 M$), liquidité solide,
    pas effondré, volume qui continue, plus d'achats que de ventes. Renvoie un dict ou None."""
    now = now or time.time()
    if not (MOM_AGE_MIN_H <= t["age_h"] <= MOM_AGE_MAX_H and MOM_MCAP_MIN <= t["mcap"] <= MOM_MCAP_MAX):
        return None
    if t["liq"] < MOM_LIQ_MIN or t["liq"] < MOM_LIQ_SUR_MCAP * t["mcap"]:
        return None
    if t["price"] < MOM_DEPUIS_HAUT * max(e["ath"], t["price"]):
        return None
    if t["vol_1h"] < 0.8 * t["vol_6h"] / 6 or t["buys_6h"] < t["sells_6h"]:
        return None
    if t["chg_6h"] < 0 or t.get("chg_5m", 0) <= CHUTE_5M_MAX:
        return None
    ref = next((p for p in e["serie"] if p[0] >= now - 12 * 3600), e["serie"][0])
    if t["liq"] < SURV_LIQ_STABLE * ref[3]:
        return None
    return {"liq_pct": round(t["liq"] / t["mcap"] * 100, 1),
            "depuis_haut_pct": round((t["price"] / max(e["ath"], t["price"]) - 1) * 100)}
