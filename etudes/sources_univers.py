"""Sonde : où trouver plus de tokens installés (Solana, 24 h+, mcap 300 k$-5 M$, liquidité ≥ 50 k$ et ≥ 10 %)."""
import json
import time
from pathlib import Path

import requests

UA = {"User-Agent": "alertes-crypto/1.0", "Accept": "application/json"}
now = time.time()


def dans_cible(mcap, liq, age_h):
    return 300e3 <= (mcap or 0) <= 5e6 and (liq or 0) >= max(50e3, 0.1 * (mcap or 1)) and (age_h is None or age_h >= 24)


def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        return r.status_code, (r.json() if r.ok else r.text[:120])
    except Exception as e:
        return None, f"{type(e).__name__}"


s = json.loads(Path("/home/bot/app/alertes/suivi.json").read_text())
ok = 0
for e in s["tokens"].values():
    if e.get("chain") != "solana" or not e.get("serie"):
        continue
    p = e["serie"][-1]
    age = (now - e["created"]) / 3600 if e.get("created") else None
    ok += dans_cible(p[2], p[3] if len(p) > 3 else 0, age)
print(f"Univers actuel : {ok} tokens Solana dans la cible parmi {len(s['tokens'])} suivis")

for base in ("https://lite-api.jup.ag", "https://api.jup.ag"):
    for cat in ("toptraded", "toporganicscore", "toptrending"):
        code, d = get(f"{base}/tokens/v2/{cat}/24h?limit=100")
        if isinstance(d, list):
            n = 0
            for x in d:
                fp = (x.get("firstPool") or {}).get("createdAt")
                try:
                    age = (now - time.mktime(time.strptime(fp[:19], "%Y-%m-%dT%H:%M:%S"))) / 3600 if fp else None
                except ValueError:
                    age = None
                n += dans_cible(x.get("mcap"), x.get("liquidity"), age)
            print(f"Jupiter {base[8:]} {cat} : {code}, {len(d)} tokens, {n} dans la cible ; clés : {sorted(d[0])[:12] if d else ''}")
        else:
            print(f"Jupiter {base[8:]} {cat} : {code} {d}")

vus = set()
n = 0
for page in range(1, 6):
    time.sleep(6.5)
    code, d = get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools?page={page}&sort=h24_volume_usd_desc")
    if not isinstance(d, dict):
        print("GeckoTerminal pools :", code, d)
        break
    for p in d.get("data") or []:
        a = p["attributes"]
        tok = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
        cree = a.get("pool_created_at")
        age = (now - time.mktime(time.strptime(cree[:19], "%Y-%m-%dT%H:%M:%S"))) / 3600 if cree else None
        mc = float(a.get("market_cap_usd") or a.get("fdv_usd") or 0)
        if tok not in vus and dans_cible(mc, float(a.get("reserve_in_usd") or 0), age):
            n += 1
        vus.add(tok)
print(f"GeckoTerminal pools par volume 24 h (5 pages) : {len(vus)} tokens, {n} dans la cible")
