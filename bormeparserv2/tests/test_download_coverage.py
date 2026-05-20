#!/usr/bin/env python
#
# test_download_coverage.py - Branches secundarias de download.py.
# Copyright (C) 2015-2026 Marc Rivero López <mriverolopez@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Cobertura adicional de ``bormeparserv2.download``.

Cubre las funciones de utilidad y los caminos error/idempotente sin
red, y los caminos de red bajo ``BORMEPARSERV2_LIVE=1``: descarga
multihilo (``download_urls_multi``, ``download_urls_multi_names``),
``download_xml``, ``download_pdfs`` y las variantes ``get_url_pdfs_*``
contra el sumario de boe.es.
"""

import datetime
import os
import tempfile
import unittest

from bormeparserv2 import PROVINCIA, SECCION
from bormeparserv2.exceptions import (
    BormeDoesntExistException,
    MissingFilterException,
)

EXAMPLES = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "examples"))
SUMARIO_FIXTURE = os.path.join(EXAMPLES, "BORME-S-20150924.xml")

LIVE = os.environ.get("BORMEPARSERV2_LIVE") == "1"
require_live = unittest.skipUnless(
    LIVE, "set BORMEPARSERV2_LIVE=1 to run tests that hit boe.es"
)


class GetNboFromXmlTestCase(unittest.TestCase):
    """``get_nbo_from_xml`` extrae el atributo ``numero`` del ``<diario>``."""

    def test_extracts_nbo_from_fixture(self):
        from bormeparserv2.download import get_nbo_from_xml

        nbo = get_nbo_from_xml(SUMARIO_FIXTURE)
        self.assertEqual(nbo, "183")

    def test_missing_diario_raises(self):
        from bormeparserv2.download import get_nbo_from_xml

        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(
                '<?xml version="1.0"?><sumario>'
                "<metadatos><fecha_publicacion>20150210</fecha_publicacion></metadatos>"
                "</sumario>"
            )
            path = fp.name
        try:
            with self.assertRaises(BormeDoesntExistException):
                get_nbo_from_xml(path)
        finally:
            os.unlink(path)

    def test_missing_numero_attr_raises(self):
        from bormeparserv2.download import get_nbo_from_xml

        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(
                '<?xml version="1.0"?><sumario>'
                "<metadatos><fecha_publicacion>20150210</fecha_publicacion></metadatos>"
                "<diario/>"
                "</sumario>"
            )
            path = fp.name
        try:
            with self.assertRaises(BormeDoesntExistException) as ctx:
                get_nbo_from_xml(path)
            self.assertIn("numero", str(ctx.exception))
        finally:
            os.unlink(path)


class GetUrlPdfFromXmlTestCase(unittest.TestCase):
    """``get_url_pdf_from_xml`` resuelve la URL desde un sumario local."""

    def test_returns_pdf_url_for_known_provincia(self):
        from bormeparserv2.download import get_url_pdf_from_xml

        url = get_url_pdf_from_xml(
            datetime.date(2015, 9, 24), SECCION.A, "CACERES", SUMARIO_FIXTURE
        )
        self.assertTrue(url.endswith("BORME-A-2015-183-10.pdf"))

    def test_unknown_provincia_raises_valueerror(self):
        from bormeparserv2.download import get_url_pdf_from_xml

        with self.assertRaises(ValueError):
            get_url_pdf_from_xml(
                datetime.date(2015, 9, 24), SECCION.A, "ZZZ", SUMARIO_FIXTURE
            )

    def test_existing_provincia_not_in_sumario_raises_domain_error(self):
        from bormeparserv2.download import get_url_pdf_from_xml

        # MELILLA es una provincia conocida pero no apareció en el sumario
        # del 2015-09-24 → BormeDoesntExistException.
        with self.assertRaises(BormeDoesntExistException):
            get_url_pdf_from_xml(
                datetime.date(2015, 9, 24), SECCION.A, "MELILLA", SUMARIO_FIXTURE
            )


class GetUrlPdfsValidationTestCase(unittest.TestCase):
    """``get_url_pdfs`` y ``get_url_pdfs_seccion`` rechazan entradas inválidas."""

    def test_get_url_pdfs_no_filter_raises(self):
        from bormeparserv2.download import get_url_pdfs

        with self.assertRaises(MissingFilterException):
            get_url_pdfs(datetime.date(2015, 9, 24))

    def test_get_url_pdfs_seccion_only_c_raises_valueerror(self):
        # ``get_url_pdfs_seccion`` solo acepta A o B (línea 224).
        from bormeparserv2.download import get_url_pdfs_seccion

        with self.assertRaises(ValueError):
            get_url_pdfs_seccion(datetime.date(2015, 9, 24), SECCION.C)


class DownloadUrlIdempotentTestCase(unittest.TestCase):
    """``download_url`` no toca red si el destino ya existe."""

    def test_returns_false_when_destination_present(self):
        from bormeparserv2.download import download_url

        with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as fp:
            fp.write(b"%PDF-1.4 ya existe")
            path = fp.name
        try:
            result = download_url("https://example.invalid/whatever.pdf", path)
            self.assertFalse(result)
        finally:
            os.unlink(path)


class DownloadXmlIdempotentTestCase(unittest.TestCase):
    """``download_xml`` no toca red si el destino ya existe (línea 129)."""

    def test_returns_false_when_destination_present(self):
        from bormeparserv2.download import download_xml

        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write("<?xml version='1.0'?><sumario/>")
            path = fp.name
        try:
            result = download_xml(datetime.date(2015, 2, 10), path)
            self.assertFalse(result)
        finally:
            os.unlink(path)


class DownloadUrlsTestCase(unittest.TestCase):
    """``download_urls`` itera URLs y solo escribe las que faltan en disco."""

    def test_returns_empty_when_all_destinations_exist(self):
        from bormeparserv2.download import download_urls

        with tempfile.TemporaryDirectory() as tmp:
            # Pre-creamos los destinos para que ``download_url`` devuelva False
            # y la función no haga red.
            existing = os.path.join(tmp, "fake.pdf")
            with open(existing, "wb") as fp:
                fp.write(b"existing")
            urls = {"x": "https://example.invalid/fake.pdf"}
            result = download_urls(urls, tmp)
            self.assertEqual(result, [])


class DownloadUrlsMultiOfflineTestCase(unittest.TestCase):
    """``download_urls_multi`` y ``_names`` no descargan si los destinos existen.

    Cubre el worker hilo, el centinela y el join de la cola. Como los
    destinos ya están en disco, ``download_url`` devuelve False y los
    workers nunca tocan la red.
    """

    def test_multi_skips_existing_files(self):
        from bormeparserv2.download import download_urls_multi

        with tempfile.TemporaryDirectory() as tmp:
            # Pre-creamos 3 destinos.
            for name in ("a.pdf", "b.pdf", "c.pdf"):
                with open(os.path.join(tmp, name), "wb") as fp:
                    fp.write(b"existing")
            urls = {
                "x1": "https://example.invalid/a.pdf",
                "x2": "https://example.invalid/b.pdf",
                "x3": "https://example.invalid/c.pdf",
            }
            files = download_urls_multi(urls, tmp, threads=2)
            self.assertEqual(files, [])

    def test_multi_names_skips_existing_files(self):
        from bormeparserv2.download import download_urls_multi_names

        with tempfile.TemporaryDirectory() as tmp:
            for name in ("borme-1.xml", "borme-2.xml"):
                with open(os.path.join(tmp, name), "wb") as fp:
                    fp.write(b"existing")
            urls = {
                "borme-1.xml": "https://example.invalid/whatever1",
                "borme-2.xml": "https://example.invalid/whatever2",
            }
            files = download_urls_multi_names(urls, tmp, threads=2)
            self.assertEqual(files, [])


@require_live
class GetUrlPdfsLiveTestCase(unittest.TestCase):
    """``get_url_pdfs_seccion`` y ``get_url_seccion_c`` contra boe.es."""

    DATE = datetime.date(2015, 9, 24)

    def test_get_url_pdfs_seccion_a_returns_provincia_keyed_dict(self):
        from bormeparserv2.download import get_url_pdfs_seccion

        urls = get_url_pdfs_seccion(self.DATE, SECCION.A)
        self.assertIn("MADRID", urls)
        self.assertTrue(urls["MADRID"].endswith(".pdf"))

    def test_get_url_seccion_c_returns_apartado_grouped_dict(self):
        from bormeparserv2.download import get_url_seccion_c

        urls = get_url_seccion_c(self.DATE, format="xml")
        # Algún apartado debe estar presente, con URLs en xml.
        self.assertTrue(urls)
        for _apartado, items in urls.items():
            self.assertTrue(all(u and u.startswith("http") for u in items.values()))

    def test_get_url_seccion_c_pdf_format(self):
        from bormeparserv2.download import get_url_seccion_c

        urls = get_url_seccion_c(self.DATE, format="pdf")
        self.assertTrue(urls)

    def test_get_url_pdfs_provincia_returns_seccion_keyed_dict(self):
        from bormeparserv2.download import get_url_pdfs_provincia

        urls = get_url_pdfs_provincia(self.DATE, PROVINCIA.MADRID)
        self.assertIn("A", urls)


@require_live
class DownloadPdfsLiveTestCase(unittest.TestCase):
    """Pipeline live: ``download_pdfs`` para una fecha+provincia → 1 fichero."""

    def test_download_pdfs_for_cc_2015_02_10(self):
        from bormeparserv2.download import download_pdfs

        with tempfile.TemporaryDirectory() as tmp:
            ok, files = download_pdfs(
                datetime.date(2015, 2, 10),
                tmp,
                provincia=PROVINCIA.CACERES,
                seccion=SECCION.A,
            )
            self.assertTrue(ok)
            # download_pdfs ⇒ get_url_pdfs (A+provincia) ⇒ download_urls.
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].endswith(".pdf"))


@require_live
class DownloadXmlLiveTestCase(unittest.TestCase):
    """``download_xml`` escribe el sumario real cuando el fichero no existe."""

    def test_download_xml_creates_file(self):
        from bormeparserv2.download import download_xml

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sumario.xml")
            ok = download_xml(datetime.date(2015, 2, 10), path)
            self.assertTrue(ok)
            self.assertGreater(os.path.getsize(path), 1000)


@require_live
class DownloadMultithreadLiveTestCase(unittest.TestCase):
    """``download_urls_multi`` descarga real con 2 hilos.

    Usamos el sumario del 2015-09-24 y pedimos solo las dos primeras
    URLs para que el test no se eternice.
    """

    def test_multi_downloads_a_pair_of_pdfs(self):
        from bormeparserv2.download import download_urls_multi
        from bormeparserv2.sumario import BormeXML

        bxml = BormeXML.from_file(SUMARIO_FIXTURE)
        urls = bxml.get_url_pdfs(seccion=SECCION.A)
        # Reducimos a 2 URLs.
        subset = dict(list(urls.items())[:2])
        with tempfile.TemporaryDirectory() as tmp:
            files = download_urls_multi(subset, tmp, threads=2)
            self.assertEqual(len(files), 2)
            for f in files:
                self.assertGreater(os.path.getsize(f), 1000)


if __name__ == "__main__":
    unittest.main()
