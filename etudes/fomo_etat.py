"""Le filtre Fomo fonctionne-t-il ? Avis donnés sur les signaux des dernières 24 h, par type, et raisons des refus.
Ne lit que les alertes de l'état du bot (aucune position)."""
import json
import time
from pathlib import Path

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
r = [a for a in st.get("alerts", []) if time.time() - a["ts"] < 86400 and a.get("type") in
     ("attente", "momentum", "temoin", "temoin_apparie")]
for t in ("attente", "momentum", "temoin", "temoin_apparie"):
    g = [a for a in r if a["type"] == t]
    print(f"{t:15} {len(g):4} signaux · ok {sum(a.get('fomo_ok') is True for a in g)} · refusé "
          f"{sum(a.get('fomo_ok') is False for a in g)} · sans avis {sum(a.get('fomo_ok') is None for a in g)}")
raisons = {}
for a in r:
    if a.get("fomo_ok") is False:
        raisons[a.get("fomo_raison", "?")[:60]] = raisons.get(a.get("fomo_raison", "?")[:60], 0) + 1
for k, n in sorted(raisons.items(), key=lambda kv: -kv[1]):
    print(f"   refus : {k} ({n})")
