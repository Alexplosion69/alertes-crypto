"""État de la simulation « fin de mois » et avertissements récents du bot à son sujet.
Ne lit que la clé « fin_de_mois » de l'état du bot (aucune position)."""
import json
import re
import subprocess
from pathlib import Path

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
print(json.dumps(st.get("fin_de_mois"), ensure_ascii=False, indent=1))
out = subprocess.run(["sudo", "journalctl", "-u", "bot-crypto", "--since", "-1h", "--no-pager"],
                     capture_output=True, text=True).stdout
print("\n".join(l[:230] for l in out.splitlines() if re.search("fin de mois|Traceback", l)) or "aucun avertissement")
import time
print("état écrit il y a", round(time.time() - Path("/home/bot/app/alertes/etat.json").stat().st_mtime), "s ;",
      "tendance contrôlée le", (st.get("tendance") or {}).get("maj_prix"))
print("\n".join(l[:200] for l in out.splitlines()[-12:]))
