"""
Briques communes (copiées du projet de veille) : appels aux API gratuites,
enrichissement DexScreener, acheteurs uniques GeckoTerminal, wash trading, GoPlus.
Aucune clé, aucune donnée personnelle ici.
"""
import time

import requests

DS = "https://api.dexscreener.com"
GT = "https://api.geckoterminal.com/api/v2"   # gratuit, ~10 appels/min sans clé
GT_NETWORKS = {"solana": "solana", "base": "base", "bsc": "bsc"}
GOPLUS_CHAINS = {"bsc": "56", "base": "8453", "robinhood": "4663"}   # 4663 : Robinhood Chain (à confirmer)
# Chaînes suivies EN OBSERVATION seulement (jamais d'alerte envoyée) : Robinhood Chain, lancée en
# juillet 2026, où passe une grosse partie des memecoins tradés sur Fomo (ex. Wolfpack, x7 le 14/10).
CHAINES_OBS = ("robinhood",)
CHAINES = tuple(GT_NETWORKS) + CHAINES_OBS
_GT_ESSAIS = {"robinhood": ("robinhood", "robinhood-chain", "robinhood_chain")}
_gt_teste = set()


def detecter_reseaux_gt():
    """GeckoTerminal couvre-t-il Robinhood Chain ? On essaie une fois par exécution les noms
    possibles ; si l'un répond, la chaîne profite aussi des tendances et des acheteurs uniques."""
    for chain, essais in _GT_ESSAIS.items():
        if chain in GT_NETWORKS or chain in _gt_teste:
            continue
        _gt_teste.add(chain)
        for net in essais:
            d = gt_get(f"/networks/{net}/trending_pools")
            if d and isinstance(d.get("data"), list):
                GT_NETWORKS[chain] = net
                print(f"GeckoTerminal couvre {chain} (réseau « {net} »)")
                break
        else:
            print(f"GeckoTerminal ne couvre pas {chain} : DexScreener seulement")
UA = {"User-Agent": "alertes-crypto/1.0"}
WASH_VOL_LIQ = 20            # volume 24 h > 20x la liquidité : wash trading probable
WASH_TX_PER_BUYER = 6        # plus de 6 achats par acheteur en 1 h : bots probables

_last_gt = [0.0]

def get_json(url, headers=None, params=None):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers or UA, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code >= 400:
                print(f"[warn] {r.status_code} sur {url.split('?')[0]} : {r.text[:200]}")
                return None
            return r.json()
        except requests.RequestException as e:
            print(f"[warn] {url.split('?')[0]} -> {e}")
            time.sleep(2)
    return None


def gt_get(path):
    """GeckoTerminal sans clé : on espace les appels pour rester sous la limite."""
    wait = 6.5 - (time.time() - _last_gt[0])
    if wait > 0:
        time.sleep(wait)
    _last_gt[0] = time.time()
    return get_json(GT + path, headers={**UA, "Accept": "application/json"})


def key_of(chain, addr):
    # adresses EVM insensibles à la casse, Solana sensible
    return f"{chain}:{addr if chain == 'solana' else addr.lower()}"


def pct(new, old):
    return round((new - old) / old * 100, 1) if old else None


def enrich(cands):
    by_chain = {}
    for c in cands.values():
        by_chain.setdefault(c["chain"], []).append(c["address"])

    best = {}  # pour chaque token, la paire la plus liquide
    for chain, addrs in by_chain.items():
        for i in range(0, len(addrs), 30):
            pairs = get_json(f"{DS}/tokens/v1/{chain}/{','.join(addrs[i:i + 30])}") or []
            for p in pairs:
                k = key_of(chain, p["baseToken"]["address"])
                if k not in cands:
                    continue
                liq = (p.get("liquidity") or {}).get("usd") or 0
                if k not in best or liq > best[k][0]:
                    best[k] = (liq, p)
            time.sleep(0.3)

    return [depuis_paire(p, cands[k]) for k, (liq, p) in best.items()]


def depuis_paire(p, cand=None):
    """Transforme une paire DexScreener en token « à plat » utilisé partout dans le bot."""
    cand = cand or {"sources": [], "boost": 0}
    now_ms = time.time() * 1000
    vol = p.get("volume") or {}
    chg = p.get("priceChange") or {}
    tx = (p.get("txns") or {}).get("h1") or {}
    tx6 = (p.get("txns") or {}).get("h6") or {}
    socials = (p.get("info") or {}).get("socials") or []
    twitter = next((s.get("url") for s in socials
                    if (s.get("type") or s.get("platform")) in ("twitter", "x")), None)
    return {
        "key": key_of(p["chainId"], p["baseToken"]["address"]),
        "chain": p["chainId"],
        "address": p["baseToken"]["address"],
        "symbol": p["baseToken"].get("symbol") or "?",
        "name": p["baseToken"].get("name") or "",
        "dexscreener": p.get("url"),
        "pair": p.get("pairAddress"),
        "dex": p.get("dexId"),
        "price": float(p.get("priceUsd") or 0),
        "mcap": p.get("marketCap") or p.get("fdv") or 0,
        "liq": (p.get("liquidity") or {}).get("usd") or 0,
        "vol_1h": vol.get("h1") or 0,
        "vol_6h": vol.get("h6") or 0,
        "vol_24h": vol.get("h24") or 0,
        "chg_5m": chg.get("m5") or 0,
        "chg_1h": chg.get("h1") or 0,
        "chg_6h": chg.get("h6") or 0,
        "chg_24h": chg.get("h24") or 0,
        "buys_1h": tx.get("buys") or 0,
        "sells_1h": tx.get("sells") or 0,
        "buys_6h": tx6.get("buys") or 0,
        "sells_6h": tx6.get("sells") or 0,
        "created_ms": p.get("pairCreatedAt"),
        "age_h": round((now_ms - (p.get("pairCreatedAt") or now_ms)) / 3.6e6, 1),
        "twitter_officiel": twitter,
        "socials": socials,
        "websites": [w.get("url") for w in (p.get("info") or {}).get("websites") or [] if w.get("url")],
        "sources": cand["sources"],
        "boost": cand["boost"],
    }


def add_traders(tokens):
    """Acheteurs / vendeurs UNIQUES (GeckoTerminal) : 500 achats par 20 wallets = bots."""
    by_chain = {}
    for t in tokens:
        if t["chain"] in GT_NETWORKS and t.get("pair"):
            by_chain.setdefault(t["chain"], []).append(t)
    for chain, toks in by_chain.items():
        for i in range(0, len(toks), 30):
            batch = toks[i:i + 30]
            data = gt_get(f"/networks/{GT_NETWORKS[chain]}/pools/multi/"
                          + ",".join(t["pair"] for t in batch)) or {}
            pools = {}
            for pool in data.get("data") or []:
                a = (pool.get("attributes") or {}).get("address") or ""
                pools[a if chain == "solana" else a.lower()] = pool["attributes"]
            for t in batch:
                attr = pools.get(t["pair"] if chain == "solana" else t["pair"].lower())
                if not attr:
                    continue
                tx = attr.get("transactions") or {}
                h1, h24 = tx.get("h1") or {}, tx.get("h24") or {}
                t["acheteurs_uniques_1h"] = h1.get("buyers")
                t["vendeurs_uniques_1h"] = h1.get("sellers")
                t["acheteurs_uniques_24h"] = h24.get("buyers")
                t["vendeurs_uniques_24h"] = h24.get("sellers")
                if h1.get("buyers"):
                    t["achats_par_acheteur_1h"] = round((h1.get("buys") or 0) / h1["buyers"], 1)


def flag_wash(t):
    vl = round(t["vol_24h"] / max(t["liq"], 1), 1)
    t["volume_sur_liquidite"] = vl
    raisons = []
    if vl > WASH_VOL_LIQ:
        raisons.append(f"volume 24 h = {vl}x la liquidité")
    if (t.get("achats_par_acheteur_1h") or 0) > WASH_TX_PER_BUYER:
        raisons.append(f"{t['achats_par_acheteur_1h']} achats par acheteur en 1 h")
    t["alerte_wash_trading"] = " ; ".join(raisons) or None


def goplus(tokens):
    """Honeypot, taxes, concentration des détenteurs pour Base et BNB (RugCheck = Solana)."""
    by_chain = {}
    for t in tokens:
        if t["chain"] in GOPLUS_CHAINS:
            by_chain.setdefault(t["chain"], []).append(t)
    for chain, toks in by_chain.items():
        for t in toks:
            # un token par requête : la version gratuite ne répond pas aux requêtes groupées
            data = get_json(f"https://api.gopluslabs.io/api/v1/token_security/{GOPLUS_CHAINS[chain]}",
                            params={"contract_addresses": t["address"]}) or {}
            res = {k.lower(): v for k, v in (data.get("result") or {}).items()}
            time.sleep(1)
            r = res.get(t["address"].lower())
            if not r:
                continue
            flags = {"is_honeypot": "honeypot (impossible de revendre)",
                     "cannot_sell_all": "impossible de tout revendre",
                     "is_mintable": "le créateur peut créer des tokens",
                     "owner_change_balance": "le créateur peut modifier les soldes",
                     "hidden_owner": "propriétaire caché",
                     "transfer_pausable": "transferts bloquables",
                     "is_blacklisted": "liste noire possible",
                     "slippage_modifiable": "taxes modifiables"}
            risques = [txt for f, txt in flags.items() if str(r.get(f)) == "1"]
            # top 10 détenteurs hors pools / tokens bloqués (approximation)
            holders = [h for h in r.get("holders") or []
                       if str(h.get("is_locked")) != "1" and str(h.get("is_contract")) != "1"]
            top10 = sum(float(h.get("percent") or 0) for h in holders[:10]) * 100
            def tax(v):
                try:
                    return round(float(v) * 100, 1)
                except (TypeError, ValueError):
                    return None
            lp = r.get("lp_holders") or []
            lp_lock = sum(float(h.get("percent") or 0) for h in lp
                          if str(h.get("is_locked")) == "1"
                          or str(h.get("address", "")).lower().startswith("0x000000000000000000000000000000000000dead"))
            t["securite_evm"] = {"risques": risques,
                                 "createur": r.get("creator_address") or None,
                                 "liquidite_verrouillee_pct": round(lp_lock * 100, 1) if lp else None,
                                 "createur_detient_pct": tax(r.get("creator_percent")),
                                 "taxe_achat_pct": tax(r.get("buy_tax")),
                                 "taxe_vente_pct": tax(r.get("sell_tax")),
                                 "detenteurs": r.get("holder_count"),
                                 "top10_detenteurs_pct": round(top10, 1) if holders else None}
