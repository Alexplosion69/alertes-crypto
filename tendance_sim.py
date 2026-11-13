"""Piste A en simulation (13/11) : suivre la tendance des grosses cryptos, sans argent.

Règle « canal 20/10 », testée sur le passé (étude tendance du 12/11 : +37 %/an depuis 2023 en moyenne sur
ces six cryptos, contre +33 % en gardant, pire chute −46 % au lieu de −69 %) :
  · chaque jour à la clôture (00 h UTC), ACHETER si la clôture bat le plus haut des 20 clôtures d'avant ;
  · REVENDRE si elle passe sous le plus bas des 10 clôtures d'avant ; sinon, ne rien changer.
Ordre au prix d'ouverture du jour qui commence, 0,25 % de frais par ordre. 100 € fictifs par crypto,
comparés à « acheter et garder » depuis le même jour. Au lancement, on prend la position que la règle a
déjà (reconstituée sur 150 jours). Données publiques Binance : aucune clé, aucun ordre."""
import json
import time

import requests

ACTIFS = [("BTC", "BTCUSDT"), ("ETH", "ETHUSDT"), ("SOL", "SOLUSDT"), ("BNB", "BNBUSDT"),
          ("XRP", "XRPUSDT"), ("DOGE", "DOGEUSDT")]
N_HAUT, N_BAS = 20, 10
FRAIS = 0.0025
MISE = 100.0
API = "https://api.binance.com/api/v3"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) alertes-crypto/1.0"}
ATTENTE_CLOTURE = 300                # 5 min après minuit UTC, le temps que la bougie soit close partout


def bougies(sym, n):
    """Bougies journalières (début, ouverture, clôture), la dernière est celle du jour (pas finie)."""
    r = requests.get(f"{API}/klines", params={"symbol": sym, "interval": "1d", "limit": n}, timeout=20, headers=UA)
    r.raise_for_status()
    return [(x[0] / 1000, float(x[1]), float(x[4])) for x in r.json()]


def prix_actuels():
    r = requests.get(f"{API}/ticker/price", timeout=20, headers=UA,
                     params={"symbols": json.dumps([s for _, s in ACTIFS], separators=(",", ":"))})
    r.raise_for_status()
    return {x["symbol"]: float(x["price"]) for x in r.json()}


def decision(closes, investi):
    """closes : clôtures finies, la dernière est celle d'hier. True = être investi aujourd'hui."""
    c = closes[-1]
    if not investi and c >= max(closes[-1 - N_HAUT:-1]):
        return True
    if investi and c <= min(closes[-1 - N_BAS:-1]):
        return False
    return investi


def prix_txt(p):
    return f"{p:,.0f}".replace(",", " ") if p >= 100 else f"{p:.4g}"


def valeur(a):
    return a["val"] * (a["prix"] / a["ref"]) if a["investi"] else a["val"]


def garder(a):
    return MISE * (1 - FRAIS) * a["prix"] / a["garder0"]


def _journee(e, jour, telegram):
    lancement = not e.get("debut")
    acts = e.setdefault("actifs", {})
    donnees = {}
    for nom, sym in ACTIFS:                                  # tout lire d'abord : pas de demi-journée traitée
        b = bougies(sym, 150 if sym not in acts else N_HAUT + 5)
        if len(b) < N_HAUT + 2 or b[-1][0] != jour:
            raise RuntimeError(f"bougie du jour pas encore ouverte pour {sym}")
        donnees[sym] = b
    msgs = []
    for nom, sym in ACTIFS:
        nouveau = sym not in acts
        b = donnees[sym]
        closes = [x[2] for x in b[:-1]]
        ouv = b[-1][1]
        if nouveau:
            veut = False
            for i in range(N_HAUT + 1, len(closes) + 1):     # état de la règle reconstitué sur l'historique
                veut = decision(closes[:i], veut)
            a = acts[sym] = {"nom": nom, "val": MISE, "investi": False, "ref": ouv, "garder0": ouv, "prix": ouv,
                             "trades": []}
        else:
            a = acts[sym]
            veut = decision(closes, a["investi"])
        if a["investi"]:
            a["val"] *= ouv / a["ref"]
        a["ref"] = a["prix"] = ouv
        if veut and not a["investi"]:
            a["val"] *= 1 - FRAIS
            a.update(investi=True, entree=ouv, t_entree=time.time())
            msgs.append(f"📈 <b>{nom}</b> : achat fictif à {prix_txt(ouv)} $"
                        + (" (la règle était déjà à l'achat)" if lancement else
                           f" · la clôture d'hier bat le plus haut des {N_HAUT} jours"))
        elif not veut and a["investi"]:
            a["val"] *= 1 - FRAIS
            res = ouv / a["entree"] * (1 - FRAIS) ** 2 - 1
            a["trades"].append({"t": a.get("t_entree"), "fin": time.time(), "res": round(res, 4)})
            a["investi"] = False
            msgs.append(f"📉 <b>{nom}</b> : vente fictive à {prix_txt(ouv)} $ · clôture sous le plus bas des "
                        f"{N_BAS} jours · ce trade : {res * 100:+.1f} % frais compris")
    e["jour"] = jour
    e["maj_prix"] = time.time()
    if lancement:
        e["debut"] = time.time()
        dehors = [a["nom"] for a in acts.values() if not a["investi"]]
        telegram("🧭 <b>Tendance grosses cryptos : simulation lancée</b> (aucun argent)\n"
                 f"100 € fictifs sur chacune : {', '.join(n for n, _ in ACTIFS)}. Règle : acheter quand la "
                 f"clôture bat le plus haut des {N_HAUT} jours, revendre sous le plus bas des {N_BAS} jours, "
                 "0,25 % de frais par ordre. Comparé à « tout acheter et garder ».\n"
                 + ("\n".join(msgs) if msgs else "Aucune crypto à l'achat aujourd'hui.")
                 + (f"\nHors marché pour l'instant : {', '.join(dehors)}." if dehors else "")
                 + "\nTu auras un message seulement quand la règle achète ou vend (quelques fois par mois).")
    elif msgs:
        telegram("🧭 <b>Tendance grosses cryptos</b> (simulation, aucun argent)\n" + "\n".join(msgs))


def tick(st, telegram):
    """Appelé à chaque cycle : la décision une fois par jour, le prix affiché une fois par heure."""
    e = st.setdefault("tendance", {})
    now = time.time()
    if now - e.get("essai", 0) < 600:
        return
    jour = int(now // 86400 * 86400)
    if e.get("jour") != jour:
        if now - jour < ATTENTE_CLOTURE:
            return
        e["essai"] = now
        _journee(e, jour, telegram)
    elif now - e.get("maj_prix", 0) >= 3600:
        e["essai"] = now
        px = prix_actuels()
        for sym, a in e.get("actifs", {}).items():
            if px.get(sym):
                a["prix"] = px[sym]
        e["maj_prix"] = now


def bilan(st):
    e = st.get("tendance") or {}
    acts = e.get("actifs") or {}
    if not acts:
        return []
    base = MISE * len(acts)
    tot = sum(valeur(a) for a in acts.values())
    hold = sum(garder(a) for a in acts.values())
    trades = [t for a in acts.values() for t in a["trades"]]
    lignes = [f"🧭 Tendance grosses cryptos (piste A, simulation depuis le "
              f"{time.strftime('%d/%m', time.gmtime(e.get('debut', time.time())))}, {len(acts)} × 100 € fictifs) : "
              f"<b>{(tot / base - 1) * 100:+.1f} %</b> contre {(hold / base - 1) * 100:+.1f} % en gardant tout",
              "   " + " · ".join(f"{a['nom']} {'investi' if a['investi'] else 'dehors'} {(valeur(a) / MISE - 1) * 100:+.0f} %"
                               for a in acts.values())]
    if trades:
        g = sum(t["res"] > 0 for t in trades)
        lignes.append(f"   {len(trades)} trade(s) terminé(s) : {g} gagnant(s), moyenne "
                      f"{sum(t['res'] for t in trades) / len(trades) * 100:+.1f} % frais compris")
    lignes.append("   (une règle de tendance se juge sur des mois : on regarde surtout si elle colle au test sur le passé)")
    return lignes
