# Déployer la mise à jour automatique sur Coolify

Un seul service à déployer. Il tourne en continu, se réveille à ses créneaux,
régénère le jeu de données et pousse sur ce dépôt — uniquement si une
observation est nouvelle.

Aucune tâche planifiée à configurer côté Coolify, aucun cron sur l'hôte :
l'ordonnanceur est dans le conteneur.

---

## Avant de commencer

**1. Le dépôt doit être sur GitHub.** Depuis ce dossier :

```bash
gh repo create priceradar-dataset --public --source=. --push
```

**2. Un jeton d'écriture.** Sur GitHub : *Settings → Developer settings →
Personal access tokens → Fine-grained tokens → Generate new token*.

| Réglage | Valeur |
| --- | --- |
| Repository access | *Only select repositories* → `priceradar-dataset` |
| Permissions | *Contents* → **Read and write** |
| Expiration | 1 an, avec un rappel dans votre agenda |

Un jeton fin limité à ce seul dépôt : s'il fuite, il ne donne accès à rien
d'autre, et il ne peut rien faire qu'écrire des CSV publics.

**3. Les deux valeurs Supabase.** L'URL du projet et la clé **anon** — celles
que le site public expose déjà dans ses pages. Jamais la clé `service_role`.

---

## Le déploiement

### 1. Créer la ressource

Dans Coolify : **+ New → Resource → Docker Compose**, puis choisissez votre
serveur et le projet.

Comme source, indiquez le dépôt `priceradar-dataset`. Il est public, Coolify n'a
donc besoin d'aucune autorisation pour le lire.

- **Branch** : `main`
- **Docker Compose Location** : `/docker-compose.yml`

### 2. Renseigner les variables

Onglet **Environment Variables**. Les quatre premières sont obligatoires :

| Variable | Valeur |
| --- | --- |
| `SUPABASE_URL` | `https://xxxxxxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | la clé anon |
| `DATASET_REPO_URL` | `https://github.com/OWNER/priceradar-dataset.git` |
| `GITHUB_TOKEN` | le jeton fin créé plus haut |

Cochez **Is Build Variable?** sur aucune : elles servent à l'exécution, pas à la
construction de l'image.

Facultatives, avec leurs valeurs par défaut :

| Variable | Défaut | Effet |
| --- | --- | --- |
| `UPDATE_TIMES` | `08:20,16:20,00:30` | Créneaux UTC |
| `RUN_ON_START` | `true` | Une mise à jour dès le démarrage |
| `PUSH` | `true` | `false` fait tourner le service à blanc |

### 3. Couper le déploiement automatique

**C'est l'étape à ne pas sauter.** Dans **Configuration → General**, désactivez
**Automatic Deployment** (ou supprimez le webhook côté GitHub).

Sans cela, vous créez une boucle : le conteneur pousse un commit de données →
GitHub notifie Coolify → Coolify redéploie → le conteneur redémarre et repousse.
La boucle s'arrête d'elle-même faute de données neuves, mais elle redéploie
votre service deux ou trois fois par jour pour rien.

Ce dépôt reçoit un commit à chaque collecte : c'est un dépôt de données, pas un
dépôt de code. Vous redéploierez à la main, les rares fois où le code changera.

### 4. Déployer

Bouton **Deploy**. La première construction prend une minute ; l'image est
minuscule, elle n'installe que `git`.

---

## Vérifier que ça marche

Ouvrez **Logs**. Un démarrage réussi ressemble à ceci :

```
[2026-09-06 19:07:43Z] Clonage de https://github.com/OWNER/priceradar-dataset.git
[2026-09-06 19:07:43Z] Creneaux UTC : 00:30, 08:20, 16:20
[2026-09-06 19:07:43Z] Mise a jour du jeu de donnees
==> Exporting observations
1590 observations written, 0 rows skipped
  FR:  1080 observations, 15 models, 2026-08-13 → 2026-09-06
==> Redrawing the chart
==> Validating against schema.json
Dataset valid — 1590 observations across 7 files
==> Checking for a new observation
No new observation — nothing to commit.
[2026-09-06 19:07:45Z] Mise a jour terminee
[2026-09-06 19:07:45Z] Prochaine mise a jour : 2026-09-07 00:30Z
```

`No new observation` juste après un déploiement est le résultat **normal** :
la donnée n'a pas bougé depuis le dernier commit. La preuve que la chaîne
fonctionne, c'est que l'export et la validation sont passés.

Pour forcer un cycle sans attendre : **Restart**. Avec `RUN_ON_START=true`, une
mise à jour part immédiatement.

Le conteneur se déclare *healthy* au bout de deux minutes. Sa sonde vérifie que
le dépôt est utilisable **et** que la boucle bat toujours — un ordonnanceur
bloqué est donc détecté, pas seulement un processus mort.

---

## Ce qui se passe ensuite

Trois fois par jour, le conteneur se réveille et :

1. se resynchronise avec la branche distante ;
2. relit toutes les observations et réécrit les CSV ;
3. redessine le graphique du README ;
4. valide chaque fichier contre `schema.json` ;
5. compare aux fichiers commités — **et ne commite que s'ils ont changé**.

L'export est déterministe : mêmes données en entrée, fichiers identiques à
l'octet près en sortie. C'est ce qui garantit que l'historique git reste un
journal des mouvements de prix, et non un journal des passages de cron.

---

## En cas de problème

| Dans les journaux | Cause | Correctif |
| --- | --- | --- |
| `Missing environment variable SUPABASE_URL` | Variable absente ou mal nommée | Vérifier l'onglet Environment Variables, puis redéployer |
| `HTTP 401` / `HTTP 403 from PostgREST` | Mauvaise clé, ou droit de lecture retiré au rôle anon | Recopier la clé anon |
| `fatal: Authentication failed` | Jeton GitHub invalide, expiré, ou sans droit d'écriture | Régénérer le jeton, permission *Contents: Read and write* |
| `Aucun depot dans /repo et DATASET_REPO_URL n'est pas defini` | `DATASET_REPO_URL` vide | La renseigner, puis redéployer |
| `No observation returned; refusing to overwrite` | La base a répondu vide | Comportement volontaire : rien n'est écrasé. Vérifier le collecteur |
| `Echec de la mise a jour (code N)` | Erreur ponctuelle | Le service continue et retentera au créneau suivant |

Le service ne s'arrête jamais sur une erreur de mise à jour : une base
injoignable ou un push refusé ne doit pas tuer l'automatisation. L'échec reste
visible dans les journaux, et le créneau suivant retente.

**Repartir de zéro** : supprimer le volume `dataset-repo` puis redéployer. Le
conteneur reclonera. Rien n'est perdu — la source de vérité est GitHub, et la
donnée d'origine est en base.

---

## Le mode observation

Pour déployer sans rien publier le temps de prendre confiance, mettez
`PUSH=false`. Le service régénère et valide à chaque créneau, affiche ce qui
aurait changé, et ne pousse rien. Passez à `true` quand vous êtes prêt.
