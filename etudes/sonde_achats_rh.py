"""Par où passent les achats des tokens « wallets gagnants » sur Robinhood Chain ? (RPC public)
Pour chaque token : ses derniers transferts → transactions → contrat appelé, méthode, contrats qui émettent
des événements, et les pools Uniswap v4 où a lieu l'échange (événement Swap du PoolManager)."""
import collections
import sys

sys.path.insert(0, ".")
import portefeuilles      # noqa: E402
import uniswap_rh as u    # noqa: E402

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SWAP_V4 = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"
CONNUS = {u.POOL_MANAGER: "Uniswap v4 PoolManager", u.POSITION_MANAGER: "Uniswap v4 PositionManager",
          "0x8876789976decbfcbbbe364623c63652db8c0904": "Uniswap UniversalRouter",
          "0x204faca1764b154221e35c0d20abb3c525710498": "Uniswap UniversalRouter 2.1.2",
          "0x000000000022d473030f116ddee9f6b43ac78ba3": "Permit2"}
bloc, err = u.rpc("eth_blockNumber", [])
bloc = int(bloc, 16)
print("bloc", bloc)
pf = portefeuilles.charger()
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"] and s.get("wallets", 0) >= 5][-4:]
appeles, emetteurs, methodes, pools = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
for s in sig:
    tok = s["address"].lower()
    logs = None
    for fenetre in (20_000, 5_000, 1_000):
        logs, err = u.rpc("eth_getLogs", [{"address": tok, "fromBlock": hex(bloc - fenetre), "toBlock": hex(bloc),
                                           "topics": [TRANSFER]}])
        if logs is not None:
            break
        print("  getLogs", fenetre, ":", err)
    if not logs:
        print(s["symbol"], ": aucun transfert récent")
        continue
    txs = list(dict.fromkeys(lg["transactionHash"] for lg in logs))[-6:]
    print(f"{s['symbol']} {tok} : {len(logs)} transferts sur la fenêtre, {len(txs)} transactions lues")
    for h in txs:
        t, _ = u.rpc("eth_getTransactionByHash", [h])
        rc, _ = u.rpc("eth_getTransactionReceipt", [h])
        if not t or not rc:
            continue
        to = (t.get("to") or "").lower()
        appeles[to] += 1
        methodes[(to, t.get("input", "")[:10])] += 1
        for lg in rc.get("logs") or []:
            a = lg["address"].lower()
            emetteurs[a] += 1
            if a == u.POOL_MANAGER and lg["topics"][0] == SWAP_V4:
                pools[(s["symbol"], lg["topics"][1])] += 1


def nom(a):
    return CONNUS.get(a, "?")


print("Contrats appelés :", [(a, nom(a), n) for a, n in appeles.most_common(8)])
print("Méthodes :", [(a[:12], m, n) for (a, m), n in methodes.most_common(8)])
print("Contrats qui émettent des événements :", [(a, nom(a), n) for a, n in emetteurs.most_common(10)])
print("Swaps Uniswap v4 (token, pool) :", [(k[0], k[1][:18], n) for k, n in pools.most_common(8)])
for (sym, pid), n in list(pools.items())[:4]:
    print("  clé du pool", sym, u.cle_du_pool(pid))
for a, _ in appeles.most_common(4):
    code, _ = u.rpc("eth_getCode", [a, "latest"])
    print("  code de", a, ":", len(code or "") // 2, "octets")
