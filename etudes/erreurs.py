"""Les plantages du bot (Traceback) des 6 dernières heures, avec les lignes qui suivent, pour savoir d'où ils viennent.
Le bot n'écrit jamais tes positions dans son journal."""
import subprocess

for unite in ("bot-crypto", "bot-smart", "bot-enregistreur"):
    out = subprocess.run(["sudo", "journalctl", "-u", unite, "--since", "-6h", "--no-pager"],
                         capture_output=True, text=True).stdout.splitlines()
    idx = [i for i, l in enumerate(out) if "Traceback" in l]
    print(f"--- {unite} : {len(idx)} plantage(s)")
    for i in idx[-3:]:
        print("\n".join(l[:230] for l in out[max(0, i - 2):i + 14]))
        print("   …")
