"""Les alertes Momentum qui passent les filtres d'évitement (+48 % au bilan du 16/11) : vraie piste ou quelques
coups chanceux ? Toutes les alertes gardées (45 jours), médiane, sans les 3 meilleurs, par moitié de période,
et comparaison avec les écartées. Ne lit que les alertes de l'état du bot (aucune position)."""
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/bot/app")
import suivi  # noqa: E402

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
mom = [a for a in st.get("alerts", []) if a.get("type") == "momentum" and "evitement" in a and a.get("sim")
       and time.time() - a["ts"] >= 86400]
print(f"Alertes Momentum notées (≥ 24 h) : {len(mom)}, du "
      f"{time.strftime('%d/%m', time.gmtime(min(a['ts'] for a in mom)))} au "
      f"{time.strftime('%d/%m', time.gmtime(max(a['ts'] for a in mom)))}")


def resume(nom, g):
    if not g:
        print(f"{nom} : aucune")
        return
    r = sorted(suivi.resultat_sim_net(a) for a in g)
    n = len(r)
    sans3 = (sum(r) - sum(r[-3:])) / (n - 3) * 100 if n > 3 else float("nan")
    morts = sum(1 for a in g if a.get("mort_zero"))
    rj = [suivi.rejeu(a, "x15") for a in g if suivi.rejeu(a, "x15") is not None]
    print(f"{nom} : {n} · moyenne {sum(r) / n * 100:+.0f} % · médiane {statistics.median(r) * 100:+.0f} % · "
          f"gagnants {sum(x > 0 for x in r) / n * 100:.0f} % · sans les 3 meilleurs {sans3:+.0f} % · morts {morts}"
          + (f" · rejeu x1,5/−30 %/12 h {sum(rj) / len(rj) * 100:+.0f} % ({len(rj)})" if rj else ""))


avec = [a for a in mom if a.get("evitement")]
sans = [a for a in mom if not a.get("evitement")]
resume("Passent l'évitement", avec)
resume("Écartées par l'évitement", sans)
mi = statistics.median(a["ts"] for a in mom)
resume("Passent, 1re moitié", [a for a in avec if a["ts"] <= mi])
resume("Passent, 2e moitié", [a for a in avec if a["ts"] > mi])
print("\nLes alertes qui passent, de la meilleure à la pire :")
for a in sorted(avec, key=lambda a: -suivi.resultat_sim_net(a)):
    print(f"   {time.strftime('%d/%m %H h', time.gmtime(a['ts']))} {str(a.get('symbol'))[:12]:12} {a.get('chain', '')[:8]:8} "
          f"mcap {(a.get('mcap') or 0) / 1e3:7.0f} k$ · plus haut x{(a.get('peak') or a['price']) / a['price']:.1f} · "
          f"résultat {suivi.resultat_sim_net(a) * 100:+.0f} %" + (" · mort" if a.get("mort_zero") else ""))
