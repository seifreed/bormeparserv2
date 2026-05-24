#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# test_parse_edges.py - Regresiones del entrypoint público parse().
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Pruebas para entradas inválidas a ``bormeparserv2.parse``.

Mantienen el contrato actual de errores: ``FileNotFoundError`` cuando
el path no existe, ``ValueError`` para una sección sin backend
registrado, y ``NotImplementedError`` cuando un backend recibe un
formato que no implementa (BORME-C PDF).
"""

import os
import tempfile
import unittest

import bormeparserv2
from bormeparserv2 import SECCION

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
PDF_FIXTURE = os.path.normpath(os.path.join(EXAMPLES, "BORME-A-2015-27-10.pdf"))


class ParseInvalidInputsTestCase(unittest.TestCase):
    def test_nonexistent_path_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            bormeparserv2.parse("/no/such/path.pdf", SECCION.A)

    def test_unknown_seccion_raises_valueerror(self):
        with self.assertRaises(ValueError):
            bormeparserv2.parse(PDF_FIXTURE, "X")

    def test_borme_a_pdf_with_seccion_c_raises_notimplemented(self):
        # El backend de sección C no acepta PDFs (solo XML/HTML).
        with self.assertRaises(NotImplementedError):
            bormeparserv2.parse(PDF_FIXTURE, SECCION.C)

    def test_non_pdf_for_seccion_a_raises_clear_error(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".pdf", delete=False, encoding="utf-8"
        ) as fp:
            fp.write("not a pdf at all\n")
            path = fp.name
        try:
            with self.assertRaises(Exception) as ctx:
                bormeparserv2.parse(path, SECCION.A)
            # pypdf lanza ``PdfStreamError``; comprobamos solo que NO
            # se filtra como ``UnicodeDecodeError`` u otra cosa rara que
            # haría imposible diagnosticar.
            self.assertIn(
                type(ctx.exception).__name__,
                ("PdfStreamError", "PdfReadError"),
                msg=f"unexpected exception: {type(ctx.exception).__name__}: {ctx.exception}",
            )
        finally:
            os.unlink(path)

    def test_empty_pdf_raises_clear_error(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as fp:
            path = fp.name
        try:
            with self.assertRaises(Exception) as ctx:
                bormeparserv2.parse(path, SECCION.A)
            self.assertIn(
                type(ctx.exception).__name__,
                ("EmptyFileError", "PdfReadError"),
                msg=f"unexpected: {type(ctx.exception).__name__}",
            )
        finally:
            os.unlink(path)
