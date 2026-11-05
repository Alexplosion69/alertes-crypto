"""État des données accumulées (lancé sur le serveur par le workflow « Analyse sur le serveur »).
Lit la mémoire du bot et l'enregistreur. Ne lit JAMAIS positions.json."""
import collections
import gzip
import json
import time
from pathlib import Path

APP, DON = Path("/home/bot/app/alertes"), Path("/home/bot/donnees")
st = json.loads((APP / "etat.json").read_text())
now = time.time()
OFFICIEL = 1793876400
types = collections.Counter(a.get("type", "classique") for a in st["alerts"] if a["ts"] >= OFFICIEL)
print("Depuis le 05/11 :", dict(types))
lab = [a for a in st["alerts"] if a["ts"] >= OFFICIEL and a.get("type") in ("temoin", "temoin_apparie")]
print("Étiquettes à l'aveugle :", dict(collections.Counter(a.get("aveugle_videur", "—") for a in lab)),
      "· concentration :", dict(collections.Counter(a.get("aveugle_concentration", "—") for a in lab)),
      "· GeckoTerminal :", sum(1 for a in lab if "gt_top10" in a))
s = json.loads((APP / "suivi.json").read_text())
print("Tokens suivis par le bot :", len(s["tokens"]), "· morts gardés :", sum(1 for e in s["tokens"].values() if e.get("mort")))
arch = Path("/home/bot/app/alertes/archives")
if arch.exists():
    for f in sorted(arch.glob("*.jsonl.gz")):
        with gzip.open(f, "rt") as g:
            print(f"Archive {f.name} : {sum(1 for _ in g)} élément(s)")
if DON.exists():
    for f in sorted(DON.glob("20*.jsonl.gz")):
        n, toks, t0, t1 = 0, set(), None, None
        with gzip.open(f, "rt") as g:
            for ligne in g:
                d = json.loads(ligne)
                n += 1
                toks.update(d["d"])
                t0, t1 = t0 or d["t"], d["t"]
        print(f"Enregistreur {f.name} : {n} photos, {len(toks)} tokens, {f.stat().st_size / 1e6:.1f} Mo, "
              f"de {time.strftime('%H:%M', time.gmtime(t0))} à {time.strftime('%H:%M', time.gmtime(t1))} UTC")
    print("État :", (DON / "etat.json").read_text() if (DON / "etat.json").exists() else "—")
SM = DON / "smart"
if SM.exists():
    print("Smart en direct :", (SM / "smart_etat.json").read_text() if (SM / "smart_etat.json").exists() else "—")
    for f in sorted(SM.glob("20*.jsonl"))[-2:]:
        evs = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        print(f"  {f.name} : {len(evs)} échanges, {len({e['w'] for e in evs})} wallets actifs, "
              f"{len({e['mint'] for e in evs})} tokens, achats {sum(e['sens'] == 'achat' for e in evs)}")
ms = st.get("meteora") or {}
print("Meteora simulé :", {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in ms.items()})
print("Faux ordres :", {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in (st.get("faux_ordres") or {}).items()})
