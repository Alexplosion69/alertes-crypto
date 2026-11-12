"""Pourquoi les signaux Robinhood morts gardent-ils un résultat positif ?"""
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
import portefeuilles  # noqa: E402
import suivi          # noqa: E402

pf = portefeuilles.charger()
sv = json.loads(Path("/home/bot/app/alertes/suivi.json").read_text())
st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
print("correction faite :", st.get("correction_morts_rh"))
sig = [s for s in pf["signaux"] if s["chain"] == "robinhood" and not s["trop_tard"] and s["ts"] >= 1794225600 and s.get("wallets", 0) >= 5]
c = collections.Counter()
for s in sig[:12]:
    e = sv["tokens"].get(s["key"])
    print(f"{str(s['symbol'])[:10]:10} suivi={'oui' if e else 'non'} mort_suivi={e.get('mort') if e else '-'} absent={e.get('absent') if e else '-'} "
          f"pair={'oui' if e and e.get('pair') else 'non'} · signal mort={s.get('mort')} zero={s.get('mort_zero')} last={s.get('last')} price={s.get('price')} "
          f"sim={s.get('sim')} → {suivi.resultat_sim_net(s)}")
for s in sig:
    e = sv["tokens"].get(s["key"])
    c[(bool(e), bool(e and e.get("mort")), bool(s.get("mort")))] += 1
print("(dans le suivi, mort au suivi, signal mort) :", dict(c))
