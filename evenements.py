"""
Actu et événements (21/10/2026)

Deux choses :
1. Calendrier : les événements datés (GTA 6, Black Friday…) de evenements_calendrier.txt et ceux
   ajoutés avec /evenement. Rappel 14 et 7 jours avant, la veille et le jour J. Si tu as une position
   dont le nom colle à l'événement, on te rappelle de vendre avant (ces tokens s'effondrent souvent le
   jour J).
2. Radar actu : toutes les 30 min, les recherches qui montent sur Google (États-Unis, là où naissent
   la plupart des memecoins). Seules les grosses actus passent (voir RADAR_*). 6 h plus tard, on
   regarde si un token du sujet a tenu.
3. Catégorie prioritaire (31/10) : tout ce qui touche à Musk (Tesla, SpaceX, Grok…), et les mots-clés
   d'un événement du calendrier le jour J et le lendemain, passent dès 2 000 recherches, même sans
   token : avec Musk, la hype part en quelques heures (Roadster volant : pic ~4 h après la démo).
   Compteur à part, qui ne prend pas la place des autres notifs actu.

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
RADAR_TRAFIC_MIN = 20_000         # 31/10 (2) : seulement les grosses actus (10 000 laissait encore trop passer)
RADAR_TOKEN_LIQ = 10_000          # il faut AUSSI au moins un token vivant dessus (≥ 10 k$ de liquidité)
RADAR_SANS_TOKEN = 200_000        # exception : événement énorme, même sans token
RADAR_SANS_TOKEN_SPORT = 500_000  # pour le sport, il faut que ce soit gigantesque (finale de Coupe du monde)
RADAR_MAX_JOUR = 3                # pas plus de 3 notifs actu « classiques » par jour
RADAR_MAX_PASSAGE = 2             # et 2 par passage, toutes catégories (pas de rafale au démarrage)
PRIO_TRAFIC_MIN = 2_000           # Musk et événements du jour : dès 2 000 recherches, même sans token
PRIO_MAX_JOUR = 5                 # compteur à part pour cette catégorie
PRIO_EVT_JOURS = (0, 1)           # mots-clés d'un événement prioritaires le jour J et le lendemain (48 h)
MUSK = re.compile(r"\b(elon|musk|tesla|spacex|starship|starlink|xai|grok|optimus|neuralink|cybertruck|"
                  r"cybercab|robotaxi|roadster|boring company|dogecoin)\b", re.I)
MOTS_MUSK = {"elon", "musk", "tesla", "spacex", "starship", "starlink", "xai", "grok", "optimus",
             "neuralink", "cybertruck", "cybercab", "robotaxi", "roadster", "boring", "company", "dogecoin"}
SPORT = re.compile(r"espn|cbssports|bleacherreport|si\.com|nfl|nba|mlb|nhl|ncaa|/sports?/|football|"
                   r"baseball|basketball|soccer|tennis|golf|athletic|247sports|onsi|yardbarker|gmenhq",
                   re.I)
TOKEN_LIQ_VIVANT = 1_000          # sous 1 k$ de liquidité, un token est mort
SUIVI_H = 6                       # nouvelles du sujet 6 h après la notif
TOKEN_AGE_MIN_H = 3               # un token « qui tient » : au moins 3 h…
TOKEN_LIQ_MIN = 20_000            # …20 k$ de liquidité…
TOKEN_MCAP_MIN = 100_000          # …et 100 k$ de mcap
CHAINES = ("solana", "bsc", "base")
RAPPELS_J = (14, 7, 1, 0)        # 31/10 : rappel 14 jours avant, pour avoir le temps de se placer
EVT_TOKEN_LIQ = 10_000           # tokens « solides » d'un événement : 10 k$ de liquidité…
EVT_TOKEN_VOL = 5_000            # …et encore 5 k$ de volume sur 24 h (sinon personne ne le trade)
MOTS_VIDES = {"the", "and", "for", "with", "from", "this", "that", "what", "when", "where", "how",
              "who", "why", "news", "today", "live", "game", "vs", "les", "des", "une", "pour", "dans"}

_etat = {"vus": {}, "sujets": [], "rappels": {}, "ajouts": [], "retires": [], "dernier_radar": 0,
         "envois": [], "envois_prio": [], "mesures": {}}


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
    _etat["envois_prio"] = [ts for ts in _etat["envois_prio"] if now - ts < 86400]
    aujourd_hui = date.today().isoformat()
    _etat["rappels"] = {k: d for k, d in _etat["rappels"].items() if d >= aujourd_hui[:7]}
    _etat["mesures"] = {k: m for k, m in (_etat.get("mesures") or {}).items()
                        if m.get("date", "9999") >= (date.today() - timedelta(days=60)).isoformat()}
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
    """Mots qui identifient le sujet dans le nom d'un token. Pour un sujet en plusieurs mots, un
    prénom seul ne suffit pas (« brian cashman » ne doit pas trouver tous les $BRIAN) : on garde le
    sujet collé et le dernier mot (souvent le nom de famille) s'il fait au moins 5 lettres."""
    mots = [_norm(m) for m in re.split(r"[\s\-_/]+", sujet)]
    mots = [m for m in mots if len(m) >= 3 and m not in MOTS_VIDES]
    colle = _norm(sujet)
    if len(mots) <= 1:
        return [colle] if len(colle) >= 3 else []
    return [colle] + ([mots[-1]] if len(mots[-1]) >= 5 else [])


def correspond(nom, sujet):
    """Le nom (ou ticker) du token reprend-il le sujet ? Sujet collé, nom de famille, ou au moins
    deux mots du sujet (« Flying Tesla » pour « tesla flying car »)."""
    nom = _norm(nom)
    if any(m in nom for m in _mots(sujet)):
        return True
    mots = [_norm(m) for m in re.split(r"[\s\-_/]+", sujet)]
    mots = [m for m in mots if len(m) >= 3 and m not in MOTS_VIDES]
    return len(mots) >= 2 and sum(m in nom for m in mots) >= 2


def _trafic(txt):
    m = re.match(r"\s*([\d.,]+)\s*([KkMm]?)", str(txt or ""))
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1))


# ---------------------------------------------------------------- tokens liés à un sujet
def tokens_du_sujet(sujet, fenetre_h=48):
    """Tokens nés récemment dont le nom ou le ticker reprend le sujet (DexScreener)."""
    if not _mots(sujet):
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
        if not (correspond(b.get("name"), sujet) or correspond(b.get("symbol"), sujet)):
            continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if liq < TOKEN_LIQ_VIVANT:
            continue                      # token mort ou vide : il ne compte pas
        cle = f"{p['chainId']}:{b.get('address')}"
        if cle not in best or liq > best[cle]["liq"]:
            best[cle] = {"symbol": b.get("symbol"), "chain": p["chainId"], "address": b.get("address"),
                         "age_h": age_h, "liq": liq, "mcap": p.get("marketCap") or p.get("fdv") or 0,
                         "chg_6h": (p.get("priceChange") or {}).get("h6") or 0, "url": p.get("url"),
                         "vol_24h": (p.get("volume") or {}).get("h24") or 0}
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
            titres = [t for t in (n.findtext("ht:news_item_title", default="", namespaces=ns)
                                  for n in it.findall("ht:news_item", ns)) if t]
            sujets.append({
                "sujet": titre, "pays": pays, "titres": titres,
                "trafic": _trafic(it.findtext("ht:approx_traffic", default="", namespaces=ns)),
                "titre": (news.findtext("ht:news_item_title", default="", namespaces=ns) if news is not None else ""),
                "source": (news.findtext("ht:news_item_source", default="", namespaces=ns) if news is not None else ""),
                "lien": (news.findtext("ht:news_item_url", default="", namespaces=ns) if news is not None else ""),
            })
    return sujets


def _mots_distinctifs(txt):
    return {_norm(m) for m in re.split(r"[\s\-_/:,.!?'’\"]+", txt or "") if len(_norm(m)) >= 4} - MOTS_VIDES


def _deja_couvert(s, now, ignorer=frozenset()):
    """Même actu déjà envoyée en 12 h ? `ignorer` : mots trop communs dans une catégorie (pour Musk,
    « tesla » en commun ne veut pas dire « même actu » : résultats trimestriels ≠ voiture volante)."""
    mots = {_norm(m) for m in re.split(r"[\s\-_/]+", s["sujet"]) if len(_norm(m)) >= 3} - MOTS_VIDES - ignorer
    titre = _mots_distinctifs(s.get("titre")) - ignorer
    for x in _etat["sujets"]:
        if now - x["ts"] > 12 * 3600:
            continue
        if s["lien"] and s["lien"] == x.get("lien"):
            return True
        autres = {_norm(m) for m in re.split(r"[\s\-_/]+", x["sujet"]) if len(_norm(m)) >= 3} - MOTS_VIDES
        if any(len(m) >= 4 for m in mots & autres):
            return True                   # un mot distinctif en commun (« como », « trump »…) en 12 h
        if len(titre & _mots_distinctifs(x.get("titre"))) >= 4:
            return True                   # même article sous un autre nom de recherche
    return False


# ---------------------------------------------------------------- catégorie prioritaire
def _motif(mot):
    """« gta6 » doit trouver « GTA 6 », « blackfriday » « Black Friday », « jayz » « Jay-Z »,
    mais « vote » ne doit pas trouver « devoted »."""
    lettres = _norm(mot)
    return re.compile(r"\b" + r"[\s\-'.]*".join(map(re.escape, lettres)) + r"\b", re.I)


def evenements_actifs(auj=None):
    """Événements du calendrier dont c'est le jour J ou le lendemain."""
    auj = auj or datetime.now(PARIS).date()
    actifs = []
    for e in evenements():
        try:
            ecart = (auj - date.fromisoformat(e["date"])).days
        except ValueError:
            continue
        if ecart in PRIO_EVT_JOURS:
            mots = [m for m in e["mots"] + [e["nom"]] if len(_norm(m)) >= 4 and not _norm(m).isdigit()]
            actifs.append({**e, "motifs": [_motif(m) for m in mots], "ignorer": {_norm(m) for m in mots}})
    return actifs


def categorie(s, actifs):
    """('musk', None), ('evenement', e) ou (None, None). On regarde la recherche ET les titres
    d'articles : « flying car » est une actu Musk si l'article parle de Tesla."""
    texte = " ".join([s["sujet"]] + s.get("titres", []))
    if MUSK.search(texte):
        return "musk", None
    for e in actifs:
        if any(m.search(texte) for m in e["motifs"]):
            return "evenement", e
    return None, None


def radar(envoyer):
    now = time.time()
    if now - _etat["dernier_radar"] < RADAR_TOUTES_MIN * 60:
        return
    _etat["dernier_radar"] = now
    actifs = evenements_actifs()
    sujets = lire_tendances()
    for s in sujets:
        s["cat"], s["evt"] = categorie(s, actifs)
    envoyes = 0
    # catégorie prioritaire d'abord : elle ne doit pas attendre derrière une grosse actu classique
    for s in sorted(sujets, key=lambda s: (s["cat"] is None, -s["trafic"])):
        cle = _norm(s["sujet"])
        if not cle or cle in _etat["vus"]:
            continue
        if s["cat"]:
            if s["trafic"] < PRIO_TRAFIC_MIN:
                continue                  # pas encore assez gros : on le reverra s'il grossit
            if envoyes >= RADAR_MAX_PASSAGE:
                continue                  # pas marqué « vu » : repris au passage suivant (30 min)
            toks = tokens_du_sujet(s["sujet"])
            _etat["vus"][cle] = now
            ignorer = MOTS_MUSK if s["cat"] == "musk" else s["evt"]["ignorer"]
            if _deja_couvert(s, now, ignorer) or len(_etat["envois_prio"]) >= PRIO_MAX_JOUR:
                continue
        else:
            if s["trafic"] < RADAR_TRAFIC_MIN:
                continue                  # pas encore assez gros : on le reverra s'il grossit
            toks = tokens_du_sujet(s["sujet"])
            vivants = [t for t in toks if t["liq"] >= RADAR_TOKEN_LIQ]
            sport = bool(SPORT.search(f"{s['lien']} {s['source']} {s['titre']}"))
            seuil_seul = RADAR_SANS_TOKEN_SPORT if sport else RADAR_SANS_TOKEN
            if not vivants and s["trafic"] < seuil_seul:
                continue                  # aucun vrai token dessus (pour l'instant)
            _etat["vus"][cle] = now
            if _deja_couvert(s, now):
                continue                  # même actu sous un autre nom (« como vs man utd » / « como - manchester united »)
            if len(_etat["envois"]) >= RADAR_MAX_JOUR or envoyes >= RADAR_MAX_PASSAGE:
                continue
        envoyes += 1
        if envoyer(message_radar(s, toks)):
            _etat["envois_prio" if s["cat"] else "envois"].append(now)
        _etat["sujets"].append({"ts": now, "sujet": s["sujet"], "trafic": s["trafic"], "lien": s["lien"],
                                "titre": s["titre"], "cat": s["cat"], "tokens": len(toks), "suivi": False})


def message_radar(s, toks):
    trafic = f"{format(s['trafic'], ',').replace(',', ' ')}+ recherches Google, {s['pays']}"
    if s["cat"] == "musk":
        lignes = [f"🚀 <b>Musk : {html.escape(s['sujet'])}</b> ({trafic})"]
    elif s["cat"] == "evenement":
        lignes = [f"📅 <b>{html.escape(s['evt']['nom'])} : {html.escape(s['sujet'])}</b> ({trafic})"]
    else:
        lignes = [f"📰 <b>Sujet chaud : {html.escape(s['sujet'])}</b> ({trafic})"]
    if s["titre"]:
        lien = f"<a href=\"{s['lien']}\">{html.escape(s['titre'])}</a>" if s["lien"] else html.escape(s["titre"])
        lignes.append(f"🗞️ {lien}" + (f" — {html.escape(s['source'])}" if s["source"] else ""))
    if toks:
        lignes.append(f"🪙 {len(toks)} token(s) déjà né(s) dessus en 48 h :")
        lignes += [f"   · {_ligne_token(t)}" for t in toks[:3]]
    else:
        lignes.append("🪙 Aucun token sur ce sujet pour l'instant.")
    if s["cat"] == "musk":
        lignes.append("<i>Catégorie Musk : prévenu dès 2 000 recherches, c'est peut-être le début. Pour le "
                      "Roadster volant, le plus gros token a culminé ~4 h après la démo, puis −95 %. "
                      f"Les premiers tokens meurent presque tous : je te dis dans {SUIVI_H} h si l'un d'eux a tenu.</i>")
    elif s["cat"] == "evenement":
        lignes.append("<i>Jour de l'événement : prévenu dès 2 000 recherches. La hype retombe souvent le jour J, "
                      f"ne cours pas après. Je te dis dans {SUIVI_H} h si un token a tenu.</i>")
    else:
        lignes.append(f"<i>Les premiers tokens d'une actu meurent presque tous. Je te dis dans {SUIVI_H} h "
                      "si l'un d'eux a tenu.</i>")
    return "\n".join(lignes)


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


def tokens_evenement(e):
    """Tokens solides liés à un événement, quel que soit leur âge : on cherche chaque mot-clé."""
    vus, tous = set(), []
    for mot in (e["mots"] or [e["nom"]])[:4]:
        for t in tokens_du_sujet(mot, fenetre_h=24 * 365):
            cle = f"{t['chain']}:{t['address']}"
            if cle not in vus:
                vus.add(cle)
                tous.append(t)
    solides = [t for t in tous if t["liq"] >= EVT_TOKEN_LIQ and t["vol_24h"] >= EVT_TOKEN_VOL]
    return sorted(solides, key=lambda t: -t["mcap"]), len(tous)


def _ligne_evt(t):
    age = f"{t['age_h']:.0f} h" if t["age_h"] < 48 else f"{t['age_h'] / 24:.0f} j"
    return (f"<a href=\"{t['url']}\">${html.escape(str(t['symbol']))}</a> ({t['chain']}) "
            f"{_usd(t['mcap'])} · liq {_usd(t['liq'])} · vol 24 h {_usd(t['vol_24h'])} · {age}")


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
            conseil = {0: ". Ces tokens s'effondrent souvent le jour J : vends maintenant si ce n'est pas fait.",
                       1: ". Si tu ne l'as pas encore vendue, c'est le moment."}.get(
                reste, ". Prévois de vendre avant le jour J : la hype monte souvent jusqu'à quelques jours avant.")
            lignes.append("⚠️ Tu as une position liée : " + ", ".join(f"${html.escape(s)}" for s in liees) + conseil)
        if reste >= 7:
            solides, total = tokens_evenement(e)
            if solides:
                lignes.append(f"🪙 Tokens solides sur le sujet (≥ {_usd(EVT_TOKEN_LIQ)} de liquidité, encore tradés) :")
                lignes += [f"   · {_ligne_evt(t)}" for t in solides[:5]]
                lignes.append("<i>Envoie l'adresse à Claude pour l'analyse avant d'acheter.</i>")
            else:
                lignes.append(f"🪙 Aucun token solide pour l'instant ({total} petit(s) token(s) sans liquidité ni volume).")
            lignes.append("<i>La hype monte souvent à l'approche de la date, et retombe le jour J : "
                          + ("c'est le bon moment pour regarder.</i>" if reste >= 14 else "vends avant.</i>"))
        envoyer("\n".join(lignes))


# ---------------------------------------------------------------- avant / après (option 6 du plan)
MESURE_AVANT_J, MESURE_APRES_J = 10, 3     # relevé quotidien de J−10 à J+3, bilan à J+3


def mesurer(envoyer):
    """Chaque jour, la mcap des tokens solides de chaque événement proche ; à J+3, le bilan :
    la hausse se fait-elle avant (J−7 → J−1) ou après (J−1 → J+3) ?"""
    maintenant = datetime.now(PARIS)
    if maintenant.hour < 10:
        return
    auj = maintenant.date()
    mesures = _etat.setdefault("mesures", {})
    for e in evenements():
        try:
            jour = date.fromisoformat(e["date"])
        except ValueError:
            continue
        reste = (jour - auj).days
        if not -MESURE_APRES_J <= reste <= MESURE_AVANT_J:
            continue
        cle = f"{_norm(e['nom'])}:{e['date']}"
        m = mesures.setdefault(cle, {"nom": e["nom"], "date": e["date"], "tokens": {}, "fini": False})
        if m["fini"] or m.get("dernier") == auj.isoformat():
            continue
        m["dernier"] = auj.isoformat()
        solides, _ = tokens_evenement(e)
        suivis_ = m["tokens"]
        for t in solides[:5]:                  # les 5 plus gros, ajoutés une fois puis suivis
            k = f"{t['chain']}:{t['address']}"
            suivis_.setdefault(k, {"symbol": t["symbol"], "mcap": {}})
        par_cle = {f"{t['chain']}:{t['address']}": t for t in solides}
        for k, s in suivis_.items():
            t = par_cle.get(k)
            if t is None:                       # sorti des « solides » : on le cherche quand même
                d = v.get_json(f"{v.DS}/tokens/v1/{k.split(':')[0]}/{k.split(':', 1)[1]}") or []
                d = [x for x in d if x.get("marketCap") or x.get("fdv")]
                mc = max((x.get("marketCap") or x.get("fdv") or 0) for x in d) if d else 0
            else:
                mc = t["mcap"]
            s["mcap"][str(-reste)] = mc         # clé = jour relatif à l'événement (−7, 0, 3…)
        if reste == -MESURE_APRES_J:
            m["fini"] = True
            lignes = [f"📏 <b>{html.escape(e['nom'])} : la hausse s'est-elle faite avant ou après ?</b>"]
            for s in suivis_.values():
                mc = s["mcap"]
                debut = next((mc[j] for j in ("-7", "-6", "-5", "-4", "-3", "-2") if mc.get(j)), None)
                veille, apres = mc.get("-1"), mc.get(str(MESURE_APRES_J))
                def pc(a, b):
                    return f"{(b / a - 1) * 100:+.0f} %" if a and b else "?"
                lignes.append(f"   · ${html.escape(str(s['symbol']))} : avant {pc(debut, veille)} · "
                              f"après {pc(veille, apres)}")
            lignes.append("<i>« avant » = d'environ J−7 à la veille, « après » = de la veille à J+3. "
                          "Mesuré une fois par jour sur les tokens les plus gros du sujet.</i>")
            envoyer("\n".join(lignes))


# ---------------------------------------------------------------- appelé par la boucle principale
def tick(envoyer, positions=None):
    for nom, f in (("calendrier", lambda: calendrier(envoyer, positions)), ("radar", lambda: radar(envoyer)),
                   ("suivis", lambda: suivis(envoyer)), ("mesures", lambda: mesurer(envoyer))):
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
        icone = {"musk": "🚀 ", "evenement": "📅 "}.get(s.get("cat"), "")
        lignes.append(f"· {h} {icone}{html.escape(s['sujet'])} ({s['trafic']}+ recherches, {s['tokens']} token(s))")
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
            "Rappels 14 et 7 jours avant, la veille et le jour J ; le jour J et le lendemain, "
            "ses mots-clés passent en priorité dans le radar actu.")


def cmd_oublie(args, envoyer):
    nom = " ".join(args)
    if not nom:
        envoyer("Exemple : <code>/oublie Halloween</code>")
        return
    _etat["ajouts"] = [e for e in _etat["ajouts"] if _norm(e["nom"]) != _norm(nom)]
    _etat["retires"].append(nom)
    sauver()
    envoyer(f"🗑️ Plus de rappel pour <b>{html.escape(nom)}</b>.")
