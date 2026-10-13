"""
Suivi de TES positions, piloté depuis Telegram (gratuit, sans Claude).

Tu écris au bot :
  /achat <adresse ou lien DexScreener> [mcap d'entrée]   ex : /achat 3sKaoP…pump 84k
  /vente <symbole> 25% [mcap]        (25 % de ce qu'il te reste ; le suivi continue)
  /vente <symbole> moitie | quart    (raccourcis : 50 %, 25 %)
  /vente <symbole> tout [mcap]       (tout ce qui reste : position fermée, mise au journal)
  Les pourcentages portent toujours sur CE QUI RESTE : 25 % puis « tout » = 100 % vendu.
  /positions                         (où en sont tes positions, tout de suite)
  /aide

Le bot vérifie tes positions environ chaque minute et te prévient :
  🚀 à x2, x3, x5, x10, x20…            avec une analyse rapide (acheteurs, volume, liquidité)
  ⚠️ à −30 % et 🛑 à −50 % de ton entrée
  📉 si ça perd 30 % depuis le plus haut atteint (une fois le plus haut ≥ x1,5)
  🚨 si la liquidité fond (risque de rug) ou si le prix chute de 20 % en 5 min
Et il tient à jour un message épinglé « 📌 Mes positions » dans la conversation.

Confidentialité : le dépôt est public, donc ses journaux d'exécution aussi. Ce module n'écrit
JAMAIS tes positions dans les journaux ; elles restent dans la mémoire privée du bot (cache).
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import outils as v

FICHIER = Path("alertes/positions.json")
PALIERS = [2, 3, 5, 10, 20, 50, 100]
SEUILS_PERTE = [(0.7, "⚠️", "−30 %"), (0.5, "🛑", "−50 %")]
REPLI_DEPUIS_HAUT = 0.30      # −30 % depuis le plus haut…
REPLI_HAUT_MIN = 1.5          # …une fois que le plus haut a dépassé x1,5
LIQ_FONTE = 0.6               # liquidité sous 60 % de son maximum : risque de rug
CHUTE_5M = -20                # −20 % en 5 minutes
VERIF_S = 60                  # vérification des prix toutes les 60 s
RESUME_MIN = 30               # message épinglé mis à jour toutes les 30 min
try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:                     # fuseau indisponible : heure d'été de Paris par défaut
    PARIS = timezone(timedelta(hours=2))

AIDE = ("🤖 <b>Suivi de tes positions</b>\n"
        "<code>/achat ADRESSE 84k</code> : ajoute une position (adresse du token ou lien DexScreener, "
        "et la mcap à laquelle tu as acheté ; sans mcap, je prends celle du moment)\n"
        "<code>/vente SYMBOLE 25%</code> : tu as vendu 25 % de ce qu'il te reste "
        "(aussi : <code>quart</code>, <code>moitie</code>, <code>tout</code>)\n"
        "Les % portent toujours sur ce qui reste : 25 % puis « tout » = 100 % vendu, jamais 125 %.\n"
        "Ajoute la mcap de vente si tu veux : <code>/vente SEALS 50% 1.8M</code>\n"
        "<code>/positions</code> : le point tout de suite\n\n"
        "Je te préviens à x2, x3, x5, x10…, à −30 % et −50 %, si ça perd 30 % depuis le plus haut, "
        "et si la liquidité fond.")


# ---------------------------------------------------------------- Telegram
def api(methode, **payload):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{methode}", json=payload, timeout=20)
        d = r.json()
        if not d.get("ok") and "not modified" not in str(d.get("description")):
            print(f"[warn] Telegram {methode} : {str(d.get('description'))[:120]}")
        return d
    except (requests.RequestException, ValueError) as e:
        print(f"[warn] Telegram {methode} -> {e}")
        return None


def envoyer(texte):
    d = api("sendMessage", chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=texte, parse_mode="HTML",
            disable_web_page_preview=True)
    return (d or {}).get("result", {}).get("message_id") if (d or {}).get("ok") else None


# ---------------------------------------------------------------- état
def charger():
    if FICHIER.exists():
        try:
            p = json.loads(FICHIER.read_text())
            for k, d in (("offset", 0), ("positions", {}), ("fermees", []), ("epingle", None),
                         ("dernier_resume", 0), ("derniere_verif", 0)):
                p.setdefault(k, d)
            return p
        except json.JSONDecodeError:
            pass
    return {"offset": 0, "positions": {}, "fermees": [], "epingle": None, "dernier_resume": 0,
            "derniere_verif": 0}


def sauver(p):
    p["fermees"] = [f for f in p["fermees"] if time.time() - f["fin"] < 90 * 86400]
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(p, separators=(",", ":")))


# ---------------------------------------------------------------- outils
def fmt_usd(x):
    return f"{x / 1e6:.2f} M$" if x >= 1e6 else f"{x / 1e3:.0f} k$"


def lire_montant(txt):
    """« 84k » -> 84000 ; « 1,2M » -> 1200000 ; « 84000 » -> 84000."""
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([kKmM]?)\$?", txt.strip())
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return n * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1)


def trouver_token(texte):
    """Retrouve le token à partir d'une adresse ou d'un lien. Renvoie un token « à plat » ou None."""
    m = re.search(r"dexscreener\.com/(solana|base|bsc)/([A-Za-z0-9]+)", texte)
    if m:
        essais = [(m.group(1), m.group(2))]
    else:
        m = re.search(r"0x[a-fA-F0-9]{40,64}", texte) or re.search(r"[1-9A-HJ-NP-Za-km-z]{32,44}", texte)
        if not m:
            return None
        a = m.group(0)
        essais = [(c, a) for c in (("base", "bsc") if a.startswith("0x") else ("solana",))]
    for chain, a in essais:
        paires = v.get_json(f"{v.DS}/tokens/v1/{chain}/{a}") or []
        if not paires:                      # c'est peut-être l'adresse d'une paire
            d = v.get_json(f"{v.DS}/latest/dex/pairs/{chain}/{a}") or {}
            paires = d.get("pairs") or []
        paires = [x for x in paires if x.get("priceUsd")]
        if paires:
            best = max(paires, key=lambda x: (x.get("liquidity") or {}).get("usd") or 0)
            return v.depuis_paire(best)
    return None


def chercher_position(p, nom):
    nom = nom.lower().lstrip("$")
    for pid, pos in p["positions"].items():
        if pos["symbol"].lower() == nom or pos["address"].lower().startswith(nom) or pid.lower() == nom:
            return pid, pos
    return None, None


# ---------------------------------------------------------------- commandes
def commandes(p):
    """Lit les nouveaux messages envoyés au bot et y répond."""
    chat = str(os.getenv("TELEGRAM_CHAT_ID") or "")
    d = api("getUpdates", offset=p["offset"], timeout=0, allowed_updates=["message"])
    for u in (d or {}).get("result") or []:
        p["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != chat:
            continue                        # quelqu'un d'autre écrit au bot : on ignore
        texte = (msg.get("text") or "").strip()
        mots = texte.split()
        if not mots:
            continue
        cmd = mots[0].lower().lstrip("/").split("@")[0]
        try:
            if cmd in ("achat", "achete", "buy"):
                cmd_achat(p, mots[1:])
            elif cmd in ("vente", "vendu", "sell"):
                cmd_vente(p, mots[1:])
            elif cmd in ("positions", "pos", "point"):
                envoyer(resume(p, maintenant=True))
            elif cmd in ("aide", "help", "start") or texte.startswith("/"):
                envoyer(AIDE)
            elif re.search(r"0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44}", texte):
                envoyer("Tu veux que je suive ce token ? Envoie <code>/achat</code> suivi de l'adresse "
                        "et de ta mcap d'entrée, par exemple <code>/achat ADRESSE 84k</code>.")
        except Exception as e:              # une commande mal tapée ne doit rien casser
            print(f"[warn] commande en erreur : {type(e).__name__}")
            envoyer("😕 Je n'ai pas compris. Exemple : <code>/achat ADRESSE 84k</code>\n/aide pour l'aide.")


def cmd_achat(p, args):
    if not args:
        envoyer("Il me faut l'adresse du token (ou le lien DexScreener). "
                "Exemple : <code>/achat 3sKaoP…pump 84k</code>")
        return
    mcap_entree = next((m for m in (lire_montant(a) for a in args) if m), None)
    t = trouver_token(" ".join(args))
    if not t:
        envoyer("😕 Token introuvable sur DexScreener. Envoie l'adresse complète du token "
                "(ou le lien DexScreener de la paire).")
        return
    prix_entree = t["price"] * (mcap_entree / t["mcap"]) if mcap_entree and t["mcap"] else t["price"]
    mcap_entree = mcap_entree or t["mcap"]
    pid = t["symbol"]
    n = 2
    while pid in p["positions"]:
        pid, n = f"{t['symbol']}{n}", n + 1
    x = t["price"] / prix_entree if prix_entree else 1
    p["positions"][pid] = {
        "symbol": t["symbol"], "chain": t["chain"], "address": t["address"], "url": t["dexscreener"],
        "ts": time.time(), "prix_entree": prix_entree, "mcap_entree": mcap_entree,
        "ratio_mcap": t["mcap"] / t["price"] if t["price"] else 0,
        "haut_x": max(1.0, x), "x": x, "liq_max": t["liq"], "reste": 1.0, "realise": 0.0, "ventes": [],
        "paliers": [q for q in PALIERS if x >= q], "envoyes": {}}
    envoyer(f"✅ Position ajoutée : <b>${t['symbol']}</b> ({t['chain']})\n"
            f"entrée mcap {fmt_usd(mcap_entree)} · maintenant {fmt_usd(t['mcap'])} (x{x:.2f})\n"
            f"Je te préviens à x2, x3, x5…, à −30 % et −50 %, si ça perd 30 % depuis le plus haut, "
            f"et si la liquidité fond.\nQuand tu vends : <code>/vente {pid} 25%</code>, "
            f"<code>/vente {pid} moitie</code> ou <code>/vente {pid} tout</code>")
    p["dernier_resume"] = 0                  # mettre à jour le message épinglé


MOTS_POURCENT = {"tout": 100, "all": 100, "moitie": 50, "moitié": 50, "demi": 50,
                 "quart": 25, "tiers": 100 / 3}


def lire_pourcent(txt):
    """« 25% », « 25 », « quart », « moitie », « tout » -> pourcentage ; « 1.8M », « 84k » -> None."""
    t = txt.strip().lower()
    if t in MOTS_POURCENT:
        return MOTS_POURCENT[t]
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*%?", t)
    if m:
        n = float(m.group(1).replace(",", "."))
        if 0 < n <= 100 and (t.endswith("%") or n <= 100):
            return n
    return None


def cmd_vente(p, args):
    """Vente d'un pourcentage de CE QUI TE RESTE : 25 % puis 100 % = tout vendu, jamais 125 %."""
    if not args:
        envoyer("Exemples : <code>/vente SEALS 25%</code>, <code>/vente SEALS moitie</code>, "
                "<code>/vente SEALS tout 1.8M</code>")
        return
    pid, pos = chercher_position(p, args[0])
    if not pos:
        envoyer(f"😕 Pas de position « {args[0][:20]} ». Tape /positions pour voir la liste.")
        return
    pos.setdefault("reste", 1.0)
    pos.setdefault("realise", 0.0)
    pct, mcap_sortie = None, None
    for a in args[1:]:
        if pct is None and lire_pourcent(a) is not None and not re.search(r"[kKmM]\$?$", a):
            pct = lire_pourcent(a)
        elif lire_montant(a):
            mcap_sortie = lire_montant(a)
    pct = 100 if pct is None else pct
    x = (mcap_sortie / pos["mcap_entree"]) if mcap_sortie and pos["mcap_entree"] else pos["x"]
    pos["haut_x"] = max(pos["haut_x"], x)
    part = pos["reste"] * pct / 100            # part de la position DE DÉPART vendue maintenant
    pos["realise"] += part * x                 # ce que ça rapporte, en multiple de ta mise de départ
    pos["reste"] -= part
    pos.setdefault("ventes", []).append([round(time.time()), round(part, 4), round(x, 4)])
    if pos["reste"] > 0.005:
        envoyer(f"👍 ${pos['symbol']} : {pct:.0f} % de ce qui restait vendu à x{x:.2f}.\n"
                f"Il te reste <b>{pos['reste'] * 100:.0f} %</b> de ta position de départ ; "
                f"déjà encaissé : {pos['realise']:.2f}x ta mise. Je continue de surveiller le reste.")
    else:
        resultat = pos["realise"]              # tout est vendu : résultat = total encaissé / mise
        p["fermees"].append({"symbol": pos["symbol"], "chain": pos["chain"], "debut": pos["ts"],
                             "fin": time.time(), "x": round(resultat, 3), "haut_x": round(pos["haut_x"], 2),
                             "ventes": len(pos["ventes"])})
        del p["positions"][pid]
        envoyer(f"🏁 ${pos['symbol']} fermée en {len(pos['ventes'])} vente(s) : résultat "
                f"<b>x{resultat:.2f}</b> ({(resultat - 1) * 100:+.0f} %), plus haut atteint "
                f"x{pos['haut_x']:.1f}.\n" + journal_txt(p))
    p["dernier_resume"] = 0


def journal_txt(p, jours=30):
    f = [x for x in p["fermees"] if time.time() - x["fin"] < jours * 86400]
    if not f:
        return ""
    gagnes = sum(1 for x in f if x["x"] > 1)
    moy = sum(x["x"] for x in f) / len(f)
    rate = sum(1 for x in f if x["haut_x"] >= 2 and x["x"] < 1.5)
    txt = (f"📒 Ton journal ({jours} j) : {len(f)} trade(s), {gagnes} gagnant(s), "
           f"résultat moyen x{moy:.2f}")
    if rate:
        txt += f"\n⚠️ {rate} trade(s) étaient montés à x2 ou plus, puis tu as vendu sous x1,5"
    return txt


# ---------------------------------------------------------------- analyse rapide
def analyse(t, pos):
    """Lecture rapide, sans Claude : renvoie (score, lignes). Score > 0 = sain, < 0 = faiblesse."""
    v.add_traders([t])
    v.flag_wash(t)
    score, lignes = 0, []
    b, s = t.get("acheteurs_uniques_1h"), t.get("vendeurs_uniques_1h")
    if b and s:
        if b >= 1.15 * s:
            score += 1
            lignes.append(f"✅ plus d'acheteurs que de vendeurs sur 1 h ({b} / {s})")
        elif s >= 1.15 * b:
            score -= 1
            lignes.append(f"❌ plus de vendeurs que d'acheteurs sur 1 h ({s} / {b}) : des gens encaissent")
        else:
            lignes.append(f"➖ autant d'acheteurs que de vendeurs ({b} / {s})")
    rythme = t["vol_1h"] / max(t["vol_6h"] / 6, 1)
    if rythme >= 1.2:
        score += 1
        lignes.append(f"✅ le volume accélère (1 h = {rythme:.1f}x la moyenne des 6 h)")
    elif rythme <= 0.5:
        score -= 1
        lignes.append(f"❌ le volume s'essouffle (1 h = {rythme:.1f}x la moyenne des 6 h)")
    liq_ratio = t["liq"] / max(pos["liq_max"], 1)
    if liq_ratio >= 0.9:
        score += 1
        lignes.append("✅ liquidité stable")
    elif liq_ratio < 0.75:
        score -= 2
        lignes.append(f"❌ liquidité en baisse ({(liq_ratio - 1) * 100:.0f} % depuis son maximum)")
    if t["chg_5m"] <= -10:
        score -= 1
        lignes.append(f"❌ chute en cours ({t['chg_5m']:+.0f} % sur 5 min)")
    if t.get("alerte_wash_trading"):
        score -= 1
        lignes.append(f"❌ volume suspect ({t['alerte_wash_trading']})")
    return score, lignes


def verdict(evenement, score, pos):
    if evenement == "hausse":
        if score >= 1:
            base = "Rien d'alarmant pour l'instant."
            plan = ("Ton plan : sécurise une partie (la moitié à x2 si ce n'est pas fait) et laisse courir "
                    "le reste, stop à −30 % du plus haut." if pos.get("reste", 1) >= 0.99 else
                    f"Tu as déjà sécurisé {(1 - pos['reste']) * 100:.0f} % : laisse courir le reste, "
                    f"stop à −30 % du plus haut.")
        elif score <= -1:
            base = "⚠️ Des signaux de faiblesse malgré la hausse."
            plan = "Envisage de sécuriser plus que prévu : ce genre de hausse se retourne souvent vite."
        else:
            base = "Signaux mitigés."
            plan = "Sécurise au moins ta moitié, et garde le stop à −30 % du plus haut."
        return f"{base} {plan}"
    if score <= -1:
        return "Les signaux confirment la baisse : ton plan dit de couper."
    return ("La baisse n'est pas (encore) confirmée par les acheteurs, mais un plan ne sert que s'il est "
            "respecté : c'est ton niveau de sortie.")


# ---------------------------------------------------------------- surveillance
def surveiller(p):
    if not p["positions"]:
        return
    cands = {v.key_of(x["chain"], x["address"]): {"chain": x["chain"], "address": x["address"],
                                                    "sources": [], "boost": 0}
             for x in p["positions"].values()}
    frais = {t["key"]: t for t in v.enrich(cands)}
    now = time.time()
    for pid, pos in list(p["positions"].items()):
        t = frais.get(v.key_of(pos["chain"], pos["address"]))
        if not t or not t["price"]:
            continue
        x = t["price"] / pos["prix_entree"]
        pos["x"], pos["mcap"] = x, t["mcap"]
        pos["haut_x"] = max(pos["haut_x"], x)
        pos["liq_max"] = max(pos["liq_max"], t["liq"])
        evts = []
        nouveaux = [q for q in PALIERS if x >= q and q not in pos["paliers"]]
        if nouveaux:
            pos["paliers"] += nouveaux
            evts.append(("hausse", f"🚀 <b>${pos['symbol']} a fait x{max(nouveaux)}</b> "
                                   f"(mcap {fmt_usd(pos['mcap_entree'])} → {fmt_usd(t['mcap'])})"))
        for seuil, ic, txt in SEUILS_PERTE:
            if x <= seuil and txt not in pos["envoyes"]:
                pos["envoyes"][txt] = now
                evts.append(("baisse", f"{ic} <b>${pos['symbol']} est à {txt}</b> de ton entrée "
                                       f"(mcap {fmt_usd(pos['mcap_entree'])} → {fmt_usd(t['mcap'])})"))
        if (pos["haut_x"] >= REPLI_HAUT_MIN and x <= pos["haut_x"] * (1 - REPLI_DEPUIS_HAUT)
                and pos["envoyes"].get("repli") != round(pos["haut_x"], 2)):
            pos["envoyes"]["repli"] = round(pos["haut_x"], 2)
            evts.append(("baisse", f"📉 <b>${pos['symbol']} a perdu {(1 - x / pos['haut_x']) * 100:.0f} % "
                                   f"depuis son plus haut</b> (x{pos['haut_x']:.1f} → x{x:.2f})"))
        ref = pos["liq_ref"] = max(pos.get("liq_ref", pos["liq_max"]), t["liq"])
        if ref >= 10_000 and t["liq"] <= LIQ_FONTE * ref:
            pos["liq_ref"] = t["liq"]          # prochaine alerte seulement si ça refond encore
            evts.append(("baisse", f"🚨 <b>${pos['symbol']} : la liquidité a fondu</b> "
                                   f"({fmt_usd(ref)} → {fmt_usd(t['liq'])}). Risque de rug : "
                                   f"quelqu'un retire l'argent du pool."))
        if t["chg_5m"] <= CHUTE_5M and now - pos["envoyes"].get("chute", 0) > 1800:
            pos["envoyes"]["chute"] = now
            evts.append(("baisse", f"🚨 <b>${pos['symbol']} chute de {t['chg_5m']:.0f} % en 5 min</b>"))
        if not evts:
            continue
        typ = "baisse" if any(e[0] == "baisse" for e in evts) else "hausse"
        score, lignes = analyse(t, pos)
        msg = "\n".join([e[1] for e in evts] + [f"maintenant x{x:.2f} · plus haut x{pos['haut_x']:.1f}"]
                        + lignes + [f"👉 {verdict(typ, score, pos)}",
                                    f"<a href=\"{t['dexscreener']}\">Graphique</a> · "
                                    f"<code>/vente {pid} 25%</code> · <code>/vente {pid} moitie</code> · "
                                    f"<code>/vente {pid} tout</code>"])
        envoyer(msg)
        p["dernier_resume"] = 0


def resume(p, maintenant=False):
    heure = datetime.now(PARIS).strftime("%H:%M")
    if not p["positions"]:
        return (f"📌 <b>Mes positions</b> (maj {heure})\nAucune position suivie.\n"
                f"Ajoute-en une : <code>/achat ADRESSE 84k</code>")
    lignes = [f"📌 <b>Mes positions</b> (maj {heure})"]
    for pid, pos in sorted(p["positions"].items(), key=lambda kv: -kv[1]["x"]):
        x = pos["x"]
        ic = "🟢" if x >= 1.2 else ("🔴" if x < 0.85 else "⚪")
        lignes.append(f"{ic} <b>${pos['symbol']}</b> x{x:.2f} ({(x - 1) * 100:+.0f} %) · plus haut "
                      f"x{pos['haut_x']:.1f} · mcap {fmt_usd(pos.get('mcap') or pos['mcap_entree'])}"
                      + (f" · reste {pos['reste'] * 100:.0f} %, encaissé {pos['realise']:.2f}x"
                         if pos.get("reste", 1) < 0.995 else ""))
    j = journal_txt(p)
    if j:
        lignes.append(j)
    return "\n".join(lignes)


def epingle(p):
    """Met à jour le message épinglé (toutes les 30 min, ou tout de suite après un changement)."""
    if time.time() - p["dernier_resume"] < RESUME_MIN * 60:
        return
    if not p["positions"] and not p["epingle"]:
        return                               # rien à afficher et pas encore de message épinglé
    p["dernier_resume"] = time.time()
    texte = resume(p)
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if p["epingle"]:
        d = api("editMessageText", chat_id=chat, message_id=p["epingle"], text=texte, parse_mode="HTML",
                disable_web_page_preview=True)
        if (d or {}).get("ok") or "not modified" in str((d or {}).get("description")):
            return
    mid = envoyer(texte)
    if mid:
        p["epingle"] = mid
        api("pinChatMessage", chat_id=chat, message_id=mid, disable_notification=True)


def tick(p):
    """Appelé toutes les ~15 s par la boucle principale."""
    if not p.get("menu"):                # le menu « / » de Telegram affiche les commandes
        d = api("setMyCommands", commands=[
            {"command": "achat", "description": "ajouter une position : /achat ADRESSE 84k"},
            {"command": "vente", "description": "/vente SYMBOLE 25% (ou moitie, tout) [mcap]"},
            {"command": "positions", "description": "où en sont mes positions"},
            {"command": "aide", "description": "rappel des commandes"}])
        p["menu"] = bool((d or {}).get("ok"))
    commandes(p)
    if time.time() - p["derniere_verif"] >= VERIF_S:
        p["derniere_verif"] = time.time()
        surveiller(p)
    epingle(p)
