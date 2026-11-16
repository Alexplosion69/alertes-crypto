"""Perps (16/11) : la piste A (suivre la tendance) avec la vente à découvert et le levier, comme sur les perps de Fomo.

Question d'Alex : avec les perps et le levier, il y a peut-être quelque chose à faire sur le Bitcoin.
Règles testées, décision à la clôture du jour, ordre à l'ouverture du lendemain :
  · garder : acheter au début et ne plus rien faire (pour comparer) ;
  · long seul canal 20/10 : la règle de la piste A (acheter au plus haut 20 jours, sortir au plus bas 10 jours) ;
  · long/short canal 20/10 : pareil, plus VENDRE À DÉCOUVERT au plus bas 20 jours, sortie au plus haut 10 jours ;
  · long/short moyenne 100 : acheteur au-dessus de la moyenne 100 jours, vendeur à découvert en dessous.
Levier x1, x2, x3, x5 : la taille de la position est fixée à l'entrée (levier × capital), comme sur l'appli.
Frais des perps Fomo : 0,05 % Fomo + 0,045 % Hyperliquid à chaque ordre, sur toute la taille (levier compris).
Financement (« funding ») : celui de Binance, jour par jour (les acheteurs paient quand il est positif).
Liquidation : si le pire prix de la journée fait tomber la marge sous la marge de maintien d'Hyperliquid
(1,25 % BTC, 2 % ETH, 2,5 % SOL), tout le capital du test est perdu et il s'arrête là.
Deux périodes : avant 2023 et depuis 2023. Données publiques Binance, aucune clé, aucun ordre."""
import math
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}
FRAIS = 0.0005 + 0.00045
COUPE = time.mktime((2023, 1, 1, 0, 0, 0, 0, 0, 0))
ACTIFS = [("BTC", "BTCUSDT", 0.0125), ("ETH", "ETHUSDT", 0.02), ("SOL", "SOLUSDT", 0.025)]
LEVIERS = (1, 2, 3, 5)


def bougies(sym):
    out, debut = [], 0
    while True:
        d = requests.get("https://api.binance.com/api/v3/klines", timeout=30, headers=UA,
                         params={"symbol": sym, "interval": "1d", "startTime": debut, "limit": 1000}).json()
        if not isinstance(d, list) or not d:
            break
        out += [(x[0] / 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in d]
        debut = d[-1][0] + 1
        if len(d) < 1000:
            break
        time.sleep(0.3)
    return out[:-1]


def financement(sym):
    """{jour (début, s): somme des taux de financement du jour} ; vide si l'API des contrats est injoignable."""
    par_jour, debut = {}, 1567296000000                       # 01/09/2019 : 0 renverrait les plus récents
    try:
        while True:
            d = requests.get("https://fapi.binance.com/fapi/v1/fundingRate", timeout=30, headers=UA,
                             params={"symbol": sym, "startTime": debut, "limit": 1000}).json()
            if not isinstance(d, list) or not d:
                break
            for x in d:
                j = int(x["fundingTime"] / 1000 // 86400 * 86400)
                par_jour[j] = par_jour.get(j, 0.0) + float(x["fundingRate"])
            debut = d[-1]["fundingTime"] + 1
            if len(d) < 1000:
                break
            time.sleep(0.3)
    except (requests.RequestException, ValueError, KeyError):
        pass
    return par_jour


def regles(b):
    cl = [x[4] for x in b]

    def canal(longshort):
        etat = {"pos": 0, "i": -1}

        def f(i):
            if i < 20:
                return 0
            if etat["i"] != i:
                c, p = cl[i], etat["pos"]
                if c >= max(cl[i - 20:i]):
                    p = 1
                elif longshort and c <= min(cl[i - 20:i]):
                    p = -1
                elif p == 1 and c <= min(cl[i - 10:i]):
                    p = 0
                elif p == -1 and c >= max(cl[i - 10:i]):
                    p = 0
                etat["pos"], etat["i"] = p, i
            return etat["pos"]
        return f

    return {"garder": lambda i: 1,
            "long seul canal 20/10": canal(False),
            "long/short canal 20/10": canal(True),
            "long/short moyenne 100": lambda i: 0 if i < 100 else (1 if cl[i] > sum(cl[i - 99:i + 1]) / 100 else -1)}


def simuler(b, fund, regle, levier, mm, debut=0):
    E, pos, q, ref = 1.0, 0, 0.0, None
    courbe, trades, liq, frais_tot, fin_tot = [], 0, 0, 0.0, 0.0
    for i in range(1, len(b)):
        t, o, h, l, c = b[i]
        if E <= 0:
            courbe.append((t, 0.0))
            continue
        veut = regle(i - 1)                                    # la règle suit l'historique dès le début…
        if t < debut:
            veut = 0                                           # … mais on ne trade qu'à partir de la période testée
        ref = b[i - 1][4]
        if veut != pos:
            if pos:                                            # on ferme à l'ouverture
                E += q * (o - ref)
                E -= abs(q) * o * FRAIS
                frais_tot += abs(q) * o * FRAIS
                q, pos = 0.0, 0
            if veut and E > 0:                                 # on ouvre à l'ouverture
                q = veut * levier * E / o
                E -= abs(q) * o * FRAIS
                frais_tot += abs(q) * o * FRAIS
                pos, trades = veut, trades + 1
            ref = o
        if pos:
            f = fund.get(int(t // 86400 * 86400), 0.0) * abs(q) * c
            E -= f if pos > 0 else -f                          # financement : les acheteurs paient s'il est positif
            fin_tot += f if pos > 0 else -f
            pire = l if pos > 0 else h
            if E + q * (pire - ref) <= mm * abs(q) * pire:     # liquidation : tout est perdu
                liq += 1
                E, q, pos = 0.0, 0.0, 0
                courbe.append((t, 0.0))
                continue
            E += q * (c - ref)
        courbe.append((t, E))
    return courbe, trades, liq, frais_tot, fin_tot


def mesures(c):
    if len(c) < 60:
        return None
    v0, v1 = c[0][1], c[-1][1]
    ans = (c[-1][0] - c[0][0]) / (365.25 * 86400)
    if v0 <= 0:
        return None
    cagr = (v1 / v0) ** (1 / ans) - 1 if v1 > 0 else -1.0
    haut, dd = 0.0, 0.0
    for _, v in c:
        haut = max(haut, v)
        dd = min(dd, v / haut - 1 if haut else 0)
    return cagr, dd, v1 / v0


synthese = {}
for nom, sym, mm in ACTIFS:
    b = bougies(sym)
    fund = financement(sym)
    if not b:
        print(f"{nom} : pas de données")
        continue
    jours_f = [j for j in fund if j >= b[0][0]]
    moy_f = sum(fund[j] for j in jours_f) / len(jours_f) * 365 * 100 if jours_f else 0
    print(f"\n=== {nom} : {len(b)} jours depuis {time.strftime('%m/%Y', time.gmtime(b[0][0]))} · financement connu "
          f"depuis {time.strftime('%m/%Y', time.gmtime(min(jours_f))) if jours_f else '—'} "
          f"(en moyenne {moy_f:+.1f} %/an payés par les acheteurs)")
    for rn, regle in regles(b).items():
        for lev in LEVIERS:
            if rn == "garder" and lev not in (1, 2, 3):
                continue
            for lab, debut in (("avant 2023", None), ("depuis 2023", COUPE)):
                bb = [x for x in b if (debut is None and x[0] < COUPE) or (debut is not None and x[0] >= debut - 120 * 86400)]
                r = regles(bb)[rn]                             # règle rejouée sur la période seule
                courbe, tr, liq, fr, fi = simuler(bb, fund, r, lev, mm, debut or 0)
                if debut is not None:
                    courbe = [x for x in courbe if x[0] >= debut]
                m = mesures(courbe)
                if not m:
                    continue
                synthese.setdefault((rn, lev, lab), []).append(m + (liq,))
                print(f"   {rn:24} x{lev} {lab:11} : {m[0] * 100:+7.0f} %/an · pire creux {m[1] * 100:5.0f} % · "
                      f"capital x{m[2]:.2f} · {tr:3} ordres d'entrée · liquidé {liq} fois · frais {fr * 100:.0f} % "
                      f"et financement {fi * 100:+.0f} % du capital de départ")

print("\n=== Moyenne BTC / ETH / SOL (rendement par an, pire creux, nombre d'actifs liquidés au moins une fois) ===")
for rn in ("garder", "long seul canal 20/10", "long/short canal 20/10", "long/short moyenne 100"):
    for lev in LEVIERS:
        s = f"   {rn:24} x{lev}"
        vu = False
        for lab in ("avant 2023", "depuis 2023"):
            ms = synthese.get((rn, lev, lab))
            if ms:
                vu = True
                s += (f" | {lab} : {sum(m[0] for m in ms) / len(ms) * 100:+6.0f} %/an, creux "
                      f"{sum(m[1] for m in ms) / len(ms) * 100:4.0f} %, liquidé {sum(1 for m in ms if m[3])}/{len(ms)}")
        if vu:
            print(s)
