"""Historique d'un token suivi (relevés de 30 min) et ce que le bot en a noté. Adresse dans TOKEN ci-dessous."""
import json
import time
from pathlib import Path

TOKEN = "BWJfBNeXpapG7uoqByp5KSwWgCQba8QcDmA2DQiEpump"
s = json.loads(Path("/home/bot/app/alertes/suivi.json").read_text())
e = s["tokens"].get(f"solana:{TOKEN}")
if e:
    print("Créé :", time.strftime("%d/%m %H:%M UTC", time.gmtime(e["created"])), "· ajouté au suivi :",
          time.strftime("%d/%m %H:%M UTC", time.gmtime(e["ajoute"])))
    for p in e["serie"][-40:]:
        print(f"  {time.strftime('%d/%m %H:%M', time.gmtime(p[0]))} UTC · mcap {p[2] / 1e3:.0f} k$ · liq {p[3] / 1e3:.0f} k$")
st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
for a in st["alerts"]:
    if a.get("address") == TOKEN:
        print({k: a.get(k) for k in ("type", "ts", "mcap", "repli_pct", "hausse", "peak", "last", "sim", "zid",
                                     "verdict_complet", "porteurs0", "porteurs", "smart_achats", "etape", "raison")})
fo = st.get("faux_ordres") or {}
for k, p in (fo.get("ouvertes") or {}).items():
    if p.get("address") == TOKEN:
        print("Achat fictif en cours :", {x: p.get(x) for x in ("ts", "haut", "non_confirmes")})
for x in fo.get("fermees") or []:
    if x.get("symbol") == "Leonida":
        print("Achat fictif fermé :", x)
