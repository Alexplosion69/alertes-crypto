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

EN_DIRECT = True              # messages Telegram « 🧪 Meteora fictif » (aucun argent engagé)
SOURCES = {"liste d'attente": "sur un signal Repli", "pool Meteora": "grosse pool Meteora qui replie"}   # libellés
API = "https://dlmm.datapi.meteora.ag"
SOL = "So11111111111111111111111111111111111111112"
CAPITAL_USD = 115             # ≈ 100 €
DECLENCHE = 0.10              # on « place » quand le prix est 10 % sous le sommet…
ZONE_HAUT, ZONE_BAS = 0.15, 0.35   # …des cases de −15 % à −35 % sous le sommet
STOP = 0.50                   # 50 % sous le sommet : on vend le token
REMONTE_H = 1                 # au-dessus de la zone pendant 1 h : on ferme
DUREE_MAX_H = 72
POOL_TVL_MIN, POOL_VOL_MIN = 10_000, 30_000   # 02/11 : 30 k$ / 100 k$ ne laissait passer aucun token
PART_METEORA = 0.10           # part des frais gardée par Meteora sur les pools de memecoins
MAX_OUVERTES = 10
# 05/11 (option 21) : les tokens de la liste d'attente n'ont presque jamais de pool Meteora ; on teste
# donc aussi l'idée directement sur les pools Meteora de memecoins les plus actifs
POOLS_TOUTES_MIN = 30
POOLS_MCAP = (100_000, 50_000_000)
POOLS_VOL_MIN, POOLS_TVL_MIN = 100_000, 30_000


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


def ouvrir(st, t, f, envoyer, source="liste d'attente"):
    m = st.setdefault("meteora", {"ouvertes": {}, "fermees": [], "pools": {}})
    cache = m["pools"].get(t["key"])
    if cache and time.time() - cache[0] < 12 * 3600 and not cache[1]:
        return                                   # pas de pool assez gros, revu dans 12 h
    p = trouver_pool(t["address"])
    m["pools"][t["key"]] = [time.time(), p["address"] if p else None]
    if not p:
        m["sans_pool"] = m.get("sans_pool", 0) + 1
        print(f"meteora simulé : pas de pool Meteora assez actif pour {t['symbol']}")
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
        "touche": False, "source": source}
    if EN_DIRECT:
        envoyer(f"🧪 <b>Meteora fictif : position ouverte sur ${html.escape(str(t['symbol']))}</b> "
                f"({SOURCES.get(source, source)})\n"
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
         "touche": pos["touche"], "pool": pos["nom_pool"], "taux": pos["taux"],
         "source": pos.get("source", "liste d'attente")}
    m["fermees"].append(r)
    v.archiver("meteora", [x for x in m["fermees"] if time.time() - x["fin"] >= 60 * 86400])
    m["fermees"] = [x for x in m["fermees"] if time.time() - x["fin"] < 60 * 86400]
    del m["ouvertes"][k]
    if EN_DIRECT:
        envoyer(f"🧪 <b>Meteora fictif : position fermée sur ${html.escape(str(pos['symbol']))}</b> ({raison})\n"
                + (f"Liquidité : <b>{lp * 100:+.1f} %</b> (dont frais {pos['frais_sol'] * 100:+.1f} %), "
                   f"soit {lp * 100:+.0f} € sur 100 €\n"
                   f"Ordres échelonnés (mêmes achats, token gardé) : {ech * 100:+.1f} %"
                   if pos["touche"] else "Le prix n'est jamais descendu dans la zone : rien acheté, 0 €.")
                + "\n<i>Simulation, aucun argent engagé.</i>")


def candidats_pools(st, envoyer):
    """Option 21 : parmi les pools Meteora de memecoins les plus actifs (token-SOL), ceux dont le token
    a monté d'au moins 30 % sur 48 h puis replie de 10 à 35 % : on y « place » 100 € fictifs."""
    m = st["meteora"]
    now = time.time()
    if now - m.get("pools_vus_ts", 0) < POOLS_TOUTES_MIN * 60:
        return
    m["pools_vus_ts"] = now
    deja = {x["symbol"] for x in m["fermees"] if now - x["fin"] < 72 * 3600}
    d = _get("/pools?page_size=50&sort_by=volume_24h:desc&filter_by=is_blacklisted=false") or {}
    vus = 0
    for p in d.get("data") or []:
        if len(m["ouvertes"]) >= MAX_OUVERTES:
            break
        x, y = p.get("token_x") or {}, p.get("token_y") or {}
        if SOL not in (x.get("address"), y.get("address")):
            continue
        tok = y if x.get("address") == SOL else x
        mint, sym = tok.get("address"), tok.get("symbol") or "?"
        if not mint or sym in deja or f"solana:{mint}" in m["ouvertes"]:
            continue
        if not (POOLS_MCAP[0] <= (tok.get("market_cap") or 0) <= POOLS_MCAP[1]):
            continue
        if (p.get("tvl") or 0) < POOLS_TVL_MIN or ((p.get("volume") or {}).get("24h") or 0) < POOLS_VOL_MIN:
            continue
        vus += 1
        c = _get(f"/pools/{p['address']}/ohlcv?timeframe=1h&start_time={int(now - 48 * 3600)}") or {}
        b = sorted(c.get("data") or [], key=lambda z: z.get("timestamp") or 0)
        x_token = x.get("address") != SOL
        try:
            hauts = [_prix_token(float(z["high"]), x_token) for z in b]
            bas = [_prix_token(float(z["low"]), x_token) for z in b]
            if not x_token:                      # prix inversé : le haut et le bas s'échangent
                hauts, bas = bas, hauts
            prix = _prix_token(float(b[-1]["close"]), x_token)
        except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
            continue
        if len(b) < 12 or not prix:
            continue
        i = max(range(len(hauts)), key=lambda j: hauts[j])
        sommet, creux = hauts[i], min(bas[:i + 1]) if i else bas[0]
        hausse, repli = (sommet / creux if creux else 0), 1 - prix / sommet
        if hausse >= 1.30 and DECLENCHE <= repli < ZONE_BAS:
            try:
                ouvrir(st, {"key": f"solana:{mint}", "address": mint, "symbol": sym}, {"repli": repli},
                       envoyer, source="pool Meteora")
            except Exception as e:
                print(f"[warn] meteora ouverture {sym} : {type(e).__name__}")
    print(f"meteora simulé : {vus} pool(s) Meteora de memecoins examiné(s)")


def tick(st, sv, frais, forme, envoyer):
    """frais : dernier relevé (ou None hors relevé) ; forme : attente.forme."""
    m = st.setdefault("meteora", {"ouvertes": {}, "fermees": [], "pools": {}})
    if m.get("seuils") != [POOL_TVL_MIN, POOL_VOL_MIN]:    # seuils changés : on revoit tous les pools
        m["pools"], m["seuils"] = {}, [POOL_TVL_MIN, POOL_VOL_MIN]
    for k, pos in list(m["ouvertes"].items()):
        try:
            suivre(st, k, pos, envoyer)
        except Exception as e:                  # une API qui répond mal ne doit rien casser
            print(f"[warn] meteora {pos.get('symbol')} : {type(e).__name__}")
    # 02/11 : les zones d'entrée de la liste d'attente déclenchent aussi une position (avant, il
    # fallait attraper le token entre −10 % et −15 % pendant un relevé de 30 min : quasi jamais)
    vu = m.get("vu_zones", time.time() - 3600)
    for a in [a for a in st.get("alerts", []) if a.get("type") == "attente" and a.get("ts", 0) > vu]:
        m["vu_zones"] = max(m.get("vu_zones", 0), a["ts"])
        if a.get("chain") != "solana" or a["key"] in m["ouvertes"] or len(m["ouvertes"]) >= MAX_OUVERTES:
            continue
        try:
            ouvrir(st, {"key": a["key"], "address": a["address"], "symbol": a["symbol"]},
                   {"repli": (a.get("repli_pct") or 15) / 100}, envoyer)
        except Exception as e:
            print(f"[warn] meteora ouverture {a.get('symbol')} : {type(e).__name__}")
    m.setdefault("vu_zones", vu)
    try:
        candidats_pools(st, envoyer)
    except Exception as e:
        print(f"[warn] meteora pools : {type(e).__name__}")
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
        sp = (st.get("meteora") or {}).get("sans_pool", 0)
        return [f"🧪 Meteora fictif (100 € fictifs placés dans une pool) : aucune position fermée pour l'instant ({n} ouverte(s) ; "
                f"{sp} token(s) en repli sans pool Meteora assez actif)"]
    lignes = []
    for source in ("liste d'attente", "pool Meteora"):
        g_ = [x for x in f if x.get("source", "liste d'attente") == source]
        if not g_:
            continue
        lp = sum(x["lp"] for x in g_) / len(g_)
        ech = sum(x["echelonne"] for x in g_) / len(g_)
        fr = sum(x["frais"] for x in g_) / len(g_)
        g = sum(x["lp"] > 0 for x in g_) / len(g_)
        lignes.append(f"🧪 <b>Meteora fictif ({SOURCES[source]})</b> : {len(g_)} positions · liquidité <b>{lp * 100:+.1f} %</b> "
                      f"en moyenne (dont frais {fr * 100:+.1f} %, gagnantes {g * 100:.0f} %) · ordres échelonnés "
                      f"{ech * 100:+.1f} %")
    return lignes
