# Alertes crypto sur Telegram — guide complet

Ce dépôt envoie sur ton Telegram une **alerte** dès qu'un token jeune (mais qui a survécu à
ses premières heures) décolle avec de vrais signaux : acheteurs uniques en hausse, pas de
wash trading, sécurité propre.

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

1. [Créer le bot Telegram (téléphone)](#partie-1--créer-le-bot-telegram-sur-ton-téléphone)
2. [Trouver ton « chat id » (ordinateur)](#partie-2--trouver-ton-chat-id-sur-ordinateur)
3. [Créer le dépôt GitHub public](#partie-3--créer-le-dépôt-github-public)
4. [Ajouter les deux secrets](#partie-4--ajouter-les-deux-secrets)
5. [Tester](#partie-5--tester)
6. [Au quotidien](#partie-6--au-quotidien)
7. [Si ça ne marche pas](#partie-7--si-ça-ne-marche-pas)

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
3. Glisse-dépose ces **4 fichiers** : `alertes.py`, `outils.py`, `requirements.txt`,
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
        description: "test = message Telegram de test, once = une vérification, loop = 52 min"
        default: "test"
        type: choice
        options: [test, once, loop]

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

      # mémoire des alertes (tokens déjà signalés, suivi des tokens jeunes)
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
`README.md`, `alertes.py`, `outils.py`, `requirements.txt`.

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
- token âgé de **1 h à 12 h** (il a survécu, mais c'est encore tôt) ;
- mcap de **100 k$ à 5 M$**, liquidité **≥ 30 k$**, volume **≥ 30 k$** sur 1 h ;
- prix **+25 % sur 1 h**, ou mcap **+40 %** depuis qu'on le suit ;
- au moins **150 acheteurs uniques** sur 1 h, et **1,2 fois plus** d'acheteurs que de vendeurs ;
- nombre d'acheteurs **en hausse** ;
- **pas de wash trading** ;
- sécurité propre : RugCheck sans « danger » et liquidité verrouillée **≥ 80 %** (Solana),
  ou GoPlus sans honeypot ni taxe de vente > 10 % (Base/BNB).

Maximum **6 alertes par heure**, jamais deux fois le même token en 24 h.

### Lire une alerte

```
🚨 $TOKEN (solana) — 2.4 h, sur pumpswap
mcap 420 k$ · liq 65 k$ · vol 1 h 90 k$
📈 prix +38 % sur 1 h · mcap +52 % depuis 45 min
👥 310 acheteurs uniques / 140 vendeurs sur 1 h (×2.2) · acheteurs +35 % depuis 45 min
🔁 volume/liquidité 7.1 · 1.4 achat(s) par acheteur : pas de wash détecté
🛡️ RugCheck sans danger, liquidité verrouillée 100 %
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
| `AGE_MIN_H`, `AGE_MAX_H` | 1 – 12 | Âge du token (heures) |
| `MAX_ALERTES_HEURE` | 6 | Plafond anti-spam |

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

Pour tout autre problème : copie les 20 dernières lignes du log et envoie-les à Claude.
