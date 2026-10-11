"""
Alertes en temps réel sur Telegram : tokens jeunes qui décollent avec de vrais signaux.

  python alertes.py loop   -> tourne ~52 min, vérifie toutes les ~4 min (lancé chaque heure)
  python alertes.py once   -> une seule vérification (pour tester)
  python alertes.py test   -> envoie juste un message de test sur Telegram

Variables d'environnement : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Gratuit : DexScreener, GeckoTerminal, RugCheck, GoPlus. Pas de X ni de Claude ici.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

import outils as v  # briques communes : API gratuites, wash trading, GoPlus

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
    return {"watch": {}, "alerted": {}, "alerts": [], "rejected": {}, "names": {}, "narr_alerted": {}}


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
    st["alerts"] = [a for a in st["alerts"] if now - a["ts"] < 30 * 86400]
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(st))


# ---------------------------------------------------------------- Candidats
def fresh_candidates():
    """Nouveaux pools + tendances GeckoTerminal, et nouveautés DexScreener."""
    cands = {}

    def add(chain, addr, tag):
        if chain in v.GT_NETWORKS and addr:
            c = cands.setdefault(v.key_of(chain, addr),
                                 {"chain": chain, "address": addr, "sources": [], "boost": 0})
            if tag not in c["sources"]:
                c["sources"].append(tag)

    for chain, net in v.GT_NETWORKS.items():
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


def norm_nom(sym):
    """« $Altia! » -> « altia » (garde les lettres de toutes les langues)."""
    return "".join(ch for ch in (sym or "").lower() if ch.isalnum())


def narratifs(st, tokens, sent_this_hour):
    """Repère les noms clonés en masse et signale le token que le marché a choisi."""
    now = time.time()
    names = st.setdefault("names", {})
    for t in tokens:  # on mémorise le nom de tous les tokens jeunes vus passer
        if t["age_h"] <= NARR_FENETRE_H * 2:
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
        leader = membres[0]
        second_vol = membres[1]["vol_1h"] if len(membres) > 1 else 0
        if not (leader["liq"] >= NARR_LEADER_LIQ_MIN and leader["vol_1h"] >= NARR_LEADER_VOL_MIN
                and leader["chg_1h"] <= NARR_HAUSSE_MAX and leader.get("chg_5m", 0) > CHUTE_5M_MAX
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
        if sent_this_hour[0] >= MAX_ALERTES_HEURE:
            continue
        chaines = {}
        for k in ks:
            chaines[names[k]["chain"]] = chaines.get(names[k]["chain"], 0) + 1
        ecart = (f"×{leader['vol_1h'] / second_vol:.0f} le volume du n°2" if second_vol
                 else "seul à avoir du volume")
        autres = " · ".join(f"{m['chain']} {fmt_usd(m['vol_1h'])}" for m in membres[1:4])
        lignes = [
            f"🧩 <b>Narratif détecté : « {leader['symbol']} »</b> — {len(ks)} tokens de ce nom "
            f"lancés en {NARR_FENETRE_H} h ({', '.join(f'{c} {n}' for c, n in chaines.items())})",
            f"👑 Leader : <b>${leader['symbol']}</b> ({leader['chain']}) — {leader['age_h']:.1f} h, "
            f"mcap {fmt_usd(leader['mcap'])} · liq {fmt_usd(leader['liq'])}",
            f"📊 vol 1 h {fmt_usd(leader['vol_1h'])} ({ecart}) · prix {leader['chg_1h']:+.0f} % sur 1 h, "
            f"{leader.get('chg_5m', 0):+.0f} % sur 5 min",
            f"👥 {b} acheteurs uniques / {sl} vendeurs sur 1 h",
            f"🛡️ {sec_txt}",
            f"Suivants (volume 1 h) : {autres}" if autres else "",
            f"⚠️ Plusieurs tokens portent ce nom : sur Fomo, vérifie que l'adresse se termine par "
            f"<code>{leader['address'][-6:]}</code>",
            f"<a href=\"{leader['dexscreener']}\">Voir le leader sur DexScreener</a>",
            "<i>Signal automatique, pas un conseil. Petite mise seulement.</i>",
        ]
        if telegram("\n".join(x for x in lignes if x)):
            sent_this_hour[0] += 1
            nb += 1
            st["narr_alerted"][nom] = now
            st["alerted"][leader["key"]] = now
            st["alerts"].append({"ts": now, "type": "narratif", "nom": nom, "key": leader["key"],
                                 "symbol": leader["symbol"], "chain": leader["chain"],
                                 "address": leader["address"], "price": leader["price"],
                                 "mcap": leader["mcap"], "url": leader["dexscreener"],
                                 "clones": len(ks)})
    return nb


def cheap_filter(t):
    """Filtre gratuit et rapide (données DexScreener uniquement)."""
    return (AGE_MIN_H <= t["age_h"] <= AGE_MAX_H
            and MCAP_MIN <= t["mcap"] <= MCAP_MAX
            and t["liq"] >= LIQ_MIN and t["vol_1h"] >= VOL_1H_MIN
            and t["chg_1h"] <= HAUSSE_1H_MAX)


# ---------------------------------------------------------------- Sécurité
def securite(t):
    """Renvoie (ok, résumé lisible)."""
    if t["chain"] == "solana":
        d = v.get_json(f"https://api.rugcheck.xyz/v1/tokens/{t['address']}/report/summary")
        if not d:
            return False, "RugCheck indisponible"
        dangers = [r.get("name") for r in d.get("risks") or [] if r.get("level") == "danger"]
        lp = d.get("lpLockedPct")
        if dangers:
            return False, "RugCheck : " + ", ".join(dangers[:3])
        if lp is not None and float(lp) < LP_VERROUILLEE_MIN:
            return False, f"liquidité verrouillée à {float(lp):.0f} % seulement"
        lp_txt = f", liquidité verrouillée {float(lp):.0f} %" if lp is not None else ""
        warns = [r.get("name") for r in d.get("risks") or [] if r.get("level") == "warn"]
        warn_txt = f" (à noter : {', '.join(warns[:2])})" if warns else ""
        return True, f"RugCheck sans danger{lp_txt}{warn_txt}"
    v.goplus([t])
    sec = t.get("securite_evm")
    if not sec:
        return False, "GoPlus indisponible"
    graves = [r for r in sec["risques"] if any(m in r for m in
              ("honeypot", "impossible", "modifier les soldes", "caché"))]
    if graves:
        return False, "GoPlus : " + ", ".join(graves)
    # données manquantes = token pas encore analysé par GoPlus : on refuse (inconnu ≠ sûr)
    if sec.get("taxe_vente_pct") is None or sec.get("taxe_achat_pct") is None:
        return False, "GoPlus : taxes inconnues (token pas encore analysé)"
    if sec.get("top10_detenteurs_pct") is None:
        return False, "GoPlus : répartition des détenteurs inconnue"
    if sec["top10_detenteurs_pct"] > TOP10_MAX:
        return False, f"top 10 détenteurs {sec['top10_detenteurs_pct']} % (trop concentré)"
    if sec["taxe_vente_pct"] > TAXE_VENTE_MAX:
        return False, f"taxe de vente {sec['taxe_vente_pct']} %"
    parts = [f"taxes {sec.get('taxe_achat_pct')}/{sec.get('taxe_vente_pct')} %"]
    if sec.get("top10_detenteurs_pct") is not None:
        parts.append(f"top 10 détenteurs {sec['top10_detenteurs_pct']} %")
    if sec["risques"]:
        parts.append("à noter : " + ", ".join(sec["risques"][:2]))
    return True, "GoPlus OK, " + ", ".join(parts)


# ---------------------------------------------------------------- Un cycle
def fmt_usd(x):
    return f"{x / 1e6:.2f} M$" if x >= 1e6 else f"{x / 1e3:.0f} k$"


def cycle(st, sent_this_hour):
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
    nb_narr = narratifs(st, tokens, sent_this_hour)
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
        if sent_this_hour[0] >= MAX_ALERTES_HEURE:
            print(f"limite d'alertes atteinte, {t['symbol']} non envoyé")
            continue

        stade = ("encore sur pump.fun" if t.get("dex") == "pumpfun"
                 else f"sur {t.get('dex') or '?'}")
        lignes = [
            f"🚨 <b>${t['symbol']}</b> ({t['chain']}) — {t['age_h']:.1f} h, {stade}",
            f"mcap {fmt_usd(t['mcap'])} · liq {fmt_usd(t['liq'])} · vol 1 h {fmt_usd(t['vol_1h'])}",
            f"📈 prix {t['chg_1h']:+.0f} % sur 1 h · {t.get('chg_5m', 0):+.0f} % sur 5 min" + (
                f" · mcap {hausse_suivi:+.0f} % depuis {int((now - ref['ts']) / 60)} min" if ref else ""),
            f"👥 {b} acheteurs uniques / {s} vendeurs sur 1 h (×{ratio:.1f})" + (
                f" · acheteurs {hausse_ach:+.0f} % depuis {int((now - ref_b['ts']) / 60)} min"
                if hausse_ach is not None else ""),
            f"🔁 volume/liquidité {t['volume_sur_liquidite']} · "
            f"{t.get('achats_par_acheteur_1h', '?')} achat(s) par acheteur : pas de wash détecté",
            f"🛡️ {sec_txt}",
            f"<a href=\"{t['dexscreener']}\">Voir sur DexScreener</a>",
            "<i>Signal automatique, pas un conseil. Petite mise seulement.</i>",
        ]
        if telegram("\n".join(lignes)):
            sent_this_hour[0] += 1
            nb += 1
            st["alerted"][t["key"]] = now
            st["alerts"].append({"ts": now, "key": t["key"], "symbol": t["symbol"],
                                 "chain": t["chain"], "address": t["address"],
                                 "price": t["price"], "mcap": t["mcap"], "url": t["dexscreener"]})
    print(f"{time.strftime('%H:%M')} : {len(tokens)} tokens observés, "
          f"{len(short)} passent le filtre rapide, {nb} alerte(s)")


def main(mode):
    if mode == "test":
        ok = telegram("✅ Les alertes crypto sont bien connectées à ce Telegram.")
        print("Message envoyé." if ok else "Échec de l'envoi (voir ci-dessus).")
        sys.exit(0 if ok else 1)
    st = load_state()
    start = time.time()
    sent = [0]
    while True:
        t0 = time.time()
        try:
            cycle(st, sent)
        except Exception as e:  # une erreur ponctuelle ne doit pas tout arrêter
            print(f"[warn] cycle en erreur : {e!r}")
        save_state(st)
        if mode != "loop" or time.time() - start > (LOOP_MIN - CYCLE_MIN) * 60:
            break
        time.sleep(max(10, CYCLE_MIN * 60 - (time.time() - t0)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "once")
