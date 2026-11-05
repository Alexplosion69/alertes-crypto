"""Aperçu du bilan du jour avec les vraies données, sans rien envoyer ni sauvegarder (lancé sur le serveur).
Ne lit JAMAIS positions.json : les journaux de GitHub sont publics, tes trades n'y apparaissent pas."""
import re
import sys

sys.path.insert(0, ".")
import alertes as A          # noqa: E402
import portefeuilles         # noqa: E402
import positions             # noqa: E402
import suivi                 # noqa: E402

positions.charger = lambda: {"offset": 0, "positions": {}, "fermees": [], "epingle": None,
                             "dernier_resume": 0, "derniere_verif": 0}
sortie = []
A.envoyer_long = lambda t: sortie.append(t) or True
A.bilan_quotidien(A.load_state(), suivi.charger(), portefeuilles.charger(), forcer=True)
print(re.sub(r"<[^>]+>", "", sortie[0]) if sortie else "rien")
