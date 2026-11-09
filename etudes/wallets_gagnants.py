"""Le signal « 3 wallets gagnants sur le même token » depuis le 01/11 17 h UTC : par chaîne, taille, délai."""
import statistics
import sys
import time

sys.path.insert(0, ".")
import portefeuilles  # noqa: E402
import suivi          # noqa: E402

pf = portefeuilles.charger()
sig = [s for s in pf["signaux"] if s["ts"] >= 1793552400]
print(f"{len(sig)} signaux depuis le 01/11 17 h UTC, dont trop tard : {sum(s['trop_tard'] for s in sig)}, "
      f"sécurité OK : {sum(bool(s.get('securite_ok')) for s in sig)}")


def ligne(nom, g):
    g = [s for s in g if s.get("price") and (s.get("peak") or s["price"]) / s["price"] <= 50]
    if not g:
        return
    r = sorted(suivi.resultat_sim_net(s) for s in g)
    n = len(r)
    rj = [s["rejeu"]["net"] for s in g if (s.get("rejeu") or {}).get("net") is not None]
    x2 = sum(1 for s in g if (s.get("peak") or s["price"]) / s["price"] >= 2)
    print(f"  {nom:28} {n:4} · moyenne {sum(r) / n * 100:+5.0f} % · médiane {statistics.median(r) * 100:+5.0f} % · "
          f"gagnants {sum(x > 0 for x in r) / n * 100:3.0f} % · x2 {x2:3} · sans les 3 meilleurs "
          f"{(sum(r) - sum(r[-3:])) / max(n - 3, 1) * 100:+4.0f} %"
          + (f" · re-simulé ({len(rj)}) {sum(rj) / len(rj) * 100:+.0f} %" if rj else ""))


ok = [s for s in sig if not s["trop_tard"]]
print("À temps :")
ligne("tous", ok)
for ch in sorted({s["chain"] for s in ok}):
    ligne(ch, [s for s in ok if s["chain"] == ch])
print("Par taille au signal :")
for a, b in ((0, 30e3), (30e3, 100e3), (100e3, 300e3), (300e3, 1e6), (1e6, 1e12)):
    ligne(f"mcap {a / 1e3:.0f}-{b / 1e3:.0f} k$", [s for s in ok if a <= (s.get("mcap") or 0) < b])
print("Par nombre de wallets :")
for n in (3, 4, 5):
    ligne(f"{n}{'+' if n == 5 else ''} wallets", [s for s in ok if (s["wallets"] >= 5 if n == 5 else s["wallets"] == n)])
print("Avec / sans sécurité OK :")
ligne("sécurité OK", [s for s in ok if s.get("securite_ok")])
ligne("sécurité refusée", [s for s in ok if not s.get("securite_ok")])
print("Trop tard (pour comparer) :")
ligne("trop tard", [s for s in sig if s["trop_tard"]])
print("Par jour :")
for j in sorted({time.strftime('%d/%m', time.gmtime(s['ts'])) for s in ok}):
    ligne(j, [s for s in ok if time.strftime('%d/%m', time.gmtime(s['ts'])) == j])
print("Hausse déjà faite au signal (prix / entrée moyenne des wallets) :",
      [round(s["price"] / s["entree_moy"], 2) for s in ok[-25:] if s.get("entree_moy")])
s_ = portefeuilles.smart(pf)
print("Gagnants prouvés par chaîne :", {c: sum(1 for k in s_ if k.startswith(c + ":")) for c in ("bsc", "base", "robinhood", "solana")})
