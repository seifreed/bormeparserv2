#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# download_borme_pdfs_A.py - Download BORME PDF files
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


import bormeparserv2
from bormeparserv2.exceptions import BormeDoesntExistException
from bormeparserv2.sumario import BormeXML
from bormeparserv2.utils import FIRST_BORME, get_borme_xml_filepath, get_borme_pdf_path

import argparse
import datetime
import logging
import os
import sys

BORME_ROOT = bormeparserv2.CONFIG["borme_root"]

logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
logger.addHandler(ch)


def download_range(begin, end, directory, seccion, provincia=None):
    """Downloads PDFs using threads"""
    next_date = begin
    total_downloaded = 0

    while next_date and next_date <= end:
        path = get_borme_pdf_path(next_date, directory)
        xml_path = get_borme_xml_filepath(next_date, directory)
        logger.info(
            "\nDownloading files from {} (sección {}) to {}\n".format(
                next_date, seccion, path
            )
        )
        try:
            bxml = BormeXML.from_file(xml_path)
            if bxml.next_borme:
                logger.debug(
                    "{filename} already exists!".format(
                        filename=os.path.basename(xml_path)
                    )
                )
            else:
                logger.debug(
                    "Re-downloading {filename}".format(
                        filename=os.path.basename(xml_path)
                    )
                )
                bxml = BormeXML.from_date(next_date)
                os.makedirs(os.path.dirname(xml_path), exist_ok=True)
                bxml.save_to_file(xml_path)

        except IOError:
            logger.debug(
                "Downloading {filename}".format(filename=os.path.basename(xml_path))
            )
            bxml = BormeXML.from_date(next_date)
            os.makedirs(os.path.dirname(xml_path), exist_ok=True)
            bxml.save_to_file(xml_path)

        os.makedirs(path, exist_ok=True)

        _, files = bxml.download_borme(path, provincia=provincia, seccion=seccion)

        if len(files) > 0:
            logger.info("Downloaded {} files from {}".format(len(files), next_date))
        total_downloaded += len(files)
        next_date = bxml.next_borme

    logger.info("\n{} total files were downloaded".format(total_downloaded))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download BORME PDF files.")
    parser.add_argument(
        "-f",
        "--fromdate",
        default="today",
        help='ISO formatted date (ex. 2015-01-01) or "init". Default: today',
    )
    parser.add_argument(
        "-t",
        "--to",
        default="today",
        help="ISO formatted date (ex. 2016-01-01). Default: today",
    )
    parser.add_argument(
        "-d",
        "--directory",
        default=BORME_ROOT,
        help="Directory to download files (default is {})".format(BORME_ROOT),
    )
    parser.add_argument(
        "-s",
        "--seccion",
        default=bormeparserv2.SECCION.A,
        choices=["A", "B", "C"],
        help="BORME seccion",
    )
    parser.add_argument(
        "-p",
        "--provincia",
        choices=bormeparserv2.provincia.ALL_PROVINCIAS,
        help="BORME provincia",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Verbose mode"
    )
    args = parser.parse_args(argv)

    bormeparserv2.borme.logger.setLevel(logging.ERROR)
    if args.verbose:
        bormeparserv2.download.logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    else:
        bormeparserv2.download.logger.setLevel(logging.ERROR)
        logger.setLevel(logging.INFO)

    if args.fromdate == "init":
        date_from = FIRST_BORME[2009]
    elif args.fromdate == "today":
        date_from = datetime.date.today()
    else:
        date_from = datetime.datetime.strptime(args.fromdate, "%Y-%m-%d").date()

    if args.to == "today":
        date_to = datetime.date.today()
    else:
        date_to = datetime.datetime.strptime(args.to, "%Y-%m-%d").date()

    try:
        download_range(date_from, date_to, args.directory, args.seccion, args.provincia)
    except BormeDoesntExistException:
        logger.warning(
            "It looks like there is no BORME for the start date ({}). Nothing was downloaded".format(
                date_from
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
