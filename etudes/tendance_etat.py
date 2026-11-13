"""Où en est la simulation « tendance grosses cryptos » (piste A) : état enregistré par le bot + ses messages
d'erreur des 3 dernières heures. Ne lit que la clé « tendance » de l'état du bot (aucune position)."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/bot/app")
st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
e = st.get("tendance")
if not e:
    print("pas encore lancée")
else:
    print(f"lancée le {time.strftime('%d/%m %H:%M', time.gmtime(e.get('debut', 0)))} UTC · jour traité "
          f"{time.strftime('%d/%m', time.gmtime(e.get('jour', 0)))} · prix mis à jour "
          f"{time.strftime('%d/%m %H:%M', time.gmtime(e.get('maj_prix', 0)))} UTC")
    for sym, a in e.get("actifs", {}).items():
        print(f"   {a['nom']:5} {'investi' if a['investi'] else 'dehors '} · prix {a['prix']:.6g} · départ {a['garder0']:.6g} · "
              f"{len(a['trades'])} trade(s) fini(s)")
    import tendance_sim
    print("\n".join(tendance_sim.bilan(st)))
out = subprocess.run(["sudo", "journalctl", "-u", "bot-crypto", "--since", "-3h", "--no-pager"],
                     capture_output=True, text=True).stdout
print("\n".join(l[:230] for l in out.splitlines() if re.search("tendance|Traceback", l))[-3000:] or "aucune erreur tendance")
