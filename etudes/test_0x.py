"""Teste un devis 0x sur Robinhood Chain (la clé est lue dans bot.env, jamais affichée)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")
for l in Path("/home/bot/bot.env").read_text().splitlines():
    if l.startswith("ZEROX_API_KEY="):
        os.environ["ZEROX_API_KEY"] = l.split("=", 1)[1].strip()
import faux_ordres_rh as F  # noqa: E402
import portefeuilles        # noqa: E402

print("clé présente :", bool(F.cle()))
pf = portefeuilles.charger()
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"]][-3:]
px = F._prix({s["address"].lower() for s in sig})
for s in sig:
    p = px.get(s["address"].lower())
    if not p or not p[3]:
        print(s["symbol"], ": pas de prix DexScreener")
        continue
    wei = F.MISE_USD / p[3] * 1e18
    d = F.devis(F.ETH, s["address"], wei)
    print(f"{s['symbol']} : ETH à {p[3]:.0f} $ · devis d'achat {'OK' if d else 'refusé'}"
          + (f" · taxe {d[2]} % · frais réseau {d[1] / 1e18 * p[3]:.3f} $" if d else ""))
    if d:
        r = F.devis(s["address"], F.ETH, d[0])
        print(f"   revente immédiate : {'OK, ' + format((r[0] - r[1]) / wei - 1, '+.1%') if r else 'AUCUN CHEMIN'}")
