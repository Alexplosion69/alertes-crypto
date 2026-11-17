"""Acheter à la clôture, revendre à l'ouverture du lendemain (17/11, idée d'Alex).

Pour chaque action ou indice : le rendement de la nuit (clôture → ouverture suivante, dividendes compris)
et celui de la journée (ouverture → clôture). On compare « que la nuit », « que la journée » et « garder ».
Frais par aller-retour (un achat + une vente chaque jour) : 0,02 % (courtier pro, gros montants),
0,10 % (courtier bon marché + écart de prix), 0,19 % (perps Fomo : 2 × 0,095 %).
Pour ne pas se tromper soi-même : on choisit les meilleures actions sur 2010-2017 et on regarde ce
qu'elles font ensuite, sur 2018-2026, sans rien rechoisir. Données Yahoo Finance, aucune clé."""
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
           "WMT", "COST", "HD", "MCD", "NKE", "DIS", "BA", "MSTR", "SMCI", "PLTR", "COIN",
           "MC.PA", "TTE.PA", "AIR.PA", "OR.PA", "SAN.PA", "BNP.PA"]


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
        k = a / c                                   # divisions et dividendes : le dividende tombe dans la nuit
        out.append((t, o * k, a))
    return out


def jours(b):
    """[(temps, nuit, journée, jour de la semaine)]"""
    out = []
    for (t0, o0, c0), (t1, o1, c1) in zip(b, b[1:]):
        n, j = o1 / c0 - 1, c1 / o1 - 1
        if abs(n) > 0.5 or abs(j) > 0.5:            # donnée aberrante
            continue
        out.append((t1, n, j, time.gmtime(t1).tm_wday))
    return out


def annuel(rs, frais=0.0):
    if len(rs) < 100:
        return None
    lg = sum(math.log(max(1e-9, 1 + r - frais)) for r in rs)
    return math.exp(lg * 252 / len(rs)) - 1


def creux(rs):
    v, haut, pire = 1.0, 1.0, 0.0
    for r in rs:
        v *= 1 + r
        haut = max(haut, v)
        pire = min(pire, v / haut - 1)
    return pire


def pc(x):
    return "   —  " if x is None else f"{x * 100:+5.0f} %"


res = {}
for s in TICKERS:
    try:
        d = jours(yahoo(s))
    except Exception as e:
        print(f"{s} : pas de données ({type(e).__name__})")
        continue
    time.sleep(0.6)
    res[s] = {"A": [x for x in d if x[0] < COUPE], "B": [x for x in d if x[0] >= COUPE]}

print("Rendement par an · nuit seule (brut, puis avec 0,02 / 0,10 / 0,19 % par aller-retour) · journée seule · garder")
for per, lab in (("A", "2010-2017"), ("B", "2018-2026")):
    print(f"\n=== {lab} ===")
    for s, r in res.items():
        g = r[per]
        if len(g) < 200:
            continue
        n, j = [x[1] for x in g], [x[2] for x in g]
        tout = [(1 + a) * (1 + b) - 1 for a, b in zip(n, j)]
        print(f"   {s:7} nuit {pc(annuel(n))} → net {pc(annuel(n, FRAIS[0]))} {pc(annuel(n, FRAIS[1]))} {pc(annuel(n, FRAIS[2]))}"
              f" · journée {pc(annuel(j))} · garder {pc(annuel(tout))} · nuits gagnantes {sum(x > 0 for x in n) / len(n) * 100:.0f} %"
              f" · pire chute de la nuit seule {creux(n) * 100:.0f} % · frais qui annulent tout : {statistics.mean(n) * 100:.3f} %")

print("\n=== Le vrai test : les 10 meilleures « nuit » de 2010-2017, et ce qu'elles font ensuite (2018-2026) ===")
cand = [(annuel([x[1] for x in r["A"]]), s) for s, r in res.items() if len(r["A"]) >= 800 and len(r["B"]) >= 800]
cand.sort(reverse=True)
for k, (a, s) in enumerate(cand[:10]):
    nB = [x[1] for x in res[s]["B"]]
    print(f"   {k + 1:2}. {s:7} 2010-2017 {pc(a)} → 2018-2026 brut {pc(annuel(nB))}, net 0,02 % {pc(annuel(nB, FRAIS[0]))}, "
          f"net 0,10 % {pc(annuel(nB, FRAIS[1]))}")
moy = lambda f, per: statistics.mean(f([x[1] for x in res[s][per]]) for _, s in cand[:10])
if cand:
        print(f"   moyenne des 10 : 2010-2017 {pc(moy(annuel, 'A'))} → 2018-2026 {pc(moy(annuel, 'B'))} brut, "
          f"{pc(statistics.mean(annuel([x[1] for x in res[s]['B']], FRAIS[1]) for _, s in cand[:10]))} avec 0,10 % de frais")

print("\n=== Quelle nuit de la semaine ? (toutes les actions, 2018-2026, moyenne par nuit) ===")
noms = ["lundi (nuit du week-end)", "mardi", "mercredi", "jeudi", "vendredi"]
for wd in range(5):
    v = [x[1] for r in res.values() for x in r["B"] if x[3] == wd]
    if v:
        print(f"   ouverture du {noms[wd]:25} : {statistics.mean(v) * 100:+.3f} % en moyenne, gagnante {sum(x > 0 for x in v) / len(v) * 100:.0f} %")
