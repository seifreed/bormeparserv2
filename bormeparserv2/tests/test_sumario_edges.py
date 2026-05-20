#!/usr/bin/env python
#
# test_sumario_edges.py - Regresiones de bordes del parser de sumario.
# Copyright (C) 2015-2026 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Pruebas para entradas malformadas del sumario.

Los usuarios del paquete consumen ``BormeXML.from_file`` con ficheros
que pueden haber sido truncados, vacíos o sustituidos por basura. La
infraestructura ``lxml`` lanza ``XMLSyntaxError``, que es un detalle de
implementación: el paquete debe traducir esos errores a la jerarquía
declarada en ``bormeparserv2.exceptions``.
"""

import os
import tempfile
import unittest

from bormeparserv2.exceptions import BormeDoesntExistException
from bormeparserv2.sumario import BormeXML


class MalformedXmlIsConvertedToDomainErrorTestCase(unittest.TestCase):
    """``XMLSyntaxError`` se traduce a ``BormeDoesntExistException``."""

    def _from_file_with(self, content: str):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(content)
            path = fp.name
        try:
            return BormeXML.from_file(path)
        finally:
            os.unlink(path)

    def test_empty_file_raises_domain_exception(self):
        with self.assertRaises(BormeDoesntExistException):
            self._from_file_with("")

    def test_truncated_xml_raises_domain_exception(self):
        with self.assertRaises(BormeDoesntExistException):
            self._from_file_with('<?xml version="1.0"?><not closed')

    def test_wrong_root_raises_domain_exception(self):
        with self.assertRaises(BormeDoesntExistException) as ctx:
            self._from_file_with('<?xml version="1.0"?><root><foo>bar</foo></root>')
        self.assertIn("Expected <response> or <sumario>", str(ctx.exception))

    def test_xml_without_metadatos_fecha_raises_domain_exception(self):
        # <sumario> sin <metadatos><fecha_publicacion> debería romper
        # el parseo, no propagar AttributeError ni IndexError.
        with self.assertRaises(BormeDoesntExistException):
            self._from_file_with(
                '<?xml version="1.0"?><sumario><diario numero="1"/></sumario>'
            )


if __name__ == "__main__":
    unittest.main()
