"""
Actu et événements (21/10/2026)

Deux choses :
1. Calendrier : les événements datés (GTA 6, Black Friday…) de evenements_calendrier.txt et ceux
   ajoutés avec /evenement. Rappel 7 jours avant, la veille et le jour J. Si tu as une position dont
   le nom colle à l'événement, on te rappelle de vendre avant (ces tokens s'effondrent souvent le jour J).
2. Radar actu : toutes les 30 min, les recherches qui montent sur Google (États-Unis, là où naissent
   la plupart des memecoins). Un sujet qui explose, ou un sujet sur lequel des tokens viennent déjà
   de naître, t'envoie une notif. 6 h plus tard, on regarde si un token du sujet a tenu.

Leçon des alertes : les premiers tokens nés sur une actu meurent presque tous (bots, clones). La notif
sert à savoir qu'un sujet chauffe ; un token ne vaut le coup que s'il tient plusieurs heures.

Commandes : /actu (sujets des dernières 24 h), /evenements (à venir),
/evenement AAAA-MM-JJ Nom [mots-clés…] (ajouter), /oublie Nom (retirer).
"""
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import outils as v

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:
    PARIS = timezone(timedelta(hours=2))

FICHIER = Path("alertes/evenements.json")
CALENDRIER = Path("evenements_calendrier.txt")

TRENDS_URL = "https://trends.google.com/trending/rss"
TRENDS_PAYS = ("US",)
RADAR_TOUTES_MIN = 30
RADAR_TRAFIC_MIN = 1_000          # « 1000+ recherches » : un vrai pic aux États-Unis
RADAR_TRAFIC_MEME = 200           # plus bas si des tokens sont déjà nés sur le sujet…
RADAR_TOKENS_MEME = 2             # …au moins 2 en 48 h
RADAR_MAX_JOUR = 8                # pas plus de 8 notifs actu par jour
SUIVI_H = 6                       # nouvelles du sujet 6 h après la notif
TOKEN_AGE_MIN_H = 3               # un token « qui tient » : au moins 3 h…
TOKEN_LIQ_MIN = 20_000            # …20 k$ de liquidité…
TOKEN_MCAP_MIN = 100_000          # …et 100 k$ de mcap
CHAINES = ("solana", "bsc", "base")
RAPPELS_J = (7, 1, 0)
MOTS_VIDES = {"the", "and", "for", "with", "from", "this", "that", "what", "when", "where", "how",
              "who", "why", "news", "today", "live", "game", "vs", "les", "des", "une", "pour", "dans"}

_etat = {"vus": {}, "sujets": [], "rappels": {}, "ajouts": [], "retires": [], "dernier_radar": 0,
         "envois": []}


# ---------------------------------------------------------------- état
def charger():
    global _etat
    if FICHIER.exists():
        try:
            _etat = {**_etat, **json.loads(FICHIER.read_text())}
        except json.JSONDecodeError:
            pass
    return _etat


def sauver():
    now = time.time()
    _etat["vus"] = {k: ts for k, ts in _etat["vus"].items() if now - ts < 3 * 86400}
    _etat["sujets"] = [s for s in _etat["sujets"] if now - s["ts"] < 3 * 86400]
    _etat["envois"] = [ts for ts in _etat["envois"] if now - ts < 86400]
    aujourd_hui = date.today().isoformat()
    _etat["rappels"] = {k: d for k, d in _etat["rappels"].items() if d >= aujourd_hui[:7]}
    FICHIER.parent.mkdir(exist_ok=True)
    FICHIER.write_text(json.dumps(_etat, separators=(",", ":")))


# ---------------------------------------------------------------- outils
def _usd(x):
    x = x or 0
    if x >= 1e6:
        return f"{x / 1e6:.2f} M$"
    if x >= 1e3:
        return f"{x / 1e3:.0f} k$"
    return f"{x:.0f} $"


def _norm(txt):
    return re.sub(r"[^a-z0-9]", "", str(txt or "").lower())


def _mots(sujet):
    mots = [_norm(m) for m in re.split(r"[\s\-_/]+", sujet)]
    mots = [m for m in mots if len(m) >= 4 and m not in MOTS_VIDES]
    colle = _norm(sujet)
    return ([colle] if len(colle) >= 4 else []) + mots


def _trafic(txt):
    m = re.match(r"\s*([\d.,]+)\s*([KkMm]?)", str(txt or ""))
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1))


# ---------------------------------------------------------------- tokens liés à un sujet
def tokens_du_sujet(sujet, fenetre_h=48):
    """Tokens nés récemment dont le nom ou le ticker reprend le sujet (DexScreener)."""
    mots = _mots(sujet)
    if not mots:
        return []
    d = v.get_json(f"{v.DS}/latest/dex/search", params={"q": sujet}) or {}
    now_ms = time.time() * 1000
    best = {}
    for p in d.get("pairs") or []:
        if p.get("chainId") not in CHAINES or not p.get("pairCreatedAt"):
            continue
        age_h = (now_ms - p["pairCreatedAt"]) / 3.6e6
        if age_h > fenetre_h:
            continue
        b = p.get("baseToken") or {}
        nom = _norm(b.get("name")) + " " + _norm(b.get("symbol"))
        if not any(m in nom for m in mots):
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        cle = f"{p['chainId']}:{b.get('address')}"
        if cle not in best or liq > best[cle]["liq"]:
            best[cle] = {"symbol": b.get("symbol"), "chain": p["chainId"], "address": b.get("address"),
                         "age_h": age_h, "liq": liq, "mcap": p.get("marketCap") or p.get("fdv") or 0,
                         "chg_6h": (p.get("priceChange") or {}).get("h6") or 0, "url": p.get("url")}
    return sorted(best.values(), key=lambda t: -t["mcap"])


def _ligne_token(t):
    return (f"<a href=\"{t['url']}\">${html.escape(str(t['symbol']))}</a> ({t['chain']}) "
            f"{_usd(t['mcap'])} · liq {_usd(t['liq'])} · {t['age_h']:.0f} h")


# ---------------------------------------------------------------- radar actu
def lire_tendances():
    sujets = []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    for pays in TRENDS_PAYS:
        try:
            r = requests.get(TRENDS_URL, params={"geo": pays}, headers=v.UA, timeout=20)
            racine = ET.fromstring(r.content)
        except (requests.RequestException, ET.ParseError) as e:
            print(f"[warn] tendances Google {pays} : {type(e).__name__}")
            continue
        for it in racine.iter("item"):
            titre = (it.findtext("title") or "").strip()
            if not titre:
                continue
            news = it.find("ht:news_item", ns)
            sujets.append({
                "sujet": titre, "pays": pays,
                "trafic": _trafic(it.findtext("ht:approx_traffic", default="", namespaces=ns)),
                "titre": (news.findtext("ht:news_item_title", default="", namespaces=ns) if news is not None else ""),
                "source": (news.findtext("ht:news_item_source", default="", namespaces=ns) if news is not None else ""),
                "lien": (news.findtext("ht:news_item_url", default="", namespaces=ns) if news is not None else ""),
            })
    return sujets


def radar(envoyer):
    now = time.time()
    if now - _etat["dernier_radar"] < RADAR_TOUTES_MIN * 60:
        return
    _etat["dernier_radar"] = now
    for s in sorted(lire_tendances(), key=lambda s: -s["trafic"]):
        cle = _norm(s["sujet"])
        if not cle or cle in _etat["vus"] or s["trafic"] < RADAR_TRAFIC_MEME:
            continue
        toks = tokens_du_sujet(s["sujet"])
        if s["trafic"] < RADAR_TRAFIC_MIN and len(toks) < RADAR_TOKENS_MEME:
            continue                      # ni gros pic, ni tokens : on le reverra s'il grossit
        _etat["vus"][cle] = now
        if len(_etat["envois"]) >= RADAR_MAX_JOUR:
            continue
        lignes = [f"📰 <b>Sujet chaud : {html.escape(s['sujet'])}</b> "
                  f"({format(s['trafic'], ',').replace(',', ' ')}+ recherches Google, {s['pays']})"]
        if s["titre"]:
            lien = f"<a href=\"{s['lien']}\">{html.escape(s['titre'])}</a>" if s["lien"] else html.escape(s["titre"])
            lignes.append(f"🗞️ {lien}" + (f" — {html.escape(s['source'])}" if s["source"] else ""))
        if toks:
            lignes.append(f"🪙 {len(toks)} token(s) déjà né(s) dessus en 48 h :")
            lignes += [f"   · {_ligne_token(t)}" for t in toks[:3]]
        else:
            lignes.append("🪙 Aucun token sur ce sujet pour l'instant.")
        lignes.append(f"<i>Les premiers tokens d'une actu meurent presque tous. Je te dis dans {SUIVI_H} h "
                      "si l'un d'eux a tenu.</i>")
        if envoyer("\n".join(lignes)):
            _etat["envois"].append(now)
        _etat["sujets"].append({"ts": now, "sujet": s["sujet"], "trafic": s["trafic"],
                                "tokens": len(toks), "suivi": False})


def suivis(envoyer):
    """6 h après : un token du sujet a-t-il tenu ?"""
    now = time.time()
    for s in _etat["sujets"]:
        if s["suivi"] or now - s["ts"] < SUIVI_H * 3600:
            continue
        s["suivi"] = True
        toks = tokens_du_sujet(s["sujet"], fenetre_h=SUIVI_H + 48)
        tiennent = [t for t in toks if t["age_h"] >= TOKEN_AGE_MIN_H and t["liq"] >= TOKEN_LIQ_MIN
                    and t["mcap"] >= TOKEN_MCAP_MIN]
        if not toks:
            continue                      # rien n'est né dessus : pas la peine de te déranger
        if tiennent:
            lignes = [f"🧭 <b>{html.escape(s['sujet'])}</b>, {SUIVI_H} h après : "
                      f"{len(tiennent)} token(s) tiennent sur {len(toks)}"]
            lignes += [f"   · {_ligne_token(t)} · {t['chg_6h']:+.0f} % sur 6 h" for t in tiennent[:3]]
            lignes.append("<i>Envoie l'adresse à Claude pour l'analyse avant d'acheter.</i>")
        else:
            lignes = [f"🧭 <b>{html.escape(s['sujet'])}</b>, {SUIVI_H} h après : aucun des "
                      f"{len(toks)} token(s) n'a tenu (liquidité ou mcap trop faible)."]
        envoyer("\n".join(lignes))


# ---------------------------------------------------------------- calendrier
def evenements():
    """Liste des événements : fichier + ajouts par /evenement, moins ceux retirés."""
    liste = []
    if CALENDRIER.exists():
        for ligne in CALENDRIER.read_text(encoding="utf-8").splitlines():
            ligne = ligne.split("#", 1)[0].strip()
            parts = [p.strip() for p in ligne.split("|")]
            if len(parts) >= 2 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
                mots = [m.strip() for m in (parts[2] if len(parts) > 2 else "").split(",") if m.strip()]
                liste.append({"date": parts[0], "nom": parts[1], "mots": mots})
    liste += _etat["ajouts"]
    retires = {_norm(n) for n in _etat["retires"]}
    return sorted([e for e in liste if _norm(e["nom"]) not in retires], key=lambda e: e["date"])


def _positions_liees(e, positions):
    mots = {_norm(m) for m in e["mots"] + [e["nom"]] if len(_norm(m)) >= 3}
    return [p["symbol"] for p in (positions or {}).values()
            if len(_norm(p.get("symbol"))) >= 3
            and any(m in _norm(p.get("symbol")) or _norm(p.get("symbol")) in m for m in mots)]


def calendrier(envoyer, positions=None):
    maintenant = datetime.now(PARIS)
    if maintenant.hour < 9:               # rappels à partir de 9 h (heure de Paris)
        return
    auj = maintenant.date()
    for e in evenements():
        try:
            jour = date.fromisoformat(e["date"])
        except ValueError:
            continue
        reste = (jour - auj).days
        if reste not in RAPPELS_J:
            continue
        cle = f"{_norm(e['nom'])}:{e['date']}:{reste}"
        if cle in _etat["rappels"]:
            continue
        _etat["rappels"][cle] = e["date"]
        quand = {0: "c'est <b>aujourd'hui</b>", 1: "c'est <b>demain</b>"}.get(reste, f"dans <b>{reste} jours</b>")
        lignes = [f"📅 <b>{html.escape(e['nom'])}</b> : {quand} ({jour.strftime('%d/%m')})"]
        liees = _positions_liees(e, positions)
        if liees:
            lignes.append("⚠️ Tu as une position liée : " + ", ".join(f"${html.escape(s)}" for s in liees)
                          + (". Ces tokens s'effondrent souvent le jour J : vends avant."
                             if reste else ". Si tu ne l'as pas encore vendue, c'est le moment."))
        elif reste == 7:
            toks = tokens_du_sujet(e["mots"][0] if e["mots"] else e["nom"], fenetre_h=24 * 30)
            if toks:
                lignes.append("🪙 Tokens sur le sujet :")
                lignes += [f"   · {_ligne_token(t)}" for t in toks[:3]]
            lignes.append("<i>La hype monte souvent à l'approche de la date, et retombe le jour J.</i>")
        envoyer("\n".join(lignes))


# ---------------------------------------------------------------- appelé par la boucle principale
def tick(envoyer, positions=None):
    for nom, f in (("calendrier", lambda: calendrier(envoyer, positions)), ("radar", lambda: radar(envoyer)),
                   ("suivis", lambda: suivis(envoyer))):
        try:
            f()
        except Exception as e:            # une source en panne ne doit rien bloquer
            print(f"[warn] actu / {nom} : {e!r}")
    sauver()


# ---------------------------------------------------------------- commandes Telegram
def cmd_actu(envoyer):
    now = time.time()
    recents = [s for s in _etat["sujets"] if now - s["ts"] < 86400]
    if not recents:
        envoyer("📰 Aucun sujet chaud repéré ces dernières 24 h.")
        return
    lignes = ["📰 <b>Sujets chauds, dernières 24 h</b>"]
    for s in sorted(recents, key=lambda s: -s["ts"]):
        h = datetime.fromtimestamp(s["ts"], PARIS).strftime("%H:%M")
        lignes.append(f"· {h} {html.escape(s['sujet'])} ({s['trafic']}+ recherches, {s['tokens']} token(s))")
    envoyer("\n".join(lignes))


def cmd_evenements(envoyer):
    auj = datetime.now(PARIS).date().isoformat()
    a_venir = [e for e in evenements() if e["date"] >= auj][:15]
    if not a_venir:
        envoyer("📅 Aucun événement à venir. Ajoute-en : <code>/evenement 2026-11-19 GTA 6 gta6,gta</code>")
        return
    lignes = ["📅 <b>Événements à venir</b>"]
    for e in a_venir:
        jour = date.fromisoformat(e["date"])
        lignes.append(f"· {jour.strftime('%d/%m/%Y')} {html.escape(e['nom'])}")
    lignes.append("Ajouter : <code>/evenement AAAA-MM-JJ Nom mots,clés</code> · retirer : <code>/oublie Nom</code>")
    envoyer("\n".join(lignes))


def cmd_evenement(args, envoyer):
    if len(args) < 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[0]):
        envoyer("Exemple : <code>/evenement 2026-11-19 GTA 6 gta6,gta</code> "
                "(date, nom, puis les mots-clés séparés par des virgules si tu veux)")
        return
    try:
        date.fromisoformat(args[0])
    except ValueError:
        envoyer("😕 Date invalide. Format : AAAA-MM-JJ, par exemple 2026-11-19.")
        return
    reste = args[1:]
    mots = []
    if len(reste) > 1 and "," in reste[-1]:
        mots = [m.strip() for m in reste.pop().split(",") if m.strip()]
    nom = " ".join(reste)
    _etat["ajouts"].append({"date": args[0], "nom": nom, "mots": mots})
    _etat["retires"] = [n for n in _etat["retires"] if _norm(n) != _norm(nom)]
    sauver()
    envoyer(f"✅ Ajouté : <b>{html.escape(nom)}</b> le {date.fromisoformat(args[0]).strftime('%d/%m/%Y')}. "
            "Rappels 7 jours avant, la veille et le jour J.")


def cmd_oublie(args, envoyer):
    nom = " ".join(args)
    if not nom:
        envoyer("Exemple : <code>/oublie Halloween</code>")
        return
    _etat["ajouts"] = [e for e in _etat["ajouts"] if _norm(e["nom"]) != _norm(nom)]
    _etat["retires"].append(nom)
    sauver()
    envoyer(f"🗑️ Plus de rappel pour <b>{html.escape(nom)}</b>.")
