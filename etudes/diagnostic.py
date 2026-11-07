"""Diagnostic du 07/11 : faux ordres aberrants, entonnoir de la stratégie Repli, avis du Filtre Claude."""
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
import suivi  # noqa: E402

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
fo = st.get("faux_ordres") or {}
print("Faux ordres fermés à l'écart aberrant :")
for x in fo.get("fermees", []):
    if x.get("papier") is not None and abs(x["papier"]) > 3:
        a = next((a for a in st["alerts"] if a.get("symbol") == x["symbol"] and abs(a["ts"] - x["ts"]) < 3600), {})
        print(f"  {x['symbol']} {x['type']} réel {x['res']:+.2f} papier {x['papier']:+.1f} ({x['raison']}) · "
              f"prix alerte {a.get('price')} mcap {a.get('mcap')} {a.get('chain')} {a.get('address')}")
OFF = 1793876400
off = [a for a in st["alerts"] if a["ts"] >= OFF]
print("Depuis le 05/11 :", dict(collections.Counter(a.get("type") for a in off)))
jetes = [a for a in off if a.get("type") == "attente_jete"]
for etape, g in sorted(collections.defaultdict(list, {e: [a for a in jetes if a.get("etape") == e]
                                                       for e in {a.get("etape") for a in jetes}}).items()):
    r = [suivi.resultat_sim_net(a) for a in g]
    print(f"  écartés à l'étape {etape} : {len(g)} · moyenne {sum(r) / len(r) * 100:+.0f} %")
print("Raisons du Filtre Claude sur les candidats Repli (dernières) :")
for a in [a for a in jetes if a.get("etape") == "Claude"][-8:]:
    print(f"  {a.get('symbol')} : {str(a.get('raison'))[:150]}")
print("Raisons des abandons en surveillance :", dict(collections.Counter(
    str(a.get("raison"))[:40] for a in jetes if a.get("etape") == "liste")))
tir = [a for a in off if a.get("type") in ("temoin", "temoin_apparie")]
print("Tirages : Filtre Claude", dict(collections.Counter(a.get("aveugle_videur", "—") for a in tir)))
print("Raisons « non » sur les tirages (échantillon) :")
for a in [a for a in tir if a.get("aveugle_videur") == "non"][-6:]:
    print(f"  {a.get('symbol')} : {str(a.get('aveugle_raison'))[:150]}")
print("En surveillance :", len(st.get("attente", {})))
