"""12/11 : les wallets gagnants passent leurs critères. Sous-groupes des duels, sécurité vérifiable ?, Leonida."""
import json
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, ".")
import portefeuilles  # noqa: E402
import suivi          # noqa: E402

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
pf = portefeuilles.charger()
w = [s for s in pf["signaux"] if not s["trop_tard"] and s["ts"] >= 1794225600]
jw = {}
for a in st["alerts"]:
    if a.get("type") == "jumeau_wallets":
        jw.setdefault(str(a.get("zid")), []).append(suivi.resultat_sim_net(a))
duels = [(s, suivi.resultat_sim_net(s) - sum(jw[str(int(s["ts"]))]) / len(jw[str(int(s["ts"]))]))
         for s in w if jw.get(str(int(s["ts"])))]


def ligne(nom, g):
    if not g:
        return
    ec = [e for _, e in g]
    r = sorted(suivi.resultat_sim_net(s) for s, _ in g)
    print(f"  {nom:26} {len(g):3} duels · écart moyen {sum(ec) / len(ec) * 100:+5.0f} · médian {statistics.median(ec) * 100:+4.0f} · "
          f"devant {sum(e > 0 for e in ec) / len(ec) * 100:3.0f} % · signal moyen {sum(r) / len(r) * 100:+4.0f} % "
          f"(médiane {statistics.median(r) * 100:+4.0f}, sans 3 meilleurs {(sum(r) - sum(r[-3:])) / max(len(r) - 3, 1) * 100:+4.0f})")


print(f"Duels : {len(duels)}")
ligne("tous", duels)
for n, f in (("3 wallets", lambda s: s["wallets"] == 3), ("4 wallets", lambda s: s["wallets"] == 4),
             ("5 wallets ou plus", lambda s: s["wallets"] >= 5)):
    ligne(n, [d for d in duels if f(d[0])])
for a, b in ((0, 50e3), (50e3, 100e3), (100e3, 1e12)):
    ligne(f"mcap {a / 1e3:.0f}-{b / 1e3:.0f} k$", [d for d in duels if a <= d[0]["mcap"] < b])
for h0, h1 in ((0, 8), (8, 16), (16, 24)):
    ligne(f"{h0}-{h1} h UTC", [d for d in duels if h0 <= time.gmtime(d[0]["ts"]).tm_hour < h1])
print("Signaux par jour (à temps) :", {j: sum(1 for s in w if time.strftime('%d/%m', time.gmtime(s['ts'])) == j)
                                       for j in sorted({time.strftime('%d/%m', time.gmtime(s['ts'])) for s in w})})
print("Dont 5 wallets ou plus :", sum(1 for s in w if s["wallets"] >= 5))
# GoPlus sait-il lire Robinhood Chain ?
adrs = [s["address"] for s in w if s["chain"] == "robinhood"][-5:]
for cid in ("4663", "46630"):
    try:
        r = requests.get(f"https://api.gopluslabs.io/api/v1/token_security/{cid}",
                         params={"contract_addresses": ",".join(adrs)}, timeout=20)
        d = r.json()
        res = d.get("result") or {}
        print(f"GoPlus chaîne {cid} : code {d.get('code')} {str(d.get('message'))[:60]} · {len(res)} réponse(s)")
        for k, x in list(res.items())[:3]:
            print("   ", k[:10], {c: x.get(c) for c in ("is_honeypot", "buy_tax", "sell_tax", "cannot_sell_all",
                                                    "is_open_source", "owner_change_balance", "holder_count")})
    except Exception as e:
        print("GoPlus", cid, type(e).__name__)
s_ = json.loads(Path("/home/bot/app/alertes/suivi.json").read_text())["tokens"].get(
    "solana:BWJfBNeXpapG7uoqByp5KSwWgCQba8QcDmA2DQiEpump")
if s_:
    print("Leonida :", [(time.strftime('%d/%m %H:%M', time.gmtime(p[0])), round(p[2] / 1e3)) for p in s_["serie"][-12:]])
