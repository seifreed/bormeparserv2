#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# utils.py - Utilidades menores (paths, slugs, normalización).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import datetime
import os
import re
import unicodedata

from .config import get_config

FIRST_BORME = {
    2009: datetime.date(2009, 1, 2),
    2010: datetime.date(2010, 1, 4),
    2011: datetime.date(2011, 1, 3),
    2012: datetime.date(2012, 1, 2),
    2013: datetime.date(2013, 1, 2),
    2014: datetime.date(2014, 1, 2),
    2015: datetime.date(2015, 1, 2),
}


BORME_WEB_URL = (
    "{protocol}://www.boe.es/borme/dias/{year}/{month:02d}/{day:02d}/"
    "index.php?s={seccion}"
)


def get_borme_website(date, seccion, secure=True):
    protocol = "https" if secure else "http"
    return BORME_WEB_URL.format(
        protocol=protocol,
        year=date.year,
        month=date.month,
        day=date.day,
        seccion=seccion,
    )


def remove_accents(string):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", string)
        if unicodedata.category(c) != "Mn"
    )


def acto_to_attr(acto):
    attr = (
        remove_accents(acto)
        .replace(" del ", " ")
        .replace(" por ", " ")
        .replace(" de ", " ")
    )
    attr = attr.replace(" ", "_").replace("/", "_").replace(".", "_").lower()
    # Conserva dígitos: "Adaptación Ley 44/2015" debe distinguirse de
    # "Adaptación Ley 2/95", no colisionar en "adaptacion_ley".
    attr = re.sub(r"[^A-Za-z0-9_]+", "", attr)
    # Colapsa runs de guiones bajos que dejan los separadores múltiples.
    attr = re.sub(r"_+", "_", attr)
    return attr.strip("_")


def _resolve_borme_root(directory):
    return directory if directory is not None else get_config()["borme_root"]


def get_borme_xml_filepath(date, directory=None):
    directory = _resolve_borme_root(directory)
    year = str(date.year)
    month = "{:02d}".format(date.month)
    day = "{:02d}".format(date.day)
    filename = "BORME-S-{}{}{}.xml".format(year, month, day)
    return os.path.join(directory, "xml", year, month, filename)


def get_borme_pdf_path(date, directory=None):
    directory = _resolve_borme_root(directory)
    year = str(date.year)
    month = "{:02d}".format(date.month)
    day = "{:02d}".format(date.day)
    return os.path.join(directory, "pdf", year, month, day)
