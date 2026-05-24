#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# borme_poller.py - Espera a que el BORME del día esté disponible
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


# El BORME se publica los días laborables y normalmente a las 7:30 de la mañana
import argparse
import datetime
import sys
import time

import requests

# El endpoint antiguo (``boe.es/diario_borme/xml.php?id=BORME-S-...``)
# redirige a ``/error/errorParametros.php``; la API actual de datos
# abiertos devuelve 404 cuando todavía no hay BORME del día.
URL_BASE = "https://www.boe.es/datosabiertos/api/borme/sumario/"
DEFAULT_DELAY = 5 * 60  # 5 minutes
DEFAULT_LOGFILE = "xmlpoller.log"
TIMEOUT = 10


def is_available(status_code: int) -> bool:
    """``True`` si el sumario está publicado; ``False`` si la API
    indica que aún no existe (HTTP 404)."""
    return status_code == 200


def log_result(logfile: str, found: bool, status_code: int, delay: int) -> None:
    with open(logfile, "a") as fp:
        fp.write(str(datetime.datetime.now()) + "\n")
        print(datetime.datetime.now())
        minutes = int(delay / 60)
        if found:
            message = f"AVAILABLE! (HTTP {status_code})"
        else:
            message = (
                f"Not available yet (HTTP {status_code}). "
                f"I will try again in {minutes} minutes."
            )
        fp.write(message)
        print(message)
        fp.write("\n\n")


def wait_till_seven(logfile: str) -> None:
    now = datetime.datetime.now()
    with open(logfile, "a") as fp:
        fp.write(str(now) + "\n")
        print(now)
        fp.write("Sleep until next 7:00")
        print("Sleep until next 7:00")
        fp.write("\n\n")
    wake_date = datetime.datetime.now() + datetime.timedelta(days=1)
    wake_date = wake_date.replace(hour=7, minute=0, second=0, microsecond=0)
    wake_seconds = (wake_date - datetime.datetime.now()).total_seconds()
    time.sleep(wake_seconds)


def wait_till_monday(logfile: str) -> None:
    now = datetime.datetime.now()
    with open(logfile, "a") as fp:
        fp.write(str(now) + "\n")
        print(now)
        fp.write("Sleep until next Monday 7:00")
        print("Sleep until next Monday 7:00")
        fp.write("\n\n")

    n = (0 - now.weekday()) % 7  # Days till next Monday
    wake_date = now + datetime.timedelta(days=n)
    wake_date = wake_date.replace(hour=7, minute=0, second=0, microsecond=0)
    wake_seconds = (wake_date - datetime.datetime.now()).total_seconds()
    time.sleep(wake_seconds)


def check_once(
    url_base: str = URL_BASE, target_date: datetime.date | None = None
) -> int:
    """Consulta la API una vez y devuelve el status code (-1 si la red falla)."""
    if target_date is None:
        target_date = datetime.date.today()
    url = url_base + target_date.strftime("%Y%m%d")
    try:
        response = requests.get(
            url, headers={"Accept": "application/xml"}, timeout=TIMEOUT
        )
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return -1
    return response.status_code


def poll_xml_dl(
    url_base: str = URL_BASE,
    delay: int = DEFAULT_DELAY,
    logfile: str = DEFAULT_LOGFILE,
    once: bool = False,
) -> int:
    """Bucle de polling. Devuelve el status code de la última consulta.

    Con ``once=True`` ejecuta una sola iteración (útil para tests y
    cron). En modo bucle, espera ``delay`` segundos entre intentos,
    salta el fin de semana, y tras encontrar el sumario duerme hasta
    las 7:00 del día siguiente.
    """
    while True:
        today = datetime.date.today()
        if today.weekday() in (5, 6) and not once:
            wait_till_monday(logfile)
            continue
        status = check_once(url_base, today)
        if status == -1:
            if once:
                return status
            time.sleep(delay)
            continue
        found = is_available(status)
        log_result(logfile, found, status, delay)
        if once:
            return status
        if found:
            wait_till_seven(logfile)
        else:
            time.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Polls the BOE BORME sumario endpoint until the daily issue is "
            "published. Designed to run as a daemon."
        )
    )
    parser.add_argument(
        "--url",
        default=URL_BASE,
        help=f"Base URL of the sumario endpoint (default: {URL_BASE})",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_DELAY,
        help=f"Seconds between attempts when not yet published (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--logfile",
        default=DEFAULT_LOGFILE,
        help=f"File to append polling history (default: {DEFAULT_LOGFILE})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single check then exit (exit code 0 if available, 1 otherwise)",
    )
    args = parser.parse_args(argv)

    status = poll_xml_dl(
        url_base=args.url,
        delay=args.delay,
        logfile=args.logfile,
        once=args.once,
    )
    if args.once:
        return 0 if is_available(status) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
