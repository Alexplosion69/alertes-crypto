"""Sonde v4 (4) : rejouer en devis un vrai achat (Texel, 0,07 ETH via le routeur 0xd6d3…) pour valider le Quoter."""
import sys

sys.path.insert(0, ".")
import uniswap_rh as u    # noqa: E402

TEXEL = "0x18d70f75ea98ef8a9b71d293bad3e1bf5e4945ea"
for fee, ts in ((100, 1), (0, 100), (100, 100), (0, 1)):
    cle = {"c0": "0x0000000000000000000000000000000000000000", "c1": TEXEL, "fee": fee, "ts": ts,
           "hooks": "0x0000000000000000000000000000000000000000"}
    r, info = u.devis(cle, True, 7 * 10**16)
    print(f"fee {fee} tickSpacing {ts} → {r if r is not None else str(info)[:90]}")
rc, _ = u.rpc("eth_getTransactionReceipt", ["0xd98725407e98a6987d774e689a18865ee6306135b938ccda1450227d27a548da"])
for lg in (rc or {}).get("logs", []):
    if lg["address"].lower() == u.POOL_MANAGER:
        d = lg["data"][2:]
        w = [d[i:i + 64] for i in range(0, len(d), 64)]
        print("Swap : pool", lg["topics"][1][:18], "· liquidité", int(w[3], 16), "· fee", int(w[5], 16))
        pid = lg["topics"][1]
        print("clé (PositionManager ou Initialize) :", u.cle_du_pool(pid))
        for nom, sel in (("getLiquidity", "fa6793d5"), ("getSlot0", "c815641c")):
            r_, e_ = u.rpc("eth_call", [{"to": "0xf3334192d15450cdd385c8b70e03f9a6bd9e673b", "data": "0x" + sel + pid[2:]}, "latest"])
            print("  StateView", nom, (r_ or e_)[:140])
