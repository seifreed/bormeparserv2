#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# borme_to_json.py - Convert BORME A PDF files to JSON
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
import logging
import os
import sys

import bormeparserv2
import bormeparserv2.backends.pypdf.parser


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert BORME A PDF files to JSON.")
    parser.add_argument("filename", help="BORME A PDF filename")
    parser.add_argument(
        "--debug", action="store_true", default=False, help="Debug mode"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory or filename (default is current directory)",
    )
    args = parser.parse_args(argv)

    if args.debug:
        # basicConfig conecta un handler; sin él los DEBUG se pierden
        # aunque el nivel del logger sea DEBUG.
        logging.basicConfig(level=logging.DEBUG)
        bormeparserv2.borme.logger.setLevel(logging.DEBUG)
        bormeparserv2.backends.pypdf.parser.logger.setLevel(logging.DEBUG)

    print("\nParsing {}".format(args.filename))
    borme = bormeparserv2.parse(args.filename, bormeparserv2.SECCION.A, sanitize=True)
    path = borme.to_json(args.output)

    if path:
        print("Created {}".format(os.path.abspath(path)))
        return 0
    print("Error creating JSON for {}".format(args.filename))
    return 1


if __name__ == "__main__":
    sys.exit(main())
