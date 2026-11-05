"""Liste des wallets « smart » vue par le bot (diagnostic de l'écoute en direct)."""
import collections, json, sys
from pathlib import Path
sys.path.insert(0, "/home/bot/app")
import portefeuilles
pf = portefeuilles.charger()
s = portefeuilles.smart(pf)
print("wallets dans la base :", len(pf["w"]), "· smart :", len(s), "· taux de base :", round(portefeuilles.taux_de_base(pf), 3))
print("par chaîne :", dict(collections.Counter(k.split(":", 1)[0] for k in s)))
print("exemples :", [k[:20] + "…" for k in sorted(s)[:5]])
print("fichier lu :", portefeuilles.FICHIER.resolve())
