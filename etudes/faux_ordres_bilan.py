"""Point du 16/11 : les achats fictifs au vrai prix (Jupiter) après deux semaines.
Critère validé le 05/11 : wallet perso seulement si au moins 30 achats fictifs fermés et un glissement moyen
(réel − affiché) inférieur à 5 points. Ne lit que la clé « faux_ordres » de l'état du bot (aucune position)."""
import json
import statistics
import time
from pathlib import Path

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
fo = st.get("faux_ordres") or {}
f = fo.get("fermees") or []
ouv = fo.get("ouvertes") or {}
NOMS = {"attente": "signaux Repli", "temoin": "tirages au hasard", "temoin_apparie": "jumeaux"}


def pc(x):
    return f"{x * 100:+.1f}"


print(f"Fermés : {len(f)} · en cours : {len(ouv)} · devis refusés par Jupiter : {fo.get('refus', 0)}")
if f:
    print(f"Du {time.strftime('%d/%m %H h', time.gmtime(min(x['ts'] for x in f)))} au "
          f"{time.strftime('%d/%m %H h', time.gmtime(max(x['fin'] for x in f)))} UTC")
nc = sum(p.get("non_confirmes", 0) for p in ouv.values())
print(f"Objectif/stop affichés mais non confirmés par le vrai prix Jupiter (positions en cours) : {nc}")


def ecarts(g):
    ok, exclus = [], 0
    for x in g:
        if x.get("papier") is None:
            continue
        if -1 <= x["papier"] <= 9 and abs(x["res"] - x["papier"]) <= 0.5:
            ok.append(x["res"] - x["papier"])
        else:
            exclus += 1
    return ok, exclus


for nom, g in [("TOUS", f)] + [(NOMS.get(t, t), [x for x in f if x["type"] == t]) for t in NOMS]:
    if not g:
        continue
    r = [x["res"] for x in g]
    ec, exclus = ecarts(g)
    rea = [x["reaction_min"] for x in g if x.get("reaction_min") is not None]
    raisons = {}
    for x in g:
        raisons[x["raison"]] = raisons.get(x["raison"], 0) + 1
    print(f"\n== {nom} : {len(g)} fermés")
    print(f"   résultat réel : moyenne {pc(statistics.mean(r))} %, médiane {pc(statistics.median(r))} %, "
          f"gagnants {sum(v > 0 for v in r)} sur {len(r)}, pire {pc(min(r))} %, meilleur {pc(max(r))} %")
    if ec:
        print(f"   glissement réel − affiché : moyenne {statistics.mean(ec) * 100:+.1f} points, médiane "
              f"{statistics.median(ec) * 100:+.1f} points, sur {len(ec)} ordres ({exclus} écartés : prix affiché faux)")
        print(f"   part des ordres avec plus de 5 points de glissement : {sum(e < -0.05 for e in ec) / len(ec) * 100:.0f} %")
    if rea:
        print(f"   temps de réaction (alerte → devis) : médiane {statistics.median(rea):.1f} min, max {max(rea):.1f} min")
    print("   sorties : " + ", ".join(f"{k} {v}" for k, v in sorted(raisons.items(), key=lambda kv: -kv[1])))
    for k in sorted(raisons):
        rr = [x["res"] for x in g if x["raison"] == k]
        print(f"      {k} : moyenne {pc(statistics.mean(rr))} %")

print("\nPar semaine (tous types) :")
sem = {}
for x in f:
    sem.setdefault(time.strftime("%W", time.gmtime(x["ts"])), []).append(x)
for k in sorted(sem):
    g = sem[k]
    ec, _ = ecarts(g)
    print(f"   semaine {k} : {len(g)} fermés · réel {pc(statistics.mean(x['res'] for x in g))} % · glissement "
          f"{(statistics.mean(ec) * 100 if ec else 0):+.1f} points")
