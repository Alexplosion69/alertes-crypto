# Alertes crypto sur Telegram — guide complet

Ce dépôt t'envoie sur Telegram :

| | Alerte | Quand |
|---|---|---|
| 🚨 | **Classique** | un token de 2 h à 12 h décolle avec de vrais acheteurs |
| 🌱 | **Survivant** | un token de 12 h à 7 jours a tenu un plancher et repart (ou monte régulièrement) |
| 🐋 | **Smart wallets** | au moins 3 wallets gagnants ont acheté le même token (*mode observation au départ*) |
| 🧩 | **Narratif** | un nom cloné en masse : le bot signale le leader, **avant que la foule arrive** |
| 📊 | **Bilan quotidien** | chaque matin vers 9 h : ce que sont devenues toutes les alertes |

Chaque alerte passe par la sécurité (RugCheck / GoPlus) et le **filtre dev** 👤, et affiche
l'**identité** 🪪 du token (compte X à son nom, site… ou simple lien vers le tweet de quelqu'un).

Il est **séparé** de ton résumé du matin :

| Dépôt | Visibilité | Contenu |
|---|---|---|
| `veille-hype` (déjà en place) | **privé** | résumé du matin, journal, bilan, clés Claude et X |
| `alertes-crypto` (ce guide) | **public** | alertes Telegram uniquement, aucune clé payante |

Pourquoi public ? Un dépôt public a des **minutes GitHub illimitées**, ce qui permet de
surveiller toute la journée gratuitement. Le seul secret de ce dépôt (le token du bot Telegram)
reste caché dans les « secrets » GitHub, invisible même en public.

**Temps total : environ 20 minutes.** Il te faut ton téléphone (Telegram) et ton ordinateur
(GitHub).

---

## Sommaire

0. [Mise à jour d'octobre (si tu as déjà installé)](#mise-à-jour-doctobre-si-tu-as-déjà-installé)
1. [Créer le bot Telegram (téléphone)](#partie-1--créer-le-bot-telegram-sur-ton-téléphone)
2. [Trouver ton « chat id » (ordinateur)](#partie-2--trouver-ton-chat-id-sur-ordinateur)
3. [Créer le dépôt GitHub public](#partie-3--créer-le-dépôt-github-public)
4. [Ajouter les deux secrets](#partie-4--ajouter-les-deux-secrets)
5. [Tester](#partie-5--tester)
6. [Au quotidien](#partie-6--au-quotidien)
7. [Si ça ne marche pas](#partie-7--si-ça-ne-marche-pas)

## Mise à jour d'octobre (si tu as déjà installé)

Ton bot et tes secrets ne changent pas, et la mémoire du bot (alertes déjà envoyées) est conservée.

1. Dézippe `alertes-crypto.zip`.
2. Sur GitHub, dans ton dépôt `alertes-crypto` : **Add file** → **Upload files**.
3. Glisse-dépose ces **8 fichiers** (ceux qui existent déjà seront remplacés) :
   `alertes.py`, `outils.py`, `devs.py`, `suivi.py`, `portefeuilles.py`,
   `portefeuilles_manuels.txt`, `requirements.txt`, `README.md`.
4. **Commit changes**.
5. *(Facultatif, pour avoir le bouton « bilan maintenant »)* ouvre
   `.github/workflows/alertes.yml` → crayon ✏️ → remplace la ligne
   `options: [test, once, loop]` par `options: [test, once, loop, bilan]` → **Commit changes**.

C'est tout. À la prochaine heure, le bot tourne avec les nouveautés. Les alertes 🌱 ont besoin
d'au moins 6 h de suivi avant de pouvoir partir, et la base de smart wallets se construit
toute seule en **une à deux semaines** (voir plus bas).

---

> 💡 Comme pour la première installation, ouvre un fichier texte temporaire sur ton ordinateur
> pour y coller le **token** et le **chat id** au fur et à mesure. Tu le supprimeras à la fin.

---

## Partie 1 — Créer le bot Telegram (sur ton téléphone)

Un « bot » Telegram, c'est un compte automatique. Le tien n'aura qu'un rôle : t'envoyer les
alertes. Personne d'autre ne le trouvera ni ne l'utilisera.

### 1.1 Rétablir les notifications Telegram

Tu m'as dit les avoir coupées. Sans elles, les alertes arrivent en silence.

1. Ouvre Telegram → **Paramètres** (en bas à droite sur iPhone, menu ☰ sur Android).
2. **Notifications et sons**.
3. Active **Discussions privées** (c'est là qu'arriveront les messages du bot).
4. Vérifie aussi dans les **réglages du téléphone** → Notifications → Telegram → autorisées.

### 1.2 Ouvrir BotFather

**BotFather** est le bot officiel de Telegram qui sert à créer des bots.

1. Dans Telegram, touche la **loupe** (recherche) et tape `BotFather`.
2. Choisis celui qui s'appelle exactement **@BotFather**, avec un **badge bleu ✔** à côté du
   nom. ⚠️ Il existe des imitations sans badge : ne les utilise pas.
3. Touche **Démarrer** (ou **Start**) en bas de l'écran.

### 1.3 Créer ton bot

1. Envoie le message : `/newbot`
2. BotFather demande un **nom** (celui qui s'affichera). Envoie par exemple :
   `Veille Crypto`
3. Il demande ensuite un **identifiant** (username). Règles :
   - il doit **finir par `bot`** ;
   - il doit être **unique** sur tout Telegram ;
   - lettres, chiffres et `_` uniquement.

   Envoie par exemple : `veille_crypto_alex_bot`.
   Si BotFather répond que c'est déjà pris (*« Sorry, this username is already taken »*),
   ajoute des chiffres : `veille_crypto_alex_2026_bot`.
4. BotFather répond *« Done! Congratulations on your new bot »* avec :
   - un lien vers ton bot, du genre `t.me/veille_crypto_alex_bot` ;
   - un **token**, une longue suite du genre :
     `7123456789:AAHk3x9...` (des chiffres, `:`, puis environ 35 caractères).

### 1.4 Copier le token

1. **Touche le token** dans le message de BotFather : il est copié automatiquement
   (ou appui long sur le message → **Copier**).
2. Envoie-le-toi pour le récupérer sur l'ordinateur (par exemple dans tes « Messages
   enregistrés » Telegram, que tu peux ouvrir sur ordinateur via web.telegram.org), puis
   colle-le dans ton fichier texte temporaire.

⚠️ **Ce token est secret.** Avec lui, n'importe qui peut envoyer des messages via ton bot.
Ne le mets jamais dans un fichier du dépôt, ne l'envoie à personne. S'il fuit un jour :
dans BotFather, envoie `/revoke`, choisis ton bot, et il t'en donne un nouveau (à remettre
dans le secret GitHub de la partie 4).

### 1.5 Démarrer la conversation avec ton bot

Un bot n'a pas le droit d'écrire en premier : c'est toi qui dois lui parler une fois.

1. Touche le lien `t.me/...` donné par BotFather (ou cherche ton bot par son identifiant).
2. Touche **Démarrer**.
3. Envoie-lui n'importe quel message, par exemple `salut`. Il ne répondra rien : c'est normal.

---

## Partie 2 — Trouver ton « chat id » (sur ordinateur)

Le **chat id** est le numéro de ta conversation avec le bot : c'est l'adresse à laquelle le
script enverra les alertes.

### 2.1 Ouvrir l'adresse magique

1. Sur ton ordinateur, ouvre ton navigateur.
2. Copie cette adresse dans la barre d'adresse **sans l'ouvrir tout de suite** :
   ```
   https://api.telegram.org/botTON_TOKEN/getUpdates
   ```
3. Remplace `TON_TOKEN` par ton token. ⚠️ Garde bien le mot `bot` collé devant, sans espace.
   Exemple (faux token) :
   ```
   https://api.telegram.org/bot7123456789:AAHk3x9abcdefghijklmnopqrstuvwxyz12/getUpdates
   ```
4. Appuie sur **Entrée**.

### 2.2 Lire le chat id

La page affiche du texte un peu brut, qui ressemble à ça :

```
{"ok":true,"result":[{"update_id":123,"message":{"message_id":1,
"from":{"id":987654321,"is_bot":false,"first_name":"Alex"...},
"chat":{"id":987654321,"first_name":"Alex","type":"private"},
"date":1760100000,"text":"salut"}}]}
```

Cherche **`"chat":{"id":`** : le nombre juste après (ici `987654321`) est ton **chat id**.
Copie-le (juste les chiffres) dans ton fichier texte.

> Astuce : avec **Ctrl+F** (ou **Cmd+F** sur Mac), cherche `"chat"` pour le trouver tout de suite.

### 2.3 Si ça ne s'affiche pas comme prévu

| Ce que tu vois | Cause | Solution |
|---|---|---|
| `{"ok":true,"result":[]}` | Le bot n'a pas encore reçu ton message | Renvoie `salut` au bot sur ton téléphone, puis rafraîchis la page |
| `"error_code":401` / `Unauthorized` | Token mal copié | Recopie le token en entier, sans espace |
| `"error_code":404` / `Not Found` | Le mot `bot` manque devant le token | L'adresse doit contenir `/bot7123…`, collé |

---

## Partie 3 — Créer le dépôt GitHub public

### 3.1 Créer le dépôt

1. Sur **github.com**, clique sur le **+** en haut à droite → **New repository**.
2. **Repository name** : `alertes-crypto`.
3. Coche **Public**.
4. Coche **Add a README file**.
5. Clique sur **Create repository**.

### 3.2 Envoyer les fichiers

1. Dézippe `alertes-crypto.zip` sur ton ordinateur.
2. Dans le nouveau dépôt : **Add file** → **Upload files**.
3. Glisse-dépose ces **8 fichiers** : `alertes.py`, `outils.py`, `devs.py`, `suivi.py`,
   `portefeuilles.py`, `portefeuilles_manuels.txt`, `requirements.txt`,
   `README.md` (il remplace celui créé automatiquement).
4. Clique sur **Commit changes**.

### 3.3 Créer le fichier de planification

Comme la première fois, le dossier `.github` est caché sur ton ordinateur : on crée le
fichier directement sur GitHub.

1. **Add file** → **Create new file**.
2. Nom du fichier, tape exactement :
   ```
   .github/workflows/alertes.yml
   ```
3. Colle **tout** ce contenu, sans toucher aux espaces en début de ligne :

```yaml
name: Alertes temps réel

on:
  schedule:
    - cron: "7 * * * *"      # relancé chaque heure ; chaque exécution surveille ~52 min
  workflow_dispatch:
    inputs:
      mode:
        description: "test = message Telegram de test, once = une vérification, loop = 52 min, bilan = bilan maintenant"
        default: "test"
        type: choice
        options: [test, once, loop, bilan]

concurrency:
  group: alertes             # jamais deux surveillances en même temps
  cancel-in-progress: false

permissions:
  contents: write            # uniquement pour le « maintien en vie » mensuel

jobs:
  alertes:
    runs-on: ubuntu-latest
    timeout-minutes: 70
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install -r requirements.txt

      # mémoire : alertes envoyées, suivi 7 jours, base de wallets, mémoire des devs
      - uses: actions/cache@v4
        with:
          path: alertes
          key: alertes-etat-${{ github.run_id }}
          restore-keys: alertes-etat-

      - name: Surveiller
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python alertes.py ${{ inputs.mode || 'loop' }}

      # dépôt public : GitHub coupe les tâches programmées après 60 jours sans activité.
      # Le 1er et le 15 du mois, on fait un commit vide pour l'éviter.
      - name: Maintien en vie
        if: github.event_name == 'schedule'
        run: |
          if [ "$(date -u +%d)" = "01" ] || [ "$(date -u +%d)" = "15" ]; then
            if [ "$(date -u +%H)" = "00" ]; then
              git config user.name "veille-bot"
              git config user.email "veille-bot@users.noreply.github.com"
              git commit --allow-empty -m "maintien en vie des alertes"
              git push
            fi
          fi
```

4. **Commit changes**.

✅ **Vérification** : la page d'accueil du dépôt affiche le dossier `.github` et les fichiers
`README.md`, `alertes.py`, `outils.py`, `devs.py`, `suivi.py`, `portefeuilles.py`,
`portefeuilles_manuels.txt`, `requirements.txt`.

---

## Partie 4 — Ajouter les deux secrets

1. Dans le dépôt `alertes-crypto` : onglet **Settings** (engrenage, tout à droite de la
   rangée d'onglets du dépôt — pas les réglages de ton compte).
2. Menu de gauche, partie **Security** : **Secrets and variables** → **Actions**.
   Raccourci : `https://github.com/Alexplosion69/alertes-crypto/settings/secrets/actions`
3. **New repository secret**, deux fois :

| Name (nom exact) | Secret (valeur) |
|---|---|
| `TELEGRAM_BOT_TOKEN` | le token donné par BotFather (`7123456789:AAH…`) |
| `TELEGRAM_CHAT_ID` | ton chat id (juste les chiffres, ex. `987654321`) |

Après avoir collé chaque valeur, vérifie qu'il n'y a ni espace ni ligne vide à la fin.

🗑️ Tu peux maintenant supprimer ton fichier texte temporaire.

---

## Partie 5 — Tester

### 5.1 Test de connexion

1. Onglet **Actions** du dépôt.
2. Si GitHub affiche un bouton du genre **« I understand my workflows, go ahead and enable
   them »**, clique dessus.
3. Clique sur **Alertes temps réel** dans la liste à gauche.
4. À droite : **Run workflow** → le menu **mode** est sur **test** → bouton vert
   **Run workflow**.
5. Attends ~1 minute. Tu dois recevoir sur Telegram :
   **« ✅ Les alertes crypto sont bien connectées à ce Telegram. »**

### 5.2 Test sur le vrai marché

1. Relance **Run workflow**, mais choisis cette fois le mode **once**.
2. Quand c'est fini (rond vert, ~2-3 minutes), clique sur l'exécution → **alertes** →
   déplie l'étape **Surveiller**. Tu verras par exemple :
   ```
   16:42 : 87 tokens observés, 3 passent le filtre rapide, 0 alerte(s)
   ```
   **Zéro alerte est normal** la plupart du temps : les conditions sont strictes exprès.

### 5.3 C'est en route

Tu n'as plus rien à faire : GitHub lance la surveillance **toute seule chaque heure**
(vers h+7), et chaque surveillance vérifie le marché toutes les ~4 minutes pendant 52 minutes.

---

## Partie 6 — Au quotidien

### Ce qui déclenche une alerte

Toutes ces conditions à la fois (réglables en haut de `alertes.py`) :
- token âgé de **2 h à 12 h** (il a survécu à son lancement, mais c'est encore tôt) ;
- mcap de **100 k$ à 5 M$**, liquidité **≥ 30 k$**, volume **≥ 30 k$** sur 1 h ;
- prix **entre +25 % et +150 % sur 1 h** (au-delà, le pump est déjà fait ou fabriqué), ou mcap **+40 %** sur les 30 à 60 dernières minutes avec un prix encore en hausse sur 1 h (≥ +10 %) ;
- pas en train de chuter : moins de -10 % sur les 5 dernières minutes ;
- au moins **150 acheteurs uniques** sur 1 h, et **1,2 fois plus** d'acheteurs que de vendeurs ;
- nombre d'acheteurs **en hausse** ;
- **pas de wash trading** ;
- sécurité propre : RugCheck sans « danger » et liquidité verrouillée **≥ 80 %** (Solana),
  ou GoPlus sans honeypot, taxe de vente ≤ 10 % et top 10 des détenteurs ≤ 35 % (Base/BNB).
  Si GoPlus n'a pas encore de données sur le token, **pas d'alerte** : inconnu ne veut pas dire sûr.

Maximum **6 alertes par heure** (tous types confondus), jamais deux fois le même token en 24 h.

### Le filtre dev 👤

Le créateur du token (le « dev ») est celui qui gagne le plus… souvent en vendant quand la
communauté achète. On ne le **suit** donc pas : on s'en sert pour **écarter** un token quand :
- le dev détient encore **plus de 5 %** de l'offre (il peut tout vendre d'un coup) ;
- des wallets « initiés » liés entre eux détiennent **plus de 15 %** (Solana, RugCheck) ;
- le dev a déjà lancé **5 autres tokens ou plus** (dev en série) ;
- **2 de ses tokens précédents sont déjà morts** sous les yeux du bot (récidiviste).

Les deux derniers points s'appuient sur la mémoire du bot (`alertes/devs.json`) : plus il
tourne, plus il reconnaît les devs. Sur Base/BNB, le « créateur » est souvent la plateforme de
lancement elle-même : là, seule sa part détenue compte. Chaque alerte affiche une ligne 👤.

### Les alertes « survivant » 🌱

Le constat du premier bilan et des meilleurs trades Fomo de la semaine : les gros gains ne se
font pas dans les premières minutes, mais sur des tokens qui ont **déjà survécu** et qui
repartent (entrées à 500 k$ – 1 M$ de mcap). Le bot garde donc l'historique de prix de tous
les tokens qu'il voit (un relevé toutes les 30 min, pendant 7 jours) et cherche deux formes :

**Rebond sur plancher** : le token a corrigé de **30 à 80 %** depuis son sommet, n'a pas fait
de nouveau plus bas depuis **au moins 3 h** (le plancher tient), a rebondi de **+25 %** et
**casse le haut** de sa zone des 6 dernières heures.

**Montée régulière** (le profil WangChai) : sur 12 à 18 h, des creux **et** des sommets de
plus en plus hauts, au moins **+40 %**, sans jamais chuter de plus de 35 %.

Dans les deux cas, il faut aussi : 12 h à 7 jours d'âge, mcap 300 k$ – 10 M$, liquidité
≥ 40 k$ **et stable sur 12 h** (personne ne la retire), volume ≥ 50 k$ sur 6 h, plus d'achats
que de ventes sur 6 h, au moins 30 acheteurs uniques sur 1 h et 300 sur 24 h, pas de wash
trading, sécurité et filtre dev OK.

L'alerte donne un **niveau d'invalidation** (🎯) : le plancher, ou le dernier creux. S'il est
cassé, le scénario est raté : c'est ton repère pour couper.

### Les smart wallets 🐋 (mode observation)

L'idée : repérer les wallets qui achètent **tôt** les tokens qui finissent par faire x3, puis
être prévenu quand **plusieurs** d'entre eux achètent le même nouveau token.

**Comment la liste se construit, toute seule et gratuitement :**
1. Pour chaque token de moins de 24 h suivi, le bot lit les 300 dernières transactions
   (GeckoTerminal) et note qui a acheté, à quel prix et pour combien (achats < 50 $ ignorés).
2. Si le token monte ensuite à **3x le prix d'achat** d'un wallet : un **bon coup** pour lui.
   S'il meurt, ou ne fait pas x3 en 72 h : un **coup raté**.
3. Un wallet devient **« smart »** avec **au moins 2 bons coups et 40 % de réussite**. Les bots
   qui achètent tout ont un taux de réussite très bas : ils restent dehors.

**Le signal** : au moins **3 smart wallets** ont acheté le même token (pas forcément en même
temps) **et** le prix n'est pas déjà à plus de **2x leur prix d'entrée moyen**. C'est la
réponse au problème des alertes « baleine » de Fomo : quand tu cliques, le prix a déjà pris
40 %. Ici, si on arrive trop tard, le signal est marqué « trop tard ».

**Pourquoi en observation :** la base de wallets part de zéro et met **une à deux semaines**
à se remplir. Pendant ce temps, les signaux ne sont pas envoyés en alerte : ils apparaissent
dans le **bilan quotidien** avec ce qu'ils sont devenus. Quand le bilan montre que ça marche,
ouvre `portefeuilles.py` et passe `EN_DIRECT = False` à `EN_DIRECT = True`.

**Ajouter des wallets à la main** : si tu repères l'adresse d'un trader qui t'inspire
confiance, ajoute-la dans `portefeuilles_manuels.txt` (une par ligne). Elle comptera toujours
comme smart.

> Limites honnêtes : tu achèteras toujours **après** eux ; les wallets connus sont copiés par
> d'autres bots, ce qui peut créer un pump artificiel juste après leur achat ; certains le
> savent et achètent exprès pour vendre aux copieurs. C'est pour ça qu'on mesure avant d'y croire.

### Le bilan quotidien 📊

Chaque matin vers 9 h (8 h en hiver), un message récapitule les 7 derniers jours, par type
d'alerte : combien ont **touché x2**, combien sont **en hausse aujourd'hui**, combien sont
**mortes**, puis le détail des dernières 24 h (mcap à l'alerte, plus haut atteint, maintenant).
Les smart wallets en observation y figurent aussi, marqués *(obs.)*, et les narratifs sont
séparés : envoyés, ⭐ profil SEALS, saturés (non envoyés), et selon leur identité.

Pour l'avoir tout de suite : **Actions** → **Alertes temps réel** → **Run workflow** →
mode **bilan** (si tu as fait l'étape 5 de la mise à jour).

### Les alertes « narratif » 🧩

> **Ce qu'on a appris sur les 7 premiers narratifs (10 au 13/10)**
>
> | Leader | Âge | Mcap | Acheteurs/h | Vol 1 h | Écart n°2 | Résultat |
> |---|---|---|---|---|---|---|
> | **SEALS** | 2,1 h | 84 k$ | **354** | **26 k$** | **×25** | **x10** |
> | COWE | 0,3 h | 85 k$ | 768 | 42 k$ | ×2 | sommet x2,3 puis rechute |
> | Isabella | 0,2 h | 94 k$ | 2 590 | 299 k$ | ×3 | −95 % |
> | DOPE | 0,5 h | 142 k$ | 1 441 | 172 k$ | ×4 | −96 % |
> | CAESAR | 0,8 h | 175 k$ | 3 136 | 517 k$ | ×2 | −84 % |
> | Gem | 1,1 h | 159 k$ | 3 076 | 587 k$ | ×2 | −97 % |
> | nonce | 1,2 h | 103 k$ | 2 139 | 257 k$ | ×2 | −89 % |
>
> Les 2 qui ont doublé ont été signalés **avant la foule** (moins de 800 acheteurs/h, moins de
> 50 k$ de volume). Les 5 morts avaient déjà 1 400 à 3 100 acheteurs/h : on arrivait au sommet.

Ce qui change donc :
- **Filtre « avant la foule »** : si le leader a plus de **1 200 acheteurs/h** ou plus de
  **150 k$** de volume sur 1 h, le narratif est jugé **saturé** : pas d'alerte (il reste compté
  dans le bilan, ligne « saturés », pour vérifier que c'était le bon choix).
- **⭐ Profil SEALS** : si le leader écrase le n°2 (**≥ 5x** son volume) et a déjà survécu
  **1 h 30**, l'alerte porte une étoile.
- **🪪 Identité** : les 4 « tokens de tweet » (qui renvoient juste au tweet de quelqu'un d'autre)
  sont tous morts. Avoir un compte X à son nom aide sans suffire (SEALS x10, nonce mort).
  C'est une info à lire, pas un filtre.
- **🎯 Plan** : la moitié à x2, couper à −50 %. Un narratif est une loterie : le gagnant ne
  rembourse les perdants que si on coupe vite.

⚠️ 7 cas, c'est très peu : ces seuils collent au passé, ils peuvent rater le prochain. Le bilan
quotidien dira si les « saturés » meurent bien et si les envoyés font mieux. Réglages :
`NARR_ACHETEURS_MAX`, `NARR_VOL_1H_MAX`, `NARR_ETOILE_ECART`, `NARR_ETOILE_AGE_H` ; pour couper
complètement : `NARRATIFS_EN_DIRECT = False`.

Quand une actu devient virale (un animal célèbre, une déclaration, un mème…), des dizaines
de tokens portant le même nom sont lancés en quelques heures. **Beaucoup de clones = un vrai
narratif.** Et en général, le marché choisit très vite **un** gagnant : les autres meurent.

Le script mémorise le nom de tous les tokens jeunes qu'il voit passer. Dès qu'un même nom
apparaît sur **au moins 5 tokens lancés en 3 h**, il cherche le **leader**, celui que le
marché a déjà choisi :
- volume sur 1 h **au moins 2 fois** celui du n°2 (sinon, pas encore de gagnant net : pas d'alerte) ;
- liquidité ≥ 20 k$ et volume ≥ 20 k$ sur 1 h ;
- au moins 100 acheteurs uniques sur 1 h, et plus d'acheteurs que de vendeurs ;
- pas de wash trading, sécurité propre, pas déjà à plus de +300 % sur 1 h, pas en chute sur 5 min.

Les noms trop génériques (PEPE, DOGE, TRUMP, AI…), clonés en permanence, sont ignorés.
Un même narratif n'est signalé qu'une fois toutes les 12 h.

```
🧩 Narratif détecté : « ALTIA » — 14 tokens de ce nom lancés en 3 h (solana 12, base 2)
👑 Leader : $ALTIA (solana) — 1.8 h, mcap 850 k$ · liq 120 k$
📊 vol 1 h 400 k$ (×6 le volume du n°2) · prix +80 % sur 1 h, +2 % sur 5 min
👥 900 acheteurs uniques / 400 vendeurs sur 1 h
🛡️ RugCheck sans danger, liquidité verrouillée 100 %
Suivants (volume 1 h) : solana 65 k$ · base 20 k$ · solana 8 k$
⚠️ Plusieurs tokens portent ce nom : sur Fomo, vérifie que l'adresse se termine par 7xK2pQ
Voir le leader sur DexScreener
```

⚠️ **Le piège n°1 des narratifs, c'est d'acheter le mauvais clone.** Sur Fomo, plusieurs
tokens auront le même nom et le même logo. Vérifie toujours que l'adresse du contrat se
termine bien par les 6 caractères indiqués dans l'alerte.

> Limite : le script ne voit qu'une partie des nouveaux tokens (les API gratuites donnent
> les derniers lancés à chaque vérification, pas tous). Un petit narratif peut lui échapper ;
> un gros, avec des dizaines de clones, sera repéré.

### Lire une alerte

```
🚨 $TOKEN (solana) — 2.4 h, sur pumpswap
mcap 420 k$ · liq 65 k$ · vol 1 h 90 k$
📈 prix +38 % sur 1 h · +3 % sur 5 min · mcap +52 % depuis 45 min
👥 310 acheteurs uniques / 140 vendeurs sur 1 h (×2.2) · acheteurs +35 % depuis 45 min
🔁 volume/liquidité 7.1 · 1.4 achat(s) par acheteur : pas de wash détecté
🛡️ RugCheck sans danger, liquidité verrouillée 100 %
🪪 compte X à son nom (@TokenOfficiel) + site web
👤 dev : dev détient 0 %, pas d'autre token connu de ce dev
Voir sur DexScreener
```

Une alerte veut dire **« ce token mérite un coup d'œil maintenant »**, pas « achète ».
Avant d'acheter :
1. ouvre le lien DexScreener et regarde le graphique des 15 dernières minutes ;
2. si le prix est déjà en train de **retomber**, laisse passer ;
3. n'achète jamais une grande bougie verte verticale juste par peur de rater le train ;
4. petite mise, que tu acceptes de perdre.

### Mettre en pause / relancer

Onglet **Actions** → **Alertes temps réel** → bouton **⋯** en haut à droite →
**Disable workflow** (pause) ou **Enable workflow** (relance).

### Trop ou pas assez d'alertes ?

Dans `alertes.py` (crayon ✏️ sur GitHub), en haut du fichier :

| Réglage | Défaut | Effet |
|---|---|---|
| `ACHETEURS_1H_MIN` | 150 | Plus haut = moins d'alertes, plus solides |
| `HAUSSE_1H_MIN` | 25 | Hausse sur 1 h exigée (%) |
| `LIQ_MIN` | 30 000 | Liquidité minimale ($) |
| `MCAP_MIN`, `MCAP_MAX` | 100 k – 5 M | Fourchette de taille |
| `AGE_MIN_H`, `AGE_MAX_H` | 2 – 12 | Âge du token (heures) |
| `HAUSSE_1H_MAX` | 150 | Hausse max sur 1 h (%) : au-delà, on considère que c'est trop tard |
| `TOP10_MAX` | 35 | Base/BNB : part max des 10 plus gros détenteurs (%) |
| `MAX_ALERTES_HEURE` | 6 | Plafond anti-spam |
| `NARR_MIN_CLONES` | 5 | Nombre de tokens du même nom pour parler de narratif |
| `NARR_ECART_MIN` | 2 | Le leader doit faire X fois le volume du n°2 |
| `NARRATIFS_EN_DIRECT` | True | False = ne plus envoyer les narratifs (bilan seulement) |

Dans `suivi.py` (survivants) :

| Réglage | Défaut | Effet |
|---|---|---|
| `SURV_MCAP_MIN`, `SURV_MCAP_MAX` | 300 k – 10 M | Fourchette de taille |
| `SURV_CORRECTION_MIN` | 0.30 | Correction minimale depuis le sommet (30 %) |
| `SURV_PLANCHER_H` | 3 | Heures sans nouveau plus bas |
| `SURV_MONTEE_X` | 1.4 | Montée régulière : hausse minimale sur la fenêtre (x1,4) |

Dans `portefeuilles.py` (smart wallets) :

| Réglage | Défaut | Effet |
|---|---|---|
| `EN_DIRECT` | False | True = envoyer les signaux en alerte |
| `SIGNAL_MIN_WALLETS` | 3 | Nombre de smart wallets sur le même token |
| `SMART_MIN_BONS_COUPS` | 2 | Bons coups (x3) pour devenir smart |
| `SMART_MIN_TAUX` | 0.40 | Taux de réussite minimum |
| `SIGNAL_TROP_TARD_X` | 2 | Au-delà de 2x leur entrée moyenne : trop tard |

Dans `devs.py` : `DEV_DETIENT_MAX` (5 %), `DEV_SERIE_MAX` (5 tokens), `DEV_MORTS_MAX` (2).

### Ce qui coûte

**Rien.** Pas de Claude, pas d'API X, et les minutes GitHub sont illimitées sur un dépôt public.

### Ce qui est visible publiquement

Le code de ce dépôt et l'historique des exécutions. **Pas** le token du bot ni le chat id
(ils sont dans les secrets), et **rien** de ton dépôt privé `veille-hype`.

> GitHub met en pause les tâches programmées d'un dépôt public après 60 jours sans
> activité. Le script fait automatiquement un petit commit vide le 1er et le 15 du mois
> pour l'éviter. Tu verras donc passer des commits « maintien en vie des alertes » : c'est normal.

### Limites à connaître

- GitHub n'est pas toujours pile à l'heure : il peut y avoir des **trous de 10 à 30 minutes**
  dans la surveillance de temps en temps.
- Une alerte arrive forcément **après** une première hausse : c'est voulu (on attend des
  signaux confirmés), mais ça veut dire que tu n'auras jamais le tout début du mouvement.

---

## Partie 7 — Si ça ne marche pas

Ouvre l'exécution en rouge (**Actions** → la ligne rouge → **alertes** → l'étape en erreur)
et regarde les dernières lignes.

| Ce que tu vois | Cause probable | Solution |
|---|---|---|
| `TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquants` | Secret absent ou mal nommé | Vérifie les noms exacts à la partie 4 |
| `Telegram 401` | Token faux ou révoqué | Recopie le token de BotFather dans le secret |
| `Telegram 400 … chat not found` | Chat id faux, ou tu n'as jamais écrit au bot | Envoie `salut` au bot, refais la partie 2 |
| `Telegram 403 … bot was blocked by the user` | Tu as bloqué le bot | Ouvre la conversation avec le bot → **Débloquer** / **Redémarrer** |
| Mode test vert mais aucun message | Notifications coupées | Refais la partie 1.1, vérifie la conversation du bot |
| `[warn] 429` | Trop d'appels aux API gratuites | Rien à faire, le script attend et réessaie |
| `0 alerte(s)` tout le temps pendant des jours | Conditions trop strictes pour le marché du moment | Baisse un peu `ACHETEURS_1H_MIN` ou `HAUSSE_1H_MIN` |
| Le workflow n'apparaît pas dans **Actions** | Fichier `.yml` mal placé | Il doit être dans `.github/workflows/alertes.yml` |
| `ModuleNotFoundError: No module named 'devs'` (ou `suivi`, `portefeuilles`) | Un des nouveaux fichiers n'a pas été envoyé | Refais l'étape 3 de la mise à jour avec les 8 fichiers |
| `wallets : 0 observés` pendant plusieurs heures | GeckoTerminal refuse la lecture des transactions | Rien de grave : les autres alertes marchent ; envoie le log à Claude |

Dans le log, la ligne `suivi : 180 tokens, 4 morts, 0 survivant(s) ; wallets : 2300 observés,
12 smart` te dit où en est le bot.

Pour tout autre problème : copie les 20 dernières lignes du log et envoie-les à Claude.
