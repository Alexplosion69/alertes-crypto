"""Lignes du journal du bot sur les tirages au hasard, l'écoute des wallets et les erreurs (3 dernières heures).
Le bot n'écrit jamais tes positions dans son journal."""
import subprocess

for unite, motif in (("bot-crypto", "univers élargi|tirage au hasard|analyste|jumeaux|appari|Traceback|Error"),
                     ("bot-smart", "smart en direct|warn|Traceback")):
    out = subprocess.run(["sudo", "journalctl", "-u", unite, "--since", "-3h", "--no-pager"],
                         capture_output=True, text=True).stdout
    import re
    lignes = [l[:230] for l in out.splitlines() if re.search(motif, l)]
    print(f"--- {unite} : {len(lignes)} ligne(s)")
    print("\n".join(lignes[-25:]))
