"""Ne garder que les bonnes nuits (17/11, idée d'Alex) : moins d'achats, donc moins de frais.

Moments testés (achat à la clôture, revente à l'heure dite) :
  · une seule nuit par semaine : celle qui finit le lundi, le mardi… (52 achats par an) ;
  · la fin de mois : achat à la clôture du dernier jour du mois, revente à la clôture du 3e jour du mois
    suivant (effet « tournant du mois », connu des chercheurs ; 12 achats par an) ;
  · la nuit de fin de mois seule (dernière clôture → première ouverture) ;
  · la veille de jour férié : achat à la clôture de l'avant-veille, revente à la clôture de la veille.
Frais par aller-retour : 0,02 % (courtier pro), 0,10 % (courtier bon marché), 0,19 % (perps Fomo).
Le reste du temps l'argent dort (0 %). On choisit sur 2010-2017 et on vérifie sur 2018-2026."""
import math
import statistics
import sys
import time

import requests

sys.stdout.reconfigure(line_buffering=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}
COUPE = time.mktime((2018, 1, 1, 0, 0, 0, 0, 0, 0))
FRAIS = (0.0002, 0.001, 0.0019)
TICKERS = ["SPY", "QQQ", "IWM", "DIA", "GLD", "^FCHI", "^GDAXI",
           "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "AVGO", "ORCL", "INTC", "CSCO",
           "CRM", "ADBE", "JPM", "BAC", "GS", "V", "MA", "XOM", "CVX", "JNJ", "UNH", "LLY", "PG", "KO", "PEP",
           "WMT", "COST", "HD", "MCD", "NKE", "DIS", "BA", "MSTR", "SMCI",
           "MC.PA", "TTE.PA", "AIR.PA", "OR.PA", "SAN.PA", "BNP.PA"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]


def yahoo(sym):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=30, headers=UA,
                     params={"period1": 1262304000, "period2": int(time.time()), "interval": "1d", "events": "div,split"})
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    out = []
    for t, o, c, a in zip(res["timestamp"], q["open"], q["close"], adj):
        if None in (o, c, a) or not c or not o:
            continue
        out.append((t, o * a / c, a))
    return out


def trades(b):
    """{nom du moment: [(temps, rendement)]}"""
    m = {f"nuit → {j}": [] for j in JOURS}
    m.update({"fin de mois (4 jours)": [], "nuit de fin de mois": [], "veille de férié": []})
    for i in range(1, len(b)):
        (t0, o0, c0), (t1, o1, c1) = b[i - 1], b[i]
        n = o1 / c0 - 1
        if abs(n) > 0.5:
            continue
        g0, g1 = time.gmtime(t0), time.gmtime(t1)
        m[f"nuit → {JOURS[g1.tm_wday]}"].append((t1, n)) if g1.tm_wday < 5 else None
        if g1.tm_mon != g0.tm_mon:                                  # i = 1er jour du mois
            m["nuit de fin de mois"].append((t1, n))
            if i + 2 < len(b):
                m["fin de mois (4 jours)"].append((t1, b[i + 2][2] / c0 - 1))
        ecart = round((t1 - t0) / 86400)
        if ecart >= 2 and not (ecart == 3 and g0.tm_wday == 4) and i >= 2:   # trou qui n'est pas un simple week-end
            m["veille de férié"].append((t0, c0 / b[i - 2][2] - 1))
    return m


def stats(rs, ans, frais):
    if len(rs) < 15:
        return None
    lg = sum(math.log(max(1e-9, 1 + r - frais)) for r in rs)
    return math.exp(lg / ans) - 1


def pc(x, d=0):
    return "   —  " if x is None else f"{x * 100:+.{d}f} %"


donnees = {}
for s in TICKERS:
    try:
        b = yahoo(s)
    except Exception as e:
        print(f"{s} : pas de données ({type(e).__name__})")
        continue
    time.sleep(0.6)
    donnees[s] = (b, trades(b))
ANS = {"A": 8.0, "B": (time.time() - COUPE) / (365.25 * 86400)}


def periode(rs, per):
    return [r for t, r in rs if (t < COUPE) == (per == "A")]


moments = list(next(iter(donnees.values()))[1].keys())
print("Par moment : gain moyen par achat (frais non compris), part des achats gagnants, achats par an,")
print("puis rendement par an avec 0,02 / 0,10 / 0,19 % de frais — moyenne de toutes les actions, puis SPY, QQQ, CAC 40")
for per, lab in (("A", "2010-2017"), ("B", "2018-2026")):
    print(f"\n=== {lab} ===")
    for mo in moments:
        tout = [periode(donnees[s][1][mo], per) for s in donnees]
        tout = [x for x in tout if len(x) >= 15]
        if not tout:
            continue
        moy = statistics.mean(statistics.mean(x) for x in tout)
        gag = statistics.mean(sum(r > 0 for r in x) / len(x) for x in tout)
        par_an = statistics.mean(len(x) for x in tout) / ANS[per]
        nets = [statistics.mean(stats(x, ANS[per], f) for x in tout) for f in FRAIS]
        pos = sum(stats(x, ANS[per], FRAIS[1]) > 0 for x in tout)
        print(f"   {mo:22} {moy * 100:+.3f} %/achat · gagnants {gag * 100:.0f} % · {par_an:4.0f}/an · par an "
              f"{pc(nets[0], 1)} / {pc(nets[1], 1)} / {pc(nets[2], 1)} · gagnant net 0,10 % sur {pos}/{len(tout)} titres")
        for s in ("SPY", "QQQ", "^FCHI"):
            if s in donnees:
                x = periode(donnees[s][1][mo], per)
                if len(x) >= 15:
                    print(f"        {s:6} {statistics.mean(x) * 100:+.3f} %/achat · gagnants {sum(r > 0 for r in x) / len(x) * 100:.0f} % · "
                          f"par an {pc(stats(x, ANS[per], FRAIS[0]), 1)} / {pc(stats(x, ANS[per], FRAIS[1]), 1)} / "
                          f"{pc(stats(x, ANS[per], FRAIS[2]), 1)}")

print("\n=== Le vrai test : pour chaque titre, sa meilleure nuit de la semaine en 2010-2017… et ensuite ===")
res = []
for s, (b, m) in donnees.items():
    nuits = [(statistics.mean(periode(m[f'nuit → {j}'], 'A')), j) for j in JOURS if len(periode(m[f'nuit → {j}'], 'A')) >= 200]
    if not nuits:
        continue
    a, j = max(nuits)
    xb = periode(m[f"nuit → {j}"], "B")
    if len(xb) < 100:
        continue
    res.append((s, j, a, statistics.mean(xb), stats(xb, ANS["B"], FRAIS[1]), stats(xb, ANS["B"], FRAIS[2])))
for s, j, a, bm, n10, n19 in sorted(res, key=lambda x: -x[2])[:15]:
    print(f"   {s:7} meilleure : nuit → {j:9} {a * 100:+.3f} %/achat en 2010-2017 → {bm * 100:+.3f} % ensuite · "
          f"par an net 0,10 % {pc(n10, 1)}, net 0,19 % {pc(n19, 1)}")
if res:
    print(f"   moyenne sur {len(res)} titres : {statistics.mean(r[2] for r in res) * 100:+.3f} %/achat → "
          f"{statistics.mean(r[3] for r in res) * 100:+.3f} % ensuite · encore gagnants avec 0,10 % de frais : "
          f"{sum(r[4] > 0 for r in res)}/{len(res)}")
