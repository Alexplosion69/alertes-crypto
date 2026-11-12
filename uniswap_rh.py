"""
Uniswap v4 sur Robinhood Chain (12/11/2026), en lecture seule : retrouver le pool d'un token et demander
au contrat « Quoter » d'Uniswap le prix exact d'un échange, sans rien acheter (eth_call).
Adresses : https://developers.uniswap.org/docs/protocols/v4/deployments (chaîne 4663).
"""
import os

import requests

RPC = os.getenv("ROBINHOOD_RPC_URL", "").strip() or "https://rpc.mainnet.chain.robinhood.com"
POOL_MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
POSITION_MANAGER = "0x58daec3116aae6d93017baaea7749052e8a04fa7"
QUOTER = "0x8dc178efb8111bb0973dd9d722ebeff267c98f94"
SEL_QUOTE = "aa9d21cb"          # quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))
SEL_POOLKEYS = "86b6be7d"       # poolKeys(bytes25)
TOPIC_INIT = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"   # Initialize(...)
UA = {"User-Agent": "alertes-crypto/1.0"}


def rpc(methode, params):
    try:
        r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": methode, "params": params},
                          headers=UA, timeout=20)
        d = r.json()
    except (requests.RequestException, ValueError):
        return None, "réseau"
    if "error" in d:
        e = d["error"]
        return None, (str(e.get("message", ""))[:80] + (" " + str(e.get("data"))[:400] if e.get("data") else ""))
    return d.get("result"), None


def _mot(x):
    return format(x % (1 << 256), "064x")


def _adr(a):
    return a.lower().replace("0x", "").rjust(64, "0")


def cle_du_pool(pool_id):
    """PoolKey (currency0, currency1, fee, tickSpacing, hooks) d'un pool v4 à partir de son identifiant
    (l'adresse de paire de DexScreener). D'abord le PositionManager, sinon l'événement Initialize."""
    pid = pool_id.lower().replace("0x", "")
    res, _ = rpc("eth_call", [{"to": POSITION_MANAGER, "data": "0x" + SEL_POOLKEYS + pid[:50].ljust(64, "0")}, "latest"])
    if res and len(res) >= 2 + 64 * 5 and int(res[2:], 16):
        m = [res[2 + 64 * i: 2 + 64 * (i + 1)] for i in range(5)]
        ts = int(m[3], 16)
        return {"c0": "0x" + m[0][24:], "c1": "0x" + m[1][24:], "fee": int(m[2], 16),
                "ts": ts - (1 << 256) if ts >= 1 << 255 else ts, "hooks": "0x" + m[4][24:]}
    logs, err = rpc("eth_getLogs", [{"address": POOL_MANAGER, "fromBlock": "0x0", "toBlock": "latest",
                                     "topics": [TOPIC_INIT, "0x" + pid]}])
    if not logs:
        return None
    lg = logs[0]
    data = lg["data"][2:]
    m = [data[64 * i: 64 * (i + 1)] for i in range(len(data) // 64)]
    ts = int(m[1], 16)
    return {"c0": "0x" + lg["topics"][2][-40:], "c1": "0x" + lg["topics"][3][-40:], "fee": int(m[0], 16),
            "ts": ts - (1 << 256) if ts >= 1 << 255 else ts, "hooks": "0x" + m[2][24:]}


def devis(cle, zero_pour_un, montant):
    """Quantité reçue pour `montant` (unités brutes) : zero_pour_un=True vend currency0 (l'ETH), False vend
    currency1 (le token). Renvoie (reçu, gaz estimé) ou (None, raison)."""
    data = ("0x" + SEL_QUOTE + _mot(0x20) + _adr(cle["c0"]) + _adr(cle["c1"]) + _mot(cle["fee"]) + _mot(cle["ts"])
            + _adr(cle["hooks"]) + _mot(1 if zero_pour_un else 0) + _mot(int(montant)) + _mot(0x100) + _mot(0))
    res, err = rpc("eth_call", [{"to": QUOTER, "data": data}, "latest"])
    if not res or len(res) < 2 + 128:
        return None, err or "réponse vide"
    return int(res[2:66], 16), int(res[66:130], 16)


def prix_gaz():
    res, _ = rpc("eth_gasPrice", [])
    return int(res, 16) if res else 0
