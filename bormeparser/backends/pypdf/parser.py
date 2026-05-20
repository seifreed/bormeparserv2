# bormeparser.backends.pypdf.parser
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Parseo de los PDF de la sección A del BORME usando ``pypdf``.

El PDF llega como un stream de líneas con marcadores que delimitan
metadatos del boletín (``/Fecha``, ``/Numero_BORME``, …) y los actos
mercantiles (``/Cabecera_acto``, ``/Texto_acto``). El parser es un
state-machine que recorre esas líneas una a una; el estado mutable vive
en :class:`_ParseState` y cada tipo de línea tiene su propio handler.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator

from pypdf import PdfReader

from bormeparser.backends.base import BormeAParserBackend
from bormeparser.regex import (
    REGEX_ARGCOLON,
    REGEX_BORME_CVE,
    REGEX_BORME_NUM,
    REGEX_NOARG,
    REGEX_PDF_TEXT,
    is_acto_bold,
    is_acto_bold_mix,
    is_acto_cargo,
    regex_argcolon,
    regex_bold_acto,
    regex_cargos,
    regex_empresa,
    regex_noarg,
)

logger = logging.getLogger(__name__)


@dataclass
class _ParseState:
    """Estado mutable del bucle de :meth:`PyPDFParser._parse`.

    La lista de actos no vive aquí: cuelga de :attr:`PyPDFParser.actos`
    porque los helpers ``_parse_acto*`` la mutan directamente.
    """

    cabecera: bool = False
    texto: bool = False
    changing_page: bool = False
    last_font: int = 0
    nombreacto: str | None = None
    data: str = ""
    # Metadato del boletín que se está capturando actualmente
    # (``"fecha"``, ``"num"``, …) o ``None`` si no hay captura activa.
    capture: str | None = None
    # Cabecera procesada más reciente: se rellena en cuanto se cierra el
    # primer ``/Cabecera_acto`` y se reutiliza al finalizar cada anuncio.
    anuncio_id: int | None = None
    empresa: str | None = None
    extra: dict | None = None


class PyPDFParser(BormeAParserBackend):
    """Parse BORME-A PDFs using the pypdf library.

    Args:
        filename: Path to the BORME-A PDF.
        sanitize: When True, normalises company names (drops trailing
            type acronyms like S.L., S.A.) before storing them.
        log_level: Logging level for the parser (default WARN).
    """

    # Marker → (capture mode, DATA key it fills). Listed in the same
    # order BORME PDFs emit them.
    _METADATA_MARKERS = (
        ("/Fecha", "fecha", "borme_fecha"),
        ("/Numero_BORME", "num", "borme_num"),
        ("/Seccion", "seccion", "borme_seccion"),
        ("/Subseccion", "subseccion", "borme_subseccion"),
        ("/Provincia", "provincia", "borme_provincia"),
        ("/Codigo_verificacion", "cve", "borme_cve"),
    )

    _DATA_TEMPLATE = {
        "borme_fecha": None,
        "borme_num": None,
        "borme_seccion": None,
        "borme_subseccion": None,
        "borme_provincia": None,
        "borme_cve": None,
    }

    def __init__(self, filename, *, sanitize=False, log_level=logging.WARN):
        super().__init__(filename)
        logger.setLevel(log_level)
        self.actos: list = []
        self.sanitize = sanitize

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _parse(self) -> dict:
        data_out: dict = dict(self._DATA_TEMPLATE)
        state = _ParseState()
        self.actos = []

        for content in self._iter_page_contents():
            logger.debug("---- BEGIN OF PAGE ----")
            for line in content.split("\n"):
                self._handle_line(line, state, data_out)
            logger.debug("---- END OF PAGE ----")
            state.changing_page = True

        if state.nombreacto:
            self._parse_acto(state.nombreacto, state.data, prefix="END")
            self._commit_anuncio(state, data_out)

        return data_out

    def _iter_page_contents(self) -> Iterator[str]:
        """Lee el PDF y produce el contenido decodificado de cada página."""
        with open(self.filename, "rb") as fp:
            reader = PdfReader(fp)
            pages: list[str] = []
            for page in reader.pages:
                contents = page.get_contents()
                if contents is None:
                    continue
                # Content streams del PDF son bytes con literales latin-1;
                # los escapes propios del PDF (\(, \), \\) los deshace
                # _clean_data más abajo.
                pages.append(contents.get_data().decode("latin-1"))
        yield from pages

    def _handle_line(self, line: str, state: _ParseState, data_out: dict) -> None:
        """Despacha una línea del content stream al handler apropiado."""
        logger.debug("### LINE: %s", line)

        if line.startswith("/Cabecera_acto"):
            self._open_cabecera(state, data_out)
            return

        if line.startswith("/Texto_acto"):
            state.texto = True
            return

        if self._open_metadata_marker(line, state, data_out):
            return

        if line == "BT":
            return

        if line == "ET":
            self._close_text_block(state)
            return

        if not (state.texto or state.cabecera or state.capture):
            return

        if line == "/F1 8 Tf":
            self._handle_font_bold(state)
            return

        if line == "/F2 8 Tf":
            self._handle_font_normal(state)
            return

        match = REGEX_PDF_TEXT.match(line)
        if match:
            self._handle_text_chunk(match.group(1), state, data_out)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _open_cabecera(self, state: _ParseState, data_out: dict) -> None:
        """Procesa el marcador ``/Cabecera_acto``: cierra el anuncio en curso
        (si lo hay) y abre uno nuevo."""
        state.cabecera = True
        if state.changing_page:
            state.changing_page = False

        if state.nombreacto:
            self._parse_acto(state.nombreacto, state.data, prefix="BT")
            state.nombreacto = None
            self._commit_anuncio(state, data_out)

        state.data = ""
        self.actos = []

    def _open_metadata_marker(
        self, line: str, state: _ParseState, data_out: dict
    ) -> bool:
        """Si ``line`` es uno de los marcadores de metadato del boletín,
        activa la captura y devuelve True. En otro caso devuelve False."""
        for marker, mode, key in self._METADATA_MARKERS:
            if line.startswith(marker):
                if not data_out[key]:
                    logger.debug("START: %s", mode)
                    state.capture = mode
                return True
        return False

    def _close_text_block(self, state: _ParseState) -> None:
        """Procesa el marcador ``ET`` cerrando la cabecera o el bloque de texto."""
        if state.cabecera:
            state.cabecera = False
            cabecera_text = self._clean_data(state.data)
            state.anuncio_id, state.empresa, state.extra = regex_empresa(
                cabecera_text, sanitize=self.sanitize
            )
            logger.debug("anuncio_id=%s empresa=%s", state.anuncio_id, state.empresa)
            state.data = ""
        if state.texto:
            state.texto = False

    def _handle_font_bold(self, state: _ParseState) -> None:
        """Procesa el cambio a fuente F1 (bold): cierra el acto en curso si
        veníamos de F2 (o si no hay cambio de página)."""
        logger.debug(
            "START: font bold. changing_page=%s last_font=%s",
            state.changing_page,
            state.last_font,
        )
        if state.nombreacto is not None and (
            not state.changing_page or state.last_font == 2
        ):
            self._parse_acto(state.nombreacto, state.data, prefix="F1")
            state.nombreacto = None
            state.data = ""
        # changing_page se consume al primer cambio de fuente posterior.
        state.changing_page = False
        state.last_font = 1

    def _handle_font_normal(self, state: _ParseState) -> None:
        """Procesa el cambio a fuente F2 (normal): extrae los actos en bold
        acumulados y prepara ``data`` para el cuerpo del acto."""
        logger.debug(
            "START: font normal. changing_page=%s last_font=%s",
            state.changing_page,
            state.last_font,
        )

        if state.changing_page:
            state.changing_page = False
            if not state.nombreacto:
                state.nombreacto = self._clean_data(state.data)[:-1]
            if state.last_font != 1:
                state.last_font = 2
                return

        state.nombreacto = self._clean_data(state.data)[:-1]
        while True:
            end, state.nombreacto = self._parse_acto_bold(state.nombreacto, state.data)
            if end:
                break

        if is_acto_bold_mix(state.nombreacto):
            state.nombreacto = "Escisión total"
            state.data = "Sociedades beneficiarias de la escisión:"
        else:
            state.data = ""
        state.last_font = 2

    def _handle_text_chunk(self, text: str, state: _ParseState, data_out: dict) -> None:
        """Procesa un fragmento de texto extraído del PDF: lo asigna al
        metadato en captura (si lo hay) y lo acumula en ``state.data``."""
        if state.capture == "fecha":
            data_out["borme_fecha"] = text
            logger.debug("fecha: %s", text)
        elif state.capture == "num":
            match_num = REGEX_BORME_NUM.match(text)
            if match_num is None:
                raise ValueError(f"No se pudo parsear borme_num desde el PDF: {text!r}")
            data_out["borme_num"] = int(match_num.group(1))
            logger.debug("num: %d", data_out["borme_num"])
        elif state.capture == "seccion":
            data_out["borme_seccion"] = text
            logger.debug("seccion: %s", text)
        elif state.capture == "subseccion":
            data_out["borme_subseccion"] = text
            logger.debug("subseccion: %s", text)
        elif state.capture == "provincia":
            data_out["borme_provincia"] = text
            logger.debug("provincia: %s", text)
        elif state.capture == "cve":
            match_cve = REGEX_BORME_CVE.match(text)
            if match_cve is None:
                raise ValueError(f"No se pudo parsear borme_cve desde el PDF: {text!r}")
            data_out["borme_cve"] = match_cve.group(1)
            logger.debug("cve: %s", data_out["borme_cve"])
        state.capture = None
        state.data += " " + text
        logger.debug("TOTAL DATA: %s", state.data)

    def _commit_anuncio(self, state: _ParseState, data_out: dict) -> None:
        """Persiste el anuncio actual en ``data_out`` si la cabecera ha sido
        procesada. No hace nada si todavía no ha aparecido un
        ``/Cabecera_acto`` (PDF anómalo)."""
        if state.anuncio_id is None:
            return
        data_out[state.anuncio_id] = {
            "Empresa": state.empresa,
            "Extra": state.extra,
            "Actos": list(self.actos),
        }

    # ------------------------------------------------------------------
    # Helpers reutilizados por los handlers
    # ------------------------------------------------------------------

    def _clean_data(self, data: str) -> str:
        """Deshace los escapes \\( \\) del PDF y colapsa dobles espacios."""
        return data.replace(r"\(", "(").replace(r"\)", ")").replace("  ", " ").strip()

    def _parse_acto(self, nombreacto: str, data: str, prefix: str = "") -> None:
        data = self._clean_data(data)
        if is_acto_cargo(nombreacto):
            cargos = regex_cargos(data, sanitize=self.sanitize)
            if not cargos:
                logger.warning("No se encontraron cargos en la cadena: %s", data)
            data = cargos

        logger.debug("%s nombreacto=%s data=%s", prefix, nombreacto, data)
        self.actos.append({nombreacto: data})

    def _parse_acto_bold(self, nombreacto, data):
        """Extrae un acto bold/colon/noarg del bloque que sigue al cambio de
        fuente. Devuelve ``(end, nombreacto_restante)``: cuando ``end`` es
        True, el llamador debe parar de iterar."""
        if is_acto_bold_mix(nombreacto):
            return True, nombreacto

        if is_acto_bold(nombreacto):
            acto_colon, arg_colon, nombreacto = regex_bold_acto(nombreacto)
            self.actos.append({acto_colon: arg_colon})
            logger.debug("F2 bold: %s -- %s", acto_colon, arg_colon)
            return False, nombreacto

        if REGEX_ARGCOLON.match(nombreacto):
            acto_colon, arg_colon, nombreacto = regex_argcolon(nombreacto)
            self.actos.append({acto_colon: arg_colon})
            logger.debug("F2 colon: %s -- %s", acto_colon, arg_colon)
            return False, nombreacto

        if REGEX_NOARG.match(nombreacto):
            acto_noarg, nombreacto = regex_noarg(nombreacto)
            self.actos.append({acto_noarg: None})
            logger.debug("F2 noarg: %s", acto_noarg)
            return False, nombreacto

        return True, nombreacto
