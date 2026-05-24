#!/usr/bin/env python
#
# test_pypdf_handlers.py - Tests unitarios de los handlers del parser pypdf.
# Copyright (C) 2015-2026 Marc Rivero López <mriverolopez@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Cubre las ramas internas de :class:`PyPDFParser` que el flujo end-to-end
contra el BORME real no toca: cabeceras malformadas, capturas de
``borme_num``/``borme_cve`` con texto inválido, ``_commit_anuncio`` sin
anuncio previo, transiciones de fuente al cambiar de página, escisión
total como acto y la rama ``COLON_KEYWORDS`` dentro de ``_parse_acto_bold``.

No es mocking: instanciamos un :class:`_ParseState` real, llamamos a los
métodos del parser real con argumentos reales y verificamos sus
efectos. El PDF físico (fixture de Cáceres) sirve solo para satisfacer
la validación ``isfile`` del constructor.
"""

import logging
import os
import unittest

from bormeparserv2.backends.pypdf.parser import PyPDFParser, _ParseState

EXAMPLES = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "examples"))
PDF_FIXTURE = os.path.join(EXAMPLES, "BORME-A-2015-27-10.pdf")


def _make_parser() -> PyPDFParser:
    """Devuelve un parser inicializado contra el fixture real de Cáceres."""
    return PyPDFParser(PDF_FIXTURE, sanitize=True, log_level=logging.WARN)


class HandleTextChunkValidationTestCase(unittest.TestCase):
    """``_handle_text_chunk`` rechaza ``borme_num`` y ``borme_cve``
    inválidos con ``ValueError`` (líneas 291, 306)."""

    def test_invalid_borme_num_raises_valueerror(self):
        parser = _make_parser()
        state = _ParseState()
        state.capture = "num"
        data_out: dict = {}
        with self.assertRaises(ValueError) as ctx:
            parser._handle_text_chunk("texto sin numero", state, data_out)
        self.assertIn("borme_num", str(ctx.exception))

    def test_invalid_borme_cve_raises_valueerror(self):
        parser = _make_parser()
        state = _ParseState()
        state.capture = "cve"
        data_out: dict = {}
        with self.assertRaises(ValueError) as ctx:
            parser._handle_text_chunk("texto sin CVE BORME", state, data_out)
        self.assertIn("borme_cve", str(ctx.exception))

    def test_valid_borme_num_persisted_as_int(self):
        # Sanity check del happy path para asegurar que el regex existe y
        # las dos ramas de igual prioridad están cubiertas (línea 292).
        parser = _make_parser()
        state = _ParseState()
        state.capture = "num"
        data_out: dict = {}
        parser._handle_text_chunk("Núm. 27", state, data_out)
        self.assertEqual(data_out["borme_num"], 27)
        self.assertIsNone(state.capture)

    def test_valid_borme_cve_persisted(self):
        parser = _make_parser()
        state = _ParseState()
        state.capture = "cve"
        data_out: dict = {}
        # ``REGEX_BORME_CVE`` espera ``cve: <id>``.
        parser._handle_text_chunk("cve: BORME-A-2015-27-10", state, data_out)
        self.assertEqual(data_out["borme_cve"], "BORME-A-2015-27-10")


class CommitAnuncioEarlyReturnTestCase(unittest.TestCase):
    """``_commit_anuncio`` no escribe nada si no se ha visto cabecera (línea 318)."""

    def test_commits_nothing_when_anuncio_id_is_none(self):
        parser = _make_parser()
        state = _ParseState()
        # state.anuncio_id sigue siendo None (default)
        data_out: dict = {}
        parser._commit_anuncio(state, data_out)
        self.assertEqual(data_out, {})

    def test_commits_anuncio_when_id_present(self):
        parser = _make_parser()
        state = _ParseState()
        state.anuncio_id = 99999
        state.empresa = "TEST SL"
        state.extra = {"registro": "", "sucursal": False, "liquidacion": False}
        parser.actos = [{"Nombramientos": {"Adm. Unico": {"PEPE"}}}]
        data_out: dict = {}
        parser._commit_anuncio(state, data_out)
        self.assertIn(99999, data_out)
        self.assertEqual(data_out[99999]["Empresa"], "TEST SL")

    def test_commits_correction_header_without_id_from_text_act_number(self):
        parser = _make_parser()
        state = _ParseState()
        state.cabecera = True
        state.data = " - SOCIEDAD ESTATAL LOTERIAS Y APUESTAS DEL ESTADO SA."
        parser._close_text_block(state)

        self.assertIsNone(state.anuncio_id)
        self.assertEqual(
            state.empresa, "SOCIEDAD ESTATAL LOTERIAS Y APUESTAS DEL ESTADO SA"
        )

        state.data = (
            "Advertido error en la publicación del acto número 138.028 de fecha "
            "28 de marzo de 2011."
        )
        parser.actos = [{"Corrección de errores": state.data}]
        data_out: dict = {}
        parser._commit_anuncio(state, data_out)

        self.assertIn(138028, data_out)
        self.assertEqual(
            data_out[138028]["Empresa"],
            "SOCIEDAD ESTATAL LOTERIAS Y APUESTAS DEL ESTADO SA",
        )


class HandleFontNormalChangingPageTestCase(unittest.TestCase):
    """``_handle_font_normal`` durante cambio de página (líneas 264-267)."""

    def test_changing_page_without_nombreacto_extracts_from_data(self):
        """Cuando ``changing_page`` está activo y ``nombreacto`` es None,
        el handler reconstruye ``nombreacto`` a partir de ``state.data``
        (línea 264). Si ``last_font != 1`` el handler vuelve sin parsear
        el bloque (líneas 265-267)."""
        parser = _make_parser()
        state = _ParseState()
        state.changing_page = True
        state.nombreacto = None
        state.last_font = 2  # cualquier valor distinto de 1
        state.data = "Modificaciones estatutarias."
        parser._handle_font_normal(state)
        # _clean_data(...)[:-1] elimina el último carácter.
        self.assertEqual(state.nombreacto, "Modificaciones estatutarias")
        # last_font se mantiene en 2 y la función retorna pronto.
        self.assertEqual(state.last_font, 2)


class HandleFontNormalEscisionTotalTestCase(unittest.TestCase):
    """``is_acto_bold_mix(nombreacto)`` ⇒ se reescribe a "Escisión total"
    (líneas 275-277)."""

    def test_escision_total_rewrites_nombreacto_and_data(self):
        parser = _make_parser()
        state = _ParseState()
        # changing_page=False fuerza el flujo "normal" hasta el if final.
        state.changing_page = False
        state.last_font = 0
        # El acto bold acumulado contiene "Escisión total" exactamente —
        # is_acto_bold_mix devolverá True tras consumir el bloque, así que
        # las líneas 275-277 se ejecutan.
        state.data = "Escisión total."
        parser._handle_font_normal(state)
        self.assertEqual(state.nombreacto, "Escisión total")
        self.assertEqual(state.data, "Sociedades beneficiarias de la escisión:")
        self.assertEqual(state.last_font, 2)


class ParseActoEmptyCargosWarningTestCase(unittest.TestCase):
    """``_parse_acto`` loguea warning si ``regex_cargos`` devuelve dict vacío
    para un acto de cargo (línea 343)."""

    def test_empty_cargos_logs_warning(self):
        parser = _make_parser()
        with self.assertLogs(
            "bormeparserv2.backends.pypdf.parser", level="WARNING"
        ) as cap:
            # ``regex_cargos("")`` devuelve {} → no encuentra cargos.
            parser._parse_acto("Nombramientos", "", prefix="UT")
        self.assertTrue(
            any("No se encontraron cargos" in m for m in cap.output),
            msg=f"captured={cap.output!r}",
        )


class PdfWithBlankPageTestCase(unittest.TestCase):
    """Una página con ``/Contents == None`` debe saltarse silenciosamente
    (línea 145). Construimos el PDF a partir del fixture real añadiendo
    una blank page al final con :class:`pypdf.PdfWriter`."""

    def test_blank_page_is_skipped_without_crash(self):
        import tempfile

        import bormeparserv2
        from pypdf import PdfReader, PdfWriter

        # Construye un PDF nuevo: páginas del fixture + 1 página blank.
        with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as fp:
            target = fp.name
        try:
            with open(PDF_FIXTURE, "rb") as src:
                reader = PdfReader(src)
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                writer.add_blank_page(width=595, height=842)
                with open(target, "wb") as out:
                    writer.write(out)

            # Sanity: la última página efectivamente tiene get_contents() == None.
            r = PdfReader(target)
            self.assertIsNone(r.pages[-1].get_contents())

            # El parser debe ignorar la blank page y producir los anuncios
            # normales del fixture original (Cáceres → 30 anuncios).
            borme = bormeparserv2.parse(target, bormeparserv2.SECCION.A, sanitize=True)
            self.assertEqual(borme.cve, "BORME-A-2015-27-10")
            self.assertEqual(len(borme.anuncios), 30)
        finally:
            os.unlink(target)


class ParseActoBoldVariantsTestCase(unittest.TestCase):
    """``_parse_acto_bold`` distintos casos de retorno."""

    def test_acto_bold_mix_returns_early(self):
        """Si el ``nombreacto`` empieza por "Escisión total" se devuelve
        (end=True, nombreacto) sin tocar self.actos (línea 354)."""
        parser = _make_parser()
        parser.actos = []
        end, remaining = parser._parse_acto_bold(
            "Escisión total. seguido de mas texto", "ignore"
        )
        self.assertTrue(end)
        self.assertEqual(remaining, "Escisión total. seguido de mas texto")
        self.assertEqual(parser.actos, [])

    def test_acto_bold_colon_branch(self):
        """Cuando el ``nombreacto`` no es bold ni mix pero sí encaja con
        REGEX_ARGCOLON, el handler guarda el par acto/argumento y devuelve
        (end=False, nombreacto restante) — líneas 363-366."""
        parser = _make_parser()
        parser.actos = []
        # ``Modificación de duración`` es uno de los COLON_KEYWORDS.
        end, remaining = parser._parse_acto_bold(
            "Modificación de duración: 99 años. Nombramientos", "ignore"
        )
        self.assertFalse(end)
        # Se añadió la entrada acto:arg.
        self.assertEqual(len(parser.actos), 1)
        acto_dict = parser.actos[0]
        self.assertIn("Modificación de duración", acto_dict)

    def test_exact_bold_keyword_returns_as_act_header(self):
        """Un BOLD_KEYWORD exacto puede ser la cabecera completa del acto.

        Regresión real: BORME-A-2024-132-28 contiene
        ``Acuerdo de ampliación de capital social sin ejecutar. Importe del acuerdo``
        como cabecera exacta; no debe pasar por ``regex_bold_acto()``, que
        solo parsea los bold con argumento y siguiente acto en la misma cadena.
        """
        parser = _make_parser()
        parser.actos = []
        acto = (
            "Acuerdo de ampliación de capital social sin ejecutar. Importe del acuerdo"
        )
        end, remaining = parser._parse_acto_bold(acto, "ignore")
        self.assertTrue(end)
        self.assertEqual(remaining, acto)
        self.assertEqual(parser.actos, [])


class ExtractedTextLayoutTestCase(unittest.TestCase):
    """Fallback para PDFs BOE nuevos que usan ``Identity-H``/``ToUnicode``.

    Regresión real: desde BORME-A-2025-39-02 el content stream ya no
    contiene ``(texto)Tj`` bajo marcadores ``/Fecha``; ``pypdf.extract_text``
    sí devuelve el texto visible y los metadatos vienen en ``/Keywords``.
    """

    def test_parses_numbered_announcements_from_extracted_text(self):
        parser = _make_parser()
        text = """SECCIÓN PRIMERA
Empresarios
Actos inscritos
ALBACETE
93634 - PRIUS SAM SOCIEDAD LIMITADA.
Ceses/Dimisiones. Adm. Solid.: SANCHEZ MULITERNO GARCIA ALONSO;SANCHEZ-MULITERNO GARCIA JOSE CARLOS.
Fusión por absorción. Sociedades absorbidas: PRIUS ENERGY SOCIEDAD LIMITADA. Disolución. Fusion. Extinción. Datos registrales. S 8 , H AB 14638, I/A 8 (18.02.25).
BOLETÍN OFICIAL DEL REGISTRO MERCANTIL
Núm. 39 Miércoles 26 de febrero de 2025 Pág. 9616
cve: BORME-A-2025-39-02
Verificable en https://www.boe.es
93635 - PRIUS ENERGY SOCIEDAD LIMITADA.
Revocaciones. Apoderado: ALGARRA INIESTA OSCAR. Datos registrales. S 8 , H AB 16329, I/A 12 (18.02.25).
"""
        raw = parser._parse_extracted_text_document(
            text,
            {
                "/Keywords": (
                    "BORME-A-2025-39-02;BORME 39 de 2025;" "ALBACETE;26/02/2025"
                )
            },
        )

        self.assertEqual(raw["borme_fecha"], "Miércoles 26 de febrero de 2025")
        self.assertEqual(raw["borme_num"], 39)
        self.assertEqual(raw["borme_cve"], "BORME-A-2025-39-02")
        self.assertEqual(raw["borme_seccion"], "SECCIÓN PRIMERA")
        self.assertEqual(raw["borme_subseccion"], "Actos inscritos")
        self.assertEqual(raw["borme_provincia"], "ALBACETE")
        self.assertEqual(raw[93634]["Empresa"], "PRIUS SAM SL")
        self.assertIn(
            {
                "Ceses/Dimisiones": {
                    "Adm. Solid.": {
                        "SANCHEZ MULITERNO GARCIA ALONSO",
                        "SANCHEZ-MULITERNO GARCIA JOSE CARLOS",
                    }
                }
            },
            raw[93634]["Actos"],
        )
        self.assertIn(
            {"Datos registrales": "S 8 , H AB 14638, I/A 8 (18.02.25)"},
            raw[93634]["Actos"],
        )
        self.assertEqual(raw[93635]["Empresa"], "PRIUS ENERGY SL")

    def test_prefers_visible_province_over_lossy_keywords(self):
        parser = _make_parser()
        text = """SECCIÓN PRIMERA
Empresarios
Actos inscritos
ALMERÍA
208574 - GRUPO AGF FASHION SL.
Nombramientos. Auditor: BNFIX AMB AUDITORES SLP. Datos registrales. S 8 , H AL 39803, I/A 30 (23.04.26).
"""
        raw = parser._parse_extracted_text_document(
            text,
            {"/Keywords": ("BORME-A-2026-82-04;BORME 82 de 2026;" "ALMERA;30/04/2026")},
        )

        self.assertEqual(raw["borme_subseccion"], "Actos inscritos")
        self.assertEqual(raw["borme_provincia"], "ALMERÍA")
        self.assertEqual(raw[208574]["Empresa"], "GRUPO AGF FASHION SL")

    def test_parses_correction_without_numbered_header(self):
        parser = _make_parser()
        text = """BOLETÍN OFICIAL DEL REGISTRO MERCANTIL
Núm. 39 Miércoles 26 de febrero de 2025 Pág. 9873
cve: BORME-B-2025-39-31
Verificable en https://www.boe.es
SECCIÓN PRIMERA
Empresarios
Otros actos publicados en el Registro Mercantil
NAVARRA
Corrección de errores
La sociedad HERMANOS PERNAUT SL estaba inscrita en la hoja 6960.
"""
        raw = parser._parse_extracted_text_document(
            text,
            {
                "/Keywords": (
                    "BORME-B-2025-39-31;BORME 39 de 2025;" "NAVARRA;26/02/2025"
                )
            },
        )

        self.assertEqual(
            raw["borme_subseccion"], "Otros actos publicados en el Registro Mercantil"
        )
        self.assertEqual(raw[31]["Empresa"], "Corrección de errores")
        self.assertEqual(
            raw[31]["Actos"],
            [
                {
                    "Otros conceptos": (
                        "Corrección de errores La sociedad HERMANOS PERNAUT SL "
                        "estaba inscrita en la hoja 6960."
                    )
                }
            ],
        )
