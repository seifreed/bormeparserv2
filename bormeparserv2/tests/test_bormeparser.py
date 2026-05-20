#!/usr/bin/env python
#
# test_bormeparser.py - Tests para la API pública de bormeparserv2
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

import bormeparserv2
from bormeparserv2.borme import Borme
from bormeparserv2.exceptions import BormeDoesntExistException

LIVE = os.environ.get("BORMEPARSERV2_LIVE") == "1"
require_live = unittest.skipUnless(
    LIVE,
    "set BORMEPARSERV2_LIVE=1 to run tests that hit boe.es",
)

DATE = (2015, 6, 2)
SUMARIO_URL_HTTPS = "https://www.boe.es/datosabiertos/api/borme/sumario/20150602"
SUMARIO_URL_HTTP = "http://www.boe.es/datosabiertos/api/borme/sumario/20150602"
MALAGA_PDF_URL = "https://www.boe.es/borme/dias/2015/06/02/pdfs/BORME-A-2015-102-29.pdf"


class BormeparserUrlBuildersTestCase(unittest.TestCase):
    """Construcción de URLs — puramente funcional, sin red."""

    def test_url_xml_tuple(self):
        self.assertEqual(
            bormeparserv2.get_url_xml(DATE, secure=True), SUMARIO_URL_HTTPS
        )

    def test_url_xml_datetime(self):
        date = datetime.date(*DATE)
        self.assertEqual(
            bormeparserv2.get_url_xml(date, secure=True), SUMARIO_URL_HTTPS
        )

    def test_url_xml_insecure(self):
        self.assertEqual(
            bormeparserv2.get_url_xml(DATE, secure=False), SUMARIO_URL_HTTP
        )


class BormeparserInvalidDateTestCase(unittest.TestCase):
    """Fechas inválidas — falla en la construcción, sin red."""

    bad_date = (2015, 6, 31)

    def test_url_xml_raises(self):
        self.assertRaises(ValueError, bormeparserv2.get_url_xml, self.bad_date)

    def test_url_pdf_raises(self):
        self.assertRaises(
            ValueError,
            bormeparserv2.get_url_pdf,
            self.bad_date,
            bormeparserv2.SECCION.A,
            bormeparserv2.PROVINCIA.MALAGA,
        )

    def test_url_pdfs_raises(self):
        self.assertRaises(
            ValueError,
            bormeparserv2.get_url_pdfs,
            self.bad_date,
            bormeparserv2.SECCION.A,
        )


@require_live
class BormeparserLivePdfUrlsTestCase(unittest.TestCase):
    """Construcción de URLs de PDF que consulta el sumario remoto."""

    def test_url_pdf_malaga(self):
        url = bormeparserv2.get_url_pdf(
            DATE, bormeparserv2.SECCION.A, bormeparserv2.PROVINCIA.MALAGA
        )
        self.assertEqual(url, MALAGA_PDF_URL)

    def test_url_pdfs_seccion_contains_all_provinces(self):
        urls = bormeparserv2.get_url_pdfs(DATE, seccion=bormeparserv2.SECCION.A)
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
            bormeparserv2.get_url_pdf,
            self.weekend_date,
            bormeparserv2.SECCION.A,
            bormeparserv2.PROVINCIA.MALAGA,
        )

    def test_url_pdfs_raises(self):
        self.assertRaises(
            BormeDoesntExistException,
            bormeparserv2.get_url_pdfs,
            self.weekend_date,
            bormeparserv2.SECCION.A,
        )


@require_live
class BormeparserLiveDownloadTestCase(unittest.TestCase):
    def test_download_xml(self):
        path = os.path.join(tempfile.gettempdir(), "20150602.xml")
        try:
            downloaded = bormeparserv2.download_xml(DATE, path)
            self.assertTrue(downloaded)
            self.assertGreater(os.path.getsize(path), 1000)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_download_pdf(self):
        path = os.path.join(tempfile.gettempdir(), "BORME-A-2015-102-29.pdf")
        try:
            downloaded = bormeparserv2.download_pdf(
                DATE,
                path,
                bormeparserv2.SECCION.A,
                bormeparserv2.PROVINCIA.MALAGA,
            )
            self.assertTrue(downloaded)
            self.assertGreater(os.path.getsize(path), 10000)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_download_and_parse_pdf(self):
        path = os.path.join(tempfile.gettempdir(), "BORME-A-2015-102-29.pdf")
        try:
            borme = bormeparserv2.download_pdf(
                DATE,
                path,
                bormeparserv2.SECCION.A,
                bormeparserv2.PROVINCIA.MALAGA,
                parse=True,
            )
            self.assertIsInstance(borme, Borme)
        finally:
            if os.path.exists(path):
                os.unlink(path)


class ConfigTestCase(unittest.TestCase):
    """Regresión: get_config debe tolerar ficheros sin sección
    ``[general]`` y mezclar siempre los valores por defecto."""

    def setUp(self):
        # Mantenemos el cache aislado entre tests.
        from bormeparserv2 import config

        self._previous_cache = config._cached_config
        config._cached_config = None
        self._previous_path = config.CONFIG_FILE

    def tearDown(self):
        from bormeparserv2 import config

        config._cached_config = self._previous_cache
        config.CONFIG_FILE = self._previous_path

    def test_no_file_uses_defaults(self):
        from bormeparserv2 import config

        config.CONFIG_FILE = "/does/not/exist/.bormecfg"
        cfg = config.get_config()
        self.assertIn("borme_root", cfg)

    def test_missing_general_section_falls_back(self):
        from bormeparserv2 import config

        with tempfile.NamedTemporaryFile(
            "w", suffix=".cfg", delete=False, encoding="utf-8"
        ) as fp:
            fp.write("[otro]\nkey=value\n")
            path = fp.name
        try:
            config.CONFIG_FILE = path
            cfg = config.get_config()
            self.assertIn("borme_root", cfg)
        finally:
            os.unlink(path)

    def test_partial_general_merges_defaults(self):
        from bormeparserv2 import config

        with tempfile.NamedTemporaryFile(
            "w", suffix=".cfg", delete=False, encoding="utf-8"
        ) as fp:
            fp.write("[general]\notra_clave=valor\n")
            path = fp.name
        try:
            config.CONFIG_FILE = path
            cfg = config.get_config()
            # La clave del fichero está…
            self.assertEqual(cfg["otra_clave"], "valor")
            # …y borme_root sigue ahí porque viene de DEFAULTS.
            self.assertIn("borme_root", cfg)
        finally:
            os.unlink(path)

    def test_malformed_file_falls_back_to_defaults(self):
        """Regresión: un ``~/.bormecfg`` sin cabecera ``[general]``
        reventaba ``import bormeparserv2`` con ``MissingSectionHeaderError``.
        Ahora se loguea un warning y se usan los defaults."""
        from bormeparserv2 import config

        with tempfile.NamedTemporaryFile(
            "w", suffix=".cfg", delete=False, encoding="utf-8"
        ) as fp:
            fp.write("this is not ini at all\n!!!\n")
            path = fp.name
        try:
            config.CONFIG_FILE = path
            with self.assertLogs("bormeparserv2.config", level="WARNING") as captured:
                cfg = config.get_config()
            self.assertIn("borme_root", cfg)
            self.assertEqual(cfg["borme_root"], config.DEFAULTS["borme_root"])
            self.assertTrue(
                any("malformed" in m for m in captured.output),
                msg=f"captured={captured.output!r}",
            )
        finally:
            os.unlink(path)

    def test_borme_root_override_from_general_section(self):
        """Una entrada ``borme_root`` en ``[general]`` sustituye al default."""
        from bormeparserv2 import config

        with tempfile.NamedTemporaryFile(
            "w", suffix=".cfg", delete=False, encoding="utf-8"
        ) as fp:
            fp.write("[general]\nborme_root=/srv/bormes\n")
            path = fp.name
        try:
            config.CONFIG_FILE = path
            cfg = config.get_config()
            self.assertEqual(cfg["borme_root"], "/srv/bormes")
        finally:
            os.unlink(path)

    def test_config_file_pointing_to_directory_falls_back(self):
        """``isfile`` excluye directorios: ``borme_root`` viene de defaults."""
        from bormeparserv2 import config

        with tempfile.TemporaryDirectory() as tmpdir:
            config.CONFIG_FILE = tmpdir
            cfg = config.get_config()
            self.assertEqual(cfg["borme_root"], config.DEFAULTS["borme_root"])

    def test_empty_file_falls_back(self):
        """Un fichero vacío no rompe ConfigParser, pero tampoco aporta nada."""
        from bormeparserv2 import config

        with tempfile.NamedTemporaryFile(
            "w", suffix=".cfg", delete=False, encoding="utf-8"
        ) as fp:
            path = fp.name
        try:
            config.CONFIG_FILE = path
            cfg = config.get_config()
            self.assertEqual(cfg, config.DEFAULTS)
        finally:
            os.unlink(path)


class ActoIdsUniqueTestCase(unittest.TestCase):
    """Regresión: ``REACTIVACION_DE_LA_SOCIEDAD`` y
    ``CIERRE_PROVISIONAL_REVOCACION_NIF`` apuntaban ambos a 32; las
    búsquedas por id devolvían el primero indistintamente."""

    def test_acto_ids_unique(self):
        from bormeparserv2.acto import ACTO

        # Recogemos los enteros declarados como atributos de la clase.
        ids = [
            getattr(ACTO, attr)
            for attr in vars(ACTO)
            if not attr.startswith("_") and isinstance(getattr(ACTO, attr), int)
        ]
        self.assertEqual(len(ids), len(set(ids)), "Hay IDs de acto duplicados")
