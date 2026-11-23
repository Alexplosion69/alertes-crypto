"""Grande revue (données arrêtées le 22/11/2026 à 23 h 59, heure de Paris), critères validés à l'avance.
1) Repli contre ses jumeaux · 2) wallets gagnants contre leurs jumeaux · 3) filtres à blanc
· 4) règle de vente (rejeux en bougies de 5 min, achats fictifs au vrai prix, bilans avant/après d'événements).
Ne lit que l'état du bot, les signaux de wallets et les relevés d'événements : aucune position."""
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, ".")
import alertes as A          # noqa: E402
import portefeuilles         # noqa: E402
import suivi                 # noqa: E402

CUT = 1795388399             # 22/11/2026 23:59:59 Paris
st = A.load_state()
st["alerts"] = [a for a in st["alerts"] if a["ts"] <= CUT]
pf = portefeuilles.charger()
pf["signaux"] = [s for s in pf.get("signaux", []) if s["ts"] <= CUT]
net = suivi.resultat_sim_net


def propre(x):
    return re.sub(r"<[^>]+>", "", x)


def ok_aberrant(a):
    return not (a.get("price") and (a.get("peak") or a["price"]) / a["price"] > A.X_ABERRANT)


def resume(nom, g):
    r = sorted(net(a) for a in g)
    if not r:
        return f"   {nom} : aucun"
    sans3 = (sum(r) - sum(r[-3:])) / (len(r) - 3) * 100 if len(r) > 3 else float("nan")
    return (f"   {nom} : {len(r)} · moyenne {sum(r) / len(r) * 100:+.1f} % · médiane {statistics.median(r) * 100:+.1f} % · "
            f"gagnants {sum(x > 0 for x in r) / len(r) * 100:.0f} % · sans les 3 meilleurs {sans3:+.1f} %")


off = [a for a in st["alerts"] if a["ts"] >= A.OFFICIEL_DEPUIS and ok_aberrant(a)]
print("=== 1) Repli (depuis le 05/11 12 h) ===")
print("\n".join(propre(l) for l in A.bilan_course(st)))
zones = [a for a in off if a.get("type") == "attente"]
print(resume("signaux Repli, frais Fomo compris", zones))
tem = [a for a in off if a.get("type") == "temoin"]
print(resume("tirages au hasard, même période", tem))
fo = [x for x in (st.get("faux_ordres") or {}).get("fermees", []) if x["ts"] <= CUT]
for t in ("attente", "temoin", "temoin_apparie"):
    g = [x["res"] for x in fo if x["type"] == t]
    if g:
        print(f"   achats fictifs au vrai prix ({t}) : {len(g)} · moyenne {statistics.mean(g) * 100:+.1f} % · "
              f"médiane {statistics.median(g) * 100:+.1f} %")

print("\n=== 2) Wallets gagnants (duels depuis le 09/11 13 h) ===")
strat = lambda lst, titre: [f"{titre} : {len(lst)} signal(s)"]
print("\n".join(propre(l) for l in A.bilan_wallets(st, pf, strat)))
w = [s for s in pf["signaux"] if not s["trop_tard"] and s["ts"] >= A.JUMEAUX_W_DEPUIS]
print(resume("signaux wallets depuis le 09/11", w))
print(f"   dont Robinhood Chain : {sum(1 for s in w if s.get('chain') == 'robinhood')}")

print("\n=== 3) Filtres à blanc (tirages et jumeaux depuis le 05/11) — critère : ≥ 150 avis, « non » ≥ 10 pts sous « oui » "
      "en moyenne ET en médiane ===")
lab = tem + [a for a in off if a.get("type") == "temoin_apparie"]


def comparer(nom, oui, non):
    ro, rn = [net(a) for a in oui], [net(a) for a in non]
    n = len(ro) + len(rn)
    if not ro or not rn:
        print(f"   {nom} : {len(ro)} oui / {len(rn)} non — pas comparable")
        return
    dm = statistics.mean(ro) - statistics.mean(rn)
    dmed = statistics.median(ro) - statistics.median(rn)
    garde = n >= 150 and dm >= 0.10 and dmed >= 0.10
    print(f"   {nom} : {n} avis ({len(ro)} oui, {len(rn)} non) · oui {statistics.mean(ro) * 100:+.1f} % (méd. "
          f"{statistics.median(ro) * 100:+.1f}) · non {statistics.mean(rn) * 100:+.1f} % (méd. {statistics.median(rn) * 100:+.1f})"
          f" · écart {dm * 100:+.1f} pts / médiane {dmed * 100:+.1f} pts → {'GARDÉ' if garde else 'pas gardé'}")


comparer("Filtre Claude (avis rapide)", [a for a in lab if a.get("aveugle_videur") == "oui"],
         [a for a in lab if a.get("aveugle_videur") == "non"])
comparer("Analyse Claude (complète)", [a for a in tem if a.get("verdict_complet") == "GO"],
         [a for a in tem if a.get("verdict_complet") in ("NON", "PRUDENCE")])
comparer("Gros porteurs (« acceptable » = oui)", [a for a in lab if a.get("aveugle_concentration") == "ok"],
         [a for a in lab if a.get("aveugle_concentration") == "non"])
comparer("Wallets suivis acheteurs (6 h avant)", [a for a in lab if a.get("smart_6h")],
         [a for a in lab if "smart_6h" in a and not a.get("smart_6h")])
comparer("Filtre Fomo (depuis le 16/11)", [a for a in lab if a.get("fomo_ok") is True],
         [a for a in lab if a.get("fomo_ok") is False])
alertes7 = [a for a in st["alerts"] if a["ts"] >= A.OFFICIEL_DEPUIS]
refus_c = ([a for a in alertes7 if a.get("type") == "attente_jete" and a.get("etape") == "Claude" and ok_aberrant(a)]
           + [a for a in zones if a.get("videur") == "non"])
acc_c = [a for a in zones if a.get("videur") != "non"]
comparer("Filtre Claude sur les candidats Repli (acceptés / refusés)", acc_c, refus_c)

print("\n=== 4) Règle de vente ===")
regles = {"net": "moitié à x2, reste suivi (règle du bilan)", "x15": "tout vendu à x1,5, stop −30 %, 12 h max",
          "pos": "tes alertes de position (stop −50 %, puis −30 % du plus haut)"}
avec = sorted((a for a in off if all(suivi.rejeu(a, k) is not None for k in regles)), key=lambda a: a["ts"])
print(f"Re-simulations en bougies de 5 min (tous types de signaux depuis le 05/11) : {len(avec)}")
h = len(avec) // 2
for k, nom in regles.items():
    v = [suivi.rejeu(a, k) for a in avec]
    if v:
        print(f"   {nom:58} : moyenne {statistics.mean(v) * 100:+.1f} % · médiane {statistics.median(v) * 100:+.1f} % · "
              f"moitiés {statistics.mean(v[:h]) * 100:+.1f} / {statistics.mean(v[h:]) * 100:+.1f} %")
for t in ("attente", "temoin", "temoin_apparie", "momentum"):
    g = [a for a in avec if a.get("type") == t]
    if len(g) >= 20:
        print(f"   {t:15} ({len(g)}) : " + " · ".join(f"{k} {statistics.mean(suivi.rejeu(a, k) for a in g) * 100:+.1f} %"
                                                     for k in regles))
try:
    ev = json.loads(Path("alertes/evenements.json").read_text())
    for cle, m in (ev.get("mesures") or {}).items():
        if any(x in m["nom"].lower() for x in ("gta", "breakpoint")):
            print(f"\nAvant / après : {m['nom']} ({m['date']})")
            for k, s in m["tokens"].items():
                mc = {int(j): x for j, x in s["mcap"].items()}
                print(f"   ${str(s['symbol'])[:12]:12} " + " · ".join(f"J{j:+d} {mc[j] / 1e3:,.0f}k" for j in sorted(mc)))
except (OSError, ValueError) as e:
    print("événements illisibles :", type(e).__name__)
