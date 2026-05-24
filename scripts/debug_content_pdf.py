#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# debug_content_pdf.py - Debug PDF content
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
import sys

from pypdf import PdfReader


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debug PDF content.")
    parser.add_argument("filename", help="BORME A PDF filename")
    args = parser.parse_args(argv)

    # PdfReader lee el stream de forma perezosa: ``page.get_contents()``
    # vuelve al fichero para resolver objetos indirectos. Si el ``with``
    # cierra el handle antes del bucle, pypdf revienta con
    # ``ValueError: seek of closed file``.
    with open(args.filename, "rb") as fp:
        reader = PdfReader(fp)
        for page in reader.pages:
            contents = page.get_contents()
            if contents is None:
                continue
            # Mismo decode que ``PyPDFParser._iter_page_contents``: el
            # content stream del PDF es latin-1, no unicode_escape (que
            # interpretaría secuencias ``\n`` literales como saltos).
            content = contents.get_data().decode("latin-1")
            for line in content.split("\n"):
                print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
