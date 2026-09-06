#!/usr/bin/env bash
#
# Point d'entree du conteneur.
#
# Il prepare le depot dans /repo, puis passe la main. Toute la logique metier
# vit dans les scripts du depot, jamais dans l'image : le conteneur execute
# donc forcement la version qui accompagne les donnees qu'il met a jour.
#
# Deux situations, distinguees automatiquement :
#
#   1. **Volume vide + DATASET_REPO_URL** — le conteneur clone. C'est le mode
#      serveur : rien a preparer sur la machine hote.
#   2. **Depot deja present** — soit le volume d'un demarrage precedent, soit
#      un depot monte depuis l'hote pour travailler en local.
#
set -euo pipefail

REPO=/repo

log() { printf '[%s] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S')Z" "$*"; }

# ---------------------------------------------------------------------------
# Authentification git
# ---------------------------------------------------------------------------
# Le jeton passe par les variables GIT_CONFIG_* plutot que par l'URL du remote
# ou par `git config`. C'est la seule facon de l'utiliser sans qu'il soit ecrit
# quelque part : ni dans .git/config, ni dans le volume, ni dans l'historique
# du shell. Il vit le temps du processus, et disparait avec lui.
if [ -n "${GITHUB_TOKEN:-}" ]; then
  basic="$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')"
  export GIT_CONFIG_COUNT=1
  export GIT_CONFIG_KEY_0="http.extraheader"
  export GIT_CONFIG_VALUE_0="Authorization: Basic $basic"
  unset basic
fi

# ---------------------------------------------------------------------------
# Preparation du depot
# ---------------------------------------------------------------------------
if [ -d "$REPO/.git" ]; then
  cd "$REPO"
  log "Depot present dans $REPO"

  # Sur un serveur, le clone appartient au conteneur : le remettre a niveau
  # avant d'ecrire evite un push refuse au premier decalage. En local, on ne
  # touche a rien — un pull automatique ecraserait un travail en cours.
  if [ "${AUTO_PULL:-${DATASET_REPO_URL:+true}}" = "true" ] \
     && git rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
    log "Synchronisation avec la branche distante"
    git pull --rebase --autostash --quiet || log "!! Echec du pull, on continue avec l'etat local"
  fi

elif [ -n "${DATASET_REPO_URL:-}" ]; then
  log "Clonage de $DATASET_REPO_URL"
  git clone --quiet "$DATASET_REPO_URL" "$REPO"
  cd "$REPO"

else
  log "Aucun depot dans $REPO et DATASET_REPO_URL n'est pas defini."
  log ""
  log "Sur un serveur, laissez le conteneur cloner :"
  log "    -e DATASET_REPO_URL=https://github.com/OWNER/priceradar-dataset.git"
  log "En local, montez le depot :"
  log "    -v \"\$PWD:/repo\""
  exit 1
fi

if [ ! -x "$REPO/scripts/update.sh" ]; then
  log "Le depot dans $REPO ne contient pas scripts/update.sh executable."
  log "Verifiez DATASET_REPO_URL, ou que vous montez bien la racine du depot."
  exit 1
fi

# Identite des commits, fixee ici pour que le clone du serveur n'ait pas besoin
# d'une configuration git prealable.
git config user.name "${GIT_AUTHOR_NAME:-priceradar-bot}"
git config user.email "${GIT_AUTHOR_EMAIL:-priceradar-bot@users.noreply.github.com}"

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
# Une commande explicite l'emporte : c'est ce qui permet de lancer une seule
# operation sans reconstruire l'image.
#   docker compose run --rm dataset python3 scripts/validate_dataset.py
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec python3 "$REPO/scripts/scheduler.py"
