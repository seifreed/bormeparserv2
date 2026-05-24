# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-License-Identifier: GPL-3.0-or-later
#
from .pypdf.parser import PyPDFParser
from .seccion_c.lxml.parser import LxmlBormeCParser

__all__ = ["PyPDFParser", "LxmlBormeCParser"]
