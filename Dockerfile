# Image de mise a jour du jeu de donnees.
#
# Elle ne contient **que** le point d'entree : ni les scripts, ni le schema, ni
# les donnees. Tout cela vient du depot, monte ou clone dans /repo au
# demarrage.
#
# Ce choix n'est pas de la coquetterie. Si l'image embarquait une copie des
# scripts, elle finirait par valider les donnees publiees contre un schema plus
# ancien que celui du depot, et une image oubliee sur le serveur reecrirait le
# jeu de donnees avec une logique perimee. En lisant le depot, le conteneur
# execute forcement la version qui accompagne les donnees.
#
# Deux facons de s'en servir, detaillees dans SETUP.md :
#   depot monte  : docker compose run --rm update
#   depot clone  : docker compose run --rm publish   (avec DATASET_REPO_URL)

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# git est la seule dependance systeme : les scripts n'utilisent que la
# bibliotheque standard, il n'y a donc ni pip install ni requirements.txt.
# `ca-certificates` sert a joindre PostgREST et GitHub en HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /repo

COPY scripts/entrypoint.sh /opt/priceradar/entrypoint.sh
RUN chmod +x /opt/priceradar/entrypoint.sh

# Execution sans privileges. L'UID est surchargeable a l'execution
# (`user: "${UID}:${GID}"` dans docker-compose) : sur un depot monte depuis
# l'hote, les fichiers ecrits doivent appartenir a l'utilisateur de l'hote,
# sinon ils reviennent en root et git devient inutilisable hors du conteneur.
RUN useradd --create-home --uid 10001 radar \
    && chown -R radar:radar /repo /opt/priceradar
USER radar

# git refuse d'operer sur un depot dont le proprietaire differe de
# l'utilisateur courant. Sur un volume monte c'est le cas des que les UID ne
# coincident pas ; la regle leve ce refus pour ce chemin, et pour lui seul.
RUN git config --global --add safe.directory /repo

ENTRYPOINT ["/opt/priceradar/entrypoint.sh"]
