"""
Smart wallets en direct (option 20, 05/11/2026).

Écoute en continu les wallets « smart » Solana du bot (liste recalculée toutes les 30 min) grâce aux
WebSockets standard de Helius, compris dans l'offre gratuite (2 crédits par 0,1 Mo reçus). Pour chaque
échange repéré, il lit la transaction (1 crédit) pour savoir quel token a été acheté ou vendu, et combien.

Chaque achat ou vente est écrit dans /home/bot/donnees/smart/AAAA-MM-JJ.jsonl. Le bot s'en sert à chaque
zone d'entrée (« smart wallets acheteurs pendant le repli ») et sur les témoins ; le tout reste pour l'étude.

Garde-fous : 12 000 lectures de transactions par jour au maximum (≈ 360 000 crédits par mois sur le
million gratuit), et un compte des données reçues dans smart_etat.json.
Tourne à part du bot (service « bot-smart ») : s'il plante, le bot continue.
"""
import asyncio
import json
import os
import time
from pathlib import Path

import requests
import websockets

import outils as v
import portefeuilles

DOSSIER = Path(os.getenv("DONNEES_DIR", "/home/bot/donnees")) / "smart"
RPC = os.getenv("SOLANA_RPC_URL", "").strip()
WS = RPC.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
LECTURES_MAX_JOUR = 12_000
LISTE_TOUTES_MIN = 30
SOL = "So11111111111111111111111111111111111111112"
IGNORES = {SOL, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",      # USDC
           "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}      # USDT
MOTS_ECHANGE = ("Instruction: Buy", "Instruction: Sell", "Instruction: Swap", "Route", "ray_log", "swap")

compteurs = {"jour": "", "lectures": 0, "octets": 0, "evenements": 0, "plafond_atteint": False}


def _jour():
    return time.strftime("%Y-%m-%d", time.gmtime())


def _compter(**kw):
    if compteurs["jour"] != _jour():
        compteurs.update(jour=_jour(), lectures=0, octets=0, evenements=0, plafond_atteint=False)
    for k, n in kw.items():
        compteurs[k] += n


def wallets_smart():
    """Adresses Solana des wallets « smart » d'après la mémoire du bot."""
    try:
        pf = json.loads(Path("alertes/portefeuilles.json").read_text())
        return sorted(k.split(":", 1)[1] for k in portefeuilles.smart(pf) if k.startswith("solana:"))
    except (OSError, ValueError, KeyError) as e:
        print(f"[warn] smart en direct : liste illisible ({type(e).__name__})")
        return []


def lire_transaction(sig):
    r = requests.post(RPC, timeout=20, json={
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}]})
    return (r.json() or {}).get("result") if r.ok else None


def echanges(tx, wallet):
    """Ce que le wallet a acheté ou vendu dans cette transaction : [(mint, +/-quantité, sol)]."""
    meta = tx.get("meta") or {}
    if meta.get("err"):
        return []
    cles = [(k.get("pubkey") if isinstance(k, dict) else k)
            for k in ((tx.get("transaction") or {}).get("message") or {}).get("accountKeys") or []]
    sol = 0.0
    if wallet in cles:
        i = cles.index(wallet)
        sol = ((meta.get("postBalances") or [0] * (i + 1))[i] - (meta.get("preBalances") or [0] * (i + 1))[i]) / 1e9
    avant, apres = {}, {}
    for src, dst in ((meta.get("preTokenBalances") or [], avant), (meta.get("postTokenBalances") or [], apres)):
        for b in src:
            if b.get("owner") != wallet:
                continue
            q = float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0)
            dst[b.get("mint")] = dst.get(b.get("mint"), 0) + q
    sol += apres.get(SOL, 0) - avant.get(SOL, 0)            # SOL « emballé » compté comme du SOL
    out = []
    for mint in set(avant) | set(apres):
        if mint in IGNORES:
            continue
        d = apres.get(mint, 0) - avant.get(mint, 0)
        if abs(d) > 0:
            out.append((mint, d, sol))
    return out


def ecrire(ev):
    DOSSIER.mkdir(parents=True, exist_ok=True)
    with open(DOSSIER / f"{_jour()}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, separators=(",", ":")) + "\n")


def ecrire_etat(n_wallets):
    v.ecrire_json(DOSSIER / "smart_etat.json",
                  {**compteurs, "wallets": n_wallets, "credits_estimes_jour":
                   round(compteurs["lectures"] + compteurs["octets"] / 1e5 * 2), "maj": round(time.time())})


async def traiter(sig, wallet, vus):
    if sig in vus:
        return
    vus[sig] = time.time()
    _compter()
    if compteurs["lectures"] >= LECTURES_MAX_JOUR:
        if not compteurs["plafond_atteint"]:
            compteurs["plafond_atteint"] = True
            print(f"[warn] smart en direct : plafond de {LECTURES_MAX_JOUR} lectures atteint pour aujourd'hui")
        return
    _compter(lectures=1)
    try:
        tx = await asyncio.to_thread(lire_transaction, sig)
    except requests.RequestException:
        return
    if not tx:
        return
    for mint, d, sol in echanges(tx, wallet):
        ecrire({"t": tx.get("blockTime") or round(time.time()), "w": wallet, "mint": mint,
                "sens": "achat" if d > 0 else "vente", "sol": round(abs(sol), 4), "sig": sig})
        _compter(evenements=1)


async def ecouter(wallets):
    """Une connexion, un abonnement par wallet ; rend la main au bout de LISTE_TOUTES_MIN pour
    recharger la liste (ou en cas de coupure)."""
    vus = {}
    async with websockets.connect(WS, ping_interval=30, ping_timeout=30, max_size=2 ** 22) as ws:
        for i, w in enumerate(wallets):
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": i + 1, "method": "logsSubscribe",
                                      "params": [{"mentions": [w]}, {"commitment": "confirmed"}]}))
        abonnement = {}
        fin = time.time() + LISTE_TOUTES_MIN * 60
        dernier_etat = 0
        while time.time() < fin:
            try:
                brut = await asyncio.wait_for(ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                continue
            _compter(octets=len(brut))
            m = json.loads(brut)
            if "id" in m and "result" in m and isinstance(m["result"], int):
                abonnement[m["result"]] = wallets[m["id"] - 1]
                continue
            if m.get("method") != "logsNotification":
                continue
            p = m.get("params") or {}
            val = ((p.get("result") or {}).get("value")) or {}
            wallet = abonnement.get(p.get("subscription"))
            if not wallet or val.get("err"):
                continue
            logs = " ".join(val.get("logs") or [])
            if any(mot in logs for mot in MOTS_ECHANGE):
                asyncio.create_task(traiter(val.get("signature"), wallet, vus))
            if time.time() - dernier_etat > 300:
                dernier_etat = time.time()
                for s in [s for s, t in vus.items() if time.time() - t > 3600]:
                    del vus[s]
                ecrire_etat(len(wallets))


async def principal():
    if not RPC:
        print("smart en direct : pas de SOLANA_RPC_URL, rien à faire")
        while True:
            await asyncio.sleep(3600)
    attente = 5
    while True:
        wallets = wallets_smart()
        print(f"smart en direct : écoute de {len(wallets)} wallets ; aujourd'hui "
              f"{compteurs['lectures']} lectures, {compteurs['evenements']} échanges, "
              f"{compteurs['octets'] / 1e6:.1f} Mo reçus")
        if not wallets:
            await asyncio.sleep(600)
            continue
        try:
            await ecouter(wallets)
            attente = 5
        except Exception as e:                  # coupure, refus… : on se reconnecte un peu plus tard
            print(f"[warn] smart en direct : {type(e).__name__} : {str(e)[:150]}")
            await asyncio.sleep(attente)
            attente = min(attente * 2, 600)


if __name__ == "__main__":
    asyncio.run(principal())
