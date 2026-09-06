#!/usr/bin/env bash
#
# Point d'entree du conteneur.
#
# Il prepare le depot puis delegue a `update.sh`, qui porte toute la logique
# metier et est aussi ce qu'appelle le workflow GitHub. Ce fichier ne fait donc
# qu'une chose : s'assurer qu'il existe un depot git utilisable dans /repo.
#
# Deux situations :
#
#   1. **Depot monte** (`-v $PWD:/repo`). On travaille en place. C'est le mode
#      de developpement : on voit les fichiers changer sous ses yeux.
#   2. **Depot clone** (`DATASET_REPO_URL` fourni, /repo vide). Le conteneur
#      clone, met a jour, pousse. C'est le mode serveur : rien a preparer sur
#      la machine hote, un `docker run` suffit.
#
set -euo pipefail

REPO=/repo

log() { printf '%s\n' "$*"; }

if [ -d "$REPO/.git" ]; then
  log "==> Depot monte detecte dans $REPO"
  # Un depot monte peut etre en retard sur la branche distante. On le signale
  # sans decider a la place de l'utilisateur : un `git pull` automatique
  # ecraserait un travail local en cours.
  if [ "${PUSH:-false}" = "true" ] && git -C "$REPO" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
    git -C "$REPO" fetch --quiet || true
    behind="$(git -C "$REPO" rev-list --count 'HEAD..@{upstream}' 2>/dev/null || echo 0)"
    if [ "$behind" != "0" ]; then
      log "!! Le depot local est en retard de $behind commit(s) sur la branche distante."
      log "   Faites 'git pull --rebase' avant de publier, sinon le push sera refuse."
      exit 1
    fi
  fi

elif [ -n "${DATASET_REPO_URL:-}" ]; then
  log "==> Clonage de $DATASET_REPO_URL"
  # Le jeton n'est jamais ecrit sur disque ni dans l'URL du remote : il est
  # injecte le temps de la commande via un en-tete. Sans cette precaution il
  # finirait en clair dans .git/config, donc dans l'image ou le volume.
  auth=()
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    basic="$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')"
    auth=(-c "http.extraheader=Authorization: Basic $basic")
  fi
  git "${auth[@]}" clone --quiet "$DATASET_REPO_URL" "$REPO"
  cd "$REPO"
  if [ ${#auth[@]} -gt 0 ]; then
    git config "http.extraheader" "Authorization: Basic $basic"
  fi

else
  log "Aucun depot dans $REPO et DATASET_REPO_URL n'est pas defini."
  log
  log "Montez le depot :"
  log "    docker run --rm -v \"\$PWD:/repo\" --env-file .env priceradar-dataset"
  log "ou laissez le conteneur le cloner :"
  log "    docker run --rm -e DATASET_REPO_URL=… -e GITHUB_TOKEN=… priceradar-dataset"
  exit 1
fi

cd "$REPO"

# Les scripts viennent du depot, jamais de l'image : le conteneur execute donc
# la version qui accompagne les donnees qu'il met a jour.
if [ ! -x "$REPO/scripts/update.sh" ]; then
  log "Le depot dans $REPO ne contient pas scripts/update.sh executable."
  log "Verifiez que vous montez bien la racine du depot priceradar-dataset."
  exit 1
fi

# Les arguments passes au conteneur sont transmis tels quels, ce qui permet de
# lancer un script isole sans reconstruire l'image :
#   docker compose run --rm update python3 scripts/validate_dataset.py
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec "$REPO/scripts/update.sh"
