#!/usr/bin/env python
#
# borme_info.py - Shows BORME A info
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
import bormeparserv2.backends.pypdf.parser
from bormeparserv2.exceptions import BormeAnuncioNotFound

import argparse
import logging
import sys


def print_anuncio(anuncio):
    print("\nAnuncio {}".format(anuncio.id))
    print("-" * (8 + len(str(anuncio.id))))
    print()
    for acto, valor in anuncio.get_actos():
        print("  {}".format(acto))
        print("    {}".format(valor))
    print("  Datos registrales")
    print("    " + anuncio.datos_registrales)
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shows BORME A info.")
    parser.add_argument("filename", help="BORME A PDF filename")
    # ``action='append'`` evita la ambigüedad de ``nargs='*'``: con
    # ``nargs='*' type=int`` argparse devoraba ``filename`` como número
    # más (``invalid int value: '<ruta al PDF>'``). Ahora se invoca como
    # ``-n 57315 -n 57316`` y el positional queda separado sin tener que
    # forzar ``--``.
    parser.add_argument(
        "-n",
        "--number",
        action="append",
        type=int,
        metavar="NUMBER",
        help="Filtra anuncios por id; repetir el flag para varios",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Verbose mode"
    )
    args = parser.parse_args(argv)

    if args.verbose:
        # Sin basicConfig los loggers no tienen handler y los mensajes
        # DEBUG se descartan aunque pongas el nivel del logger en DEBUG.
        logging.basicConfig(level=logging.DEBUG)
        bormeparserv2.borme.logger.setLevel(logging.DEBUG)
        bormeparserv2.backends.pypdf.parser.logger.setLevel(logging.DEBUG)

    borme = bormeparserv2.parse(args.filename, bormeparserv2.SECCION.A)

    if args.number:
        anuncios = []
        for n in args.number:
            try:
                anuncio = borme.get_anuncio(n)
                anuncios.append(anuncio)
            except BormeAnuncioNotFound:
                print(
                    "No existe el anuncio {}. Elije uno entre {} y {}.".format(
                        n, borme.anuncios_rango[0], borme.anuncios_rango[1]
                    )
                )
                return 1
    else:
        anuncios = borme.get_anuncios()

    for anuncio in anuncios:
        print_anuncio(anuncio)

    if not args.number:
        print("Otros datos")
        print("-----\n")
        print("  CVE: {}".format(borme.cve))
        print("  Fecha: {}".format(borme.date))
        print("  Num: {}".format(borme.num))
        print("  Provincia: {}".format(borme.provincia))
        print("  Seccion: {}".format(borme.seccion))
        print("  Anuncios incluidos: {}".format(len(borme.get_anuncios())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
