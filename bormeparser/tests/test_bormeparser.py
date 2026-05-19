#!/usr/bin/env python
#
# test_bormeparser.py - Tests para la API pública de bormeparser
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import datetime
import os
import tempfile
import unittest

import bormeparser
from bormeparser.borme import Borme
from bormeparser.exceptions import BormeDoesntExistException

LIVE = os.environ.get("BORMEPARSER_LIVE") == "1"
require_live = unittest.skipUnless(
    LIVE,
    "set BORMEPARSER_LIVE=1 to run tests that hit boe.es",
)

DATE = (2015, 6, 2)
SUMARIO_URL_HTTPS = "https://www.boe.es/datosabiertos/api/borme/sumario/20150602"
SUMARIO_URL_HTTP = "http://www.boe.es/datosabiertos/api/borme/sumario/20150602"
MALAGA_PDF_URL = (
    "https://www.boe.es/borme/dias/2015/06/02/pdfs/BORME-A-2015-102-29.pdf"
)


class BormeparserUrlBuildersTestCase(unittest.TestCase):
    """Construcción de URLs — puramente funcional, sin red."""

    def test_url_xml_tuple(self):
        self.assertEqual(
            bormeparser.get_url_xml(DATE, secure=True), SUMARIO_URL_HTTPS
        )

    def test_url_xml_datetime(self):
        date = datetime.date(*DATE)
        self.assertEqual(
            bormeparser.get_url_xml(date, secure=True), SUMARIO_URL_HTTPS
        )

    def test_url_xml_insecure(self):
        self.assertEqual(
            bormeparser.get_url_xml(DATE, secure=False), SUMARIO_URL_HTTP
        )


class BormeparserInvalidDateTestCase(unittest.TestCase):
    """Fechas inválidas — falla en la construcción, sin red."""

    bad_date = (2015, 6, 31)

    def test_url_xml_raises(self):
        self.assertRaises(ValueError, bormeparser.get_url_xml, self.bad_date)

    def test_url_pdf_raises(self):
        self.assertRaises(
            ValueError,
            bormeparser.get_url_pdf,
            self.bad_date,
            bormeparser.SECCION.A,
            bormeparser.PROVINCIA.MALAGA,
        )

    def test_url_pdfs_raises(self):
        self.assertRaises(
            ValueError,
            bormeparser.get_url_pdfs,
            self.bad_date,
            bormeparser.SECCION.A,
        )


@require_live
class BormeparserLivePdfUrlsTestCase(unittest.TestCase):
    """Construcción de URLs de PDF que consulta el sumario remoto."""

    def test_url_pdf_malaga(self):
        url = bormeparser.get_url_pdf(
            DATE, bormeparser.SECCION.A, bormeparser.PROVINCIA.MALAGA
        )
        self.assertEqual(url, MALAGA_PDF_URL)

    def test_url_pdfs_seccion_contains_all_provinces(self):
        urls = bormeparser.get_url_pdfs(DATE, seccion=bormeparser.SECCION.A)
        self.assertIn("MÁLAGA", urls)
        self.assertEqual(urls["MÁLAGA"], MALAGA_PDF_URL)
        self.assertTrue(
            all(u.startswith("https://www.boe.es/borme/") for u in urls.values())
        )


@require_live
class BormeparserLiveBormeDoesntExistTestCase(unittest.TestCase):
    """El BOE no publica BORME en domingos."""

    weekend_date = (2015, 6, 6)

    def test_url_pdf_raises(self):
        self.assertRaises(
            BormeDoesntExistException,
            bormeparser.get_url_pdf,
            self.weekend_date,
            bormeparser.SECCION.A,
            bormeparser.PROVINCIA.MALAGA,
        )

    def test_url_pdfs_raises(self):
        self.assertRaises(
            BormeDoesntExistException,
            bormeparser.get_url_pdfs,
            self.weekend_date,
            bormeparser.SECCION.A,
        )


@require_live
class BormeparserLiveDownloadTestCase(unittest.TestCase):
    def test_download_xml(self):
        path = os.path.join(tempfile.gettempdir(), "20150602.xml")
        try:
            downloaded = bormeparser.download_xml(DATE, path)
            self.assertTrue(downloaded)
            self.assertGreater(os.path.getsize(path), 1000)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_download_pdf(self):
        path = os.path.join(tempfile.gettempdir(), "BORME-A-2015-102-29.pdf")
        try:
            downloaded = bormeparser.download_pdf(
                DATE,
                path,
                bormeparser.SECCION.A,
                bormeparser.PROVINCIA.MALAGA,
            )
            self.assertTrue(downloaded)
            self.assertGreater(os.path.getsize(path), 10000)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_download_and_parse_pdf(self):
        path = os.path.join(tempfile.gettempdir(), "BORME-A-2015-102-29.pdf")
        try:
            borme = bormeparser.download_pdf(
                DATE,
                path,
                bormeparser.SECCION.A,
                bormeparser.PROVINCIA.MALAGA,
                parse=True,
            )
            self.assertIsInstance(borme, Borme)
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
