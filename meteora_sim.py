"""
Meteora en simulation (option 15 du plan, 01/11/2026). Aucun argent engagé.

Quand un token de la liste d'attente commence à replier, le bot fait comme s'il plaçait 100 € de SOL
dans son pool Meteora (DLMM), en cases réparties de −15 % à −35 % sous le sommet, et suit la position
avec les vraies bougies de 5 minutes du pool (prix et volume) et le vrai taux de frais du pool.

Deux résultats pour la même échelle de prix, pour comparer :
  · « liquidité » : ce que donnerait la position Meteora. Une case achète le token quand le prix passe
    dessous et le revend AU MÊME PRIX quand il remonte : le gain vient seulement des frais, et la perte
    du token gardé si le prix casse vers le bas ;
  · « ordres échelonnés » : les mêmes achats aux mêmes prix, mais on garde le token (pas de frais
    touchés, mais on profite du rebond). C'est l'équivalent d'acheter le repli par paliers.

Frais touchés (estimation prudente, « fournisseur moyen ») : volume de la bougie × taux moyen du pool
× 90 % (Meteora garde 10 %) × notre part de la liquidité du pool × part de la bougie passée dans notre
zone. La part exacte dans chaque case (lecture des cases sur la blockchain) viendra dans un second temps.

Sorties fixées à l'avance : le prix casse 50 % sous le sommet (stop : on vend le token), ou il repasse
au-dessus de la zone pendant 1 h (tout est redevenu SOL + frais), ou 72 h.
"""
import html
import math
import time

import outils as v

EN_DIRECT = True              # messages Telegram « 🧪 Meteora simulé » (aucun argent engagé)
API = "https://dlmm.datapi.meteora.ag"
SOL = "So11111111111111111111111111111111111111112"
CAPITAL_USD = 115             # ≈ 100 €
DECLENCHE = 0.10              # on « place » quand le prix est 10 % sous le sommet…
ZONE_HAUT, ZONE_BAS = 0.15, 0.35   # …des cases de −15 % à −35 % sous le sommet
STOP = 0.50                   # 50 % sous le sommet : on vend le token
REMONTE_H = 1                 # au-dessus de la zone pendant 1 h : on ferme
DUREE_MAX_H = 72
POOL_TVL_MIN, POOL_VOL_MIN = 30_000, 100_000
PART_METEORA = 0.10           # part des frais gardée par Meteora sur les pools de memecoins
MAX_OUVERTES = 6


def _get(path):
    return v.get_json(API + path)


def trouver_pool(mint):
    """Le pool token-SOL le plus actif du token, s'il est assez gros. Renvoie le dict du pool ou None."""
    d = _get(f"/pools?query={mint}&page_size=20&sort_by=volume_24h:desc") or {}
    bons = []
    for p in d.get("data") or []:
        x, y = (p.get("token_x") or {}).get("address"), (p.get("token_y") or {}).get("address")
        if {x, y} != {mint, SOL} or p.get("is_blacklisted"):
            continue
        if (p.get("tvl") or 0) >= POOL_TVL_MIN and ((p.get("volume") or {}).get("24h") or 0) >= POOL_VOL_MIN:
            bons.append(p)
    return max(bons, key=lambda p: (p.get("volume") or {}).get("24h") or 0) if bons else None


def _infos(p):
    """Taux moyen payé par échange (frais 24 h / volume 24 h), liquidité, prix du SOL, sens du prix."""
    vol = (p.get("volume") or {}).get("24h") or 0
    taux = ((p.get("fees") or {}).get("24h") or 0) / vol if vol else (p["pool_config"]["base_fee_pct"] / 100)
    x_est_token = (p.get("token_x") or {}).get("address") != SOL
    sol_usd = ((p.get("token_y") if x_est_token else p.get("token_x")) or {}).get("price") or 0
    return {"taux": taux, "tvl": p.get("tvl") or 0, "sol_usd": sol_usd, "x_token": x_est_token,
            "bin_step": (p.get("pool_config") or {}).get("bin_step") or 0,
            "taux_base": (p.get("pool_config") or {}).get("base_fee_pct")}


def _prix_token(c, x_token):
    """Prix du token en SOL à partir d'un prix de pool (inversé si le token est en y)."""
    return c if x_token else (1 / c if c else 0)


def _cases(haut_zone, bas_zone, bin_step):
    """Prix des cases (en SOL par token), de haut en bas, une case par pas du pool."""
    pas = 1 + (bin_step or 20) / 10_000
    n = max(1, int(math.log(haut_zone / bas_zone) / math.log(pas)) + 1)
    return [haut_zone / pas ** i for i in range(n)]


def ouvrir(st, t, f, envoyer):
    m = st.setdefault("meteora", {"ouvertes": {}, "fermees": [], "pools": {}})
    cache = m["pools"].get(t["key"])
    if cache and time.time() - cache[0] < 12 * 3600 and not cache[1]:
        return                                   # pas de pool assez gros, revu dans 12 h
    p = trouver_pool(t["address"])
    m["pools"][t["key"]] = [time.time(), p["address"] if p else None]
    if not p:
        return
    i = _infos(p)
    prix = _prix_token(p.get("current_price") or 0, i["x_token"])
    if not prix or not i["sol_usd"]:
        return
    sommet = prix / max(1 - f["repli"], 0.01)
    haut_zone, bas_zone = min(prix, sommet * (1 - ZONE_HAUT)), sommet * (1 - ZONE_BAS)
    if haut_zone <= bas_zone:
        return
    cases = _cases(haut_zone, bas_zone, i["bin_step"])
    m["ouvertes"][t["key"]] = {
        "symbol": t["symbol"], "pool": p["address"], "nom_pool": p.get("name"), "ts": time.time(),
        "x_token": i["x_token"], "taux": i["taux"], "taux_base": i["taux_base"], "tvl": i["tvl"],
        "sol_usd": i["sol_usd"], "sommet": sommet, "cases": cases, "plus_bas": prix, "frais_sol": 0.0,
        "dernier_ts": int(time.time()) - 300, "au_dessus_depuis": None, "prix": prix,
        "touche": False}
    if EN_DIRECT:
        envoyer(f"🧪 <b>Meteora simulé : position ouverte sur ${html.escape(str(t['symbol']))}</b>\n"
                f"Pool {html.escape(str(p.get('name')))} · taux {i['taux_base']} % (payé en moyenne "
                f"{i['taux'] * 100:.2f} %) · liquidité {i['tvl'] / 1e3:.0f} k$\n"
                f"100 € de SOL fictifs en {len(cases)} cases, de −{ZONE_HAUT * 100:.0f} % à "
                f"−{ZONE_BAS * 100:.0f} % sous le sommet (le prix est à −{f['repli'] * 100:.0f} %).\n"
                f"<i>Simulation, aucun argent engagé. Sortie : −50 % sous le sommet, retour au-dessus de la "
                f"zone pendant 1 h, ou 72 h.</i>")


def suivre(st, k, pos, envoyer):
    """Rejoue les nouvelles bougies de 5 min du pool sur la position."""
    d = _get(f"/pools/{pos['pool']}/ohlcv?timeframe=5m&start_time={pos['dernier_ts'] + 1}") or {}
    bougies = sorted((d.get("data") or []), key=lambda c: c.get("timestamp") or 0)
    cases = pos["cases"]
    haut_zone, bas_zone = cases[0], cases[-1]
    part_pool = (CAPITAL_USD / pos["tvl"]) if pos["tvl"] else 0
    fin = None
    for c in bougies:
        ts = c.get("timestamp") or 0
        if ts <= pos["dernier_ts"]:
            continue
        pos["dernier_ts"] = ts
        try:
            hi = _prix_token(float(c["high"]), pos["x_token"])
            lo = _prix_token(float(c["low"]), pos["x_token"])
            cl = _prix_token(float(c["close"]), pos["x_token"])
            vol = float(c.get("volume") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        hi, lo = max(hi, lo), min(hi, lo)
        if not cl or not lo:
            continue
        # frais : la part de la bougie passée dans notre zone (en échelle log)
        dedans = max(0.0, math.log(min(hi, haut_zone)) - math.log(max(lo, bas_zone)))
        largeur = math.log(hi / lo) if hi > lo else 0
        frac = (dedans / largeur) if largeur else (1.0 if bas_zone <= cl <= haut_zone else 0.0)
        if lo <= haut_zone:
            pos["touche"] = True
        # frais en dollars, ramenés en fraction du capital
        pos["frais_sol"] += vol * pos["taux"] * (1 - PART_METEORA) * part_pool * frac / CAPITAL_USD
        pos["plus_bas"] = min(pos["plus_bas"], lo)
        pos["prix"] = cl
        # sorties
        if hi > pos["sommet"] and not pos["touche"]:
            fin = ("nouveau sommet sans repli dans la zone", cl)
            break
        if lo <= pos["sommet"] * (1 - STOP):
            fin = ("stop : 50 % sous le sommet", pos["sommet"] * (1 - STOP))
            break
        if cl > haut_zone and pos["touche"]:
            pos["au_dessus_depuis"] = pos["au_dessus_depuis"] or ts
            if ts - pos["au_dessus_depuis"] >= REMONTE_H * 3600:
                fin = ("retour au-dessus de la zone pendant 1 h", cl)
                break
        else:
            pos["au_dessus_depuis"] = None
        if ts - pos["ts"] >= DUREE_MAX_H * 3600:
            fin = ("72 h écoulées", cl)
            break
    if fin:
        fermer(st, k, pos, fin[0], fin[1], envoyer)


def fermer(st, k, pos, raison, prix, envoyer):
    m = st["meteora"]
    cases = pos["cases"]
    vente = 1 - pos["taux"]                       # on revend le token gardé dans le pool : on paie ses frais
    lp_token = sum(1 / len(cases) * prix / c for c in cases if c > prix)
    lp_sol = sum(1 / len(cases) for c in cases if c <= prix)
    lp = lp_sol + lp_token * vente + pos["frais_sol"] - 1
    ech_token = sum(1 / len(cases) * prix / c for c in cases if c > pos["plus_bas"])
    ech_sol = sum(1 / len(cases) for c in cases if c <= pos["plus_bas"])
    ech = ech_sol + ech_token * vente - 1
    r = {"symbol": pos["symbol"], "ts": pos["ts"], "fin": time.time(), "raison": raison,
         "lp": round(lp, 4), "echelonne": round(ech, 4), "frais": round(pos["frais_sol"], 4),
         "touche": pos["touche"], "pool": pos["nom_pool"], "taux": pos["taux"]}
    m["fermees"].append(r)
    m["fermees"] = [x for x in m["fermees"] if time.time() - x["fin"] < 60 * 86400]
    del m["ouvertes"][k]
    if EN_DIRECT:
        envoyer(f"🧪 <b>Meteora simulé : position fermée sur ${html.escape(str(pos['symbol']))}</b> ({raison})\n"
                + (f"Liquidité : <b>{lp * 100:+.1f} %</b> (dont frais {pos['frais_sol'] * 100:+.1f} %), "
                   f"soit {lp * 100:+.0f} € sur 100 €\n"
                   f"Ordres échelonnés (mêmes achats, token gardé) : {ech * 100:+.1f} %"
                   if pos["touche"] else "Le prix n'est jamais descendu dans la zone : rien acheté, 0 €.")
                + "\n<i>Simulation, aucun argent engagé.</i>")


def tick(st, sv, frais, forme, envoyer):
    """frais : dernier relevé (ou None hors relevé) ; forme : attente.forme."""
    m = st.setdefault("meteora", {"ouvertes": {}, "fermees": [], "pools": {}})
    for k, pos in list(m["ouvertes"].items()):
        try:
            suivre(st, k, pos, envoyer)
        except Exception as e:                  # une API qui répond mal ne doit rien casser
            print(f"[warn] meteora {pos.get('symbol')} : {type(e).__name__}")
    if not frais:
        return
    now = time.time()
    deja = {x["symbol"] for x in m["fermees"] if now - x["fin"] < 72 * 3600}
    by_key = {t["key"]: t for t in frais}
    for k in list(st.get("attente", {})):
        if len(m["ouvertes"]) >= MAX_OUVERTES:
            break
        t, e = by_key.get(k), sv["tokens"].get(k)
        if not t or not e or t["chain"] != "solana" or k in m["ouvertes"] or t["symbol"] in deja:
            continue
        f = forme(e, t, now)
        if not f or f["hausse"] < 1.30 or not DECLENCHE <= f["repli"] < ZONE_BAS:
            continue
        try:
            ouvrir(st, t, f, envoyer)
        except Exception as e:
            print(f"[warn] meteora ouverture {t['symbol']} : {type(e).__name__}")
    print(f"meteora simulé : {len(m['ouvertes'])} ouverte(s), {len(m['fermees'])} fermée(s) sur 60 jours")


def bilan(st):
    f = [x for x in (st.get("meteora") or {}).get("fermees", []) if x.get("touche")]
    if not f:
        n = len((st.get("meteora") or {}).get("ouvertes", {}))
        return [f"🧪 Meteora simulé : aucune position fermée pour l'instant ({n} ouverte(s))"]
    lp = sum(x["lp"] for x in f) / len(f)
    ech = sum(x["echelonne"] for x in f) / len(f)
    fr = sum(x["frais"] for x in f) / len(f)
    g = sum(x["lp"] > 0 for x in f) / len(f)
    return [f"🧪 <b>Meteora simulé</b> : {len(f)} positions · liquidité <b>{lp * 100:+.1f} %</b> en moyenne "
            f"(dont frais {fr * 100:+.1f} %, gagnantes {g * 100:.0f} %) · ordres échelonnés {ech * 100:+.1f} %"]
