"""
Alertes en temps réel sur Telegram :
  🚨 classique  : token jeune (2-12 h) qui décolle avec de vrais acheteurs
  🌱 survivant  : token de 12 h à 7 jours qui a tenu un plancher et repart (suivi.py)
  🐋 smart wallets : plusieurs wallets gagnants achètent le même token (portefeuilles.py,
                    en mode observation au départ)
  🧩 narratif   : nom cloné en masse, on signale le leader (avec son identité 🪪 et un plan 🎯)
  📊 bilan quotidien à 9 h : ce que sont devenues toutes les alertes
Toutes les alertes passent par la sécurité (RugCheck / GoPlus) et le filtre dev (devs.py).

  python alertes.py loop   -> tourne ~52 min, vérifie toutes les ~4 min (lancé chaque heure)
  python alertes.py once   -> une seule vérification (pour tester)
  python alertes.py test   -> envoie juste un message de test sur Telegram
  python alertes.py bilan  -> envoie le bilan tout de suite

Variables d'environnement : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Gratuit : DexScreener, GeckoTerminal, RugCheck, GoPlus. Pas de X ni de Claude ici.
"""
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

import baleines
import devs
import evenements
import outils as v  # briques communes : API gratuites, wash trading, GoPlus
import portefeuilles
import positions
import suivi

for _k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
    if os.getenv(_k):
        os.environ[_k] = os.environ[_k].strip()

# ---------------------------------------------------------------- Réglages (prudents)
CYCLE_MIN = 4                 # une vérification toutes les ~4 minutes
LOOP_MIN = 52                 # durée d'une exécution (relancée chaque heure par GitHub)
AGE_MIN_H, AGE_MAX_H = 2, 12  # le token doit avoir survécu 2 h, mais avoir moins de 12 h
MCAP_MIN, MCAP_MAX = 100_000, 5_000_000
LIQ_MIN = 30_000
VOL_1H_MIN = 30_000
HAUSSE_1H_MIN = 25            # % de hausse sur 1 h…
HAUSSE_1H_MAX = 150           # …mais pas plus : au-delà, le pump est déjà fait (ou fabriqué)
HAUSSE_SUIVI_MIN = 40         # …ou % de hausse du mcap sur les 30-60 dernières minutes…
HAUSSE_1H_SI_SUIVI = 10       # …à condition que le prix monte encore sur 1 h (pas essoufflé)
CHUTE_5M_MAX = -10            # si le prix chute de plus de 10 % sur 5 min : pas d'alerte
ACHETEURS_1H_MIN = 150        # acheteurs uniques sur 1 h
RATIO_ACHETEURS_MIN = 1.2     # acheteurs uniques / vendeurs uniques
LP_VERROUILLEE_MIN = 80       # Solana : % de liquidité verrouillée/brûlée minimum
TAXE_VENTE_MAX = 10           # Base/BNB : taxe de vente max (%)
TOP10_MAX = 35                # Base/BNB : % max détenu par les 10 plus gros wallets
MAX_ALERTES_HEURE = 6         # au-delà : on n'en envoie plus (évite le spam)
REALERTE_H = 24               # pas deux alertes pour le même token en 24 h

# --- Narratifs : plusieurs tokens du même nom lancés en peu de temps
NARR_FENETRE_H = 3            # on compte les tokens lancés dans les 3 dernières heures
NARR_MIN_CLONES = 5           # au moins 5 tokens du même nom = un vrai narratif
NARR_LEADER_LIQ_MIN = 20_000  # le leader doit avoir au moins 20 k$ de liquidité…
NARR_LEADER_VOL_MIN = 20_000  # …et 20 k$ de volume sur 1 h
NARR_ECART_MIN = 2            # volume du leader ≥ 2x celui du n°2 (le marché a choisi)
NARR_HAUSSE_MAX = 300         # leader déjà à plus de +300 % sur 1 h : trop tard
NARR_ACHETEURS_MIN = 100      # acheteurs uniques du leader sur 1 h
NARR_REALERTE_H = 12          # pas deux alertes pour le même narratif en 12 h
NARR_AGE_MAX_H = 72           # au-delà de 3 jours, un token ne peut pas être le leader d'un narratif
NARR_CHUTE_1H_MAX = -10       # leader en baisse de plus de 10 % sur 1 h : pas d'alerte
# Avant la foule : sur les 7 premiers narratifs, les 2 qui ont doublé (SEALS x10, COWE x2,3)
# avaient 354 et 768 acheteurs/h et 26-42 k$ de volume à l'alerte ; les 5 morts en avaient
# 1 400 à 3 100 et 170-590 k$ : la foule était déjà là, c'était le sommet.
NARR_ACHETEURS_MAX = 1200     # au-delà : narratif saturé -> pas envoyé (gardé pour le bilan)
NARR_VOL_1H_MAX = 150_000     # idem pour le volume du leader sur 1 h
NARR_ETOILE_ECART = 5         # ⭐ profil SEALS : leader écrasant (≥ 5x le volume du n°2)…
NARR_ETOILE_AGE_H = 1.5       # …et qui a déjà survécu 1 h 30 (SEALS : x25 et 2,1 h)
CLASSIQUES_EN_DIRECT = False  # 19/10 : -28 % simulés sur 7 j -> enregistrées pour le bilan seulement
X_ABERRANT = 50               # au-delà de x50 en 7 jours, une alerte est sortie des totaux (à vérifier)
MOMENTUM_EN_DIRECT = True     # 19/10 : seule catégorie gagnante (+10 % hors meilleur coup) -> envoyé
ETOILE_LIQ_PCT = 20             # 21/10 : momentum avec liquidité ≥ 20 % de la mcap = +74 % (+38 % sans
                                # le meilleur) sur le 19-21/10 -> catégorie ⭐ à part, jugée sur la suite
NARRATIFS_EN_DIRECT = True    # False : enregistrés pour le bilan seulement (1 sur 5 au 13/10 : SEALS x10)

# --- Survivants (les critères de forme sont dans suivi.py)
SURV_ACHETEURS_1H_MIN = 30    # acheteurs uniques sur 1 h
SURV_ACHETEURS_24H_MIN = 300  # acheteurs uniques sur 24 h
SURV_REALERTE_H = 48

BILAN_HEURE_UTC = 7           # bilan quotidien vers 9 h (heure d'été) / 8 h (heure d'hiver)
# noms trop génériques (clonés en permanence, ce n'est pas un narratif)
NOMS_GENERIQUES = {"sol", "solana", "pepe", "doge", "trump", "cat", "dog", "inu", "elon",
                   "moon", "baby", "bonk", "wif", "usdc", "usdt", "eth", "weth", "bnb", "wbnb",
                   "btc", "test", "meme", "coin", "token", "pump", "fun", "the", "ai"}

STATE_FILE = Path("alertes/etat.json")


# ---------------------------------------------------------------- Telegram
def telegram(text):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[warn] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquants :\n" + text)
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True})
        if r.status_code != 200:
            print(f"[warn] Telegram {r.status_code} : {r.text[:200]}")
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"[warn] Telegram -> {e}")
        return False


# ---------------------------------------------------------------- État (entre exécutions)
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"watch": {}, "alerted": {}, "alerts": [], "rejected": {}, "names": {}, "narr_alerted": {},
            "surv_alerted": {}}


def save_state(st):
    now = time.time()
    st["watch"] = {k: w for k, w in st["watch"].items()
                   if now - w.get("created", now) < AGE_MAX_H * 3600 + 3600}
    st["alerted"] = {k: ts for k, ts in st["alerted"].items() if now - ts < 7 * 86400}
    st["rejected"] = {k: ts for k, ts in st.get("rejected", {}).items() if now - ts < 3600}
    st["names"] = {k: n for k, n in st.get("names", {}).items()
                   if now - n["created"] < NARR_FENETRE_H * 3600 * 2}
    st["narr_alerted"] = {k: ts for k, ts in st.get("narr_alerted", {}).items()
                          if now - ts < NARR_REALERTE_H * 3600}
    st["surv_alerted"] = {k: ts for k, ts in st.get("surv_alerted", {}).items()
                          if now - ts < SURV_REALERTE_H * 3600}
    st["alerts"] = [a for a in st["alerts"] if now - a["ts"] < 30 * 86400]
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(st))


# ---------------------------------------------------------------- Candidats
def fresh_candidates():
    """Nouveaux pools + tendances GeckoTerminal, et nouveautés DexScreener."""
    cands = {}

    def add(chain, addr, tag):
        if chain in v.CHAINES and addr:
            c = cands.setdefault(v.key_of(chain, addr),
                                 {"chain": chain, "address": addr, "sources": [], "boost": 0})
            if tag not in c["sources"]:
                c["sources"].append(tag)

    v.detecter_reseaux_gt()
    for chain, net in list(v.GT_NETWORKS.items()):
        for kind, tag in (("new_pools", "nouveau_gecko"), ("trending_pools", "tendance_gecko")):
            data = v.gt_get(f"/networks/{net}/{kind}") or {}
            for pool in data.get("data") or []:
                tok = (((pool.get("relationships") or {}).get("base_token") or {})
                       .get("data") or {}).get("id") or ""
                if "_" in tok:
                    add(chain, tok.split("_", 1)[1], tag)
    for tag, path in (("nouveau_profil", "/token-profiles/latest/v1"),
                      ("community_takeover", "/community-takeovers/latest/v1"),
                      ("new_boosts", "/token-boosts/latest/v1")):
        data = v.get_json(v.DS + path) or []
        if isinstance(data, dict):
            data = data.get("data") or [data]
        for item in data:
            add(item.get("chainId"), item.get("tokenAddress"), tag)
    return cands


SITES_PAS_SITES = ("x.com", "twitter.com", "4plebs", "4chan", "t.me", "instagram", "tiktok",
                   "reddit", "youtube", "youtu.be", "facebook", "pump.fun", "dexscreener")


def identite(t):
    """Le token a-t-il sa propre identité (compte X à son nom, site), ou renvoie-t-il juste au
    tweet de quelqu'un d'autre ? Renvoie (code, texte). Codes : dediee, communaute, tweet, aucune.
    Constat au 13/10 : les 4 narratifs « de tweet » (DOPE, CAESAR, Gem, Isabella) sont tous morts ;
    parmi les 2 avec compte X à leur nom + site, SEALS a fait x10 mais nonce est mort aussi.
    C'est une info à lire, pas un filtre."""
    mots = {norm_nom(t["symbol"])} | {norm_nom(w) for w in re.split(r"[\s_\-]+", t.get("name") or "")}
    mots = {m for m in mots if len(m) >= 3}
    compte = communaute = tiers = None
    for s in t.get("socials") or []:
        url = s.get("url") or ""
        if (s.get("type") or s.get("platform")) not in ("twitter", "x") \
                and "x.com/" not in url and "twitter.com/" not in url:
            continue
        if "/i/communities/" in url:
            communaute = True
            continue
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)", url)
        if not m:
            continue
        handle = m.group(1)
        if any(w in handle.lower() for w in mots):
            compte = handle
        elif "/status/" in url:
            tiers = handle
        else:
            compte = compte or handle
    site = any(w and not any(d in w.lower() for d in SITES_PAS_SITES) for w in t.get("websites") or [])
    if compte:
        return "dediee", f"compte X à son nom (@{compte})" + (" + site web" if site else "")
    if site or communaute:
        return "communaute", " + ".join(x for x in ("site web" if site else "",
                                                    "communauté X" if communaute else "") if x)
    if tiers:
        return "tweet", f"⚠️ renvoie juste au tweet de @{tiers} (token « de tweet », souvent éphémère)"
    return "aucune", "⚠️ aucun réseau social"


MOTS_CAUSE_SITE = ("fundrais", "donat", "donor", "giving", "charit", "stichting", "foundation", "fondation",
                   "nonprofit", "non-profit", "gofundme", "justgiving", "every.org", "rescue", "sanctuary",
                   "hospital", "zoo", "shelter")
MOTS_CAUSE_NOM = ("save the", "save ", "charity", "donat", "for kids", "foundation", "rescue")


def caritatif(t):
    """Token lancé pour une cause (Pump.fun propose des « Charity Coins » qui reversent les frais
    du créateur à une association vérifiée). Ex. : SEALS (x22) avait pour site une page de collecte
    d'un centre de soins des phoques. Renvoie un texte, ou "" si rien de tel n'est repéré."""
    nom = f"{t.get('name') or ''} ".lower()
    sites = [w for w in t.get("websites") or [] if w]
    site = next((w for w in sites if any(m in w.lower() for m in MOTS_CAUSE_SITE)), None)
    if site:
        dom = re.sub(r"^https?://(www\.)?", "", site).split("/")[0]
        return f"🎗️ token pour une cause : site de collecte / association ({dom})"
    if any(m in nom for m in MOTS_CAUSE_NOM):
        return "🎗️ le nom évoque une cause (« " + (t.get("name") or "")[:30] + " ») : à vérifier"
    return ""


def norm_nom(sym):
    """« $Altia! » -> « altia » (garde les lettres de toutes les langues)."""
    return "".join(ch for ch in (sym or "").lower() if ch.isalnum())


def meme_nom(nom, symbole, deja):
    """Tous les tokens de ce nom connus de DexScreener, y compris les plus anciens que la fenêtre
    de 3 h. Leçon du 11/10 : le vrai DOPE avait gradué 3 h avant l'alerte (puis a fait 4 M$) et
    le bot, qui ne regardait que les 3 dernières heures, avait désigné un clone de 30 min (mort)."""
    d = v.get_json(f"{v.DS}/latest/dex/search", params={"q": symbole}) or {}
    best = {}
    for p in d.get("pairs") or []:
        base = p.get("baseToken") or {}
        if (p.get("chainId") not in v.GT_NETWORKS or p.get("chainId") in v.CHAINES_OBS
                or norm_nom(base.get("symbol")) != nom
                or not p.get("priceUsd")):
            continue
        k = v.key_of(p["chainId"], base.get("address", ""))
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if k not in deja and (k not in best or liq > best[k][0]):
            best[k] = (liq, p)
    return [v.depuis_paire(p, {"sources": ["narratif"], "boost": 0}) for _, p in best.values()]


def narratifs(st, tokens, sent_this_hour, sv):
    """Repère les noms clonés en masse et signale le token que le marché a choisi."""
    now = time.time()
    names = st.setdefault("names", {})
    for t in tokens:  # on mémorise le nom de tous les tokens jeunes vus passer
        if t["age_h"] <= NARR_FENETRE_H * 2 and t["chain"] not in v.CHAINES_OBS:
            names[t["key"]] = {"nom": norm_nom(t["symbol"]), "symbol": t["symbol"],
                               "chain": t["chain"], "address": t["address"],
                               "created": now - t["age_h"] * 3600}
    groupes = {}
    for k, n in names.items():
        if (now - n["created"] <= NARR_FENETRE_H * 3600 and len(n["nom"]) >= 3
                and not n["nom"].isdigit() and n["nom"] not in NOMS_GENERIQUES):
            groupes.setdefault(n["nom"], []).append(k)
    gros = sorted(((nom, ks) for nom, ks in groupes.items()
                   if len(ks) >= NARR_MIN_CLONES
                   and nom not in st.setdefault("narr_alerted", {})),
                  key=lambda x: len(x[1]), reverse=True)[:3]
    by_key = {t["key"]: t for t in tokens}
    nb = 0
    for nom, ks in gros:
        manquants = {k: {"chain": names[k]["chain"], "address": names[k]["address"],
                         "sources": ["narratif"], "boost": 0}
                     for k in ks[:40] if k not in by_key}
        for t in v.enrich(manquants) if manquants else []:
            by_key[t["key"]] = t
        membres = sorted((by_key[k] for k in ks if k in by_key),
                         key=lambda t: t["vol_1h"], reverse=True)
        if not membres:
            continue
        membres = sorted(membres + meme_nom(nom, membres[0]["symbol"], {m["key"] for m in membres}),
                         key=lambda t: t["vol_1h"], reverse=True)
        # un token de plusieurs semaines n'est pas le leader d'un narratif de 3 h (DOTS, 17/10 : 18 jours)
        membres = [m for m in membres if m["age_h"] <= NARR_AGE_MAX_H]
        if not membres:
            continue
        leader = membres[0]
        # un token plus ancien (≥ 1 h d'avance) et au moins aussi liquide : souvent l'original
        ancien = max((m for m in membres if m["age_h"] >= leader["age_h"] + 1 and m["liq"] >= leader["liq"]),
                     key=lambda m: m["mcap"], default=None)
        original = False
        if ancien and ancien["vol_1h"] >= 0.5 * leader["vol_1h"]:
            leader, ancien, original = ancien, None, True   # l'original est encore très actif : c'est lui
        second_vol = max((m["vol_1h"] for m in membres if m is not leader), default=0)
        if original:
            second_vol = min(second_vol, leader["vol_1h"] / NARR_ECART_MIN)  # pas d'exigence d'écart
        if not (leader["liq"] >= NARR_LEADER_LIQ_MIN and leader["vol_1h"] >= NARR_LEADER_VOL_MIN
                and NARR_CHUTE_1H_MAX < leader["chg_1h"] <= NARR_HAUSSE_MAX
                and leader.get("chg_5m", 0) > CHUTE_5M_MAX
                and leader["vol_1h"] >= NARR_ECART_MIN * max(second_vol, 1)):
            print(f"narratif « {nom} » ({len(ks)} tokens) : pas de leader net pour l'instant")
            continue
        v.add_traders([leader])
        v.flag_wash(leader)
        b, sl = leader.get("acheteurs_uniques_1h"), leader.get("vendeurs_uniques_1h")
        if leader.get("alerte_wash_trading") or b is None or b < NARR_ACHETEURS_MIN or b < (sl or 0):
            print(f"narratif « {nom} » : leader ${leader['symbol']} écarté (acheteurs/wash)")
            continue
        ok, sec_txt = securite(leader)
        if not ok:
            print(f"narratif « {nom} » : leader écarté : {sec_txt}")
            st["narr_alerted"][nom] = now  # on ne réessaie pas avant 12 h
            continue
        if NARRATIFS_EN_DIRECT and sent_this_hour[0] >= MAX_ALERTES_HEURE:
            continue
        id_code, id_txt = identite(leader)
        cause_txt = caritatif(leader)
        fort, force_txt = suivi.force_relative(sv, leader)
        dominance = leader["vol_1h"] / second_vol if second_vol else 99
        # « saturé » ne concerne que les leaders tout jeunes : un original qui a déjà tenu 2 h et plus
        # avec beaucoup d'acheteurs, c'est le profil DOPE (x10 ensuite), pas un sommet de hype
        sature = (leader["age_h"] < 2
                  and (b > NARR_ACHETEURS_MAX or leader["vol_1h"] > NARR_VOL_1H_MAX))
        etoile = dominance >= NARR_ETOILE_ECART and leader["age_h"] >= NARR_ETOILE_AGE_H
        chaines = {}
        for k in ks:
            chaines[names[k]["chain"]] = chaines.get(names[k]["chain"], 0) + 1
        ecart = (f"×{leader['vol_1h'] / second_vol:.0f} le volume du n°2" if second_vol
                 else "seul à avoir du volume")
        autres = " · ".join(f"{m['chain']} {fmt_usd(m['vol_1h'])}" for m in [m for m in membres if m is not leader][:3])
        lignes = [
            f"🧩 <b>Narratif détecté : « {leader['symbol']} »</b> — {len(ks)} tokens de ce nom "
            f"lancés en {NARR_FENETRE_H} h ({', '.join(f'{c} {n}' for c, n in chaines.items())})",
            f"👑 Leader : <b>${leader['symbol']}</b> ({leader['chain']}) — {leader['age_h']:.1f} h, "
            f"mcap {fmt_usd(leader['mcap'])} · liq {fmt_usd(leader['liq'])}",
            f"📊 vol 1 h {fmt_usd(leader['vol_1h'])} ({ecart}) · prix {leader['chg_1h']:+.0f} % sur 1 h, "
            f"{leader.get('chg_5m', 0):+.0f} % sur 5 min",
            f"👥 {b} acheteurs uniques / {sl} vendeurs sur 1 h" + (
                "" if original else " : la foule n'est pas encore là"),
            f"👴 C'est l'original : lancé {leader['age_h']:.1f} h avant, les clones essaient de copier son "
            f"succès" if original else "",
            f"⚠️ Il existe un ${ancien['symbol']} plus ancien et plus gros ({ancien['chain']}, mcap "
            f"{fmt_usd(ancien['mcap'])}, liq {fmt_usd(ancien['liq'])}, {ancien['age_h']:.0f} h, adresse "
            f"…<code>{ancien['address'][-6:]}</code>) : le leader ci-dessous est peut-être un clone"
            if ancien else "",
            f"⭐ Profil SEALS : leader écrasant (×{min(dominance, 99):.0f} le n°2) et déjà "
            f"{leader['age_h']:.1f} h de survie" if etoile else "",
            f"🪪 {id_txt}",
            cause_txt,
            force_txt,
            f"🛡️ {sec_txt}",
            f"Suivants (volume 1 h) : {autres}" if autres else "",
            f"🎯 Plan : la moitié à x2 (mcap {fmt_usd(leader['mcap'] * 2)}) ; si ça tombe à −50 % "
            f"(mcap {fmt_usd(leader['mcap'] / 2)}), coupe. Les narratifs sont une loterie : le "
            f"gagnant ne paie les perdants que si on coupe vite.",
            f"⚠️ Plusieurs tokens portent ce nom : sur Fomo, vérifie que l'adresse se termine par "
            f"<code>{leader['address'][-6:]}</code>",
            f"<a href=\"{leader['dexscreener']}\">Voir le leader sur DexScreener</a>",
            "<i>Signal automatique, pas un conseil. Petite mise seulement.</i>",
        ]
        if not NARRATIFS_EN_DIRECT or sature:  # observation : on garde la trace pour le bilan
            print(f"narratif « {nom} » : leader ${leader['symbol']} non envoyé "
                  f"({'saturé : ' + str(b) + ' acheteurs/h' if sature else 'observation'})")
            st["narr_alerted"][nom] = now
            st["alerts"].append({"ts": now, "type": "narratif", "observation": True, "nom": nom,
                                 "key": leader["key"], "symbol": leader["symbol"],
                                 "chain": leader["chain"], "address": leader["address"],
                                 "price": leader["price"], "mcap": leader["mcap"],
                                 "url": leader["dexscreener"], "clones": len(ks),
                                 "identite": id_code, "sature": sature, "etoile": etoile,
                                 "fort": fort, "cause": bool(cause_txt), "original": original})
            suivi.ajouter(sv, leader, garder=True)
            continue
        if telegram("\n".join(x for x in lignes if x)):
            sent_this_hour[0] += 1
            nb += 1
            st["narr_alerted"][nom] = now
            st["alerted"][leader["key"]] = now
            st["alerts"].append({"ts": now, "type": "narratif", "nom": nom, "key": leader["key"],
                                 "symbol": leader["symbol"], "chain": leader["chain"],
                                 "address": leader["address"], "price": leader["price"],
                                 "mcap": leader["mcap"], "url": leader["dexscreener"],
                                 "clones": len(ks), "identite": id_code, "etoile": etoile,
                                 "fort": fort, "cause": bool(cause_txt), "original": original})
            suivi.ajouter(sv, leader, garder=True)
    return nb


def cheap_filter(t):
    """Filtre gratuit et rapide (données DexScreener uniquement)."""
    return (t["chain"] not in v.CHAINES_OBS and AGE_MIN_H <= t["age_h"] <= AGE_MAX_H
            and MCAP_MIN <= t["mcap"] <= MCAP_MAX
            and t["liq"] >= LIQ_MIN and t["vol_1h"] >= VOL_1H_MIN
            and t["chg_1h"] <= HAUSSE_1H_MAX)


# ---------------------------------------------------------------- Sécurité
def securite(t):
    """Renvoie (ok, résumé lisible)."""
    if t["chain"] == "solana":
        r = devs.rugcheck(t["address"])
        if r is None:  # rapport complet indisponible : on se rabat sur le résumé
            d = v.get_json(f"https://api.rugcheck.xyz/v1/tokens/{t['address']}/report/summary")
            if not d:
                return False, "RugCheck indisponible"
            r = {"dangers": [x.get("name") for x in d.get("risks") or [] if x.get("level") == "danger"],
                 "warns": [x.get("name") for x in d.get("risks") or [] if x.get("level") == "warn"],
                 "lp": d.get("lpLockedPct"), "rugged": False, "createur": None,
                 "dev_pct": None, "inities_pct": None, "nb_tokens_dev": None, "reseaux_inities": 0}
        lp = r["lp"]
        if r["rugged"]:
            return False, "RugCheck : token marqué « rugged »"
        if r["dangers"]:
            return False, "RugCheck : " + ", ".join(r["dangers"][:3])
        if lp is not None and float(lp) < LP_VERROUILLEE_MIN:
            return False, f"liquidité verrouillée à {float(lp):.0f} % seulement"
        ok_dev, dev_txt = devs.verdict(t, r["createur"], r["dev_pct"], r["inities_pct"],
                                       r["nb_tokens_dev"])
        if not ok_dev:
            return False, dev_txt
        t["createur"] = r["createur"]
        lp_txt = f", liquidité verrouillée {float(lp):.0f} %" if lp is not None else ""
        warn_txt = f" (à noter : {', '.join(r['warns'][:2])})" if r["warns"] else ""
        return True, f"RugCheck sans danger{lp_txt}{warn_txt}\n👤 {dev_txt}"
    v.goplus([t])
    sec = t.get("securite_evm")
    if not sec:
        return False, "GoPlus indisponible"
    graves = [r for r in sec["risques"] if any(m in r for m in
              ("honeypot", "impossible", "modifier les soldes", "caché"))]
    if graves:
        return False, "GoPlus : " + ", ".join(graves)
    if (sec.get("lp_retirable_pct") or 0) >= 50:
        return False, (f"{sec['lp_retirable_pct']:.0f} % de la liquidité chez le créateur ou un wallet, "
                       "non verrouillée : il peut la retirer d'un coup")
    # données manquantes = token pas encore analysé par GoPlus : on refuse (inconnu ≠ sûr)
    if sec.get("taxe_vente_pct") is None or sec.get("taxe_achat_pct") is None:
        return False, "GoPlus : taxes inconnues (token pas encore analysé)"
    if sec.get("top10_detenteurs_pct") is None:
        return False, "GoPlus : répartition des détenteurs inconnue"
    if sec["top10_detenteurs_pct"] > TOP10_MAX:
        return False, f"top 10 détenteurs {sec['top10_detenteurs_pct']} % (trop concentré)"
    if sec["taxe_vente_pct"] > TAXE_VENTE_MAX:
        return False, f"taxe de vente {sec['taxe_vente_pct']} %"
    ok_dev, dev_txt = devs.verdict(t, sec.get("createur"), sec.get("createur_detient_pct"))
    if not ok_dev:
        return False, dev_txt
    t["createur"] = sec.get("createur")
    parts = [f"taxes {sec.get('taxe_achat_pct')}/{sec.get('taxe_vente_pct')} %"]
    if sec.get("top10_detenteurs_pct") is not None:
        parts.append(f"top 10 détenteurs {sec['top10_detenteurs_pct']} %")
    if sec["risques"]:
        parts.append("à noter : " + ", ".join(sec["risques"][:2]))
    return True, "GoPlus OK, " + ", ".join(parts) + f"\n👤 {dev_txt}"


# ---------------------------------------------------------------- Un cycle
def fmt_usd(x):
    return f"{x / 1e6:.2f} M$" if x >= 1e6 else f"{x / 1e3:.0f} k$"


def cycle(st, sent_this_hour, sv, pf):
    now = time.time()
    cands = fresh_candidates()
    # on ré-observe aussi les tokens jeunes déjà vus (pour mesurer leur accélération)
    for k, w in st["watch"].items():
        if k not in cands:
            cands[k] = {"chain": w["chain"], "address": w["address"], "sources": ["suivi"], "boost": 0}
    tokens = v.enrich(cands)

    # liste de suivi : seulement les tokens jeunes et pas minuscules (sinon elle explose)
    found = {t["key"] for t in tokens}
    for k in [k for k in st["watch"] if k not in found]:
        del st["watch"][k]
    for t in tokens:
        if t["age_h"] > AGE_MAX_H or (t["age_h"] > 1 and t["liq"] < 10_000):
            st["watch"].pop(t["key"], None)
            continue
        w = st["watch"].setdefault(t["key"], {
            "chain": t["chain"], "address": t["address"], "first_seen": now,
            "created": now - t["age_h"] * 3600, "snaps": []})
        w["snaps"] = [x for x in w["snaps"] if now - x["ts"] < 3 * 3600]
        w["snaps"].append({"ts": now, "mcap": t["mcap"], "buyers": None})

    # narratifs d'abord : un leader signalé ne sera pas re-signalé par l'alerte classique
    nb_narr = narratifs(st, tokens, sent_this_hour, sv)
    if nb_narr:
        print(f"{nb_narr} alerte(s) narratif")
    st.setdefault("rejected", {})
    short = [t for t in tokens if cheap_filter(t)
             and now - st["alerted"].get(t["key"], 0) > REALERTE_H * 3600
             and now - st["rejected"].get(t["key"], 0) > 3600]
    v.add_traders(short)
    nb = 0
    for t in short:
        w = st["watch"].get(t["key"]) or {"snaps": [{"ts": now, "mcap": t["mcap"], "buyers": None}]}
        b, s = t.get("acheteurs_uniques_1h"), t.get("vendeurs_uniques_1h")
        w["snaps"][-1]["buyers"] = b
        v.flag_wash(t)
        if b is None or s is None or t.get("alerte_wash_trading"):
            continue
        ratio = b / max(s, 1)
        # accélération : mcap / acheteurs vs une observation d'il y a 30 min à 2 h
        old = [x for x in w["snaps"] if 1800 <= now - x["ts"] <= 3600]
        ref = old[0] if old else None
        old_b = [x for x in old if x.get("buyers")]
        ref_b = old_b[0] if old_b else None
        hausse_suivi = v.pct(t["mcap"], ref["mcap"]) if ref else None
        hausse_ach = v.pct(b, ref_b["buyers"]) if ref_b else None
        monte = (t["chg_1h"] >= HAUSSE_1H_MIN
                 or ((hausse_suivi or 0) >= HAUSSE_SUIVI_MIN and t["chg_1h"] >= HAUSSE_1H_SI_SUIVI))
        if t.get("chg_5m", 0) <= CHUTE_5M_MAX:
            continue  # en train de retomber en ce moment
        if not (monte and b >= ACHETEURS_1H_MIN and ratio >= RATIO_ACHETEURS_MIN):
            continue
        if hausse_ach is not None and hausse_ach < 0:
            continue  # le prix monte mais de moins en moins d'acheteurs : on passe
        ok, sec_txt = securite(t)
        if not ok:
            print(f"écarté {t['symbol']} : {sec_txt}")
            st["rejected"][t["key"]] = now  # on ne revérifie pas avant 1 h
            continue
        if CLASSIQUES_EN_DIRECT and sent_this_hour[0] >= MAX_ALERTES_HEURE:
            print(f"limite d'alertes atteinte, {t['symbol']} non envoyé")
            continue

        fort, force_txt = suivi.force_relative(sv, t)
        stade = ("encore sur pump.fun" if t.get("dex") == "pumpfun"
                 else f"sur {t.get('dex') or '?'}")
        lignes = [
            f"🚨 <b>${t['symbol']}</b> ({t['chain']}) — {t['age_h']:.1f} h, {stade}" + (" 💪" if fort else ""),
            f"mcap {fmt_usd(t['mcap'])} · liq {fmt_usd(t['liq'])} · vol 1 h {fmt_usd(t['vol_1h'])}",
            f"📈 prix {t['chg_1h']:+.0f} % sur 1 h · {t.get('chg_5m', 0):+.0f} % sur 5 min" + (
                f" · mcap {hausse_suivi:+.0f} % depuis {int((now - ref['ts']) / 60)} min" if ref else ""),
            f"👥 {b} acheteurs uniques / {s} vendeurs sur 1 h (×{ratio:.1f})" + (
                f" · acheteurs {hausse_ach:+.0f} % depuis {int((now - ref_b['ts']) / 60)} min"
                if hausse_ach is not None else ""),
            f"🔁 volume/liquidité {t['volume_sur_liquidite']} · "
            f"{t.get('achats_par_acheteur_1h', '?')} achat(s) par acheteur : pas de wash détecté",
            f"🪪 {identite(t)[1]}",
            caritatif(t),
            force_txt,
            f"🛡️ {sec_txt}",
            f"<a href=\"{t['dexscreener']}\">Voir sur DexScreener</a>",
            "<i>Signal automatique, pas un conseil. Petite mise seulement.</i>",
        ]
        envoye = telegram("\n".join(x for x in lignes if x)) if CLASSIQUES_EN_DIRECT else False
        if envoye or not CLASSIQUES_EN_DIRECT:
            if envoye:
                sent_this_hour[0] += 1
            nb += 1
            st["alerted"][t["key"]] = now
            st["alerts"].append({"ts": now, "type": "classique", "observation": not envoye, "key": t["key"],
                                 "symbol": t["symbol"], "chain": t["chain"], "address": t["address"],
                                 "price": t["price"], "mcap": t["mcap"], "url": t["dexscreener"],
                                 "fort": fort, "cause": bool(caritatif(t))})
            suivi.ajouter(sv, t, garder=True)
    print(f"{time.strftime('%H:%M')} : {len(tokens)} tokens observés, "
          f"{len(short)} passent le filtre rapide, {nb} alerte(s)")

    # suivi 7 jours : relevé toutes les 30 min, survivants, bons coups des wallets
    suivi.ajouter_lot(sv, tokens)
    r = suivi.rafraichir(sv, [st["alerts"], pf["signaux"]])
    if r:
        frais, morts, fins = r
        portefeuilles.resoudre(pf, sv)          # avant de retirer les morts (dernier plus haut)
        for k in morts:
            devs.marquer_mort(k)
        suivi.retirer(sv, morts + fins)
        nb_s = alertes_survivants(st, sv, frais, sent_this_hour)
        momentum_observation(st, sv, frais, sent_this_hour)
        n_w, n_smart = portefeuilles.stats(pf)
        print(f"suivi : {len(sv['tokens'])} tokens, {len(morts)} morts, {nb_s} survivant(s) ; "
              f"wallets : {n_w} observés, {n_smart} smart")

    def envoyer(texte):
        if sent_this_hour[0] >= MAX_ALERTES_HEURE:
            return False
        ok = telegram(texte)
        sent_this_hour[0] += 1 if ok else 0
        return ok
    portefeuilles.collecter(pf, sv, securite, envoyer)
    try:
        baleines.surveiller(st, sv, lambda t: suivi.ajouter(sv, t, garder=True), envoyer)
    except Exception as e:                 # une source indisponible ne doit pas bloquer le reste
        print(f"[warn] baleines : {type(e).__name__}")


# ---------------------------------------------------------------- Survivants
def alertes_survivants(st, sv, frais, sent_this_hour):
    now = time.time()
    st.setdefault("surv_alerted", {})
    cands = []
    for t in frais:
        e = sv["tokens"].get(t["key"])
        if (not e or t["chain"] in v.CHAINES_OBS
                or now - st["surv_alerted"].get(t["key"], 0) < SURV_REALERTE_H * 3600
                or now - st.get("rejected", {}).get(t["key"], 0) < 3600):
            continue
        m = suivi.motif_survivant(e, t, now)
        if m:
            cands.append((t, m))
    if not cands:
        return 0
    v.add_traders([t for t, _ in cands])
    nb = 0
    for t, (motif, d) in cands:
        v.flag_wash(t)
        b, s, b24 = (t.get("acheteurs_uniques_1h"), t.get("vendeurs_uniques_1h"),
                     t.get("acheteurs_uniques_24h"))
        if (t.get("alerte_wash_trading") or b is None or b < SURV_ACHETEURS_1H_MIN
                or b < (s or 0) or (b24 or 0) < SURV_ACHETEURS_24H_MIN):
            print(f"survivant {t['symbol']} écarté : acheteurs {b}/{s} (24 h : {b24}) "
                  f"ou wash ({t.get('alerte_wash_trading')})")
            continue
        ok, sec_txt = securite(t)
        if not ok:
            print(f"survivant {t['symbol']} écarté : {sec_txt}")
            st.setdefault("rejected", {})[t["key"]] = now
            continue
        if sent_this_hour[0] >= MAX_ALERTES_HEURE:
            continue
        age = f"{t['age_h']:.0f} h" if t["age_h"] < 48 else f"{t['age_h'] / 24:.1f} jours"
        fort, force_txt = suivi.force_relative(sv, t)
        if motif == "rebond":
            forme = [f"🌱 <b>Survivant : ${t['symbol']}</b> ({t['chain']}) — {age}, rebond sur plancher",
                     f"📉 sommet {fmt_usd(d['sommet_mcap'])} → plancher {fmt_usd(d['plancher_mcap'])} "
                     f"(−{d['correction_pct']} %), tenu depuis {d['plancher_h']:.0f} h",
                     f"📈 rebond +{d['rebond_pct']} % depuis le plancher, casse le haut de sa zone des "
                     f"6 dernières heures"]
            stop = f"🎯 si ça repasse sous le plancher ({fmt_usd(d['plancher_mcap'])}), le scénario est raté"
        else:
            forme = [f"🌱 <b>Survivant : ${t['symbol']}</b> ({t['chain']}) — {age}, montée régulière",
                     f"📈 x{d['x_fenetre']} en {d['fenetre_h']} h, creux et sommets de plus en plus hauts, "
                     f"repli max −{d['repli_max_pct']} %"]
            stop = (f"🎯 si ça repasse sous le dernier creux ({fmt_usd(d['dernier_creux_mcap'])}), "
                    f"la tendance est cassée")
        lignes = forme + [
            f"mcap {fmt_usd(t['mcap'])} · liq {fmt_usd(t['liq'])} (stable sur 12 h) · "
            f"vol 6 h {fmt_usd(t['vol_6h'])}",
            f"prix {t['chg_1h']:+.0f} % sur 1 h · {t['chg_6h']:+.0f} % sur 6 h · {t['chg_24h']:+.0f} % sur 24 h",
            f"👥 {b} acheteurs / {s} vendeurs sur 1 h · {b24} acheteurs uniques sur 24 h · "
            f"achats/ventes 6 h : {t['buys_6h']}/{t['sells_6h']}",
            f"🪪 {identite(t)[1]}",
            caritatif(t),
            force_txt,
            f"🛡️ {sec_txt}",
            stop,
            f"<a href=\"{t['dexscreener']}\">Voir sur DexScreener</a>",
            "<i>Signal automatique, pas un conseil. Petite mise seulement.</i>",
        ]
        if fort:
            lignes[0] += " 💪"
        if telegram("\n".join(x for x in lignes if x)):
            sent_this_hour[0] += 1
            nb += 1
            st["surv_alerted"][t["key"]] = now
            st["alerts"].append({"ts": now, "type": "survivant", "motif": motif, "key": t["key"],
                                 "symbol": t["symbol"], "chain": t["chain"], "address": t["address"],
                                 "price": t["price"], "mcap": t["mcap"], "url": t["dexscreener"],
                                 "fort": fort, "cause": bool(caritatif(t))})
            suivi.ajouter(sv, t, garder=True)
    return nb


# ---------------------------------------------------------------- Momentum (observation)
MOM_MAX_PAR_RELEVE = 5        # au plus 5 nouveaux par relevé (vérification de sécurité incluse)


def momentum_observation(st, sv, frais, sent_this_hour=None):
    """Tokens « momentum confirmé » : envoyés en direct (MOMENTUM_EN_DIRECT, hors Robinhood Chain)
    et toujours enregistrés pour mesurer leur gain simulé."""
    now = time.time()
    vus = st.setdefault("mom_vus", {})
    for k in [k for k, ts in vus.items() if now - ts > 48 * 3600]:
        del vus[k]
    deja = {a["key"] for a in st["alerts"] if now - a["ts"] < 48 * 3600}
    n = 0
    for t in sorted(frais, key=lambda t: -t["vol_1h"]):
        if n >= MOM_MAX_PAR_RELEVE:
            break
        e = sv["tokens"].get(t["key"])
        if not e or t["key"] in vus or t["key"] in deja:
            continue
        m = suivi.motif_momentum(e, t, now)
        if not m:
            continue
        vus[t["key"]] = now
        ok, sec_txt = securite(t)
        sec_inconnue = False
        if not ok and t["chain"] in v.CHAINES_OBS and ("indisponible" in sec_txt or "inconnue" in sec_txt):
            ok, sec_inconnue = True, True      # Robinhood : pas de scanner sûr, on note quand même
        if not ok:
            continue
        n += 1
        envoye = False
        if (MOMENTUM_EN_DIRECT and not sec_inconnue and t["chain"] not in v.CHAINES_OBS
                and (sent_this_hour is None or sent_this_hour[0] < MAX_ALERTES_HEURE)):
            fort, force_txt = suivi.force_relative(sv, t)
            lignes = [
                (f"⭐ <b>Liquidité forte : {m['liq_pct']:.0f} % de la mcap</b> (meilleur filtre du bilan)"
                 if m["liq_pct"] >= ETOILE_LIQ_PCT else ""),
                f"🚀 <b>Momentum confirmé : ${html.escape(str(t['symbol']))}</b> ({t['chain']}) — "
                f"{t['age_h']:.0f} h" + (" 💪" if fort else ""),
                f"mcap {fmt_usd(t['mcap'])} · liq {fmt_usd(t['liq'])} ({m['liq_pct']:.0f} %) · "
                f"vol 1 h {fmt_usd(t['vol_1h'])}",
                f"📈 {t['chg_6h']:+.0f} % sur 6 h · {t['chg_1h']:+.0f} % sur 1 h · "
                f"{m['depuis_haut_pct']:+.0f} % depuis son plus haut",
                f"👥 {t['buys_6h']} achats / {t['sells_6h']} ventes sur 6 h",
                f"🪪 {identite(t)[1]}",
                force_txt,
                f"🛡️ {sec_txt}",
                f"<a href=\"{t['dexscreener']}\">Voir sur DexScreener</a>",
                "<i>Token déjà installé qui continue de monter. Pas un conseil : petite mise, "
                "moitié vendue à x2, coupé à −50 %.</i>",
            ]
            envoye = telegram("\n".join(x for x in lignes if x))
            if envoye and sent_this_hour is not None:
                sent_this_hour[0] += 1
        st["alerts"].append({"ts": now, "type": "momentum", "observation": not envoye, "key": t["key"],
                             "symbol": t["symbol"], "chain": t["chain"], "address": t["address"],
                             "price": t["price"], "mcap": t["mcap"], "url": t["dexscreener"],
                             "fort": suivi.force_relative(sv, t)[0], "cause": bool(caritatif(t)),
                             "securite_inconnue": sec_inconnue, "age_h": round(t["age_h"], 1),
                             "etoile_liq": m["liq_pct"] >= ETOILE_LIQ_PCT, **m})
        suivi.ajouter(sv, t, garder=True)
    if n:
        print(f"momentum : {n} token(s) enregistré(s)" + (" et envoyé(s)" if MOMENTUM_EN_DIRECT else ""))


# ---------------------------------------------------------------- Bilan quotidien
def envoyer_long(texte):
    """Envoie un long message en plusieurs morceaux, coupés entre deux lignes (jamais au milieu
    d'une balise HTML, sinon Telegram refuse tout le message). Repli en texte brut si refusé."""
    morceaux, cour = [], ""
    for ligne in texte.split("\n"):
        if cour and len(cour) + len(ligne) + 1 > 3800:
            morceaux.append(cour)
            cour = ""
        cour = f"{cour}\n{ligne}" if cour else ligne
    if cour:
        morceaux.append(cour)
    ok = True
    for m in morceaux:
        if not telegram(m):
            ok = telegram(re.sub(r"<[^>]+>", "", m)) and ok   # balises en cause : texte brut
    return ok


def bilan_quotidien(st, sv, pf, forcer=False):
    now = time.time()
    jour = time.strftime("%Y-%m-%d", time.gmtime(now))
    # à partir de l'heure prévue, et tant qu'il n'est pas parti aujourd'hui (rattrapage si raté)
    if not forcer and (time.gmtime(now).tm_hour < BILAN_HEURE_UTC or st.get("dernier_bilan") == jour):
        return
    alertes = [a for a in st["alerts"] if now - a["ts"] < 7 * 86400]
    signaux = [s for s in pf["signaux"] if now - s["ts"] < 7 * 86400]
    # alertes faussées par un ancien relevé aberrant (avant le contrôle prix / capitalisation) :
    # on efface leur historique, il est recalculé avec des relevés cohérents
    for a in alertes + signaux:
        if a.get("price") and ((a.get("peak") or 0) / a["price"] > suivi.X_MAX
                               or (a.get("last") and not suivi.releve_coherent(a, a["last"], a.get("last_mcap")))
                               or suivi.resultat_sim(a) > suivi.X_MAX):
            for cle in ("sim", "peak", "last", "last_mcap"):
                a.pop(cle, None)
            print(f"[info] relevé aberrant effacé : {a.get('symbol')}")
    # prix actuel des tokens qui ne sont plus dans le suivi (anciennes alertes)
    manquants = {a["key"]: {"chain": a["chain"], "address": a["address"], "sources": [], "boost": 0}
                 for a in alertes + signaux if a["key"] not in sv["tokens"] and not a.get("mort")}
    frais = {t["key"]: t for t in v.enrich(manquants)} if manquants else {}
    for a in alertes + signaux:
        t = frais.get(a["key"])
        if t and not suivi.releve_coherent(a, t["price"], t["mcap"]):
            continue
        if t:
            a["last"], a["last_mcap"] = t["price"], t["mcap"]
            a["peak"] = max(a.get("peak") or a["price"], t["price"])
        elif a["key"] in manquants and frais:
            a["mort"] = True                       # disparu de DexScreener
    # âge du token au moment de l'alerte : noté seulement depuis le 20/10. Pour les alertes plus
    # anciennes, on le recalcule (date de création du token connue par le suivi ou DexScreener).
    for a in alertes:
        if a.get("age_h") is not None:
            continue
        e = sv["tokens"].get(a["key"])
        age = None
        if e and e.get("created"):
            age = (a["ts"] - e["created"]) / 3600
        elif frais.get(a["key"], {}).get("age_h"):
            age = frais[a["key"]]["age_h"] - (now - a["ts"]) / 3600
        if age is not None and age >= 0:
            a["age_h"] = round(age, 1)
    # alertes jamais suivies toutes les 30 min (anciennes versions du bot) : sans ça leur gain simulé
    # comptait 0 € au lieu d'une perte. On rejoue la règle avec le plus haut connu puis le prix actuel.
    for a in alertes + signaux:
        if "sim" not in a and a.get("price"):
            suivi.simuler(a, (a.get("peak") or a["price"]) / a["price"])
            dernier = 0.0 if a.get("mort") and not a.get("last") else (a.get("last") or a["price"])
            suivi.simuler(a, dernier / a["price"], fin=bool(a.get("mort")))

    def perf(a):
        p0 = a["price"] or 1e-18
        x_now = 0.0 if a.get("mort") and not a.get("last") else (a.get("last") or a["price"]) / p0
        return x_now, (a.get("peak") or a["price"]) / p0

    def aberrant(a):
        return a.get("price") and (a.get("peak") or a["price"]) / a["price"] > X_ABERRANT

    def resume(liste, titre):
        exclus = [a for a in liste if aberrant(a)]
        liste = [a for a in liste if not aberrant(a)]
        if not liste:
            return []
        xs = [perf(a) for a in liste]
        x2 = sum(1 for _, pk in xs if pk >= 2)
        morts = sum(1 for (xn, _), a in zip(xs, liste) if a.get("mort") or xn < 0.1)
        hausse = sum(1 for xn, _ in xs if xn > 1)
        brut = sum(suivi.resultat_sim(a) for a in liste)
        gains = [suivi.resultat_sim_net(a) for a in liste]
        gain = sum(gains)
        m = suivi.MISE_SIM
        txt = (f"<b>{titre}</b> : {len(liste)} · x2 touché : {x2} · en hausse : {hausse} · morts : {morts}"
               f"\n   💶 après frais : <b>{gain * m:+.2f} €</b> pour {len(liste) * m:.0f} € misés "
               f"({gain / len(liste) * 100:+.0f} %) · sans frais : {brut * m:+.2f} €")
        # si une seule alerte pèse plus de la moitié du gain, on la nomme (à vérifier à la main :
        # un x énorme peut être un vrai coup… ou un prix mal coté par DexScreener)
        i = max(range(len(liste)), key=lambda j: gains[j])
        if gains[i] >= 5 and gains[i] > 0.5 * max(gain, 0.01):
            a = liste[i]
            txt += (f"\n   ↳ dont <b>{gains[i] * m:+.2f} €</b> pour ${html.escape(str(a.get('symbol')))} seul "
                    f"(plus haut x{xs[i][1]:.0f}) · sans lui : {(gain - gains[i]) * m:+.2f} €"
                    + (f" · <a href=\"{a['url']}\">vérifier</a>" if a.get("url") else ""))
        for a in exclus:
            pk = (a.get("peak") or a["price"]) / a["price"]
            txt += (f"\n   ↳ hors total : ${html.escape(str(a.get('symbol')))} (plus haut x{pk:.0f}, "
                    f"invraisemblable : prix mal coté ou token piégé)")
        return [txt]

    def detail(liste, label):
        """Ligne courte pour comparer des sous-groupes d'une même catégorie."""
        liste = [a for a in liste if not aberrant(a)]
        if not liste:
            return []
        gs = [suivi.resultat_sim_net(a) for a in liste]
        g = sum(gs)
        x2 = sum(1 for a in liste if perf(a)[1] >= 2)
        sans = ""
        if len(liste) >= 3:            # le résultat tient-il sans son meilleur coup ?
            g2 = g - max(gs)
            sans = f" · sans le meilleur : {g2 / (len(liste) - 1) * 100:+.0f} %"
        return [f"   · {label} : {len(liste)} · x2 : {x2} · après frais {g * suivi.MISE_SIM:+.2f} € "
                f"({g / len(liste) * 100:+.0f} %){sans}"]

    lignes = ["📊 <b>Bilan quotidien</b> (7 derniers jours, prix au moment de l'alerte → maintenant)"]
    titre_cl = "🚨 Classiques" + ("" if CLASSIQUES_EN_DIRECT else " (observation depuis le 19/10)")
    for typ, titre in (("classique", titre_cl), ("survivant", "🌱 Survivants")):
        lignes += resume([a for a in alertes if a.get("type", "classique") == typ
                          and (typ == "classique" or not a.get("observation"))], titre)
        if typ == "classique":       # tes gagnants ont été repérés vers 400 k$ - 1 M$ : on compare
            cl = [a for a in alertes if a.get("type", "classique") == "classique"]
            lignes += resume([a for a in cl if a["mcap"] < 250_000], "   dont mcap &lt; 250 k$ à l'alerte")
            lignes += resume([a for a in cl if a["mcap"] >= 250_000], "   dont mcap ≥ 250 k$ à l'alerte")
    lignes += resume([a for a in alertes if a.get("type") == "momentum" and a["chain"] not in v.CHAINES_OBS],
                     "🚀 Momentum confirmé" + (" (en direct depuis le 19/10)" if MOMENTUM_EN_DIRECT
                                              else " (observation)"))
    mom = [a for a in alertes if a.get("type") == "momentum" and a["chain"] not in v.CHAINES_OBS]
    if mom:                          # quel sous-groupe du momentum gagne vraiment ?
        lignes.append("   <i>découpage :</i>")
        lignes += detail([a for a in mom if a["mcap"] < 700_000], "mcap 300-700 k$")
        lignes += detail([a for a in mom if 700_000 <= a["mcap"] < 1_500_000], "mcap 0,7-1,5 M$")
        lignes += detail([a for a in mom if a["mcap"] >= 1_500_000], "mcap 1,5-3 M$")
        lignes += detail([a for a in mom if a.get("liq_pct", 0) >= 20], "liquidité ≥ 20 % de la mcap")
        lignes += detail([a for a in mom if a.get("liq_pct", 100) < 20], "liquidité &lt; 20 %")
        lignes += detail([a for a in mom if a.get("depuis_haut_pct", -100) >= -10], "à moins de 10 % de son plus haut")
        lignes += detail([a for a in mom if a.get("depuis_haut_pct", 0) < -10], "plus de 10 % sous son plus haut")
        lignes += detail([a for a in mom if a.get("fort")], "tient quand le marché baisse 💪")
        lignes += detail([a for a in mom if a.get("age_h") is not None and a["age_h"] < 24], "moins de 24 h")
        lignes += detail([a for a in mom if a.get("age_h") is not None and a["age_h"] >= 24], "24 h et plus")
        lignes += detail([a for a in mom if a["chain"] == "solana"], "Solana")
        lignes += detail([a for a in mom if a["chain"] != "solana"], "BSC / Base")
        liq = [a for a in mom if a.get("liq_pct", 0) >= ETOILE_LIQ_PCT]
        lignes += detail([a for a in liq if a["chain"] == "solana"], "liquidité ≥ 20 % · Solana")
        lignes += detail([a for a in liq if a["chain"] != "solana"], "liquidité ≥ 20 % · BSC / Base")
        lignes += detail([a for a in mom if a.get("liq_pct", 100) < ETOILE_LIQ_PCT and a["chain"] != "solana"],
                         "liquidité &lt; 20 % · BSC / Base")
        sans_age = sum(1 for a in mom if a.get("age_h") is None)
        if sans_age:
            lignes.append(f"   <i>âge inconnu pour {sans_age} alerte(s) (token disparu du suivi)</i>")
    # catégorie ⭐ : seulement les alertes marquées ⭐ au moment de l'envoi (à partir du 21/10),
    # pour la juger sur des alertes qui n'ont pas servi à la choisir
    lignes += resume([a for a in mom if a.get("etoile_liq")],
                     "⭐ Momentum liquidité ≥ 20 % (catégorie à part, depuis le 21/10)")
    lignes += resume([a for a in alertes if a.get("type") == "momentum" and a["chain"] in v.CHAINES_OBS],
                     "🟣 Momentum sur Robinhood Chain (observation, sécurité souvent non vérifiée)")
    narr = [a for a in alertes if a.get("type") == "narratif"]
    lignes += resume([a for a in narr if not a.get("observation")], "🧩 Narratifs envoyés")
    lignes += resume([a for a in narr if a.get("etoile")], "   dont ⭐ profil SEALS")
    lignes += resume([a for a in narr if a.get("sature")], "🧩 Narratifs saturés (non envoyés)")
    lignes += resume([a for a in narr if a.get("identite") == "dediee"], "🪪 Narratifs avec compte X à leur nom")
    lignes += resume([a for a in narr if a.get("identite") == "tweet"], "🪪 Narratifs « tokens de tweet »")
    lignes += resume([a for a in alertes if a.get("cause")], "🎗️ Tokens pour une cause (tous types)")
    lignes += resume([a for a in alertes if a.get("type") == "baleines"],
                     f"🐳 Baleines ({baleines.BALEINES_MIN}+ sur le même token en {baleines.FENETRE_H} h)")
    lignes += resume([s for s in signaux if not s["trop_tard"]], "🐋 Smart wallets à temps (observation)")
    lignes += resume([s for s in signaux if s["trop_tard"]], "🐋 Smart wallets trop tard (observation)")

    lignes += resume([a for a in alertes if a.get("fort") and not a.get("observation")],
                     "💪 Alertes en force relative")
    lignes += resume([a for a in alertes if a.get("fort") is False and not a.get("observation")],
                     "   alertes sans force relative (pour comparer)")
    lignes.append(f"<i>💶 gain simulé = {suivi.MISE_SIM:.0f} € par alerte, moitié vendue à x2, tout coupé à −50 % "
                  "avant ça, le reste vendu s'il retombe à x1 ou perd 50 % depuis son plus haut. Frais Fomo : "
                  f"{suivi.FRAIS_PCT * 100:.1f} % par ordre, {suivi.FRAIS_MIN:.2f} € minimum (achat et chaque vente).</i>")
    pf_pos = positions.charger()
    j = positions.journal_txt(pf_pos, jours=7)
    if j or pf_pos["positions"]:
        lignes.append("\n" + (j or "📒 Aucun trade fermé cette semaine")
                      + f" · {len(pf_pos['positions'])} position(s) ouverte(s)")
    m = sv.get("marche") or {}
    if m:
        lignes.append(f"🌡️ Marché : memecoins suivis {m['med_6h']:+.0f} % sur 6 h, {m['med_24h']:+.0f} % "
                      f"sur 24 h (médiane de {m['n']} tokens)")

    recentes = sorted((a for a in alertes + signaux if now - a["ts"] < 86400), key=lambda a: a["ts"])
    if recentes:
        lignes.append("\n<b>Dernières 24 h :</b>")
        icones = {"classique": "🚨", "survivant": "🌱", "narratif": "🧩", "momentum": "🚀", "baleines": "🐳"}
        for a in recentes:
            xn, pk = perf(a)
            ic = "🐋" if "wallets" in a else ("🟣" if a.get("chain") in v.CHAINES_OBS
                                              else icones.get(a.get("type", "classique"), "•"))
            fin = "mort ☠️" if a.get("mort") or xn < 0.1 else f"maintenant x{xn:.2f}"
            note = (" (trop tard)" if a.get("trop_tard") else "") + (
                " (obs.)" if a.get("observation") or ("wallets" in a and not a.get("envoye")) else "")
            lignes.append(f"{ic} ${html.escape(str(a['symbol']))}{note} : mcap {fmt_usd(a['mcap'])} · plus haut x{pk:.1f} · {fin}"
                          f" · simulé {suivi.resultat_sim_net(a) * suivi.MISE_SIM:+.2f} €")
    n_w, n_smart = portefeuilles.stats(pf)
    lignes.append(f"\n🐋 Base de wallets : {n_w} observés, {n_smart} « smart » "
                  f"(≥ {portefeuilles.SMART_MIN_BONS_COUPS} coups à x{portefeuilles.BON_COUP_X}, "
                  f"≥ {int(portefeuilles.SMART_MIN_TAUX * 100)} % de réussite)")
    nb_b, ach_b = baleines.stats()
    if nb_b:
        lignes.append(f"🐳 {nb_b} baleine(s) suivie(s), {ach_b} achat(s) repéré(s) en 24 h\n   "
                      + html.escape(baleines.etat_rpc()))
    lignes.append(f"👀 {len(sv['tokens'])} tokens suivis en ce moment")
    lignes.append("<i>« plus haut » = mesuré toutes les 30 min, le vrai sommet a pu être un peu plus haut.</i>")
    if envoyer_long("\n".join(lignes)):
        st["dernier_bilan"] = jour             # marqué envoyé seulement si Telegram l'a accepté
    else:
        print("[warn] bilan non envoyé, nouvel essai au prochain cycle")


def main(mode):
    if mode == "test":
        ok = telegram("✅ Les alertes crypto sont bien connectées à ce Telegram.")
        print("Message envoyé." if ok else "Échec de l'envoi (voir ci-dessus).")
        sys.exit(0 if ok else 1)
    st = load_state()
    sv = suivi.charger()
    pf = portefeuilles.charger()
    pos = positions.charger()
    devs.charger()
    baleines.charger()
    evenements.charger()
    if mode == "bilan":
        bilan_quotidien(st, sv, pf, forcer=True)
        save_state(st)
        return
    start = time.time()
    sent = [0]
    try:
        positions.tick(pos)                  # répondre tout de suite aux messages en attente
    except Exception as e:
        print(f"[warn] positions : {type(e).__name__}")
    while True:
        t0 = time.time()
        try:                                 # le bilan passe en premier : une erreur ailleurs ne le bloque plus
            bilan_quotidien(st, sv, pf)
        except Exception as e:
            print(f"[warn] bilan en erreur : {e!r}")
        try:
            cycle(st, sent, sv, pf)
        except Exception as e:  # une erreur ponctuelle ne doit pas tout arrêter
            import traceback
            traceback.print_exc()
            print(f"[warn] cycle en erreur : {e!r}")
        try:                                 # actu : calendrier, sujets chauds sur Google, suivi 6 h après
            evenements.tick(telegram, pos.get("positions"))
        except Exception as e:
            print(f"[warn] actu : {e!r}")
        save_state(st)
        suivi.sauver(sv)
        portefeuilles.sauver(pf)
        devs.sauver()
        baleines.sauver()
        # entre deux cycles : tes commandes Telegram et tes positions, toutes les ~15 s
        while True:
            try:
                positions.tick(pos)
            except Exception as e:
                print(f"[warn] positions : {type(e).__name__}")
            positions.sauver(pos)
            if mode != "loop" or time.time() - t0 >= CYCLE_MIN * 60 - 15:
                break
            time.sleep(15)
        if mode != "loop" or time.time() - start > (LOOP_MIN - CYCLE_MIN) * 60:
            break


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "once")
