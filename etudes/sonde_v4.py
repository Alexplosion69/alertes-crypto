"""Sonde : devis Uniswap v4 sur Robinhood Chain pour les derniers signaux « wallets gagnants »."""
import sys

sys.path.insert(0, ".")
import outils as v        # noqa: E402
import portefeuilles      # noqa: E402
import uniswap_rh as u    # noqa: E402

print("bloc :", u.rpc("eth_blockNumber", []), "· prix du gaz :", u.prix_gaz())
pf = portefeuilles.charger()
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"]][-8:]
for s in sig:
    paires = v.get_json(f"{v.DS}/tokens/v1/robinhood/{s['address']}") or []
    if not paires:
        print(s["symbol"], ": pas de paire")
        continue
    p = max(paires, key=lambda x: (x.get("liquidity") or {}).get("usd") or 0)
    cle = u.cle_du_pool(p["pairAddress"])
    if not cle:
        print(s["symbol"], ": pool introuvable", p["pairAddress"][:12])
        continue
    eth_usd = float(p["priceUsd"]) / float(p["priceNative"]) if p.get("priceNative") else 0
    wei = int(5.75 / eth_usd * 1e18) if eth_usd else int(2.5e15)
    eth_en_c0 = int(cle["c0"], 16) == 0
    recu, gaz = u.devis(cle, eth_en_c0, wei)
    if recu is None:
        print(f"{s['symbol']} : devis d'achat refusé ({gaz}) · clé {cle} · token {s['address']} · pool {p['pairAddress'][:14]}")
        continue
    retour, gaz2 = u.devis(cle, not eth_en_c0, recu)
    print(f"{s['symbol']} : fee {cle['fee'] / 1e4:.2f} % · hooks {'oui ' + cle['hooks'][:10] if int(cle['hooks'], 16) else 'non'} · "
          f"achat {recu} · revente immédiate "
          + (f"{retour / wei - 1:+.1%}" if retour is not None else f"REFUSÉE ({gaz2})")
          + f" · gaz ~{gaz} unités · liq {p['liquidity']['usd'] / 1e3:.0f} k$")
