#!/usr/bin/env python3
"""Boucle d'ordonnancement du conteneur.

Le conteneur reste actif, dort jusqu'au prochain creneau, lance la mise a jour,
puis se rendort. C'est le meme principe que le worker de collecte : un service
qui tourne, pas une tache que l'hebergeur doit savoir declencher.

Pourquoi pas cron dans l'image : cron veut un demon, tourne en root, ecrit ses
journaux dans un fichier plutot que sur la sortie standard, et avale les
variables d'environnement du conteneur. Une boucle de vingt lignes evite les
quatre problemes et se lit d'un coup d'oeil.

Environnement :
  UPDATE_TIMES     creneaux UTC, separes par des virgules. Defaut : 08:20,16:20,00:30
  RUN_ON_START     "true" (defaut) pour une mise a jour des le demarrage
  PUSH             transmis a update.sh ; le compose le met a "true"
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UPDATE = REPO / "scripts" / "update.sh"

DEFAULT_TIMES = "08:20,16:20,00:30"

# Touche a chaque reveil. Le healthcheck du conteneur regarde sa fraicheur :
# un fichier qui cesse d'etre touche signale une boucle bloquee, ce qu'un test
# de presence du processus ne verrait pas.
HEARTBEAT = Path("/tmp/scheduler-heartbeat")

_stop = False


def _handle_stop(signum, _frame) -> None:
    """Coolify arrete un conteneur par SIGTERM ; on sort proprement.

    Sans ce gestionnaire, l'arret survient au milieu d'un sleep et le
    conteneur est tue au bout du delai de grace, ce qui pollue les journaux a
    chaque redeploiement.
    """
    global _stop
    _stop = True
    log(f"Signal {signal.Signals(signum).name} recu, arret apres l'operation en cours.")


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}Z] {message}", flush=True)


def parse_times(raw: str) -> list[tuple[int, int]]:
    times: list[tuple[int, int]] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            hour, minute = chunk.split(":")
            slot = (int(hour), int(minute))
        except ValueError:
            sys.exit(f"UPDATE_TIMES invalide : {chunk!r} (format attendu HH:MM)")
        if not (0 <= slot[0] < 24 and 0 <= slot[1] < 60):
            sys.exit(f"UPDATE_TIMES hors bornes : {chunk!r}")
        times.append(slot)
    if not times:
        sys.exit("UPDATE_TIMES est vide : aucun creneau a programmer.")
    return sorted(set(times))


def next_run(times: list[tuple[int, int]], now: datetime) -> datetime:
    """Prochain creneau strictement posterieur a `now`, en UTC."""
    for hour, minute in times:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    hour, minute = times[0]
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)


def run_update() -> None:
    log("Mise a jour du jeu de donnees")
    result = subprocess.run(["bash", str(UPDATE)], cwd=REPO)
    if result.returncode == 0:
        log("Mise a jour terminee")
    else:
        # On ne s'arrete pas : une base injoignable ou un push refuse ne doit
        # pas tuer le service. Le creneau suivant retentera, et l'echec reste
        # visible dans les journaux Coolify.
        log(f"Echec de la mise a jour (code {result.returncode}) — nouvel essai au prochain creneau")


def beat() -> None:
    try:
        HEARTBEAT.touch()
    except OSError:
        pass


def sleep_until(target: datetime) -> None:
    """Dort jusqu'a `target`, par tranches, pour rester reactif a l'arret."""
    while not _stop:
        beat()
        remaining = (target - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    if not UPDATE.exists():
        sys.exit(f"{UPDATE} introuvable : le depot est-il bien monte dans /repo ?")

    beat()
    times = parse_times(os.environ.get("UPDATE_TIMES", DEFAULT_TIMES))
    log(f"Creneaux UTC : {', '.join(f'{h:02d}:{m:02d}' for h, m in times)}")

    if os.environ.get("RUN_ON_START", "true").lower() == "true":
        # Une mise a jour au demarrage rend le deploiement verifiable tout de
        # suite : on voit dans les journaux que la chaine complete fonctionne,
        # sans attendre le premier creneau. Elle ne commite que s'il y a du
        # nouveau, donc un redemarrage ne pollue pas l'historique.
        run_update()

    while not _stop:
        target = next_run(times, datetime.now(timezone.utc))
        log(f"Prochaine mise a jour : {target.strftime('%Y-%m-%d %H:%M')}Z")
        sleep_until(target)
        if _stop:
            break
        run_update()

    log("Arret.")


if __name__ == "__main__":
    main()
