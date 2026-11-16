"""Piste « événements » (16/11) : Alex a gagné sur GTA 6 et la Coupe du monde. Est-ce une stratégie ?

Pour des événements passés très attendus, on retrouve les memecoins à leur nom (recherche GeckoTerminal sur
Solana, BSC et Base) et leur prix jour par jour, de J−30 à J+7 (J = le jour de l'événement). On mesure :
  · quand ils atteignent leur plus haut (avant ou après l'événement) ;
  · ce qu'aurait donné un achat à J−30, J−14, J−7, J−3 ou J−1, revendu la veille, le jour J ou après ;
  · avec trois façons de choisir : tous les tokens achetables, le plus gros (volume) au moment d'acheter, les 3 plus gros.
« Achetable » = au moins 10 k$ échangés ce jour-là. Plus d'échange pendant 3 jours = token mort (−100 %).
Frais Fomo comptés : 6 % l'aller-retour (petite mise).
Limite : la recherche montre surtout les tokens encore connus aujourd'hui (les morts oubliés manquent),
ce qui rend le résultat plutôt trop beau. Données publiques GeckoTerminal, aucune clé."""
import json
import re
import statistics
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

sys.stdout.reconfigure(line_buffering=True)              # afficher au fur et à mesure (étude longue)
CACHE = Path("/tmp/cache_gt_evenements.json")            # réponses gardées entre deux lancements
try:
    _rep = json.loads(CACHE.read_text())
except (OSError, ValueError):
    _rep = {}
DEBUT, BUDGET = time.time(), 22 * 60                     # au-delà, on s'arrête et on résume ce qu'on a
stats_appels = {"ok": 0, "429": 0, "autre": 0, "cache": 0}

GT = "https://api.geckoterminal.com/api/v2"
H = {"Accept": "application/json;version=20230302", "User-Agent": "Mozilla/5.0 alertes-crypto/1.0"}
RESEAUX = ("solana", "bsc", "base")
COUT = 0.06
VOL_MIN = 10_000
MAX_TOKENS = 15
ENTREES = (-30, -14, -7, -3, -1)
SORTIES = (-1, 0, 1, 3)
EVENEMENTS = [
    ("Investiture de Trump", "2025-01-20", ["inauguration"]),
    ("Saint-Valentin 2025", "2025-02-14", ["valentine"]),
    ("GTA 6 bande-annonce 2", "2025-05-06", ["gta6", "gtavi"]),
    ("Élection du pape", "2025-05-08", ["conclave", "pope"]),
    ("Halloween 2025", "2025-10-31", ["halloween", "pumpkin"]),
    ("Thanksgiving 2025", "2025-11-27", ["thanksgiving"]),
    ("Noël 2025", "2025-12-25", ["christmas", "xmas"]),
    ("Super Bowl LX", "2026-02-08", ["superbowl"]),
    ("Saint-Valentin 2026", "2026-02-14", ["valentine"]),
    ("Coupe du monde : ouverture", "2026-06-11", ["worldcup", "wc2026", "fifa"]),
    ("Coupe du monde : finale", "2026-07-19", ["worldcup", "wc2026", "fifa"]),
    ("Halloween 2026", "2026-10-31", ["halloween", "pumpkin"]),
    ("Élections de mi-mandat 2026", "2026-11-03", ["midterm"]),
]
_dernier = [0.0]


def gt(chemin, **params):
    cle = chemin + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    if cle in _rep:
        stats_appels["cache"] += 1
        return _rep[cle]
    if time.time() - DEBUT > BUDGET:
        return None                                      # plus le temps : on garde pour le prochain lancement
    for essai in range(3):
        attente = 2.2 - (time.time() - _dernier[0])      # 30 appels par minute au plus
        if attente > 0:
            time.sleep(attente)
        _dernier[0] = time.time()
        try:
            r = requests.get(GT + chemin, params=params, headers=H, timeout=30)
            if r.status_code == 429:
                stats_appels["429"] += 1
                time.sleep(15)
                continue
            if not r.ok:
                stats_appels["autre"] += 1
                if stats_appels["autre"] <= 3:
                    print(f"   (GeckoTerminal {r.status_code} sur {chemin[:60]})")
                return {}
            d = r.json()
            stats_appels["ok"] += 1
            _rep[cle] = d
            if stats_appels["ok"] % 20 == 0:
                CACHE.write_text(json.dumps(_rep))
            return d
        except (requests.RequestException, ValueError):
            time.sleep(5)
    return {}


def norm(x):
    return re.sub(r"[^a-z0-9]", "", str(x or "").lower())


_cache = {}


def chercher(mot):
    """Pools dont le token de base porte le mot-clé : {(réseau, adresse token): (pool, symbole, créé)}."""
    if mot in _cache:
        return _cache[mot]
    trouves = {}
    for res in RESEAUX:
        d = gt("/search/pools", query=mot, network=res, include="base_token") or {}
        noms = {x["id"]: (x.get("attributes") or {}) for x in d.get("included") or []}
        for p in d.get("data") or []:
            a = p.get("attributes") or {}
            bt = ((p.get("relationships") or {}).get("base_token") or {}).get("data") or {}
            info = noms.get(bt.get("id"), {})
            sym = info.get("symbol") or (a.get("name") or "").split(" / ")[0]
            if mot not in norm(sym) and mot not in norm(info.get("name")):
                continue
            cle = (res, bt.get("id", "").split("_", 1)[-1])
            if cle not in trouves:
                trouves[cle] = (a.get("address"), sym, a.get("pool_created_at"))
    _cache[mot] = trouves
    return trouves


def bougies(res, pool, j0):
    """{jour relatif: (clôture, volume $)} de J−35 à J+8."""
    d = gt(f"/networks/{res}/pools/{pool}/ohlcv/day", before_timestamp=int(j0 + 9 * 86400), limit=45, currency="usd")
    if d is None:
        return None
    out = {}
    for ts, o, h, l, c, vol in ((d.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []:
        j = round((ts - j0) / 86400)
        if -35 <= j <= 8 and c:
            out[j] = (float(c), float(vol or 0))
    return out


def prix_a(b, j, vivant_avant=None):
    """Clôture au jour j ; s'il n'y a pas eu d'échange ce jour-là, la dernière d'avant (≤ 3 jours), sinon mort."""
    for k in range(j, j - 4, -1):
        if k in b:
            return b[k][0]
    return 0.0 if any(k < j for k in b) else None


resume = {}                                              # (règle, entrée, sortie) -> [moyenne par événement]
pics = []
for nom, jour, mots in EVENEMENTS:
    j0 = datetime.combine(date.fromisoformat(jour), datetime.min.time(), tzinfo=timezone.utc).timestamp()
    toks = {}
    for m in mots:
        toks.update(chercher(m))
    candidats = []
    for (res, adr), (pool, sym, cree) in toks.items():
        try:
            cree_ts = datetime.fromisoformat(str(cree).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if cree_ts > j0 + 86400 or cree_ts < j0 - 540 * 86400:   # né après, ou bien trop tôt (token générique)
            continue
        candidats.append((cree_ts, res, adr, pool, sym))   # gardés dans l'ordre de la recherche (les plus connus d'abord)
    series = []
    for cree_ts, res, adr, pool, sym in candidats[:25]:
        if len(series) >= MAX_TOKENS:
            break
        b = bougies(res, pool, j0)
        if b is None:
            print("   … temps écoulé, la suite au prochain lancement")
            break
        if not b or max(v for _, v in b.values()) < VOL_MIN:
            continue                                     # jamais vraiment échangé autour de l'événement
        series.append((sym, res, b))
    print(f"\n=== {nom} ({jour}) · {len(toks)} token(s) trouvé(s), {len(candidats)} nés avant, "
          f"{len(series)} vraiment échangés autour de l'événement")
    if not series:
        continue
    for sym, res, b in series:
        jours = [j for j in b if -30 <= j <= 7]
        if not jours:
            continue
        jp = max(jours, key=lambda j: b[j][0])
        debut = min(jours)
        pics.append(jp)
        fin = prix_a(b, 7)
        print(f"   ${str(sym)[:12]:12} {res:6} · premier échange J{debut:+d} · plus haut à J{jp:+d} "
              f"(x{b[jp][0] / b[debut][0]:.1f} depuis J{debut:+d}) · J+7 : "
              + (f"x{fin / b[jp][0]:.2f} du plus haut" if fin else "mort"))
    for e in ENTREES:
        achetables = [(sym, b) for sym, res, b in series if e in b and b[e][1] >= VOL_MIN]
        if not achetables:
            continue
        par_vol = sorted(achetables, key=lambda x: -x[1][e][1])
        for regle, choix in (("tous", achetables), ("le plus gros", par_vol[:1]), ("les 3 plus gros", par_vol[:3])):
            for s in SORTIES:
                if s <= e:
                    continue
                r = []
                for sym, b in choix:
                    p = prix_a(b, s)
                    r.append((p / b[e][0] - 1) if p is not None else -1.0)
                resume.setdefault((regle, e, s), []).append((nom, sum(r) / len(r) - COUT, len(r)))
        r1 = [(prix_a(b, 0) or 0) / b[e][0] - 1 - COUT for _, b in achetables]
        print(f"   achat à J{e:+d} ({len(achetables)} achetable(s)), revente le jour J : moyenne {statistics.mean(r1) * 100:+.0f} %, "
              f"médiane {statistics.median(r1) * 100:+.0f} %, gagnants {sum(x > 0 for x in r1)}/{len(r1)} · le plus gros "
              f"(${str(par_vol[0][0])[:10]}) {((prix_a(par_vol[0][1], 0) or 0) / par_vol[0][1][e][0] - 1 - COUT) * 100:+.0f} %")

try:
    CACHE.write_text(json.dumps(_rep))
except OSError:
    pass
print(f"\nAppels GeckoTerminal : {stats_appels} · {time.time() - DEBUT:.0f} s")
if pics:
    print(f"\nJour du plus haut (tous tokens confondus, {len(pics)}) : médiane J{statistics.median(pics):+.0f} · "
          f"avant J−7 : {sum(p < -7 for p in pics)} · de J−7 à la veille : {sum(-7 <= p < 0 for p in pics)} · "
          f"le jour J ou après : {sum(p >= 0 for p in pics)}")
print("\nRésumé, frais Fomo compris (chaque événement compte pour un, moyenne des événements) :")
for regle in ("tous", "le plus gros", "les 3 plus gros"):
    for e in ENTREES:
        for s in SORTIES:
            g = resume.get((regle, e, s))
            if not g or s <= e:
                continue
            m = [x[1] for x in g]
            print(f"   {regle:15} achat J{e:+3d} → vente J{s:+d} : {len(g):2} événements · moyenne {statistics.mean(m) * 100:+6.0f} % · "
                  f"médiane {statistics.median(m) * 100:+5.0f} % · gagnant sur {sum(x > 0 for x in m)}/{len(m)}")
