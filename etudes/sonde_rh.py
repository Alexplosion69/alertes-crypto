"""Sonde : où se traitent les memecoins de Robinhood Chain, et quel service de devis sait les coter ?"""
import collections
import sys

import requests

sys.path.insert(0, ".")
import outils as v        # noqa: E402
import portefeuilles      # noqa: E402

pf = portefeuilles.charger()
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"]][-20:]
dex, labels, quotes = collections.Counter(), collections.Counter(), collections.Counter()
paires = []
for i in range(0, len(sig), 20):
    for p in v.get_json(f"{v.DS}/tokens/v1/robinhood/{','.join(s['address'] for s in sig[i:i + 20])}") or []:
        dex[p.get("dexId")] += 1
        labels[str(p.get("labels"))] += 1
        quotes[(p.get("quoteToken") or {}).get("symbol")] += 1
        paires.append(p)
print("DEX :", dict(dex), "· étiquettes :", dict(labels), "· contre :", dict(quotes))
if paires:
    p = paires[0]
    print("Exemple de paire :", p.get("pairAddress"), p.get("dexId"), p.get("url"))
tok = sig[-1]["address"]
weth = None
for p in paires:
    if (p.get("quoteToken") or {}).get("symbol") in ("WETH", "ETH"):
        weth = p["quoteToken"]["address"]
        break
print("WETH :", weth)
UA = {"User-Agent": "alertes-crypto/1.0"}
for nom, url, params in (
        ("KyberSwap", "https://aggregator-api.kyberswap.com/robinhood/api/v1/routes",
         {"tokenIn": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", "tokenOut": tok, "amountIn": str(int(2e15))}),
        ("OpenOcean", "https://open-api.openocean.finance/v4/4663/quote",
         {"inTokenAddress": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", "outTokenAddress": tok, "amountDecimals": str(int(2e15)),
          "gasPriceDecimals": "1000000"}),
        ("Odos", None, None)):
    if not url:
        continue
    try:
        r = requests.get(url, params=params, headers=UA, timeout=20)
        print(nom, r.status_code, r.text[:250])
    except Exception as e:
        print(nom, type(e).__name__)
