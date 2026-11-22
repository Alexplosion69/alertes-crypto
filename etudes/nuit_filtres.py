"""Nuit : peut-on éviter les nuits perdantes ? (22/11, idée d'Alex)

On n'achète à la clôture que si une condition connue À LA CLÔTURE est remplie :
  · tendance : clôture au-dessus de sa moyenne 200 jours (ou en dessous) ;
  · journée : le titre a baissé dans la journée (ou monté) ;
  · peur : VIX à la clôture au-dessus (ou en dessous) de sa médiane des 252 derniers jours ;
  · grosse journée : le titre a bougé de plus de 2 % (hausse ou baisse) dans la journée.
On choisit sur 2010-2017, on vérifie sur 2018-2026. Frais par aller-retour : Hyperliquid mode croissance
en ordres limite (0,006 %) ou au marché (0,018 %), Fomo mode croissance (0,118 %). Financement 0 ou 10 %/an.
Les nuits sans achat, l'argent dort (0 %)."""
import math
import statistics
import sys
import time

import requests

sys.stdout.reconfigure(line_buffering=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}
COUPE = time.mktime((2018, 1, 1, 0, 0, 0, 0, 0, 0))
FRAIS = (0.00006, 0.00018, 0.00118)
TICKERS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]


def yahoo(sym):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=30, headers=UA,
                     params={"period1": 1230768000, "period2": int(time.time()), "interval": "1d", "events": "div,split"})
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    return [(t, o * a / c, a) for t, o, c, a in zip(res["timestamp"], q["open"], q["close"], adj)
            if None not in (o, c, a) and c and o]


vix = {time.strftime("%Y-%m-%d", time.gmtime(t)): c for t, _, c in yahoo("^VIX")}
time.sleep(0.6)


def nuits(b):
    """[(temps, rendement de la nuit, heures, {condition: vrai/faux})] — conditions lues à la clôture d'avant."""
    out, closes, vh = [], [], []
    for i in range(1, len(b)):
        (t0, o0, c0), (t1, o1, c1) = b[i - 1], b[i]
        closes.append(c0)
        v = vix.get(time.strftime("%Y-%m-%d", time.gmtime(t0)))
        if v:
            vh.append(v)
        n = o1 / c0 - 1
        if len(closes) < 200 or abs(n) > 0.5 or not v or len(vh) < 252:
            continue
        mm = statistics.fmean(closes[-200:])
        j = c0 / o0 - 1
        med = statistics.median(vh[-252:])
        cond = {"toutes les nuits": True,
                "tendance haussière (> moy. 200 j)": c0 > mm, "tendance baissière (< moy. 200 j)": c0 < mm,
                "après une journée en baisse": j < 0, "après une journée en hausse": j > 0,
                "peur forte (VIX > médiane 1 an)": v > med, "peur faible (VIX < médiane 1 an)": v < med,
                "après une journée à plus de ±2 %": abs(j) > 0.02, "après une journée calme (±2 %)": abs(j) <= 0.02}
        out.append((t1, n, max(1.0, (t1 - t0) / 3600 - 6.5), cond))
    return out


def par_an(x, ans, frais=0.0, fin=0.0):
    if len(x) < 30:
        return None
    return math.exp(sum(math.log(max(1e-9, 1 + r - frais - fin * h / 8766)) for _, r, h, _ in x) / ans) - 1


def pc(x):
    return "    —" if x is None else f"{x * 100:+5.1f}"


donnees = {}
for s in TICKERS:
    try:
        donnees[s] = nuits(yahoo(s))
    except Exception as e:
        print(f"{s} : pas de données ({type(e).__name__})")
    time.sleep(0.6)

debut = min(d[0][0] for d in donnees.values())
ANS = {"A": (COUPE - debut) / (365.25 * 86400), "B": (time.time() - COUPE) / (365.25 * 86400)}
conds = list(next(iter(donnees.values()))[0][3])
print("Par condition : part des nuits gardées, gain moyen par nuit, nuits gagnantes, puis rendement par an")
print("(moyenne des 9 titres) net de 0,006 / 0,018 / 0,118 % par aller-retour, financement 0 puis 10 %/an.")
for per, lab in (("A", "2010-2017 (choix)"), ("B", "2018-2026 (vérification)")):
    print(f"\n=== {lab} ===")
    for c in conds:
        part, moy, gag, nets = [], [], [], {f: [] for f in (0, 10)}
        for s, d in donnees.items():
            tout = [y for y in d if (y[0] < COUPE) == (per == "A")]
            x = [y for y in tout if y[3][c]]
            if len(x) < 30:
                continue
            part.append(len(x) / len(tout))
            moy.append(statistics.fmean(r for _, r, _, _ in x))
            gag.append(sum(r > 0 for _, r, _, _ in x) / len(x))
            for fin in (0, 10):
                nets[fin].append([par_an(x, ANS[per], f, fin / 100) for f in FRAIS])
        if not part:
            continue
        m = {fin: [statistics.fmean(v[j] for v in nets[fin]) for j in range(3)] for fin in (0, 10)}
        print(f"   {c:36} {statistics.fmean(part) * 100:3.0f} % des nuits · {statistics.fmean(moy) * 100:+.3f} %/nuit · "
              f"gagnantes {statistics.fmean(gag) * 100:.0f} % · par an {pc(m[0][0])} {pc(m[0][1])} {pc(m[0][2])}"
              f" | fin. 10 % {pc(m[10][0])} {pc(m[10][1])} {pc(m[10][2])}")
    for s in ("SPY", "QQQ"):
        tout = [y for y in donnees[s] if (y[0] < COUPE) == (per == "A")]
        g = [y for y in tout if y[3]["tendance haussière (> moy. 200 j)"] and y[3]["après une journée en baisse"]]
        print(f"   {s} hausse + journée en baisse : {len(g) / len(tout) * 100:.0f} % des nuits, "
              f"{statistics.fmean(r for _, r, _, _ in g) * 100:+.3f} %/nuit, par an net 0,018 % {pc(par_an(g, ANS[per], FRAIS[1]))}")
