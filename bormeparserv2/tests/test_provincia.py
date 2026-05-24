#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# test_provincia.py - Regresiones sobre la coerción de provincia.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Pruebas para :meth:`PROVINCIA.coerce` y la API pública que la consume.

``Provincia.coerce`` es el adaptador entre las distintas formas
textuales que circulan por el ecosistema BORME (atributo ASCII de
``PROVINCIA``, nombre acentuado, forma bilingüe del sumario) y el
objeto :class:`Provincia` que espera el resto del paquete.

Sin esta normalización, los scripts CLI pasaban strings ASCII a
funciones que esperaban :class:`Provincia` y obtenían silencio
(:func:`get_url_pdfs`) o ``AttributeError`` (:func:`get_url_pdf`).
"""

import datetime
import os
import unittest

from bormeparserv2 import PROVINCIA, SECCION
from bormeparserv2.provincia import Provincia
from bormeparserv2.sumario import BormeXML

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
SUMARIO_FIXTURE = os.path.normpath(os.path.join(EXAMPLES, "BORME-S-20150924.xml"))


class ProvinciaCoerceTestCase(unittest.TestCase):
    """Cobertura exhaustiva de las formas que acepta ``Provincia.coerce``."""

    def test_passthrough_for_provincia_instance(self):
        self.assertIs(PROVINCIA.coerce(PROVINCIA.MADRID), PROVINCIA.MADRID)

    def test_ascii_attr_name(self):
        # Es la forma que usa ``argparse choices=ALL_PROVINCIAS``.
        self.assertIs(PROVINCIA.coerce("CACERES"), PROVINCIA.CACERES)
        self.assertIs(PROVINCIA.coerce("MADRID"), PROVINCIA.MADRID)

    def test_ascii_attr_name_case_insensitive(self):
        self.assertIs(PROVINCIA.coerce("caceres"), PROVINCIA.CACERES)
        self.assertIs(PROVINCIA.coerce("CaCeReS"), PROVINCIA.CACERES)

    def test_accented_uppercase_xml_form(self):
        # Forma exacta que emite el sumario en <titulo>.
        self.assertIs(PROVINCIA.coerce("CÁCERES"), PROVINCIA.CACERES)
        self.assertIs(PROVINCIA.coerce("ÁLAVA"), PROVINCIA.ALAVA)

    def test_human_readable_name(self):
        # Mismo nombre que ``Provincia.__str__``.
        self.assertIs(PROVINCIA.coerce("Cáceres"), PROVINCIA.CACERES)

    def test_from_title_accepts_bilingual_xml_forms(self):
        self.assertIs(PROVINCIA.from_title("VALENCIA/VALÈNCIA"), PROVINCIA.VALENCIA)
        self.assertIs(PROVINCIA.from_title("ALICANTE/ALACANT"), PROVINCIA.ALICANTE)
        self.assertIs(PROVINCIA.from_title("CASTELLÓN/CASTELLÓ"), PROVINCIA.CASTELLON)

    def test_bilingual_xml_form(self):
        # Bilingüe tal y como aparece en BORME-S: VALENCIA/VALÈNCIA,
        # ALICANTE/ALACANT, ARABA/ÁLAVA, CASTELLÓN/CASTELLÓ.
        self.assertIs(PROVINCIA.coerce("VALENCIA/VALÈNCIA"), PROVINCIA.VALENCIA)
        self.assertIs(PROVINCIA.coerce("ALICANTE/ALACANT"), PROVINCIA.ALICANTE)
        self.assertIs(PROVINCIA.coerce("ARABA/ÁLAVA"), PROVINCIA.ALAVA)
        self.assertIs(PROVINCIA.coerce("CASTELLÓN/CASTELLÓ"), PROVINCIA.CASTELLON)

    def test_underscore_separator(self):
        self.assertIs(PROVINCIA.coerce("A_CORUNA"), PROVINCIA.A_CORUNA)
        # Bilingüe inverso (con espacio): "A CORUÑA" es como lo emite el sumario.
        self.assertIs(PROVINCIA.coerce("A CORUÑA"), PROVINCIA.A_CORUNA)

    def test_unknown_string_raises_valueerror(self):
        with self.assertRaises(ValueError):
            PROVINCIA.coerce("CORUNA")  # nombre incompleto
        with self.assertRaises(ValueError):
            PROVINCIA.coerce("foo")
        with self.assertRaises(ValueError):
            PROVINCIA.coerce("")

    def test_non_string_raises_typeerror(self):
        for bad in (123, None, [], object()):
            with self.assertRaises(TypeError):
                PROVINCIA.coerce(bad)


class BormeXMLFiltersAcceptAllProvinciaFormsTestCase(unittest.TestCase):
    """``BormeXML._iter_items`` debe encontrar Cáceres con cualquier forma."""

    @classmethod
    def setUpClass(cls):
        cls.bxml = BormeXML.from_file(SUMARIO_FIXTURE)
        cls.expected = {
            "BORME-A-2015-183-10": (
                "https://www.boe.es/borme/dias/2015/09/24/pdfs/"
                "BORME-A-2015-183-10.pdf"
            )
        }

    def test_all_forms_resolve_to_same_pdf(self):
        # ``get_url_pdfs`` con seccion+provincia ⇒ dict {cve: url}.
        for value in (
            PROVINCIA.CACERES,
            "CACERES",
            "caceres",
            "CÁCERES",
            "Cáceres",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    self.bxml.get_url_pdfs(seccion=SECCION.A, provincia=value),
                    self.expected,
                )

    def test_get_sizes_accepts_ascii(self):
        sizes = self.bxml.get_sizes(seccion=SECCION.A, provincia="CACERES")
        self.assertIn("BORME-A-2015-183-10", sizes)


class DownloadApiAcceptsAllProvinciaFormsTestCase(unittest.TestCase):
    """``download.py`` debe normalizar ``provincia`` antes de filtrar.

    Sin la corrección:

    - ``get_url_pdf(date, SECCION.A, "CACERES")`` ⇒ ``AttributeError``
      al hacer ``provincia.code``.
    - ``get_url_pdfs(date, provincia="CACERES")`` ⇒ ``{}`` (silencio).
    """

    def setUp(self):
        # Cargamos el sumario una vez y monkeypatcheamos NADA: usamos las
        # funciones de download.py que se montan sobre fetchers reales,
        # pero las llamamos con un sumario local pre-cargado a través de
        # ``get_url_pdf_from_xml``.
        from bormeparserv2.download import get_url_pdf_from_xml

        self.get_url_pdf_from_xml = get_url_pdf_from_xml
        self.xml_path = SUMARIO_FIXTURE
        self.date = datetime.date(2015, 9, 24)
        self.expected = (
            "https://www.boe.es/borme/dias/2015/09/24/pdfs/BORME-A-2015-183-10.pdf"
        )

    def test_get_url_pdf_from_xml_accepts_ascii_string(self):
        url = self.get_url_pdf_from_xml(self.date, SECCION.A, "CACERES", self.xml_path)
        self.assertEqual(url, self.expected)

    def test_get_url_pdf_from_xml_accepts_accented_string(self):
        url = self.get_url_pdf_from_xml(self.date, SECCION.A, "CÁCERES", self.xml_path)
        self.assertEqual(url, self.expected)

    def test_get_url_pdf_from_xml_accepts_provincia_instance(self):
        url = self.get_url_pdf_from_xml(
            self.date, SECCION.A, PROVINCIA.CACERES, self.xml_path
        )
        self.assertEqual(url, self.expected)

    def test_unknown_provincia_raises_valueerror(self):
        with self.assertRaises(ValueError):
            self.get_url_pdf_from_xml(self.date, SECCION.A, "foo", self.xml_path)


class AllProvinciasArgparseChoicesTestCase(unittest.TestCase):
    """Toda etiqueta de ``ALL_PROVINCIAS`` debe poder coerce-arse a Provincia.

    ``argparse choices=ALL_PROVINCIAS`` solo deja pasar nombres válidos;
    si ``coerce`` rechaza alguno, el script CLI revienta más tarde con
    un error confuso.
    """

    def test_every_argparse_choice_coerces(self):
        from bormeparserv2.provincia import ALL_PROVINCIAS

        for name in ALL_PROVINCIAS:
            with self.subTest(name=name):
                prov = PROVINCIA.coerce(name)
                self.assertIsInstance(prov, Provincia)
