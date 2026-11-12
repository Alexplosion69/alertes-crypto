"""Les tokens Robinhood des signaux « wallets gagnants » et de leurs jumeaux sont-ils encore échangeables
on-chain ? (liquidité active du pool Uniswap v4 + devis de revente), comparé au résultat simulé du bot."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
import outils as v        # noqa: E402
import portefeuilles      # noqa: E402
import suivi              # noqa: E402
import uniswap_rh as u    # noqa: E402

DEPUIS = 1794225600
pf = portefeuilles.charger()
st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"] and s["ts"] >= DEPUIS]
jum = [a for a in st["alerts"] if a.get("type") == "jumeau_wallets" and a.get("chain") == "robinhood"]
paires = {}
adrs = list({x["address"].lower() for x in sig + jum})
for i in range(0, len(adrs), 30):
    for p in v.get_json(f"{v.DS}/tokens/v1/robinhood/{','.join(adrs[i:i + 30])}") or []:
        a = p["baseToken"]["address"].lower()
        if (p.get("liquidity") or {}).get("usd", 0) >= paires.get(a, {}).get("liq", -1):
            paires[a] = {"pool": p.get("pairAddress"), "liq": (p.get("liquidity") or {}).get("usd", 0)}
etat = {}


def verifier(a):
    if a in etat:
        return etat[a]
    p = paires.get(a)
    if not p or not p["pool"]:
        etat[a] = "absent de DexScreener"
        return etat[a]
    pid = p["pool"].lower().replace("0x", "")
    lq, _ = u.rpc("eth_call", [{"to": "0xf3334192d15450cdd385c8b70e03f9a6bd9e673b", "data": "0xfa6793d5" + pid}, "latest"])
    liq = int(lq, 16) if lq else None
    cle = u.cle_du_pool(p["pool"])
    vente = None
    if cle:
        eth_c0 = int(cle["c0"], 16) == 0
        r, _ = u.devis(cle, not eth_c0, 10**21)
        vente = r is not None
    etat[a] = ("vivant" if vente else "mort (revente impossible)" if vente is False else "inconnu") + (
        "" if liq else ", liquidité active nulle")
    return etat[a]


for nom, groupe in (("signaux 5+ wallets", [s for s in sig if s.get("wallets", 0) >= 5]),
                    ("tous les signaux", sig), ("jumeaux", jum)):
    par = {}
    for x in groupe:
        par.setdefault(verifier(x["address"].lower()), []).append(suivi.resultat_sim_net(x))
    print(f"{nom} ({len(groupe)}) :")
    for k, r in sorted(par.items(), key=lambda z: -len(z[1])):
        print(f"   {k:45} {len(r):4} · résultat simulé moyen {sum(r) / len(r) * 100:+5.0f} %")
