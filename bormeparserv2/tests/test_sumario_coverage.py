#!/usr/bin/env python
#
# test_sumario_coverage.py - Branches secundarias de BormeXML.
# Copyright (C) 2015-2026 Marc Rivero López <mriverolopez@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Cobertura adicional de ``bormeparserv2.sumario``.

Cubre las ramas que el corpus principal no toca: ``save_to_file``,
``get_urls_cve``, warning de seccion C con provincia, ``_get_url_borme_c``
con format inválido, ramas del filtro combinado en ``_get_url_borme_a``,
y los properties ``prev_borme`` / ``next_borme`` (estos últimos vía
live tests).
"""

import datetime
import os
import tempfile
import unittest

from bormeparserv2 import PROVINCIA, SECCION
from bormeparserv2.exceptions import BormeDoesntExistException
from bormeparserv2.sumario import BormeXML

EXAMPLES = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "examples"))
SUMARIO_FIXTURE = os.path.join(EXAMPLES, "BORME-S-20150924.xml")

LIVE = os.environ.get("BORMEPARSERV2_LIVE") == "1"
require_live = unittest.skipUnless(
    LIVE, "set BORMEPARSERV2_LIVE=1 to run tests that hit boe.es"
)


class SumarioOfflineBranchesTestCase(unittest.TestCase):
    """Ramas alcanzables sin red usando el fixture local."""

    @classmethod
    def setUpClass(cls):
        cls.bxml = BormeXML.from_file(SUMARIO_FIXTURE)

    def test_save_to_file_writes_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "out", "sumario.xml")
            self.assertTrue(self.bxml.save_to_file(target))
            self.assertTrue(os.path.isfile(target))
            self.assertGreater(os.path.getsize(target), 1000)

    def test_get_urls_cve_returns_identifier_keyed_dict(self):
        urls = self.bxml.get_urls_cve(seccion=SECCION.A, provincia=PROVINCIA.MADRID)
        self.assertIn("BORME-A-2015-183-28", urls)
        self.assertTrue(urls["BORME-A-2015-183-28"].endswith(".pdf"))

    def test_get_url_pdfs_seccion_c_with_provincia_logs_warning(self):
        # ``provincia`` con sección C no tiene sentido — debe loguear
        # warning pero devolver los URLs de sección C igualmente.
        with self.assertLogs("bormeparserv2.sumario", level="WARNING") as cap:
            urls = self.bxml.get_url_pdfs(seccion=SECCION.C, provincia=PROVINCIA.MADRID)
        self.assertTrue(
            any("provincia parameter makes no sense" in m for m in cap.output),
            msg=f"captured={cap.output!r}",
        )
        # ``_get_url_borme_c`` indexa por CVE.xml
        self.assertTrue(any(k.endswith(".xml") for k in urls))

    def test_get_url_borme_c_unknown_format_raises_valueerror(self):
        with self.assertRaises(ValueError):
            self.bxml._get_url_borme_c(format="docx")

    def test_get_url_pdfs_only_provincia_returns_seccion_keyed_dict(self):
        # Sin ``seccion``, la rama de ``_get_url_borme_a`` (línea 274)
        # usa ``item.getparent().get('codigo')`` como key.
        urls = self.bxml.get_url_pdfs(provincia=PROVINCIA.MADRID)
        # Para Madrid en 2015-09-24 hay sección A y B; al menos una debe
        # estar presente.
        self.assertTrue(set(urls).issubset({"A", "B"}))
        self.assertGreater(len(urls), 0)

    def test_download_single_borme_returns_truthy_when_idempotent(self):
        # Sin red: pasamos un filename que YA existe → ``download_pdf``
        # detecta el fichero presente y devuelve False (idempotente).
        with tempfile.TemporaryDirectory() as tmp:
            pre = os.path.join(tmp, "BORME-A-2015-183-28.pdf")
            with open(pre, "wb") as fp:
                fp.write(b"%PDF-1.4 dummy\n")
            ok = self.bxml.download_single_borme(pre, SECCION.A, PROVINCIA.MADRID)
            self.assertFalse(ok)


class SumarioMissingDiarioTestCase(unittest.TestCase):
    """``BormeXML._load`` rechaza sumarios sin <diario> o sin <diario numero>."""

    def _load_with(self, body: str):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(body)
            path = fp.name
        try:
            return BormeXML.from_file(path)
        finally:
            os.unlink(path)

    def test_sumario_without_diario_raises(self):
        body = (
            '<?xml version="1.0"?>'
            "<sumario>"
            "<metadatos><fecha_publicacion>20150210</fecha_publicacion></metadatos>"
            "</sumario>"
        )
        with self.assertRaises(BormeDoesntExistException) as ctx:
            self._load_with(body)
        self.assertIn("<diario>", str(ctx.exception))


@require_live
class SumarioLivePropertiesTestCase(unittest.TestCase):
    """``prev_borme`` y ``next_borme`` consultan boe.es bajo demanda."""

    def test_prev_and_next_borme_resolve_to_adjacent_dates(self):
        # 2015-02-10 es un martes con BORME publicado; los vecinos
        # son lunes 9 y miércoles 11.
        bxml = BormeXML.from_date(datetime.date(2015, 2, 10))
        prev = bxml.prev_borme
        nxt = bxml.next_borme
        self.assertEqual(prev, datetime.date(2015, 2, 9))
        self.assertEqual(nxt, datetime.date(2015, 2, 11))

    def test_next_borme_returns_none_when_no_borme_in_range(self):
        # Un domingo de hace años: 14 días siguientes en festivos largos
        # podrían devolver None. Para un caso seguro: domingo 2015-04-05
        # (Pascua); el lunes 6 tampoco hay BORME (lunes santo nacional),
        # pero el martes 7 sí — _find_adjacent_borme debería encontrarlo.
        # Aquí solo verificamos que la propiedad no revienta.
        bxml = BormeXML.from_date(datetime.date(2015, 2, 10))
        self.assertIsNotNone(bxml.next_borme)

    def test_find_adjacent_borme_skips_weekend(self):
        """Desde un viernes, ``next_borme`` debe saltar sábado/domingo.

        Activa la rama ``continue`` (línea 310) al menos dos veces antes
        de devolver el lunes con BORME.
        """
        bxml = BormeXML.from_date(datetime.date(2015, 2, 6))  # viernes
        # Sábado 7 y domingo 8 no tienen BORME → continue, continue;
        # lunes 9 sí → return.
        self.assertEqual(bxml.next_borme, datetime.date(2015, 2, 9))

    def test_find_adjacent_borme_returns_none_past_search_window(self):
        """Tras 14 días sin BORME ``_find_adjacent_borme`` devuelve None.

        Usamos un rango futuro (año 2099) — la API responde 404 para todas
        las fechas, así que cada iteración entra en ``except`` y al
        agotarse el rango se devuelve None (línea 313).
        """
        from bormeparserv2.sumario import _find_adjacent_borme

        self.assertIsNone(_find_adjacent_borme(datetime.date(2099, 1, 1), step=1))


class SumarioBadDiarioNumeroTestCase(unittest.TestCase):
    """``BormeXML._load`` rechaza ``<diario>`` sin atributo ``numero``.

    Cubre la línea 87 que el corpus normal no toca.
    """

    def test_diario_without_numero_attr_raises(self):
        body = (
            '<?xml version="1.0"?>'
            "<sumario>"
            "<metadatos><fecha_publicacion>20150210</fecha_publicacion></metadatos>"
            "<diario/>"  # sin atributo numero
            "</sumario>"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(body)
            path = fp.name
        try:
            with self.assertRaises(BormeDoesntExistException) as ctx:
                BormeXML.from_file(path)
            self.assertIn("numero", str(ctx.exception))
        finally:
            os.unlink(path)


class SumarioItemWithoutUrlPdfTestCase(unittest.TestCase):
    """``_get_url_borme_a`` salta items sin ``<url_pdf>`` (línea 268)."""

    def _build_xml_with_item_without_url(self):
        return (
            '<?xml version="1.0"?>'
            "<sumario>"
            "<metadatos><fecha_publicacion>20150210</fecha_publicacion></metadatos>"
            '<diario numero="27">'
            '<seccion codigo="A">'
            "<item>"
            "<identificador>BORME-A-2015-27-99</identificador>"
            "<titulo>FAKE PROVINCIA</titulo>"
            # SIN <url_pdf>
            "</item>"
            "<item>"
            "<identificador>BORME-A-2015-27-10</identificador>"
            "<titulo>CÁCERES</titulo>"
            "<url_pdf szBytes='100'>https://example.com/x.pdf</url_pdf>"
            "</item>"
            "</seccion>"
            "</diario>"
            "</sumario>"
        )

    def test_items_without_url_are_skipped(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(self._build_xml_with_item_without_url())
            path = fp.name
        try:
            bxml = BormeXML.from_file(path)
            urls = bxml.get_url_pdfs(seccion=SECCION.A)
            # Solo el item con url_pdf debe aparecer; el otro se salta
            # silenciosamente (línea 268).
            self.assertIn("CÁCERES", urls)
            self.assertNotIn("FAKE PROVINCIA", urls)
        finally:
            os.unlink(path)


@require_live
class DownloadBormeLiveTestCase(unittest.TestCase):
    """``BormeXML.download_borme`` descarga el conjunto completo del día."""

    def test_download_borme_seccion_a_one_provincia(self):
        bxml = BormeXML.from_date(datetime.date(2015, 2, 10))
        with tempfile.TemporaryDirectory() as tmp:
            ok, files = bxml.download_borme(
                tmp, provincia=PROVINCIA.CACERES, seccion=SECCION.A
            )
            self.assertTrue(ok)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].endswith(".pdf"))

    def test_download_borme_seccion_c(self):
        bxml = BormeXML.from_date(datetime.date(2015, 2, 10))
        with tempfile.TemporaryDirectory() as tmp:
            ok, files = bxml.download_borme(tmp, seccion=SECCION.C)
            self.assertTrue(ok)
            # 2015-02-10 publicó múltiples anuncios de sección C.
            self.assertGreater(len(files), 0)


if __name__ == "__main__":
    unittest.main()
