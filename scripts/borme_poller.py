#!/usr/bin/env python3
#
# borme_poller.py -
# Copyright (C) 2015 Pablo Castellano <pablo@anche.no>
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
import datetime
import time

import requests

# El endpoint antiguo (``boe.es/diario_borme/xml.php?id=BORME-S-...``)
# redirige a ``/error/errorParametros.php``; la API actual de datos
# abiertos devuelve 404 cuando todavía no hay BORME del día.
URL_BASE = "https://www.boe.es/datosabiertos/api/borme/sumario/"
DELAY = 5 * 60  # 5 minutes
LOGFILE = "xmlpoller.log"
TIMEOUT = 10


def is_available(status_code: int) -> bool:
    """``True`` si el sumario está publicado; ``False`` si la API
    indica que aún no existe (HTTP 404)."""
    return status_code == 200


def log_result(found: bool, status_code: int) -> None:
    with open(LOGFILE, "a") as fp:
        fp.write(str(datetime.datetime.now()) + "\n")
        print(datetime.datetime.now())
        minutes = int(DELAY / 60)
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


def wait_till_seven():
    now = datetime.datetime.now()
    with open(LOGFILE, "a") as fp:
        fp.write(str(now) + "\n")
        print(now)
        fp.write("Sleep until next 7:00")
        print("Sleep until next 7:00")
        fp.write("\n\n")
    wake_date = datetime.datetime.now() + datetime.timedelta(days=1)
    wake_date = wake_date.replace(hour=7, minute=0, second=0, microsecond=0)
    wake_seconds = (wake_date - datetime.datetime.now()).total_seconds()
    time.sleep(wake_seconds)


def wait_till_monday():
    now = datetime.datetime.now()
    with open(LOGFILE, "a") as fp:
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


def poll_xml_dl():
    while True:
        today = datetime.date.today()
        if today.weekday() in (5, 6):
            wait_till_monday()
        url = URL_BASE + today.strftime("%Y%m%d")
        try:
            response = requests.get(
                url, headers={"Accept": "application/xml"}, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            print(f"Request failed: {exc}")
            time.sleep(DELAY)
            continue
        found = is_available(response.status_code)
        log_result(found, response.status_code)
        if found:
            wait_till_seven()
        else:
            time.sleep(DELAY)


if __name__ == "__main__":
    poll_xml_dl()
