# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
from .acto import ACTO
from .borme import Borme
from .cargo import CARGO
from .download import (
    download_pdf,
    download_pdfs,
    download_xml,
    get_url_pdf,
    get_url_pdfs,
    get_url_xml,
)
from .emisor import EMISOR
from .parser import parse
from .provincia import PROVINCIA
from .seccion import SECCION
from .sumario import BormeXML

__all__ = [
    "ACTO",
    "Borme",
    "BormeXML",
    "CARGO",
    "CONFIG",
    "EMISOR",
    "PROVINCIA",
    "SECCION",
    "download_pdf",
    "download_pdfs",
    "download_xml",
    "get_url_pdf",
    "get_url_pdfs",
    "get_url_xml",
    "parse",
]


def __getattr__(name):
    # ``bormeparserv2.CONFIG`` se resuelve perezosamente: solo se lee
    # ``~/.bormecfg`` la primera vez que alguien lo solicita, en lugar
    # de hacerlo al importar el paquete.
    if name == "CONFIG":
        from .config import get_config

        return get_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
