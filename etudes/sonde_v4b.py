"""Sonde v4 (2) : sens et montants qui passent, et état du pool (StateView)."""
import sys

sys.path.insert(0, ".")
import outils as v        # noqa: E402
import portefeuilles      # noqa: E402
import uniswap_rh as u    # noqa: E402

STATEVIEW = "0xf3334192d15450cdd385c8b70e03f9a6bd9e673b"
pf = portefeuilles.charger()
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"]][-3:]
for s in sig:
    p = max(v.get_json(f"{v.DS}/tokens/v1/robinhood/{s['address']}") or [{}], key=lambda x: (x.get("liquidity") or {}).get("usd") or 0)
    if not p.get("pairAddress"):
        continue
    cle = u.cle_du_pool(p["pairAddress"])
    pid = p["pairAddress"].lower().replace("0x", "")
    # getSlot0(bytes32) = c815641c ; getLiquidity(bytes32) = fa6793d5
    s0, _ = u.rpc("eth_call", [{"to": STATEVIEW, "data": "0xc815641c" + pid}, "latest"])
    lq, _ = u.rpc("eth_call", [{"to": STATEVIEW, "data": "0xfa6793d5" + pid}, "latest"])
    print(s["symbol"], cle, "· slot0", (s0 or "")[:66], "· liquidité", int(lq, 16) if lq else None,
          "· DexScreener liq", p.get("liquidity"), p.get("labels"))
    for zfo in (True, False):
        for amt in (10**9, 10**12, 10**15, 10**18):
            r, info = u.devis(cle, zfo, amt)
            print(f"   zeroForOne={zfo} montant {amt:.0e} → {r if r is not None else str(info)[:60]}")
