"""Filtre « achetable sur Fomo » (16/11) : Alex reçoit des tokens que Fomo n'affiche pas ou marque comme
arnaque. Que disent aujourd'hui les sources publiques (Jupiter, RugCheck, GoPlus) sur les tokens des signaux
récents, et ces drapeaux séparent-ils les gagnants des perdants ?
Attention : c'est l'état ACTUEL des tokens (un token mort depuis peut paraître pire qu'au moment du signal).
Ne lit que les alertes de l'état du bot (aucune position)."""
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/bot/app")
import outils as v  # noqa: E402
import suivi  # noqa: E402

st = json.loads(Path("/home/bot/app/alertes/etat.json").read_text())
TYPES = {"attente": "Repli", "momentum": "Momentum", "temoin": "hasard"}
derniers = {}
for a in st.get("alerts", []):
    if a.get("type") in TYPES and a.get("sim") and a.get("chain") in ("solana", "bsc") \
            and 86400 <= time.time() - a["ts"] <= 15 * 86400:
        derniers[(a["type"], a["key"])] = a                 # le plus récent signal par type et token
alertes = list(derniers.values())
print(f"{len(alertes)} signaux récents (1 par token et par type) : "
      + ", ".join(f"{TYPES[t]} {sum(a['type'] == t for a in alertes)}" for t in TYPES))

# ---------------------------------------------------------------- Jupiter (Solana)
sol = sorted({a["address"] for a in alertes if a["chain"] == "solana"})
jup = {}
for i in range(0, len(sol), 50):
    d = v.get_json("https://lite-api.jup.ag/tokens/v2/search", params={"query": ",".join(sol[i:i + 50])}) or []
    for x in d if isinstance(d, list) else []:
        jup[x.get("id")] = x
    time.sleep(1)
cles_audit = set()
for x in jup.values():
    cles_audit |= set((x.get("audit") or {}).keys())
print(f"Jupiter connaît {len(jup)} tokens Solana sur {len(sol)} · champs « audit » vus : {sorted(cles_audit)}")

# ---------------------------------------------------------------- RugCheck (Solana) et GoPlus (BSC)
rc = {}
for adr in sol:
    d = v.get_json(f"https://api.rugcheck.xyz/v1/tokens/{adr}/report/summary") or {}
    rc[adr] = d
    time.sleep(0.4)
gp = {}
for adr in sorted({a["address"] for a in alertes if a["chain"] == "bsc"}):
    d = v.get_json("https://api.gopluslabs.io/api/v1/token_security/56", params={"contract_addresses": adr}) or {}
    gp[adr] = {k.lower(): x for k, x in (d.get("result") or {}).items()}.get(adr.lower()) or {}
    time.sleep(1)


def drapeaux(a):
    f = []
    if a["chain"] == "solana":
        j = jup.get(a["address"])
        if not j:
            f.append("inconnu de Jupiter")
        else:
            au = j.get("audit") or {}
            if au.get("isSus"):
                f.append("Jupiter : suspect")
            if not j.get("isVerified"):
                f.append("non vérifié")
            f.append(f"score organique {j.get('organicScoreLabel') or '?'}")
            if (au.get("topHoldersPercentage") or 0) > 30:
                f.append(f"top détenteurs {au['topHoldersPercentage']:.0f} %")
            if (au.get("devBalancePercentage") or 0) > 5:
                f.append(f"dev {au['devBalancePercentage']:.0f} %")
            if au.get("mintAuthorityDisabled") is False or au.get("freezeAuthorityDisabled") is False:
                f.append("mint/gel actif")
        r = rc.get(a["address"]) or {}
        dang = [x.get("name") for x in r.get("risks") or [] if x.get("level") == "danger"]
        if dang:
            f.append("RugCheck danger : " + ", ".join(dang[:2]))
        if r.get("rugged"):
            f.append("RugCheck : rugged")
    else:
        g = gp.get(a["address"]) or {}
        if not g:
            f.append("inconnu de GoPlus")
        for k, nom in (("is_honeypot", "honeypot"), ("cannot_sell_all", "revente bloquée"), ("hidden_owner", "propriétaire caché"),
                       ("owner_change_balance", "soldes modifiables"), ("is_blacklisted", "liste noire"),
                       ("slippage_modifiable", "taxes modifiables"), ("fake_token", "faux token")):
            if str(g.get(k)) == "1":
                f.append(nom)
        if g and str(g.get("is_open_source")) == "0":
            f.append("code caché")
        if g and str(g.get("is_in_dex")) == "0":
            f.append("pas sur un DEX")
        try:
            if float(g.get("sell_tax") or 0) > 0.05:
                f.append(f"taxe vente {float(g['sell_tax']) * 100:.0f} %")
        except ValueError:
            pass
    return f


def resume(nom, g):
    if not g:
        return
    r = sorted(suivi.resultat_sim_net(a) for a in g)
    n = len(r)
    print(f"   {nom:42} {n:4} · moyenne {sum(r) / n * 100:+5.0f} % · médiane {statistics.median(r) * 100:+5.0f} % · "
          f"gagnants {sum(x > 0 for x in r) / n * 100:3.0f} %" + (f" · sans les 3 meilleurs {(sum(r) - sum(r[-3:])) / (n - 3) * 100:+.0f} %" if n > 5 else ""))


for a in alertes:
    a["_f"] = drapeaux(a)
print("\nRésultats selon les drapeaux (tous types confondus) :")
grave = lambda a: any(x.startswith(("Jupiter : suspect", "RugCheck", "inconnu", "honeypot", "revente", "propriétaire",
                                     "soldes", "liste noire", "taxes modifiables", "faux token", "code caché",
                                     "pas sur un DEX")) for x in a["_f"])
resume("aucun drapeau grave", [a for a in alertes if not grave(a)])
resume("au moins un drapeau grave", [a for a in alertes if grave(a)])
for lab in ("Jupiter : suspect", "non vérifié", "inconnu de Jupiter", "RugCheck danger", "RugCheck : rugged",
            "score organique high", "score organique medium", "score organique low", "mint/gel actif",
            "top détenteurs", "dev ", "inconnu de GoPlus", "code caché", "honeypot", "taxe vente"):
    resume(f"avec « {lab.strip()} »", [a for a in alertes if any(x.startswith(lab) for x in a["_f"])])
for t, nom in TYPES.items():
    print(f"\n{nom} :")
    resume("sans drapeau grave", [a for a in alertes if a["type"] == t and not grave(a)])
    resume("avec drapeau grave", [a for a in alertes if a["type"] == t and grave(a)])
print("\nDétail (Repli et Momentum) :")
for a in sorted((a for a in alertes if a["type"] != "temoin"), key=lambda a: -a["ts"]):
    print(f"   {time.strftime('%d/%m', time.gmtime(a['ts']))} {TYPES[a['type']]:8} {str(a.get('symbol'))[:11]:11} {a['chain']:6} "
          f"{suivi.resultat_sim_net(a) * 100:+5.0f} % · " + (" · ".join(a["_f"]) or "rien à signaler"))
