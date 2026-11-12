"""Sonde v4 (3) : par où passent vraiment les achats de ces tokens ? (Blockscout, dernières transactions)"""
import collections
import sys

import requests

sys.path.insert(0, ".")
import portefeuilles      # noqa: E402

BS = "https://robinhoodchain.blockscout.com/api/v2"
UA = {"User-Agent": "alertes-crypto/1.0"}
pf = portefeuilles.charger()
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"]][-3:]
for s in sig:
    try:
        d = requests.get(f"{BS}/tokens/{s['address']}/transfers", headers=UA, timeout=25).json()
    except Exception as e:
        print(s["symbol"], type(e).__name__)
        continue
    hashes = list(dict.fromkeys(x.get("transaction_hash") or x.get("tx_hash") for x in (d.get("items") or [])))[:6]
    dest = collections.Counter()
    for h in hashes:
        try:
            t = requests.get(f"{BS}/transactions/{h}", headers=UA, timeout=25).json()
        except Exception:
            continue
        to = t.get("to") or {}
        dest[(to.get("hash"), to.get("name"), t.get("method"))] += 1
    print(s["symbol"], s["address"])
    for (h, n, m), c in dest.most_common():
        print(f"   {c}× vers {h} ({n}) méthode {m}")
