"""Grille « objectif / stop » sur la boîte noire (photos toutes les 3 min, tokens Solana).

Question d'Alex (12/11) : et si on visait plus petit (+20 % / −20 %, +10 %…) au lieu de x1,5 / −30 % ?
Pour chaque token échangeable (liquidité ≥ 30 k$, mcap ≥ 150 k$, volume 1 h ≥ 1 k$), une entrée fictive
toutes les 2 h, puis on suit le prix photo par photo pendant 24 h : objectif touché (vendu à l'objectif),
stop touché (vendu au prix observé), liquidité partie (0), ou fin des 24 h (vendu au prix observé).
Ensuite, mêmes entrées triées par ce qu'on savait AU MOMENT d'entrer (variation 1 h, 24 h, achats/ventes,
volume, taille, âge) pour voir si une situation gagne avant frais. Deux moitiés de la période, pour
ne pas croire un hasard. Ne lit que la boîte noire : aucune position, aucune clé."""
import array
import collections
import gzip
import json
import statistics
import time
from pathlib import Path

import os
DON = Path(os.getenv("DONNEES_DIR", "/home/bot/donnees"))
PAS_ENTREE = 40                       # une entrée toutes les 40 photos (2 h) par token
HORIZON = 24 * 3600
GRILLE = [(0.10, 0.10), (0.20, 0.20), (0.20, 0.10), (0.10, 0.20), (0.30, 0.15), (0.50, 0.30), (1.00, 0.50)]
COUT_FOMO, COUT_WALLET = 0.077, 0.037   # frais Fomo 4 % sur 5 € + écart de prix mesuré 3,7 pts ; wallet : l'écart seul

t0 = time.time()
creee = {}
try:
    for l in (DON / "tokens.jsonl").read_text().splitlines():
        x = json.loads(l)
        if x.get("creee_ms"):
            creee[x["key"]] = x["creee_ms"] / 1000
except OSError:
    pass

T = array.array("d")
idx, prix, liq = {}, {}, {}
dern_entree = {}
entrees = []                          # (clé, position, temps, caractéristiques)
for f in sorted(DON.glob("20*.jsonl.gz")):
    with gzip.open(f, "rt", encoding="utf-8") as g:
        for ligne in g:
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            n = len(T)
            T.append(d["t"])
            for k, v in d["d"].items():
                if not k.startswith("solana:") or not v[0]:
                    continue
                if k not in idx:
                    idx[k], prix[k], liq[k] = array.array("I"), array.array("f"), array.array("f")
                idx[k].append(n)
                prix[k].append(v[0])
                liq[k].append(v[2])
                if n - dern_entree.get(k, -10 ** 9) >= PAS_ENTREE and v[2] >= 30_000 and v[1] >= 150_000 and v[5] >= 1_000:
                    dern_entree[k] = n
                    age = (d["t"] - creee[k]) / 86400 if k in creee else None
                    entrees.append((k, len(prix[k]) - 1, d["t"],
                                    {"var_h1": v[12], "var_h24": v[13], "var_m5": v[11],
                                     "ratio": (v[9] / v[10]) if v[10] and v[9] + v[10] >= 20 else None,
                                     "vol_liq": v[5] / v[2], "mcap": v[1], "liq_mcap": v[2] / v[1], "age": age}))
fin_globale = T[-1]
entrees = [e for e in entrees if e[2] <= fin_globale - HORIZON]
print(f"Boîte noire : {len(T)} photos du {time.strftime('%d/%m %H:%M', time.gmtime(T[0]))} au "
      f"{time.strftime('%d/%m %H:%M', time.gmtime(fin_globale))} UTC · {len(idx)} tokens Solana · "
      f"{len(entrees)} entrées fictives sur {len({e[0] for e in entrees})} tokens · chargé en {time.time() - t0:.0f} s")

res = []                              # par entrée : [(issue, rendement)] par case de la grille + rendement 24 h
for k, pos, te, _ in entrees:
    ix, px, lq = idx[k], prix[k], liq[k]
    p0 = px[pos]
    ouverts = list(range(len(GRILLE)))
    out = [None] * len(GRILLE)
    j, x, mort = pos, 1.0, False
    while j + 1 < len(px):
        j += 1
        if T[ix[j]] - te > HORIZON:
            break
        x = px[j] / p0
        if lq[j] < 5_000:
            mort = True
            break
        if ouverts:
            reste = []
            for c in ouverts:
                tp, sl = GRILLE[c]
                if x >= 1 + tp:
                    out[c] = ("objectif", tp)
                elif x <= 1 - sl:
                    out[c] = ("stop", x - 1)
                else:
                    reste.append(c)
            ouverts = reste
    disparu = j + 1 >= len(px) and T[ix[j]] - te < HORIZON - 1800 and fin_globale - T[ix[j]] > 3600
    if mort or (disparu and (lq[j] < 5_000 or x < 0.5)):
        final = ("mort", -1.0)
    else:
        final = ("fin", x - 1)
    for c in ouverts:
        out[c] = final
    res.append((out, final[1]))


def stats(lignes, c):
    r = [o[c][1] for o, _ in lignes]
    n = len(r)
    g = sum(1 for o, _ in lignes if o[c][0] == "objectif") / n
    return n, g, sum(r) / n, statistics.median(r)


mi = sorted(e[2] for e in entrees)[len(entrees) // 2]
A = [r for r, e in zip(res, entrees) if e[2] <= mi]
B = [r for r, e in zip(res, entrees) if e[2] > mi]
print("\nGrille objectif / stop, 24 h au plus, tous les tokens échangeables (aucune sélection) :")
print(" objectif  stop |  objectif touché  stop  mort  fin 24 h | gain moyen brut  médian | net Fomo 5 €  net wallet | "
      "1re moitié  2e moitié | réussite qu'il faudrait (Fomo)")
for c, (tp, sl) in enumerate(GRILLE):
    n, g, m, med = stats(res, c)
    iss = collections.Counter(o[c][0] for o, _ in res)
    print(f"   +{tp * 100:3.0f} %  −{sl * 100:2.0f} % |      {g * 100:4.1f} %      {iss['stop'] / n * 100:4.1f} % {iss['mort'] / n * 100:4.1f} %"
          f"  {iss['fin'] / n * 100:4.1f} % |    {m * 100:+5.1f} %      {med * 100:+5.1f} % |   {(m - COUT_FOMO) * 100:+5.1f} %     "
          f"{(m - COUT_WALLET) * 100:+5.1f} % |  {stats(A, c)[2] * 100:+5.1f} %    {stats(B, c)[2] * 100:+5.1f} % |  "
          f"{(sl + COUT_FOMO) / (tp + sl) * 100:.0f} %")
h = [x for _, x in res]
print(f"Garder 24 h sans rien faire : moyenne {sum(h) / len(h) * 100:+.1f} % · médiane {statistics.median(h) * 100:+.1f} % · "
      f"en hausse {sum(x > 0 for x in h) / len(h) * 100:.0f} % · morts {sum(x <= -0.99 for x in h) / len(h) * 100:.1f} %")

C20 = GRILLE.index((0.20, 0.20))
C50 = GRILLE.index((0.50, 0.30))


def tri(nom, cle, bornes, fmt="{:g}"):
    print(f"\nSelon {nom} au moment d'entrer (objectif +20 % / stop −20 %, puis +50 % / −30 %) :")
    groupes = collections.defaultdict(list)
    for r, e in zip(res, entrees):
        val = e[3].get(cle)
        if val is None:
            continue
        b = sum(val >= x for x in bornes)
        groupes[b].append((r, e))
    for b in sorted(groupes):
        g = groupes[b]
        lo = fmt.format(bornes[b - 1]) if b > 0 else "…"
        hi = fmt.format(bornes[b]) if b < len(bornes) else "…"
        lig = [r for r, _ in g]
        n, gagne, m, _ = stats(lig, C20)
        a = [r for r, e in g if e[2] <= mi]
        bb = [r for r, e in g if e[2] > mi]
        ma = stats(a, C20)[2] * 100 if a else float("nan")
        mb = stats(bb, C20)[2] * 100 if bb else float("nan")
        print(f"   de {lo:>6} à {hi:>6} : {n:6} entrées, {len({e[0] for _, e in g}):4} tokens · +20 touché {gagne * 100:4.1f} % · "
              f"brut {m * 100:+5.1f} % (moitiés {ma:+5.1f} / {mb:+5.1f}) · +50/−30 brut {stats(lig, C50)[2] * 100:+5.1f} % · "
              f"24 h {sum(x for _, x in lig) / n * 100:+5.1f} %")


tri("la variation sur 1 h (%)", "var_h1", [-15, -5, 5, 15])
tri("la variation sur 24 h (%)", "var_h24", [-30, -10, 10, 50, 150])
tri("la variation sur 5 min (%)", "var_m5", [-5, -1, 1, 5])
tri("le rapport achats / ventes sur 1 h", "ratio", [0.7, 1.0, 1.5, 2.5])
tri("le volume 1 h / liquidité", "vol_liq", [0.05, 0.2, 1.0, 3.0])
tri("la mcap ($)", "mcap", [300_000, 1_000_000, 5_000_000, 20_000_000], "{:.0e}")
tri("la liquidité / mcap", "liq_mcap", [0.05, 0.10, 0.20])
tri("l'âge du token (jours)", "age", [1, 3, 7, 30, 180])
print(f"\nCalculé en {time.time() - t0:.0f} s")
