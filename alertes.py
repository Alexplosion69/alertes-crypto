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
    return {"watch": {}, "alerted": {}, "alerts": [], "rejected": {}}


def save_state(st):
    now = time.time()
    st["watch"] = {k: w for k, w in st["watch"].items()
                   if now - w.get("created", now) < AGE_MAX_H * 3600 + 3600}
    st["alerted"] = {k: ts for k, ts in st["alerted"].items() if now - ts < 7 * 86400}
    st["rejected"] = {k: ts for k, ts in st.get("rejected", {}).items() if now - ts < 3600}
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
