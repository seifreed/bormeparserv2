#!/usr/bin/env python3
#
# check_bormes.py - Check BORME files are present and not corrupt
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


import bormeparserv2
from bormeparserv2.exceptions import BormeDoesntExistException
from bormeparserv2._security import safe_join
from bormeparserv2.sumario import BormeXML
from bormeparserv2.utils import FIRST_BORME, get_borme_xml_filepath, get_borme_pdf_path

import argparse
import datetime
import logging
import os
import sys

BORME_ROOT = bormeparserv2.CONFIG["borme_root"]

logger = logging.getLogger("check_bormes")
ch = logging.StreamHandler()
logger.addHandler(ch)


def check_range(begin, end, provincia, seccion, directory, download_xml):
    """Downloads PDFs using threads"""
    next_date = begin
    results = {"good": 0, "missing": 0, "incorrect": 0}
    summary = []
    # bxml se rellena dentro del bucle; lo dejamos a None para no
    # disparar NameError si begin > end o el primer XML no se descarga.
    bxml = None
    xml_path = ""

    while next_date and next_date <= end:
        logger.info("Checking files from {}".format(next_date.isoformat()))
        xml_path = get_borme_xml_filepath(next_date, directory)
        logger.debug(xml_path)
        try:
            bxml = BormeXML.from_file(xml_path)
        except IOError:
            if download_xml:
                logger.info("Downloading {}".format(os.path.basename(xml_path)))
                bxml = BormeXML.from_date(next_date)
                os.makedirs(os.path.dirname(xml_path), exist_ok=True)
                bxml.save_to_file(xml_path)
            else:
                logger.info("Missing XML: {}\n".format(os.path.basename(xml_path)))
                logger.info("If you want to continue use --download-xml.\n")
                return

        sizes = bxml.get_sizes(seccion, provincia)
        path = get_borme_pdf_path(bxml.date, directory)

        for cve, size in sizes.items():
            logger.debug("Checking {}...".format(cve))
            filename = cve + ".pdf"
            filepath = safe_join(path, filename)

            logger.debug(filepath)
            if not os.path.exists(filepath):
                results["missing"] += 1
                logger.debug("Missing PDF: {}\n".format(filepath))
                summary.append(filepath)
                continue

            if os.path.getsize(filepath) != size:
                results["incorrect"] += 1
                logger.warning(
                    "{}: PDF size is incorrect (is {} but should be {})\n".format(
                        filepath, os.path.getsize(filepath), size
                    )
                )
                summary.append(filepath)
                continue

            results["good"] += 1
            logger.debug("OK\n")

        next_date = bxml.next_borme

    if bxml is None:
        print("\nNo BORMEs to check in the requested range.")
        return
    if bxml.date != end:
        print("\nWarning, could not continue and reach the end date.")
        print("Try removing " + xml_path + " and then run with --download-xml.")

    if len(summary) > 0:
        print("\nMissing or incorrect files:")
        print("\n".join(summary[:10]))
    if len(summary) > 10:
        print(
            "This list is truncated. There are {} files not shown.".format(
                len(summary) - 10
            )
        )

    print("\nResults:")
    print("\tGood: {}".format(results["good"]))
    print("\tIncorrect: {}".format(results["incorrect"]))
    print("\tMissing: {}".format(results["missing"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check BORME files are present and not corrupt."
    )
    parser.add_argument(
        "-f",
        "--fromdate",
        default="init",
        help="ISO formatted date (ex. 2015-01-01). Default: init",
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
        "-x",
        "--download-xml",
        action="store_true",
        default=False,
        help="Download missing XML BORME files",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Verbose mode"
    )
    args = parser.parse_args(argv)

    if args.verbose:
        bormeparserv2.download.logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    else:
        bormeparserv2.download.logger.setLevel(logging.INFO)
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
        check_range(
            date_from,
            date_to,
            args.provincia,
            args.seccion,
            args.directory,
            args.download_xml,
        )
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
