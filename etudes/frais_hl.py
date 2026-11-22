"""Nuit et fin de mois avec les frais d'Hyperliquid en direct (22/11, idée d'Alex : « si ce sont les frais
le problème, cherchons à les baisser »).

Les actions et indices sur Hyperliquid sont des perps HIP-3 (trade.xyz : SP500, XYZ100 ≈ Nasdaq-100,
NVDA, TSLA…). Frais par ordre (palier de base) : 0,09 % marché / 0,03 % limite en mode normal, environ
−90 % quand le marché est en « mode croissance ». Via Fomo, on ajoute 0,05 % par ordre.
Scénarios par aller-retour :
  · HL croissance, ordres limite   0,006 %
  · HL croissance, ordres marché   0,018 %
  · HL normal, ordres limite       0,06 %
  · Fomo, marché en croissance     0,118 %
  · Fomo, marché normal            0,28 %
Le financement (payé chaque heure par les acheteurs quand il est positif) est compté au prorata des
heures tenues : 0 %/an (cas idéal) et 10 %/an (ordre de grandeur des perps crypto).
SPY et QQQ servent de témoins pour SP500 et XYZ100. On compare à « garder » (ETF, sans frais).
Données Yahoo Finance, 2010-2017 puis 2018-2026."""
import math
import statistics
import sys
import time

import requests

sys.stdout.reconfigure(line_buffering=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}
COUPE = time.mktime((2018, 1, 1, 0, 0, 0, 0, 0, 0))
FRAIS = [("HL crois. limite", 0.00006), ("HL crois. marché", 0.00018), ("HL normal limite", 0.0006),
         ("Fomo crois.", 0.00118), ("Fomo normal", 0.0028)]
FIN = (0.0, 0.10)
TICKERS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "PLTR", "COIN"]


def yahoo(sym):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=30, headers=UA,
                     params={"period1": 1262304000, "period2": int(time.time()), "interval": "1d", "events": "div,split"})
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    return [(t, o * a / c, a) for t, o, c, a in zip(res["timestamp"], q["open"], q["close"], adj)
            if None not in (o, c, a) and c and o]


def achats(b):
    """nuit : (temps, rendement, heures) ; fin de mois : idem ; garder : rendement de chaque jour."""
    nuit, fdm, garder = [], [], []
    for i in range(1, len(b)):
        (t0, o0, c0), (t1, o1, c1) = b[i - 1], b[i]
        n = o1 / c0 - 1
        if abs(n) > 0.5:
            continue
        nuit.append((t1, n, max(1.0, (t1 - t0) / 3600 - 6.5)))
        garder.append((t1, c1 / c0 - 1, 0))
        if time.gmtime(t1).tm_mon != time.gmtime(t0).tm_mon and i + 2 < len(b):
            fdm.append((t1, b[i + 2][2] / c0 - 1, (b[i + 2][0] - t0) / 3600))
    return nuit, fdm, garder


def par_an(x, ans, frais=0.0, fin=0.0):
    if len(x) < 15:
        return None
    lg = sum(math.log(max(1e-9, 1 + r - frais - fin * h / 8766)) for _, r, h in x)
    return math.exp(lg / ans) - 1


def pc(x):
    return "   —  " if x is None else f"{x * 100:+6.1f}"


donnees = {}
for s in TICKERS:
    try:
        donnees[s] = achats(yahoo(s))
    except Exception as e:
        print(f"{s} : pas de données ({type(e).__name__})")
    time.sleep(0.6)

ANS = {"A": 8.0, "B": (time.time() - COUPE) / (365.25 * 86400)}
print("Rendement par an en % · brut, puis net de chaque scénario de frais (aller-retour) :")
print("   " + " | ".join(f"{n} {f * 100:.3f}" for n, f in FRAIS))
print("Seuil = frais par aller-retour qui annulent tout le gain (financement compris).")
for per, lab in (("A", "2010-2017"), ("B", "2018-2026")):
    def P(x):
        return [y for y in x if (y[0] < COUPE) == (per == "A")]
    for k, nom in ((0, "NUIT (achat à la clôture, revente à l'ouverture)"), (1, "FIN DE MOIS (dernière clôture → clôture du 3e jour)")):
        print(f"\n=== {lab} · {nom} ===")
        print(f"   {'titre':6} {'garder':>7} {'brut':>7} | " + " | ".join(f"{n[:16]:>16}" for n, _ in FRAIS) + " | seuil")
        for fin in FIN:
            print(f"   — financement {fin * 100:.0f} %/an —")
            tous = []
            for s, d in donnees.items():
                x, g = P(d[k]), P(d[2])
                if len(x) < 15:
                    continue
                nets = [par_an(x, ANS[per], f, fin) for _, f in FRAIS]
                tous.append(nets)
                cout_fin = statistics.mean(fin * h / 8766 for _, _, h in x)
                seuil = statistics.mean(r for _, r, _ in x) - cout_fin
                print(f"   {s:6} {pc(par_an(g, ANS[per])):>7} {pc(par_an(x, ANS[per], 0, fin)):>7} | "
                      + " | ".join(f"{pc(v):>16}" for v in nets) + f" | {seuil * 100:+.3f} %")
            if tous:
                print(f"   {'moy.':6} {'':>7} {'':>7} | " + " | ".join(
                    f"{pc(statistics.mean(v[j] for v in tous if v[j] is not None)):>16}" for j in range(len(FRAIS))))
