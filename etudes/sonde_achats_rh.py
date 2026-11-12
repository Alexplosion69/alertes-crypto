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
b1, _ = u.rpc("eth_getBlockByNumber", [hex(bloc), False])
b0, _ = u.rpc("eth_getBlockByNumber", [hex(bloc - 20_000), False])
if b1 and b0:
    print(f"20 000 blocs = {(int(b1['timestamp'], 16) - int(b0['timestamp'], 16)) / 60:.0f} min")
import outils as v  # noqa: E402
pf = portefeuilles.charger()
cands = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"]][-40:]
actifs = []
for i in range(0, len(cands), 30):
    for p_ in v.get_json(f"{v.DS}/tokens/v1/robinhood/{','.join(c['address'] for c in cands[i:i + 30])}") or []:
        h1 = (p_.get("txns") or {}).get("h1") or {}
        actifs.append((h1.get("buys", 0) + h1.get("sells", 0), p_["baseToken"]["address"], p_["baseToken"]["symbol"], p_.get("pairAddress")))
actifs.sort(reverse=True)
print("Les plus échangés sur 1 h :", [(a[2], a[0]) for a in actifs[:5]])
# DexScreener ne compte peut-être pas les échanges de ces pools : on prend les transactions chez GeckoTerminal,
# comme le bot pour repérer les wallets gagnants
v.detecter_reseaux_gt()
net = v.GT_NETWORKS.get("robinhood")
print("réseau GeckoTerminal :", net)
sig, hashes_gt = [], {}
for s_ in cands[-6:]:
    pa = next((a[3] for a in actifs if a[1].lower() == s_["address"].lower()), None)
    d = v.gt_get(f"/networks/{net}/pools/{pa}/trades") if pa and net else None
    tr = (d or {}).get("data") or []
    print(f"  {s_['symbol']} : pool {str(pa)[:14]} · {len(tr)} échanges chez GeckoTerminal"
          + (f", dernier {tr[0]['attributes'].get('block_timestamp')}" if tr else ""))
    if tr:
        hashes_gt[s_["symbol"]] = [t["attributes"].get("tx_hash") for t in tr[:5]]
        sig.append({"address": s_["address"], "symbol": s_["symbol"]})
appeles, emetteurs, methodes, pools = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
for s in sig:
    tok = s["address"].lower()
    logs = None
    for fenetre in (20_000, 5_000):
        logs, err = u.rpc("eth_getLogs", [{"address": tok, "fromBlock": hex(bloc - fenetre), "toBlock": hex(bloc),
                                           "topics": [TRANSFER]}])
        if logs is not None:
            break
        print("  getLogs", fenetre, ":", err)
    if not logs and not hashes_gt.get(s["symbol"]):
        print(s["symbol"], ": aucun transfert récent")
        continue
    logs = logs or []
    txs = hashes_gt.get(s["symbol"]) or list(dict.fromkeys(lg["transactionHash"] for lg in logs))[-6:]
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
