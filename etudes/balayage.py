"""Balayage de stratégies sur la boîte noire (13/11) : « est-ce qu'une combinaison marche ? »

Entrées fictives toutes les 2 h sur chaque token Solana échangeable (liquidité ≥ 30 k$, mcap ≥ 150 k$,
volume 1 h ≥ 1 k$). Pour chacune, on calcule le résultat de 384 règles de sortie :
  objectif +5 … +100 % ou aucun · stop −5 … −50 % (fixe, ou « suiveur » depuis le plus haut)
  · durée maximale 1 h, 4 h, 12 h ou 24 h · liquidité partie = −100 %.
Puis on croise avec des filtres d'entrée (une ou deux conditions connues au moment d'acheter : variation
5 min / 1 h / 24 h, repli depuis le plus haut 24 h, rebond depuis le plus bas 24 h, achats/ventes, volume,
mcap, liquidité, âge, heure, pub payée).

Pour ne pas se tromper soi-même : on CHERCHE sur la première partie de la période et on VÉRIFIE sur la
dernière, sans rien rechoisir (24 h d'écart entre les deux pour qu'aucun trade ne chevauche).
Frais : Fomo 6 % l'aller-retour (2 × 0,10 € sur 5 € + 2 points d'écart de prix mesuré), wallet perso 2,5 %.
Ne lit que la boîte noire : aucune position, aucune clé."""
import array
import bisect
import gzip
import json
import os
import time
from itertools import accumulate, combinations
from pathlib import Path

import numpy as np

DON = Path(os.getenv("DONNEES_DIR", "/home/bot/donnees"))
PAS_ENTREE = 40                       # une entrée toutes les 40 photos (2 h) par token
HORIZON = 24 * 3600
COUT_FOMO, COUT_WALLET = 0.06, 0.025
TPS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.00, None]
SLS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
HS = [3600, 4 * 3600, 12 * 3600, 24 * 3600]
CONFIGS = [(tp, sl, h, tr) for tp in TPS for sl in SLS for h in HS for tr in (False, True)]
MIN_TRAIN, MIN_TOK, MIN_TEST = 150, 40, 60


def jour(t):
    return time.strftime("%d/%m %H h", time.gmtime(t))


t0 = time.time()
creee = {}
try:
    for l in (DON / "tokens.jsonl").read_text().splitlines():
        x = json.loads(l)
        if x.get("creee_ms"):
            creee[x["key"]] = x["creee_ms"] / 1000
except OSError:
    pass

# ---------------------------------------------------------------- lecture de la boîte noire
T = array.array("d")
idx, prix, liq = {}, {}, {}
dern = {}
entrees = []                          # (clé, position, temps, caractéristiques connues à l'entrée)
for f in sorted(DON.glob("20*.jsonl.gz")):
    with gzip.open(f, "rt", encoding="utf-8") as g:
        for ligne in g:
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            n = len(T)
            t = d["t"]
            T.append(t)
            for k, v in d["d"].items():
                if not k.startswith("solana:") or not v[0]:
                    continue
                if k not in idx:
                    idx[k], prix[k], liq[k] = array.array("I"), array.array("f"), array.array("f")
                idx[k].append(n)
                prix[k].append(v[0])
                liq[k].append(v[2])
                if n - dern.get(k, -10 ** 9) >= PAS_ENTREE and v[2] >= 30_000 and v[1] >= 150_000 and v[5] >= 1_000:
                    dern[k] = n
                    pos = len(prix[k]) - 1
                    j0 = bisect.bisect_left(idx[k], bisect.bisect_left(T, t - 86400))
                    hist = prix[k][j0:pos + 1]
                    assez = t - T[idx[k][j0]] >= 12 * 3600
                    entrees.append((k, pos, t, {
                        "var_m5": v[11], "var_h1": v[12], "var_h24": v[13],
                        "repli24": (v[0] / max(hist) - 1) * 100 if assez else None,
                        "rebond24": (v[0] / min(hist) - 1) * 100 if assez and min(hist) > 0 else None,
                        "ratio": (v[9] / v[10]) if v[10] and v[9] + v[10] >= 20 else None,
                        "vol_liq": v[5] / v[2], "mcap": v[1], "liq_mcap": v[2] / v[1],
                        "age": (t - creee[k]) / 86400 if k in creee else None,
                        "heure": time.gmtime(t).tm_hour, "pub": 1 if v[14] else 0}))
fin = T[-1]
entrees = [e for e in entrees if e[2] <= fin - HORIZON]
N, C = len(entrees), len(CONFIGS)
print(f"Boîte noire : {len(T)} photos du {jour(T[0])} au {jour(fin)} UTC · {N} entrées fictives sur "
      f"{len({e[0] for e in entrees})} tokens · {C} règles de sortie · lu en {time.time() - t0:.0f} s")

# ---------------------------------------------------------------- résultat de chaque règle de sortie
M = np.zeros((N, C), dtype=np.float32)
nb_morts = 0
for e_i, (k, pos, te, _) in enumerate(entrees):
    ix, px, lq = idx[k], prix[k], liq[k]
    p0 = px[pos]
    xs, rel = [], []
    t_mort = None
    j, au_bout = pos, False
    while j + 1 < len(px):
        j += 1
        r = T[ix[j]] - te
        if r > HORIZON:
            au_bout = True
            break
        if lq[j] < 5_000:                                   # liquidité partie : invendable
            t_mort = r
            break
        xs.append(px[j] / p0)
        rel.append(r)
    if (t_mort is None and not au_bout and xs and rel[-1] < HORIZON - 1800
            and fin - (te + rel[-1]) > 3600 and xs[-1] < 0.5):
        t_mort = rel[-1]                                    # disparu de la boîte noire après −50 % : mort
    nb_morts += t_mort is not None
    n = len(xs)
    # premiers passages (indices), n = jamais ; listes monotones → recherche dichotomique
    plus_haut = list(accumulate(xs, max))
    moins_bas = [-v for v in accumulate(xs, min)]
    sommet = list(accumulate(xs, max, initial=1.0))[1:]
    recul = [-v for v in accumulate((x / s for x, s in zip(xs, sommet)), min)]
    up = {tp: bisect.bisect_left(plus_haut, 1 + tp) for tp in TPS if tp is not None}
    up[None] = n
    dn = {sl: bisect.bisect_left(moins_bas, -(1 - sl)) for sl in SLS}
    tr = {sl: bisect.bisect_left(recul, -(1 - sl)) for sl in SLS}
    ih = {h: bisect.bisect_right(rel, h) - 1 for h in HS}   # dernier relevé avant la durée max
    ligne = M[e_i]
    for c, (tp, sl, h, trail) in enumerate(CONFIGS):
        fi = ih[h]
        iu = up[tp]
        idn = (tr if trail else dn)[sl]
        if iu <= fi and iu < idn:
            ligne[c] = tp
        elif idn <= fi:
            ligne[c] = xs[idn] - 1
        elif t_mort is not None and t_mort <= h:
            ligne[c] = -1.0
        elif fi >= 0:
            ligne[c] = xs[fi] - 1
print(f"Résultats calculés en {time.time() - t0:.0f} s ({nb_morts} entrées finissent sur un token mort dans les 24 h)")

# ---------------------------------------------------------------- découpage chercher / vérifier
temps = np.array([e[2] for e in entrees])
tok = np.unique(np.array([e[0] for e in entrees]), return_inverse=True)[1]
coupe = temps.min() + (temps.max() - temps.min()) * 0.6
TR = temps <= coupe
TE = temps >= coupe + 86400
print(f"Chercher : {TR.sum()} entrées du {jour(temps.min())} au {jour(coupe)} · "
      f"vérifier : {TE.sum()} entrées du {jour(coupe + 86400)} au {jour(temps.max())}")

BORNES = {"var_m5": [-3, 0, 3], "var_h1": [-10, -3, 3, 10], "var_h24": [-30, -10, 10, 50],
          "repli24": [-40, -25, -15, -5], "rebond24": [5, 15, 40, 100], "ratio": [0.8, 1.0, 1.3, 2.0],
          "vol_liq": [0.05, 0.2, 1.0], "mcap": [300e3, 1e6, 5e6], "liq_mcap": [0.05, 0.1, 0.2],
          "age": [1, 3, 7, 30], "heure": [6, 12, 18], "pub": [1]}
NOMS = {"var_m5": "var. 5 min", "var_h1": "var. 1 h", "var_h24": "var. 24 h", "repli24": "repli / plus haut 24 h",
        "rebond24": "rebond / plus bas 24 h", "ratio": "achats/ventes 1 h", "vol_liq": "volume 1 h / liq",
        "mcap": "mcap", "liq_mcap": "liq / mcap", "age": "âge (j)", "heure": "heure UTC", "pub": "pub payée"}
conds = []
for f, bs in BORNES.items():
    val = np.array([np.nan if e[3].get(f) is None else e[3][f] for e in entrees], dtype=float)
    for b in range(len(bs) + 1):
        lo = bs[b - 1] if b > 0 else None
        hi = bs[b] if b < len(bs) else None
        lab = f"{NOMS[f]} " + (f"< {hi:g}" if lo is None else f"≥ {lo:g}" if hi is None else f"{lo:g} à {hi:g}")
        if f == "pub":
            lab = "pub payée" if lo else "sans pub"
        m = ~np.isnan(val)
        if lo is not None:
            m &= val >= lo
        if hi is not None:
            m &= val < hi
        conds.append((f, lab, m))
filtres = [("tous les tokens", np.ones(N, dtype=bool))]
filtres += [(lab, m) for _, lab, m in conds]
filtres += [(f"{a[1]} + {b[1]}", a[2] & b[2]) for a, b in combinations(conds, 2) if a[0] != b[0]]

noms, A, B, TRM, TEM = [], [], [], [], []
for nom, m in filtres:
    mtr, mte = m & TR, m & TE
    if mtr.sum() < MIN_TRAIN or mte.sum() < MIN_TEST or np.unique(tok[mtr]).size < MIN_TOK:
        continue
    noms.append(nom)
    A.append(M[mtr].mean(0))
    B.append(M[mte].mean(0))
    TRM.append(mtr)
    TEM.append(mte)
A, B = np.array(A), np.array(B)                            # filtres × règles de sortie, résultats bruts
F = len(noms)
print(f"Stratégies essayées : {F * C} ({F} filtres d'entrée avec assez d'exemples × {C} règles de sortie) · "
      f"{time.time() - t0:.0f} s")


def nom_cfg(c):
    tp, sl, h, trail = CONFIGS[c]
    return (f"objectif {'+' + format(tp * 100, 'g') + ' %' if tp else 'aucun'} · stop "
            f"{'suiveur ' if trail else ''}−{sl * 100:g} % · {h // 3600} h max")


def detail(fi, c):
    te = M[TEM[fi], c].astype(float)
    tk = tok[TEM[fi]]
    par_tok = {}
    for x, t_ in zip(te, tk):
        par_tok[t_] = par_tok.get(t_, 0) + x
    top3 = sorted(par_tok, key=lambda t_: -par_tok[t_])[:3]
    sans = [x for x, t_ in zip(te, tk) if t_ not in top3]
    return (f"vérif. médiane {np.median(te) * 100:+.0f} %, gagnantes {np.mean(te > 0) * 100:.0f} %, "
            f"sans ses 3 meilleurs tokens {np.mean(sans) * 100:+.1f} % brut")


for cout, lib in ((COUT_FOMO, "frais Fomo 6 %"), (COUT_WALLET, "frais wallet perso 2,5 %")):
    a, b = A - cout, B - cout
    gagne_a = a > 0
    print(f"\n=== Avec les {lib} ===")
    print(f"   gagnantes sur la période de recherche : {gagne_a.sum()} sur {a.size} ({gagne_a.mean() * 100:.1f} %)")
    if gagne_a.any():
        print(f"   … et encore gagnantes en vérification : {(gagne_a & (b > 0)).sum()} "
              f"({(b[gagne_a] > 0).mean() * 100:.0f} % d'entre elles)")
    print(f"   pour comparer, au hasard : {(b > 0).mean() * 100:.1f} % de toutes les stratégies gagnent en vérification")
    meilleure = a.argmax(1)                                 # meilleure sortie de chaque filtre (en recherche)
    sc = a[np.arange(F), meilleure]
    ordre = np.argsort(-sc)
    for K in (1, 10, 50, 200):
        K = min(K, F)
        sel = ordre[:K]
        bt = b[sel, meilleure[sel]]
        print(f"   choisir les {K:3} meilleures en recherche (filtres différents) : recherche {sc[sel].mean() * 100:+6.1f} % "
              f"→ vérification {bt.mean() * 100:+6.1f} % ({(bt > 0).sum()} sur {K} encore gagnantes)")

a, b = A - COUT_FOMO, B - COUT_FOMO
meilleure = a.argmax(1)
sc = a[np.arange(F), meilleure]
ordre = np.argsort(-sc)
print("\nLes 20 meilleures en recherche (frais Fomo), et ce qu'elles font ensuite :")
for fi in ordre[:20]:
    c = meilleure[fi]
    print(f"   {sc[fi] * 100:+6.1f} % → {b[fi, c] * 100:+6.1f} % · {TRM[fi].sum()} / {TEM[fi].sum()} entrées · "
          f"{noms[fi]} · {nom_cfg(c)}\n            ({detail(fi, c)})")

print("\nLes 20 meilleures en VÉRIFICATION (pour info : c'est ce qu'on aurait voulu trouver) :")
mv = b.argmax(1)
sv = b[np.arange(F), mv]
for fi in np.argsort(-sv)[:20]:
    c = mv[fi]
    print(f"   recherche {a[fi, c] * 100:+6.1f} % · vérification {sv[fi] * 100:+6.1f} % · {noms[fi]} · {nom_cfg(c)}")

print("\nSans aucun filtre (tous les tokens), les 5 meilleures règles de sortie en recherche :")
for c in np.argsort(-a[0])[:5]:
    print(f"   recherche {a[0, c] * 100:+5.1f} % → vérification {b[0, c] * 100:+5.1f} % · {nom_cfg(c)}")
for cible in ((0.20, 0.20, 24 * 3600, False), (0.10, 0.10, 24 * 3600, False), (0.50, 0.30, 24 * 3600, False)):
    c = CONFIGS.index(cible)
    print(f"   repère {nom_cfg(c)} : recherche {a[0, c] * 100:+5.1f} % · vérification {b[0, c] * 100:+5.1f} %")
print(f"\nTerminé en {time.time() - t0:.0f} s")
