"""Ce que le bot a déjà mesuré sur les événements du calendrier : mcap des plus gros tokens du sujet, jour par
jour de J−10 à J+3 (module evenements, « avant / après »), et les sujets du radar actu suivis 6 h après.
Ne lit que alertes/evenements.json (aucune position)."""
import json
from pathlib import Path

e = json.loads(Path("/home/bot/app/alertes/evenements.json").read_text())
print("Clés :", sorted(e.keys()))
for cle, m in (e.get("mesures") or {}).items():
    print(f"\n=== {m['nom']} ({m['date']}) · fini : {m.get('fini')} · dernier relevé {m.get('dernier')}")
    for k, s in m["tokens"].items():
        mc = s["mcap"]
        jours = sorted(mc, key=int)
        print(f"   ${str(s['symbol'])[:14]:14} {k.split(':')[0]:7} " + " · ".join(f"J{int(j):+d} {mc[j] / 1e3:,.0f}k" for j in jours))
suiv = e.get("suivis") or e.get("radar") or {}
print(f"\nRadar actu : {len(suiv)} sujet(s) enregistrés")
for k, s in list(suiv.items())[-40:] if isinstance(suiv, dict) else []:
    print("  ", k, json.dumps(s, ensure_ascii=False)[:260])
