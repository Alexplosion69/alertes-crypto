"""Événements récurrents (16/11) : y a-t-il un token qui monte à chaque Noël, Halloween, Saint-Valentin… ?

1) DexScreener : les tokens au nom de la fête (Solana, BSC, Base, Ethereum) encore vivants aujourd'hui
   (≥ 10 k$ de liquidité) et nés il y a plus de 10 mois, donc qui ont déjà connu au moins une fois leur fête.
2) CoinGecko (gratuit : seulement les 365 derniers jours) : pour ceux qu'il connaît, le prix autour de leur
   fête la plus récente — de J−30 à J+7 — pour voir s'ils montent avant et retombent après.
Limite : l'historique gratuit ne remonte qu'à un an, on ne peut donc pas vérifier « tous les ans ».
Données publiques, aucune clé."""
import sys
import time
from datetime import datetime, timezone

import requests

sys.stdout.reconfigure(line_buffering=True)
UA = {"User-Agent": "Mozilla/5.0 alertes-crypto/1.0"}
FETES = [("Noël", "2025-12-25", ["christmas", "xmas", "santa"]),
         ("Thanksgiving", "2025-11-27", ["thanksgiving", "turkey"]),
         ("Saint-Valentin", "2026-02-14", ["valentine"]),
         ("Halloween", "2026-10-31", ["halloween", "pumpkin", "spooky"]),
         ("Nouvel an", "2026-01-01", ["newyear"])]
CG_RESEAU = {"solana": "solana", "bsc": "binance-smart-chain", "base": "base", "ethereum": "ethereum"}


def get(url, **params):
    for _ in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
            if r.status_code == 429:
                time.sleep(30)
                continue
            return r.json() if r.ok else None
        except (requests.RequestException, ValueError):
            time.sleep(5)
    return None


now = time.time()
for nom, jour, mots in FETES:
    j0 = datetime.fromisoformat(jour).replace(tzinfo=timezone.utc).timestamp()
    vus = {}
    for m in mots:
        d = get("https://api.dexscreener.com/latest/dex/search", q=m) or {}
        for p in d.get("pairs") or []:
            b = p.get("baseToken") or {}
            if m not in (str(b.get("name")) + str(b.get("symbol"))).lower().replace(" ", ""):
                continue
            liq = (p.get("liquidity") or {}).get("usd") or 0
            cree = (p.get("pairCreatedAt") or 0) / 1000
            if p.get("chainId") not in CG_RESEAU or liq < 10_000 or not cree:
                continue
            cle = (p["chainId"], b.get("address"))
            if cle not in vus or liq > vus[cle]["liq"]:
                vus[cle] = {"sym": b.get("symbol"), "liq": liq, "cree": cree, "mcap": p.get("marketCap") or p.get("fdv") or 0}
        time.sleep(1)
    anciens = {k: t for k, t in vus.items() if now - t["cree"] > 300 * 86400}
    print(f"\n=== {nom} : {len(vus)} token(s) vivant(s) au nom de la fête, dont {len(anciens)} nés il y a plus de 10 mois")
    for (res, adr), t in sorted(anciens.items(), key=lambda kv: -kv[1]["mcap"])[:8]:
        ligne = (f"   ${str(t['sym'])[:12]:12} {res:8} né le {time.strftime('%d/%m/%Y', time.gmtime(t['cree']))} · "
                 f"mcap {t['mcap'] / 1e3:,.0f} k$ · liq {t['liq'] / 1e3:,.0f} k$")
        d = get(f"https://api.coingecko.com/api/v3/coins/{CG_RESEAU[res]}/contract/{adr}/market_chart",
                vs_currency="usd", days=365)
        time.sleep(7)
        prix = (d or {}).get("prices") or []
        if not prix:
            print(ligne + " · pas d'historique CoinGecko")
            continue
        def p_a(j):
            cible = (j0 + j * 86400) * 1000
            avant = [x for x in prix if x[0] <= cible]
            return avant[-1][1] if avant and cible - avant[-1][0] < 3 * 86400_000 else None
        p30, p7, p0, p7b = p_a(-30), p_a(-7), p_a(0), p_a(7)
        fen = [x for x in prix if j0 - 30 * 86400 <= x[0] / 1000 <= j0 + 7 * 86400]
        if not (p30 and p0 and fen):
            print(ligne + " · historique trop court autour de la fête")
            continue
        haut = max(fen, key=lambda x: x[1])
        jh = round((haut[0] / 1000 - j0) / 86400)
        an = [x[1] for x in prix]
        print(ligne + f" · J−30 → J : {(p0 / p30 - 1) * 100:+.0f} %"
              + (f" (J−7 → J : {(p0 / p7 - 1) * 100:+.0f} %)" if p7 else "")
              + (f" · J → J+7 : {(p7b / p0 - 1) * 100:+.0f} %" if p7b else "")
              + f" · plus haut de la période à J{jh:+d} · sur l'année : de {min(an):.3g} à {max(an):.3g} $")
