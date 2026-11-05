"""Pourquoi aucun wallet « smart » sur Solana ? Répartition de la base de wallets par chaîne."""
import collections, sys
sys.path.insert(0, "/home/bot/app")
import portefeuilles as P
pf = P.charger()
base = P.taux_de_base(pf)
par = collections.defaultdict(list)
for k, (n, w, _) in pf["w"].items():
    par[k.split(":", 1)[0]].append((n, w))
print(f"taux de base global : {base:.3f} · critères : au moins {P.SMART_MIN_TOKENS} tokens, "
      f"{P.SMART_MIN_BONS_COUPS} bons coups, borne de Wilson > {P.SMART_FOIS_HASARD} × base")
for ch, l in sorted(par.items(), key=lambda kv: -len(kv[1])):
    n_tot = sum(n for n, _ in l)
    taux = sum(w for _, w in l) / n_tot if n_tot else 0
    dix = [(n, w) for n, w in l if n >= P.SMART_MIN_TOKENS]
    meilleurs = sorted(((P._wilson_bas(w, n), n, w) for n, w in dix), reverse=True)[:5]
    print(f"{ch:10s} wallets {len(l):6d} · observations {n_tot:7d} · réussite {taux:.3f} · "
          f"≥ {P.SMART_MIN_TOKENS} tokens : {len(dix):5d} · meilleures bornes : "
          + ", ".join(f"{b:.2f} ({w}/{n})" for b, n, w in meilleurs))
