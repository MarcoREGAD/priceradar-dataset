#!/usr/bin/env bash
#
# Regenerate the dataset, and commit it when an observation is new.
#
# This is the single implementation of the update. The GitHub workflow and the
# Docker image both call it, so there is one place where the behaviour is
# defined and no chance of the two triggers drifting apart.
#
# Environment:
#   SUPABASE_URL        required, project REST endpoint
#   SUPABASE_ANON_KEY   required, anon (public) key
#   PUSH                "true" to commit and push; anything else regenerates
#                       the files and stops. Defaults to off on purpose:
#                       running a container should never publish by surprise.
#   GIT_AUTHOR_NAME     optional, defaults to priceradar-bot
#   GIT_AUTHOR_EMAIL    optional
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PUSH="${PUSH:-false}"
PYTHON="${PYTHON:-python3}"

echo "==> Exporting observations"
"$PYTHON" scripts/export_dataset.py

echo "==> Redrawing the chart"
"$PYTHON" scripts/render_chart.py

echo "==> Validating against schema.json"
"$PYTHON" scripts/validate_dataset.py

if [ "$PUSH" != "true" ]; then
  echo
  echo "Files regenerated. PUSH is not \"true\", so nothing was committed."
  git status --short -- data latest.csv datapackage.json stats.json \
    assets/price-history-fr.svg || true
  exit 0
fi

# `stats.json` carries the generation timestamp, which changes on every run.
# Staging it alongside the data would produce a commit even when no price
# moved, so the decision is made on the data files only. It is added after,
# once a real change is confirmed.
echo "==> Checking for a new observation"
git add data latest.csv datapackage.json assets/price-history-fr.svg

if git diff --cached --quiet; then
  echo "No new observation — nothing to commit."
  git reset --quiet
  exit 0
fi

git add stats.json
observations="$("$PYTHON" -c "import json;print(json.load(open('stats.json'))['observations'])")"

git config user.name "${GIT_AUTHOR_NAME:-priceradar-bot}"
git config user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
git commit --quiet -m "data: update observations ($observations total)"

echo "==> Pushing"
git push

echo "Done — $observations observations published."
