"""Effet « tournant du mois » en simulation (17/11, validé par Alex) : aucun argent.

Règle testée sur 2010-2026 (étude nuits_choisies) : acheter à la clôture du dernier jour de bourse du mois,
revendre à la clôture du 3e jour de bourse du mois suivant. SPY : +0,33 % puis +0,35 % par achat sur
2010-2017 et 2018-2026 ; moyenne de 50 actions +0,36 % puis +0,49 %. 12 achats par an.
Ici : SPY (S&P 500) et QQQ (Nasdaq 100), 100 € fictifs chacun, frais des perps Fomo (0,19 % l'aller-retour).
Contrôle une fois par jour après la clôture américaine (21 h 30 UTC). Données Yahoo Finance, aucune clé."""
import time
from datetime import date, datetime, timedelta, timezone

import requests

ACTIFS = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100")]
FRAIS = 0.0019
MISE = 100.0
HEURE_CONTROLE = 21.5                 # heure UTC, après la clôture de New York (21 h l'hiver, 20 h l'été)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}


def bougies(sym):
    """[(date, clôture)] des deux derniers mois, jours de bourse seulement."""
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=20, headers=UA,
                     params={"range": "2mo", "interval": "1d"})
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    return [(datetime.fromtimestamp(t, timezone.utc).date(), float(c))
            for t, c in zip(res["timestamp"], q["close"]) if c]


def prochain_jour_ouvre(j):
    j += timedelta(days=1)
    while j.weekday() >= 5:
        j += timedelta(days=1)
    return j


def prix_txt(p):
    return f"{p:,.2f}".replace(",", " ").replace(".", ",")


def _controle(e, auj, telegram):
    donnees = {sym: bougies(sym) for sym, _ in ACTIFS}
    ouvertes = e.setdefault("ouvertes", {})
    msgs_vente, msgs_achat = [], []
    for sym, nom in ACTIFS:
        b = donnees[sym]
        p = ouvertes.get(sym)
        if p:                                           # revente à la clôture du 3e jour de bourse du mois suivant
            apres = [(j, c) for j, c in b if j > date.fromisoformat(p["date"])]
            if len(apres) >= 3:
                j3, c3 = apres[2]
                res = c3 / p["prix"] - 1 - FRAIS
                e.setdefault("trades", []).append({"sym": sym, "achat": p["date"], "vente": j3.isoformat(),
                                                   "res": round(res, 5)})
                e.setdefault("valeur", {})[sym] = e.get("valeur", {}).get(sym, MISE) * (1 + res)
                del ouvertes[sym]
                msgs_vente.append(f"   · {nom} ({sym}) : vendu à {prix_txt(c3)} $ · {res * 100:+.2f} % frais Fomo compris")
    for sym, nom in ACTIFS:
        b = donnees[sym]
        if sym in ouvertes or not b:
            continue
        dj, dc = b[-1]
        mois = dj.strftime("%Y-%m")
        if dj == auj and prochain_jour_ouvre(auj).month != auj.month and e.get("fait", {}).get(sym) != mois:
            ouvertes[sym] = {"date": dj.isoformat(), "prix": dc}
            e.setdefault("fait", {})[sym] = mois
            msgs_achat.append(f"   · {nom} ({sym}) : acheté à {prix_txt(dc)} $")
        elif len(b) >= 2 and b[-1][0].month != b[-2][0].month:
            # dernier jour du mois férié ou contrôle manqué : on rattrape au prix de la vraie dernière clôture
            jm, cm = b[-2]
            if e.get("fait", {}).get(sym) != jm.strftime("%Y-%m") and e.get("debut") and jm.isoformat() >= e["debut"]:
                ouvertes[sym] = {"date": jm.isoformat(), "prix": cm}
                e.setdefault("fait", {})[sym] = jm.strftime("%Y-%m")
                msgs_achat.append(f"   · {nom} ({sym}) : acheté à {prix_txt(cm)} $ (clôture du {jm.strftime('%d/%m')}, rattrapé)")
    if msgs_vente:
        tr = e.get("trades", [])
        telegram("🗓️ <b>Fin de mois : revente</b> (simulation, aucun argent)\n" + "\n".join(msgs_vente)
                 + f"\nDepuis le début : {len(tr)} achat(s), moyenne {sum(t['res'] for t in tr) / len(tr) * 100:+.2f} % par achat.")
    if msgs_achat:
        telegram("🗓️ <b>Fin de mois : achat</b> (simulation, aucun argent)\n" + "\n".join(msgs_achat)
                 + "\nRevente à la clôture du 3e jour de bourse du mois qui commence. "
                   "Repère 2018-2026 : +0,35 % en moyenne par achat sur le S&P 500.")


def tick(st, telegram):
    """Appelé à chaque cycle du bot : un contrôle par jour de semaine, après la clôture de New York."""
    e = st.setdefault("fin_de_mois", {})
    now = datetime.now(timezone.utc)
    auj = now.date()
    if not e.get("debut"):
        e["debut"] = auj.isoformat()
        j = auj
        while not (j.weekday() < 5 and prochain_jour_ouvre(j).month != j.month):
            j += timedelta(days=1)
        telegram("🗓️ <b>Simulation « fin de mois » lancée</b> (aucun argent)\n"
                 "Règle : acheter le S&P 500 (SPY) et le Nasdaq 100 (QQQ) à la clôture du dernier jour de bourse du "
                 "mois, revendre à la clôture du 3e jour de bourse du mois suivant. 12 fois par an, frais des perps "
                 "Fomo comptés. Sur 2010-2026, cet « effet tournant du mois » a tenu sur presque toutes les actions, "
                 "mais il rapporte peu (quelques % par an).\n"
                 f"Premier achat fictif prévu le {j.strftime('%d/%m')} vers 22 h, heure de Paris.")
    if now.weekday() >= 5 or now.hour + now.minute / 60 < HEURE_CONTROLE or e.get("controle") == auj.isoformat():
        return
    if time.time() - e.get("essai", 0) < 900:
        return
    e["essai"] = time.time()
    _controle(e, auj, telegram)
    e["controle"] = auj.isoformat()


def bilan(st):
    e = st.get("fin_de_mois") or {}
    if not e.get("debut"):
        return []
    tr = e.get("trades", [])
    ouv = e.get("ouvertes", {})
    debut = date.fromisoformat(e["debut"]).strftime("%d/%m")
    if not tr:
        etat = "en cours : " + ", ".join(ouv) if ouv else "premier achat le dernier jour de bourse du mois"
        return [f"🗓️ Fin de mois (simulation depuis le {debut}, SPY et QQQ) : aucun achat terminé ({etat})"]
    moy = sum(t["res"] for t in tr) / len(tr)
    val = e.get("valeur", {})
    cumul = " · ".join(f"{s} {(v / MISE - 1) * 100:+.1f} %" for s, v in val.items())
    return [f"🗓️ Fin de mois (simulation depuis le {debut}, frais Fomo compris) : {len(tr)} achat(s), "
            f"moyenne {moy * 100:+.2f} % par achat, gagnants {sum(t['res'] > 0 for t in tr)} · cumul {cumul}"
            + (f" · en cours : {', '.join(ouv)}" if ouv else ""),
            "   (repère 2018-2026 : +0,35 % par achat sur le S&P 500 avant frais ; se juge sur une année au moins)"]
