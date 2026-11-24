"""Volume hors bourse (« dark pools ») publié par la FINRA : annonce-t-il la suite ? (24/11, vidéo vue par Alex)

Source : fichier quotidien gratuit « Reg SHO daily short sale volume » de la FINRA (CNMSshvol), publié le soir
même : par action, volume total échangé hors bourse et part vendue à découvert. C'est la base de l'indicateur
DIX (SqueezeMetrics), présenté comme « l'activité des dark pools ».
Signaux lus le soir du jour J (donc achat à l'ouverture de J+1, jamais avant la publication) :
  · part de vente à découvert hors bourse très haute / très basse (20 % des jours les plus hauts / bas de
    l'action sur les 60 derniers jours) — idée du DIX : haute = des acheteurs servis par les teneurs de marché ;
  · pic de volume hors bourse : volume du jour > 2 × sa moyenne des 20 jours précédents.
Mesure : gain de l'ouverture de J+1 à la clôture de J+5 (≈ 1 semaine) et de J+20 (≈ 1 mois), comparé à la
moyenne de tous les jours (« acheter n'importe quand »). Choix sur 2018-2022, vérification sur 2023-2026."""
import concurrent.futures as cf
import datetime as dt
import json
import os
import statistics
import sys
import time

import requests

sys.stdout.reconfigure(line_buffering=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}
SYMS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "PLTR", "COIN", "AMD", "NFLX",
        "AVGO", "MSTR"]
CACHE = "/tmp/finra_shvol.json"
COUPE = dt.date(2023, 1, 1)


def fichier(d):
    url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d:%Y%m%d}.txt"
    try:
        r = requests.get(url, timeout=30, headers=UA)
    except requests.RequestException:
        return d, None
    if r.status_code != 200:
        return d, r.status_code
    out = {}
    for ligne in r.text.splitlines()[1:]:
        p = ligne.split("|")
        if len(p) >= 5 and p[1] in SYMS:
            try:
                out[p[1]] = (float(p[2]), float(p[4]))
            except ValueError:
                pass
    return d, out


donnees = {}
if os.path.exists(CACHE):
    donnees = json.load(open(CACHE))
jours, d = [], dt.date(2018, 8, 1)
while d < dt.date.today():
    if d.weekday() < 5 and d.isoformat() not in donnees:
        jours.append(d)
    d += dt.timedelta(days=1)
erreurs = {}
with cf.ThreadPoolExecutor(8) as ex:
    for d, res in ex.map(fichier, jours):
        if isinstance(res, dict):
            donnees[d.isoformat()] = res
        else:
            erreurs[str(res)] = erreurs.get(str(res), 0) + 1
json.dump(donnees, open(CACHE, "w"))
print(f"Fichiers FINRA : {len(donnees)} jours ({min(donnees, default='—')} → {max(donnees, default='—')}), "
      f"absents/erreurs : {erreurs}")
if len(donnees) < 300:
    sys.exit("Pas assez de données FINRA.")


def yahoo(sym):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=30, headers=UA,
                     params={"period1": 1525132800, "period2": int(time.time()), "interval": "1d", "events": "div,split"})
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    return [(dt.datetime.utcfromtimestamp(t).date().isoformat(), o * a / c, a)
            for t, o, c, a in zip(res["timestamp"], q["open"], q["close"], adj) if None not in (o, c, a) and c and o]


evts = []   # (date, sym, signal, gain 5 j, gain 20 j)
for s in SYMS:
    try:
        px = yahoo(s)
    except Exception as e:
        print(f"{s} : pas de prix ({type(e).__name__})")
        continue
    time.sleep(0.5)
    ratios, vols = [], []
    for i, (jour, o, c) in enumerate(px):
        v = donnees.get(jour, {}).get(s)
        if not v or v[1] <= 0:
            continue
        ratio, vol = v[0] / v[1], v[1]
        sig = []
        if len(ratios) >= 60:
            fen = sorted(ratios[-60:])
            if ratio >= fen[int(0.8 * 60)]:
                sig.append("vente à découvert hors bourse très haute")
            if ratio <= fen[int(0.2 * 60) - 1]:
                sig.append("vente à découvert hors bourse très basse")
        if len(vols) >= 20 and vol > 2 * statistics.fmean(vols[-20:]):
            sig.append("pic de volume hors bourse (> 2 × moyenne 20 j)")
        ratios.append(ratio)
        vols.append(vol)
        if len(ratios) <= 60 or i + 20 >= len(px):
            continue
        o1 = px[i + 1][1]
        g5, g20 = px[i + 5][2] / o1 - 1, px[i + 20][2] / o1 - 1
        for x in ["tous les jours (référence)"] + sig:
            evts.append((jour, s, x, g5, g20))

print(f"{len(evts)} observations sur {len({e[1] for e in evts})} titres.")
signaux = ["tous les jours (référence)", "vente à découvert hors bourse très haute",
           "vente à découvert hors bourse très basse", "pic de volume hors bourse (> 2 × moyenne 20 j)"]
for lab, cond in (("2018-2022 (choix)", lambda j: j < COUPE.isoformat()),
                  ("2023-2026 (vérification)", lambda j: j >= COUPE.isoformat())):
    print(f"\n=== {lab} · gain moyen de l'ouverture de J+1 à J+5 / J+20, part gagnante, écart à la référence ===")
    ref = {}
    for sg in signaux:
        x = [e for e in evts if e[2] == sg and cond(e[0])]
        if len(x) < 30:
            continue
        m5, m20 = statistics.fmean(e[3] for e in x), statistics.fmean(e[4] for e in x)
        if not ref:
            ref = {"5": m5, "20": m20}
        print(f"   {sg:48} {len(x):6} cas · 1 sem. {m5 * 100:+.2f} % (gagnant {sum(e[3] > 0 for e in x) / len(x) * 100:.0f} %, "
              f"écart {(m5 - ref['5']) * 100:+.2f}) · 1 mois {m20 * 100:+.2f} % (écart {(m20 - ref['20']) * 100:+.2f})")
    for s in ("SPY", "QQQ"):
        for sg in signaux[1:]:
            x = [e for e in evts if e[1] == s and e[2] == sg and cond(e[0])]
            r = [e for e in evts if e[1] == s and e[2] == signaux[0] and cond(e[0])]
            if len(x) >= 15 and r:
                print(f"      {s} {sg[:40]:40} {len(x):4} cas · 1 sem. écart {(statistics.fmean(e[3] for e in x) - statistics.fmean(e[3] for e in r)) * 100:+.2f}"
                      f" · 1 mois écart {(statistics.fmean(e[4] for e in x) - statistics.fmean(e[4] for e in r)) * 100:+.2f}")

print("\n=== Titre par titre : écart à 1 mois du signal, 2018-2022 → 2023-2026 (gagnant si > 0 les deux fois) ===")
for sg in signaux[1:]:
    ok, lignes = 0, []
    for s in SYMS:
        ec = []
        for cond in (lambda j: j < COUPE.isoformat(), lambda j: j >= COUPE.isoformat()):
            x = [e[4] for e in evts if e[1] == s and e[2] == sg and cond(e[0])]
            r = [e[4] for e in evts if e[1] == s and e[2] == signaux[0] and cond(e[0])]
            ec.append(statistics.fmean(x) - statistics.fmean(r) if len(x) >= 10 and r else None)
        if None not in ec:
            ok += ec[0] > 0 and ec[1] > 0
            lignes.append(f"{s} {ec[0] * 100:+.1f}→{ec[1] * 100:+.1f}")
    print(f"   {sg} : positif sur les deux périodes pour {ok}/{len(lignes)} titres")
    print("      " + " · ".join(lignes))
    # un achat par mois au plus (sans chevauchement) : premier signal du mois, tenu 20 jours
    for lab, cond in (("2018-2022", lambda j: j < COUPE.isoformat()), ("2023-2026", lambda j: j >= COUPE.isoformat())):
        vus, g = set(), []
        for e in sorted(evts):
            if e[2] == sg and cond(e[0]) and (e[1], e[0][:7]) not in vus:
                vus.add((e[1], e[0][:7]))
                g.append(e[4])
        ref = statistics.fmean(e[4] for e in evts if e[2] == signaux[0] and cond(e[0]))
        if g:
            print(f"      sans chevauchement {lab} : {len(g)} achats, {statistics.fmean(g) * 100:+.2f} %/mois (référence {ref * 100:+.2f}), "
                  f"médiane {statistics.median(g) * 100:+.2f} %, gagnants {sum(x > 0 for x in g) / len(g) * 100:.0f} %")
