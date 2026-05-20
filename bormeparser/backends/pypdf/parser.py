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

import logging

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


class PyPDFParser(BormeAParserBackend):
    """Parse BORME-A PDFs using the pypdf library.

    Args:
        filename: Path to the BORME-A PDF.
        sanitize: When True, normalises company names (drops trailing
            type acronyms like S.L., S.A.) before storing them.
        log_level: Logging level for the parser (default WARN).
    """

    def __init__(self, filename, *, sanitize=False, log_level=logging.WARN):
        super().__init__(filename)
        logger.setLevel(log_level)
        self.actos = []
        self.sanitize = sanitize

    # Mapping marker → (capture mode, DATA key it fills).
    # Listed in the same order the markers appear in BORME PDFs.
    _METADATA_MARKERS = (
        ('/Fecha', 'fecha', 'borme_fecha'),
        ('/Numero_BORME', 'num', 'borme_num'),
        ('/Seccion', 'seccion', 'borme_seccion'),
        ('/Subseccion', 'subseccion', 'borme_subseccion'),
        ('/Provincia', 'provincia', 'borme_provincia'),
        ('/Codigo_verificacion', 'cve', 'borme_cve'),
    )

    def _parse(self):
        cabecera = False
        changing_page = False
        data = ""
        last_font = 0
        nombreacto = None
        texto = False

        # Qué metadato del boletín se está capturando ahora mismo (None si
        # no estamos dentro de un bloque /Fecha, /Numero_BORME, etc.).
        capture = None

        # Inicialización defensiva: si el PDF no llega a un /Cabecera_acto
        # antes del primer ET / fin de fichero, no queremos un NameError.
        anuncio_id = None
        empresa = None
        extra = None

        DATA = {
            'borme_fecha': None,
            'borme_num': None,
            'borme_seccion': None,
            'borme_subseccion': None,
            'borme_provincia': None,
            'borme_cve': None
        }
        self.actos = []

        with open(self.filename, 'rb') as fp:
            reader = PdfReader(fp)
            page_contents = []
            for page in reader.pages:
                contents = page.get_contents()
                if contents is None:
                    continue
                raw = contents.get_data()
                if isinstance(raw, bytes):
                    # PDF content streams son bytes con literales latin-1;
                    # los escapes propios del PDF (\(, \), \\) los deshace
                    # _clean_data más abajo.
                    raw = raw.decode('latin-1')
                page_contents.append(raw)

        for content in page_contents:
            logger.debug('---- BEGIN OF PAGE ----')

            for line in content.split('\n'):
                logger.debug('### LINE: %s' % line)
                if line.startswith('/Cabecera_acto'):
                    logger.debug('START: cabecera')
                    cabecera = True

                    if changing_page:
                        changing_page = False

                    logger.debug('  BT nombreacto: %s' % nombreacto)
                    logger.debug('  BT data: %s' % data)

                    if nombreacto:
                        self._parse_acto(nombreacto, data, prefix='BT')
                        nombreacto = None
                        if anuncio_id is not None:
                            DATA[anuncio_id] = {
                                'Empresa': empresa,
                                'Extra': extra,
                                'Actos': self.actos
                            }

                    data = ""
                    self.actos = []
                    continue

                if line.startswith('/Texto_acto'):
                    logger.debug('START: texto')
                    logger.debug('  nombreacto: %s' % nombreacto)
                    logger.debug('  data: %s' % data)
                    texto = True
                    continue

                matched_marker = False
                for marker, mode, key in self._METADATA_MARKERS:
                    if line.startswith(marker):
                        if not DATA[key]:
                            logger.debug('START: %s', mode)
                            capture = mode
                        matched_marker = True
                        break
                if matched_marker:
                    continue

                if line == 'BT':
                    # Begin text object
                    continue

                if line == 'ET':
                    # End text object
                    if cabecera:
                        logger.debug('END: cabecera')
                        cabecera = False
                        data = self._clean_data(data)
                        anuncio_id, empresa, extra = regex_empresa(data, sanitize=self.sanitize)
                        logger.debug('  anuncio_id: %s' % anuncio_id)
                        logger.debug('  empresa: %s' % empresa)
                        logger.debug('  extra: {}'.format(extra))
                        data = ""
                    if texto:
                        logger.debug('END: texto')
                        texto = False
                        logger.debug('  nombreacto: %s' % nombreacto)
                        logger.debug('  data: %s' % data)
                    continue

                if not (texto or cabecera or capture):
                    continue

                if line == '/F1 8 Tf':
                    # Font 1: bold
                    logger.debug('START: font bold. %s %s' % (changing_page, last_font))
                    if changing_page:
                        # FIXME: Estoy suponiendo que una cabecera no se queda partida entre dos paginas
                        if nombreacto and last_font == 2:
                            self._parse_acto(nombreacto, data, prefix='F1')
                            nombreacto = None
                            data = ""
                        changing_page = False
                    else:
                        if nombreacto:
                            self._parse_acto(nombreacto, data, prefix='F1')
                            nombreacto = None
                            data = ""

                    logger.debug('  nombreacto: %s' % nombreacto)
                    logger.debug('  data: %s' % data)
                    last_font = 1
                    continue

                if line == '/F2 8 Tf':
                    # Font 2: normal
                    logger.debug('START: font normal. %s %s' % (changing_page, last_font))
                    logger.debug('  nombreacto2: %s' % nombreacto)
                    logger.debug('  data: %s' % data)

                    if changing_page:
                        changing_page = False
                        if not nombreacto:
                            nombreacto = self._clean_data(data)[:-1]
                        if last_font != 1:
                            last_font = 2
                            continue
                    nombreacto = self._clean_data(data)[:-1]

                    while True:
                        end, nombreacto = self._parse_acto_bold(nombreacto, data)
                        if end:
                            break

                    if is_acto_bold_mix(nombreacto):
                        nombreacto = "Escisión total"
                        data = "Sociedades beneficiarias de la escisión:"
                    else:
                        data = ""
                    logger.debug('  data_1: %s' % data)
                    last_font = 2
                    continue

                m = REGEX_PDF_TEXT.match(line)
                if m:
                    text = m.group(1)
                    if capture == 'fecha':
                        DATA['borme_fecha'] = text
                        logger.debug('fecha: %s', text)
                    elif capture == 'num':
                        DATA['borme_num'] = int(REGEX_BORME_NUM.match(text).group(1))
                        logger.debug('num: %d', DATA['borme_num'])
                    elif capture == 'seccion':
                        DATA['borme_seccion'] = text
                        logger.debug('seccion: %s', text)
                    elif capture == 'subseccion':
                        DATA['borme_subseccion'] = text
                        logger.debug('subseccion: %s', text)
                    elif capture == 'provincia':
                        DATA['borme_provincia'] = text
                        logger.debug('provincia: %s', text)
                    elif capture == 'cve':
                        DATA['borme_cve'] = REGEX_BORME_CVE.match(text).group(1)
                        logger.debug('cve: %s', DATA['borme_cve'])
                    capture = None
                    data += ' ' + text
                    logger.debug('TOTAL DATA: %s', data)

            logger.debug('---- END OF PAGE ----')
            changing_page = True

        if nombreacto:
            self._parse_acto(nombreacto, data, prefix='END')
            if anuncio_id is not None:
                DATA[anuncio_id] = {
                    'Empresa': empresa,
                    'Extra': extra,
                    'Actos': self.actos
                }

        return DATA

    def _clean_data(self, data):
        """ Unscape parenthesis and removes double spaces """
        return data.replace(r'\(', '(').replace(r'\)', ')').replace('  ', ' ').strip()

    def _parse_acto(self, nombreacto, data, prefix=''):
        data = self._clean_data(data)
        if is_acto_cargo(nombreacto):
            cargos = regex_cargos(data, sanitize=self.sanitize)
            if not cargos:
                logger.warning('No se encontraron cargos en la cadena: %s' % data)
            data = cargos

        logger.debug('  %s nombreactoW: %s' % (prefix, nombreacto))
        logger.debug('  %s dataW: %s' % (prefix, data))
        self.actos.append({nombreacto: data})

    def _parse_acto_bold(self, nombreacto, data):
        end = False

        if is_acto_bold_mix(nombreacto):
            end = True
        elif is_acto_bold(nombreacto):
            acto_colon, arg_colon, nombreacto = regex_bold_acto(nombreacto)
            self.actos.append({acto_colon: arg_colon})

            logger.debug('  F2 nombreactoW: %s -- %s' % (acto_colon, arg_colon))
            logger.debug('  nombreacto: %s' % nombreacto)
            logger.debug('  data: %s' % data)
        elif REGEX_ARGCOLON.match(nombreacto):
            acto_colon, arg_colon, nombreacto = regex_argcolon(nombreacto)
            # FIXME: check
            self.actos.append({acto_colon: arg_colon})

            logger.debug('  F2 nombreactoW: %s -- %s' % (acto_colon, arg_colon))
            logger.debug('  nombreacto: %s' % nombreacto)
            logger.debug('  data: %s' % data)
        elif REGEX_NOARG.match(nombreacto):
            acto_noarg, nombreacto = regex_noarg(nombreacto)
            self.actos.append({acto_noarg: None})
            logger.debug('  F2 acto_noargW: %s -- True' % acto_noarg)
            logger.debug('  nombreacto: %s' % nombreacto)
            logger.debug('  data: %s' % data)
        else:
            end = True
        return end, nombreacto
