"""Activité des wallets écoutés en direct (smart_direct.py) : qui échange combien, sur quoi, à quel rythme."""
import collections
import json
import time
from pathlib import Path

SM = Path("/home/bot/donnees/smart")
f = sorted(SM.glob("20*.jsonl"))[-1]
evs = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
t0, t1 = min(e["t"] for e in evs), max(e["t"] for e in evs)
print(f"{f.name} : {len(evs)} échanges de {time.strftime('%H:%M:%S', time.gmtime(t0))} à "
      f"{time.strftime('%H:%M:%S', time.gmtime(t1))} UTC ({(t1 - t0) / 60:.0f} min), {len({e['sig'] for e in evs})} transactions")
par_w = collections.Counter(e["w"] for e in evs)
print("Échanges par wallet (10 plus actifs) :", [n for _, n in par_w.most_common(10)])
print("Répartition :", {"1-2": sum(1 for n in par_w.values() if n <= 2), "3-10": sum(1 for n in par_w.values() if 3 <= n <= 10),
                       "11-50": sum(1 for n in par_w.values() if 11 <= n <= 50), ">50": sum(1 for n in par_w.values() if n > 50)})
par_m = collections.Counter(e["mint"] for e in evs)
print("Échanges par token :", [(m[:6], n) for m, n in par_m.most_common(14)])
sol = [e["sol"] for e in evs]
sol.sort()
print("Montant en SOL (médiane, 90e centile) :", sol[len(sol) // 2], sol[int(len(sol) * 0.9)])
w_par_m = collections.defaultdict(set)
for e in evs:
    w_par_m[e["mint"]].add(e["w"])
print("Wallets différents par token :", sorted((len(s) for s in w_par_m.values()), reverse=True))
print("État :", (SM / "smart_etat.json").read_text())
