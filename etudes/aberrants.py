"""Les plus gros résultats de la boîte noire : vraies envolées ou erreurs de prix ?
Pour les entrées du balayage dont le prix fait plus de x5 en 24 h : le détail photo par photo autour du sommet
(prix, mcap, liquidité) pour voir si c'est une vraie hausse ou un prix aberrant. Ne lit que la boîte noire."""
import array
import gzip
import json
import os
import time
from pathlib import Path

DON = Path(os.getenv("DONNEES_DIR", "/home/bot/donnees"))
T = array.array("d")
idx, prix, liq, mc = {}, {}, {}, {}
dern, entrees = {}, []
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
                    idx[k], prix[k], liq[k], mc[k] = (array.array("I"), array.array("f"), array.array("f"),
                                                      array.array("f"))
                idx[k].append(n)
                prix[k].append(v[0])
                liq[k].append(v[2])
                mc[k].append(v[1])
                if n - dern.get(k, -10 ** 9) >= 40 and v[2] >= 30_000 and v[1] >= 150_000 and v[5] >= 1_000:
                    dern[k] = n
                    entrees.append((k, len(prix[k]) - 1, d["t"]))
fin = T[-1]
entrees = [e for e in entrees if e[2] <= fin - 86400]
gros = []
sauts = 0
for k, pos, te in entrees:
    ix, px = idx[k], prix[k]
    j = pos
    best, jb = 1.0, pos
    while j + 1 < len(px) and T[ix[j + 1]] - te <= 86400:
        j += 1
        x = px[j] / px[pos]
        if x > best:
            best, jb = x, j
    if best >= 5:
        gros.append((best, k, pos, te, jb))
print(f"{len(entrees)} entrées · {len(gros)} font plus de x5 en 24 h sur {len({g[1] for g in gros})} tokens")
vus = set()
for best, k, pos, te, jb in sorted(gros, reverse=True):
    if k in vus:
        continue
    vus.add(k)
    ix, px, lq, m = idx[k], prix[k], liq[k], mc[k]
    print(f"\n{k[:20]}… entrée {time.strftime('%d/%m %H:%M', time.gmtime(te))} : prix {px[pos]:.3g} mcap {m[pos] / 1e3:.0f} k$ "
          f"liq {lq[pos] / 1e3:.0f} k$ → sommet x{best:.1f} le {time.strftime('%d/%m %H:%M', time.gmtime(T[ix[jb]]))}")
    a, b = max(pos, jb - 4), min(len(px), jb + 5)
    for j in range(a, b):
        print(f"      {time.strftime('%d/%m %H:%M', time.gmtime(T[ix[j]]))} x{px[j] / px[pos]:9.2f} · mcap {m[j] / 1e3:9.0f} k$ · "
              f"liq {lq[j] / 1e3:7.0f} k$ · mcap/prix {m[j] / px[j] / (m[pos] / px[pos]):.2f}")
    if len(vus) >= 15:
        break
