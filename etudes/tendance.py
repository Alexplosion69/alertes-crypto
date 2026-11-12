"""Piste A (12/11) : suivi de tendance sur des actifs liquides, des années de bougies journalières, frais compris.

Règles testées (toutes « long seulement », décision à la clôture, exécution à l'ouverture du lendemain) :
  · canal N/M : acheter quand la clôture bat le plus haut des N derniers jours, vendre quand elle casse le
    plus bas des M derniers jours (M = N/2) ;
  · moyenne N : être investi tant que la clôture est au-dessus de sa moyenne sur N jours.
Frais : 0,25 % par ordre (0,5 % l'aller-retour). Comparé à « acheter et garder ».
Deux périodes : avant 2023 (pour choisir) et depuis 2023 (pour vérifier, sans rien rechoisir).
Données : Binance (crypto), Yahoo Finance (actions). Aucune clé, aucun ordre."""
import math
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}
FRAIS = 0.0025
COUPE = time.mktime((2023, 1, 1, 0, 0, 0, 0, 0, 0))


def binance(sym):
    out, debut = [], 0
    while True:
        r = requests.get("https://api.binance.com/api/v3/klines", timeout=30, headers=UA,
                         params={"symbol": sym, "interval": "1d", "startTime": debut, "limit": 1000})
        d = r.json()
        if not isinstance(d, list) or not d:
            break
        out += [(x[0] / 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in d]
        debut = d[-1][0] + 1
        if len(d) < 1000:
            break
        time.sleep(0.3)
    return out[:-1]                       # la bougie du jour n'est pas finie


def yahoo(sym):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=30, headers=UA,
                     params={"range": "max", "interval": "1d"})
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    out = []
    for t, o, h, l, c, a in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], adj):
        if None in (o, h, l, c, a) or not c:
            continue
        k = a / c                        # corrige divisions d'actions et dividendes
        out.append((t, o * k, h * k, l * k, a))
    return [x for x in out if x[0] >= time.mktime((2012, 1, 1, 0, 0, 0, 0, 0, 0))]


def simuler(b, signal):
    """signal(i) -> True si on veut être investi après la clôture du jour i. Renvoie la courbe (par jour)."""
    val, investi, courbe, trades = 1.0, False, [], 0
    jours_in = 0
    for i in range(1, len(b)):
        veut = signal(i - 1)
        o, c = b[i][1], b[i][4]
        if veut and not investi:
            val *= (1 - FRAIS) * c / o
            investi, trades = True, trades + 1
        elif not veut and investi:
            val *= (o / b[i - 1][4]) * (1 - FRAIS)
            investi = False
        elif investi:
            val *= c / b[i - 1][4]
        jours_in += investi
        courbe.append((b[i][0], val))
    return courbe, trades, jours_in / max(len(b) - 1, 1)


def mesures(courbe, par_an):
    if len(courbe) < 30:
        return None
    v0, v1 = courbe[0][1], courbe[-1][1]
    ans = (courbe[-1][0] - courbe[0][0]) / (365.25 * 86400)
    cagr = (v1 / v0) ** (1 / ans) - 1 if v1 > 0 and ans > 0 else -1
    haut, dd = 0, 0
    rets = []
    for i, (_, v) in enumerate(courbe):
        haut = max(haut, v)
        dd = min(dd, v / haut - 1)
        if i:
            rets.append(v / courbe[i - 1][1] - 1)
    m = sum(rets) / len(rets)
    sd = (sum((r - m) ** 2 for r in rets) / len(rets)) ** 0.5
    return cagr, dd, (m / sd * math.sqrt(par_an) if sd else 0)


def regles(b):
    cl = [x[4] for x in b]
    r = {"garder": lambda i: True}
    for n in (10, 20, 50, 100):
        def canal(i, n=n, etat={"in": False, "i": -1}):
            if i < n:
                return False
            if etat["i"] != i:           # appelé une fois par jour, dans l'ordre
                if not etat["in"] and cl[i] >= max(cl[i - n:i]):
                    etat["in"] = True
                elif etat["in"] and cl[i] <= min(cl[i - n // 2:i]):
                    etat["in"] = False
                etat["i"] = i
            return etat["in"]
        r[f"canal {n}/{n // 2}"] = canal
    for n in (50, 100, 200):
        r[f"moyenne {n}"] = lambda i, n=n: i >= n and cl[i] > sum(cl[i - n + 1:i + 1]) / n
    return r


def ligne(nom, courbe, trades, part, par_an):
    out = f"   {nom:14}"
    for lab, c in (("avant 2023", [x for x in courbe if x[0] < COUPE]), ("depuis 2023", [x for x in courbe if x[0] >= COUPE])):
        m = mesures(c, par_an)
        out += (f" | {lab} : {m[0] * 100:+6.0f} %/an, pire creux {m[1] * 100:4.0f} %, Sharpe {m[2]:4.2f}" if m
                else f" | {lab} : —")
    return out + f" | {trades:3} achats, investi {part * 100:3.0f} % du temps"


ACTIFS = [("BTC", "c", "BTCUSDT"), ("ETH", "c", "ETHUSDT"), ("SOL", "c", "SOLUSDT"), ("BNB", "c", "BNBUSDT"),
          ("XRP", "c", "XRPUSDT"), ("DOGE", "c", "DOGEUSDT"),
          ("S&P 500 (SPY)", "a", "SPY"), ("Nasdaq (QQQ)", "a", "QQQ"), ("Nvidia", "a", "NVDA"), ("AMD", "a", "AMD"),
          ("Google", "a", "GOOGL"), ("Tesla", "a", "TSLA")]
bilan = {}
for nom, typ, sym in ACTIFS:
    try:
        b = binance(sym) if typ == "c" else yahoo(sym)
    except Exception as e:
        print(f"{nom} : données indisponibles ({type(e).__name__})")
        continue
    if len(b) < 400:
        print(f"{nom} : trop peu de données ({len(b)})")
        continue
    par_an = 365 if typ == "c" else 252
    print(f"\n{nom} : {len(b)} jours depuis {time.strftime('%m/%Y', time.gmtime(b[0][0]))}")
    for rn, sig in regles(b).items():
        courbe, trades, part = simuler(b, sig)
        print(ligne(rn, courbe, trades, part, par_an))
        for lab, c in (("avant", [x for x in courbe if x[0] < COUPE]), ("depuis", [x for x in courbe if x[0] >= COUPE])):
            m = mesures(c, par_an)
            if m:
                bilan.setdefault((typ, rn, lab), []).append(m)
print("\nMoyenne par famille d'actifs (rendement par an, pire creux, Sharpe) :")
for typ, tn in (("c", "crypto"), ("a", "actions")):
    for rn in ["garder", "canal 10/5", "canal 20/10", "canal 50/25", "canal 100/50", "moyenne 50", "moyenne 100", "moyenne 200"]:
        s = f"   {tn:8} {rn:14}"
        for lab in ("avant", "depuis"):
            ms = bilan.get((typ, rn, lab)) or []
            if ms:
                s += (f" | {lab} 2023 : {sum(m[0] for m in ms) / len(ms) * 100:+6.0f} %/an, creux {sum(m[1] for m in ms) / len(ms) * 100:4.0f} %, "
                      f"Sharpe {sum(m[2] for m in ms) / len(ms):4.2f}")
        print(s)
