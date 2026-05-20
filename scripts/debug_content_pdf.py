#!/usr/bin/env python
#
# debug_content_pdf.py - Debug PDF content
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

from pypdf import PdfReader


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug PDF content.")
    parser.add_argument("filename", help="BORME A PDF filename")
    args = parser.parse_args()

    with open(args.filename, "rb") as fp:
        reader = PdfReader(fp)
        pages = list(reader.pages)

    for page in pages:
        contents = page.get_contents()
        if contents is None:
            continue
        content = contents.get_data()
        if isinstance(content, bytes):
            content = content.decode("unicode_escape")
        for line in content.split("\n"):
            print(line)


if __name__ == "__main__":
    main()
