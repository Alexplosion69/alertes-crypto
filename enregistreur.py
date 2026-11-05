"""
Enregistreur (05/11/2026) : la mémoire longue du projet.

Toutes les 3 minutes, une « photo » de chaque token que le bot suit (prix, mcap, liquidité, volumes,
achats et ventes, variations), gardée POUR TOUJOURS dans /home/bot/donnees/AAAA-MM-JJ.jsonl.gz.
Un token que le bot lâche reste photographié encore 3 jours, pour voir s'il meurt ou repart : pas de
biais du survivant.

Pourquoi : le bot ne garde que 30 min de résolution, 7 jours d'historique et 30 jours d'alertes. Avec ces
photos, on peut rejouer après coup n'importe quelle règle d'entrée, de sortie ou de filtre, sur tous les
tokens, sans dépendre de GeckoTerminal (lent) ni attendre de nouveaux signaux.

Tourne à part du bot (service « bot-enregistreur ») : s'il plante, le bot continue. Ne lit jamais
positions.json. Environ 10 à 20 Mo par jour ; s'arrête d'écrire s'il reste moins de 1,5 Go de disque.
"""
import gzip
import json
import os
import shutil
import time
from pathlib import Path

import outils as v

DOSSIER = Path(os.getenv("DONNEES_DIR", "/home/bot/donnees"))
PAS_MIN = 3
APRES_DEPART_H = 72
ALERTES_JOURS = 7
DISQUE_MIN_GO = 1.5
SUIVI = Path("alertes/suivi.json")
ETAT = Path("alertes/etat.json")
COLONNES = ["prix", "mcap", "liq", "liq_totale", "vol_m5", "vol_h1", "vol_h24", "achats_m5", "ventes_m5",
            "achats_h1", "ventes_h1", "var_m5", "var_h1", "var_h24", "boosts"]


def lire(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def a_photographier(memo):
    """Tokens suivis par le bot + tokens alertés depuis 7 jours (zones, témoins…) ; on garde chacun
    encore 3 jours après sa dernière apparition."""
    now = time.time()
    s = lire(SUIVI) or {}
    for k, e in (s.get("tokens") or {}).items():
        if e.get("address"):
            memo[k] = {"chain": e["chain"], "address": e["address"], "vu": now,
                       "info": memo.get(k, {}).get("info", False)}
    st = lire(ETAT) or {}
    for a in st.get("alerts") or []:
        if a.get("address") and now - a.get("ts", 0) < ALERTES_JOURS * 86400:
            m = memo.setdefault(a["key"], {"chain": a["chain"], "address": a["address"], "info": False})
            m["vu"] = now
    for k in [k for k, m in memo.items() if now - m.get("vu", 0) > APRES_DEPART_H * 3600]:
        del memo[k]


def photo(memo):
    """Une passe DexScreener (30 tokens par appel) ; renvoie {clé: valeurs} et les fiches à écrire."""
    par_chaine = {}
    for k, m in memo.items():
        par_chaine.setdefault(m["chain"], []).append(m["address"])
    meilleures, totales = {}, {}
    for chaine, adrs in par_chaine.items():
        for i in range(0, len(adrs), 30):
            for p in v.get_json(f"{v.DS}/tokens/v1/{chaine}/{','.join(adrs[i:i + 30])}") or []:
                try:
                    k = v.key_of(chaine, p["baseToken"]["address"])
                except (KeyError, TypeError):
                    continue
                if k not in memo:
                    continue
                liq = (p.get("liquidity") or {}).get("usd") or 0
                totales[k] = totales.get(k, 0) + liq
                if k not in meilleures or liq > ((meilleures[k].get("liquidity") or {}).get("usd") or 0):
                    meilleures[k] = p
            time.sleep(0.25)
    lignes, fiches = {}, []
    for k, p in meilleures.items():
        vol, chg, tx = p.get("volume") or {}, p.get("priceChange") or {}, p.get("txns") or {}
        m5, h1 = tx.get("m5") or {}, tx.get("h1") or {}
        try:
            prix = float(p.get("priceUsd") or 0)
        except (TypeError, ValueError):
            continue
        lignes[k] = [float(f"{prix:.6g}"), round(p.get("marketCap") or p.get("fdv") or 0),
                     round((p.get("liquidity") or {}).get("usd") or 0), round(totales.get(k, 0)),
                     round(vol.get("m5") or 0), round(vol.get("h1") or 0), round(vol.get("h24") or 0),
                     m5.get("buys") or 0, m5.get("sells") or 0, h1.get("buys") or 0, h1.get("sells") or 0,
                     chg.get("m5") or 0, chg.get("h1") or 0, chg.get("h24") or 0,
                     ((p.get("boosts") or {}).get("active") or 0)]
        if not memo[k].get("info"):
            memo[k]["info"] = True
            info = p.get("info") or {}
            fiches.append({"key": k, "chain": p.get("chainId"), "address": p["baseToken"].get("address"),
                           "symbol": p["baseToken"].get("symbol"), "name": p["baseToken"].get("name"),
                           "pair": p.get("pairAddress"), "dex": p.get("dexId"), "labels": p.get("labels"),
                           "creee_ms": p.get("pairCreatedAt"), "url": p.get("url"),
                           "sites": len(info.get("websites") or []), "reseaux": len(info.get("socials") or []),
                           "vu_le": round(time.time())})
    return lignes, fiches


def etat(memo, dernier):
    fichiers = sorted(DOSSIER.glob("20*.jsonl.gz"))
    taille = sum(f.stat().st_size for f in DOSSIER.glob("*") if f.is_file()) / 1e6
    v.ecrire_json(DOSSIER / "etat.json", {"jours": len(fichiers), "tokens": len(memo), "pas_min": PAS_MIN,
                                          "taille_mo": round(taille, 1), "dernier": round(dernier),
                                          "premier_jour": fichiers[0].name[:10] if fichiers else None})


def boucle():
    DOSSIER.mkdir(parents=True, exist_ok=True)
    memo = lire(DOSSIER / "memo.json") or {}
    print(f"enregistreur : démarrage, {len(memo)} token(s) en mémoire, une photo toutes les {PAS_MIN} min")
    n = 0
    while True:
        t0 = time.time()
        try:
            libre_go = shutil.disk_usage(DOSSIER).free / 1e9
            a_photographier(memo)
            if libre_go < DISQUE_MIN_GO:
                print(f"[warn] enregistreur : plus que {libre_go:.1f} Go libres, photo non écrite")
            else:
                lignes, fiches = photo(memo)
                jour = time.strftime("%Y-%m-%d", time.gmtime(t0))
                with gzip.open(DOSSIER / f"{jour}.jsonl.gz", "at", encoding="utf-8") as f:
                    f.write(json.dumps({"t": round(t0), "c": COLONNES, "d": lignes}, separators=(",", ":")) + "\n")
                if fiches:
                    with open(DOSSIER / "tokens.jsonl", "a", encoding="utf-8") as f:
                        for x in fiches:
                            f.write(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n")
                v.ecrire_json(DOSSIER / "memo.json", memo, separators=(",", ":"))
                n += 1
                if n % 20 == 1:
                    etat(memo, t0)
                    print(f"enregistreur : {len(lignes)} tokens photographiés sur {len(memo)} "
                          f"en {time.time() - t0:.0f} s, {libre_go:.1f} Go libres")
        except Exception as e:                 # une erreur d'API ne doit pas arrêter l'enregistrement
            print(f"[warn] enregistreur : {type(e).__name__} : {str(e)[:120]}")
        time.sleep(max(5, PAS_MIN * 60 - (time.time() - t0)))


if __name__ == "__main__":
    boucle()
