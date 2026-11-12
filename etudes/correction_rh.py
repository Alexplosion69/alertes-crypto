"""Résultat corrigé des signaux « wallets gagnants » et de leurs jumeaux : un token mort (disparu de
DexScreener ou pool sans liquidité active) ne se revend pas à son dernier prix affiché, mais à 0."""
import json
import statistics
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
vus = {}
adrs = list({x["address"].lower() for x in sig + jum})
for i in range(0, len(adrs), 30):
    for p in v.get_json(f"{v.DS}/tokens/v1/robinhood/{','.join(adrs[i:i + 30])}") or []:
        vus[p["baseToken"]["address"].lower()] = p.get("pairAddress")
mort = {}
for a in adrs:
    if a not in vus:
        mort[a] = True
        continue
    lq, _ = u.rpc("eth_call", [{"to": "0xf3334192d15450cdd385c8b70e03f9a6bd9e673b",
                                "data": "0xfa6793d5" + vus[a].lower().replace("0x", "")}, "latest"])
    mort[a] = not (lq and int(lq, 16))


def corrige(x):
    r = suivi.resultat_sim_net(x)
    if not mort.get(x["address"].lower()):
        return r
    s = x.get("sim") or {"cash": 0.0, "moitie": False}
    frais = suivi._frais(1.0) + (suivi._frais(1.0) if s.get("moitie") else 0)
    return round(s.get("cash", 0.0) - 1.0 - frais, 2)


def resume(nom, g):
    if not g:
        return
    r, c = [suivi.resultat_sim_net(x) for x in g], sorted(corrige(x) for x in g)
    n = len(g)
    print(f"{nom:22} {n:4} · morts {sum(mort.get(x['address'].lower(), False) for x in g):4} · simulé {sum(r) / n * 100:+5.0f} % "
          f"→ corrigé {sum(c) / n * 100:+5.0f} % (médiane {statistics.median(c) * 100:+4.0f}, sans 3 meilleurs "
          f"{(sum(c) - sum(c[-3:])) / max(n - 3, 1) * 100:+4.0f})")


resume("signaux 5+ wallets", [s for s in sig if s.get("wallets", 0) >= 5])
resume("tous les signaux", sig)
resume("jumeaux", jum)
par = {}
for a in jum:
    par.setdefault(str(a.get("zid")), []).append(corrige(a))
ec = [corrige(s) - sum(par[str(int(s["ts"]))]) / len(par[str(int(s["ts"]))]) for s in sig if par.get(str(int(s["ts"])))]
if ec:
    print(f"Duels corrigés : {len(ec)} · écart moyen {sum(ec) / len(ec) * 100:+.0f} pts · médian "
          f"{statistics.median(ec) * 100:+.0f} · devant {sum(e > 0 for e in ec)}/{len(ec)}")
print("Moitié vendue à x2 avant la mort (signaux) :", sum(1 for s in sig if (s.get('sim') or {}).get('moitie')), "sur", len(sig))
