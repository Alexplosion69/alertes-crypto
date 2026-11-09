"""Place prise par le suivi et mémoire du serveur."""
import collections
import json
import subprocess
import time
from pathlib import Path

f = Path("/home/bot/app/alertes/suivi.json")
s = json.loads(f.read_text())
now = time.time()
toks = s["tokens"].values()
print(f"suivi.json : {f.stat().st_size / 1e6:.1f} Mo, {len(s['tokens'])} tokens")
print("Par chaîne :", dict(collections.Counter(e["chain"] for e in toks)))
print("Gardés (alerte, tirage, recrue…) :", sum(1 for e in toks if e.get("garder_jusqua", 0) > now),
      "· morts :", sum(1 for e in toks if e.get("mort")))
print("Âge des tokens (jours) :", dict(collections.Counter(min(int((now - e.get("created", now)) / 86400), 8) for e in toks)))
print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
print(subprocess.run(["bash", "-c", "ps -eo rss,cmd --sort=-rss | head -6"], capture_output=True, text=True).stdout)
