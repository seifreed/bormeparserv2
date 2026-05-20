#!/usr/bin/env python3
#
# borme_json_all.py - Convert all BORME PDF files to JSON
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
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

import argparse
import os
import sys
import time
from queue import Queue
from threading import Thread

import bormeparserv2
import bormeparserv2.borme
from common import get_git_revision_short_hash

BORME_ROOT = bormeparserv2.CONFIG["borme_root"]
THREADS = 6


class ThreadConvertJSON(Thread):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def run(self):
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                return
            pdf_path, json_path = item
            print(f"Creating {json_path} ...")
            try:
                borme = bormeparserv2.parse(
                    pdf_path, bormeparserv2.SECCION.A, sanitize=True
                )
                borme.to_json(json_path)
                print("{cve}: OK".format(cve=borme.cve))
            except Exception as e:
                print("ERROR: {} ({})".format(os.path.basename(pdf_path), e))
            finally:
                self.queue.task_done()


def _listdir_sorted(path):
    """Devuelve los hijos de ``path`` ordenados o ``[]`` si no existe."""
    if not os.path.isdir(path):
        return []
    return sorted(os.listdir(path))


def walk_borme_root(bormes_root, json_root=None):
    """Recorre ``<bormes_root>/pdf/AAAA/MM/DD/`` emitiendo cada PDF.

    Si la subcarpeta ``pdf/`` no existe o está vacía el generador no
    produce nada. La versión anterior usaba ``next(os.walk(...))`` que
    lanzaba ``StopIteration`` (transformado en ``RuntimeError`` por
    PEP 479) cuando faltaba algún nivel.
    """
    pdf_root = os.path.join(bormes_root, "pdf")
    if json_root is None:
        json_root = os.path.join(bormes_root, "json")

    if not os.path.isdir(pdf_root):
        raise FileNotFoundError(
            f"No existe {pdf_root}. Estructura esperada: " f"<dir>/pdf/AAAA/MM/DD/*.pdf"
        )

    for year in _listdir_sorted(pdf_root):
        year_dir = os.path.join(pdf_root, year)
        if not os.path.isdir(year_dir):
            continue
        json_year_dir = os.path.join(json_root, year)
        for month in _listdir_sorted(year_dir):
            month_dir = os.path.join(year_dir, month)
            if not os.path.isdir(month_dir):
                continue
            json_month_dir = os.path.join(json_year_dir, month)
            for day in _listdir_sorted(month_dir):
                day_dir = os.path.join(month_dir, day)
                if not os.path.isdir(day_dir):
                    continue
                json_day_dir = os.path.join(json_month_dir, day)
                os.makedirs(json_day_dir, exist_ok=True)
                for filename in _listdir_sorted(day_dir):
                    if os.path.isfile(os.path.join(day_dir, filename)):
                        yield day_dir, json_day_dir, filename


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert all BORME PDF files to JSON.")
    parser.add_argument(
        "-d",
        "--directory",
        default=BORME_ROOT,
        help="Directory to download files (default is {})".format(BORME_ROOT),
    )
    args = parser.parse_args(argv)

    start_time = time.time()

    q: Queue = Queue()
    workers = []
    for _ in range(THREADS):
        t = ThreadConvertJSON(q)
        t.daemon = True
        t.start()
        workers.append(t)

    json_folder = "json_" + get_git_revision_short_hash()
    json_root = os.path.join(args.directory, json_folder)
    if os.path.exists(json_root):
        print("{} already exists".format(json_root))
        return 1

    try:
        items = list(walk_borme_root(args.directory, json_root))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    for day_dir, json_day_dir, filename in items:
        if not filename.endswith(".pdf") or filename.endswith("-99.pdf"):
            continue
        pdf_path = os.path.join(day_dir, filename)
        # Solo sustituye la extensión final; ``str.replace`` haría match
        # de cualquier ``.pdf`` dentro del nombre (p. ej. paths con
        # punto en el directorio padre).
        json_filename = filename[: -len(".pdf")] + ".json"
        json_path = os.path.join(json_day_dir, json_filename)
        q.put((pdf_path, json_path))
    q.join()
    for _ in workers:
        q.put(None)
    for t in workers:
        t.join()

    elapsed_time = time.time() - start_time
    print(f"Elapsed time: {elapsed_time:.2f} seconds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
