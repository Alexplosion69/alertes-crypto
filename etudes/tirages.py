"""Tirages au hasard depuis le 05/11 midi : à quelles heures, ce qu'en a dit le Filtre Claude, et le journal."""
import json
import re
import subprocess
import time
from pathlib import Path

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
tir = [a for a in st["alerts"] if a["ts"] >= 1793876400 and a.get("type") in ("temoin", "temoin_apparie")]
print(f"{len(tir)} tirage(s) depuis le 05/11 12 h :")
for a in tir:
    print(f"  {time.strftime('%d/%m %H:%M', time.gmtime(a['ts']))} UTC {a['type']:15} {str(a.get('symbol'))[:12]:12} "
          f"filtre={a.get('aveugle_videur', '—')} · {str(a.get('aveugle_raison', ''))[:110]}")
out = subprocess.run(["sudo", "journalctl", "-u", "bot-crypto", "--since", "-20h", "--no-pager"],
                     capture_output=True, text=True).stdout
lignes = [l[:250] for l in out.splitlines() if re.search(r"tirage au hasard|\[warn\] (étiquettes|analyste)", l)]
print(f"--- journal : {len(lignes)} ligne(s)")
print("\n".join(lignes))
