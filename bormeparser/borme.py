#!/usr/bin/env python
#
# borme.py -
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


import datetime
import io
import json
import logging
import os
import os.path
import re

from lxml import etree

from .acto import ACTO
from .download import (
    _fetch_sumario_tree,
    USE_HTTPS,
    download_pdf,
    download_urls_multi,
    download_urls_multi_names,
    get_url_pdf,
    get_url_pdf_from_xml,
    get_url_xml,
)
from .exceptions import (
    BormeAlreadyDownloadedException,
    BormeAnuncioNotFound,
    BormeDoesntExistException,
)
from .provincia import PROVINCIA, Provincia
from .regex import is_acto_cargo
from .seccion import SECCION
from .utils import get_borme_xml_filepath

logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
logger.addHandler(ch)
logger.setLevel(logging.WARN)

# RAW_FILE_VERSION must be a positive integer string.
# Each new version adds 1 if the result file can change.
RAW_FILE_VERSION = "1"
# Thousands file version. It represents the file version part corresponding
# to this parser
TH_FILE_VERSION = "2"
# The file version depends on parser one and parser two. It is coded to avoid
# that the parser one changes and the parser two does not.
FILE_VERSION = "{}".format(int(RAW_FILE_VERSION) + 1000 * int(TH_FILE_VERSION))


class BormeActo:
    """Representa un Acto del Registro Mercantil. Instanciar BormeActoTexto
       o BormeActoCargo
    """
    def __init__(self, name, value):
        logger.debug("new %s(%s): %s", self.__class__.__name__, name, value)
        if name not in ACTO.ALL_KEYWORDS:
            logger.warning("Invalid acto found: %s", name)
        self._set_name(name)
        self._set_value(value)

    def _set_name(self, name):
        raise NotImplementedError

    def _set_value(self, value):
        raise NotImplementedError

    def __lt__(self, other):
        return self.name < other.name

    def __repr__(self):
        return "<{}({}): {}>".format(
            self.__class__.__name__, self.name, self.value
        )


class BormeActoTexto(BormeActo):
    """
    Representa un Acto del Registro Mercantil con atributo de cadena de texto.
    """

    def _set_name(self, name):
        if is_acto_cargo(name):
            raise ValueError(
                'No se puede BormeActoTexto con un acto de cargo: %s' % name)
        self.name = name

    def _set_value(self, value):
        if not (value is None or isinstance(value, str)):
            raise ValueError('value must be str or None: %s' % value)
        self.value = value


class BormeActoCargo(BormeActo):
    """Representa un Acto del Registro Mercantil con atributo de lista de
       cargos y nombres.
    """

    def _set_name(self, name):
        if not is_acto_cargo(name):
            raise ValueError(
                'No se puede BormeActoCargo sin un acto de cargo: %s' % name)
        self.name = name

    def _set_value(self, value):
        if not isinstance(value, dict):
            raise ValueError('value must be a dictionary: %s' % value)

        for k, v in value.items():
            if not isinstance(v, set):
                if isinstance(v, list):
                    value[k] = set(v)
                else:
                    raise ValueError('v must be a set: %s' % v)

        self.value = value

    @property
    def cargos(self):
        return self.value

    def get_nombres_cargos(self):
        return list(self.value.keys())


class BormeAnuncio:
    """Representa un anuncio con un conjunto de actos mercantiles
       (Constitucion, Nombramientos, ...)
    """

    def __init__(self, id, empresa, actos, extra, datos_registrales=None):
        logger.debug("new BormeAnuncio(%s) %s (%s)", id, empresa, extra)
        self.id = id
        self.empresa = empresa
        self.registro = extra["registro"]
        self.sucursal = extra["sucursal"]
        self.liquidacion = extra["liquidacion"]
        self.datos_registrales = datos_registrales or ""
        self._set_actos(actos)

    def _set_actos(self, actos):
        self.actos = []
        for acto in actos:
            for acto_nombre, valor in acto.items():
                if acto_nombre == 'Datos registrales':
                    self.datos_registrales = valor
                    continue

                if is_acto_cargo(acto_nombre):
                    a = BormeActoCargo(acto_nombre, valor)
                else:
                    a = BormeActoTexto(acto_nombre, valor)
                self.actos.append(a)

    def get_borme_actos(self):
        return self.actos

    def get_actos(self):
        for acto in self.actos:
            yield acto.name, acto.value

    def __repr__(self):
        return "<BormeAnuncio({}) {} (r:{}, s:{}, l:{}) ({})>".format(
                    self.id, self.empresa, self.registro, self.sucursal,
                    self.liquidacion, len(self.actos))


_PROVINCIA_INDEX_TITLE = "ÍNDICE ALFABÉTICO DE SOCIEDADES"


def _parse_yyyymmdd(text):
    return datetime.datetime.strptime(text, "%Y%m%d").date()


class BormeXML:
    """Sumario XML del BORME publicado por la API datosabiertos del BOE."""

    def __init__(self):
        self._url = None
        self.date = None
        self.filename = None
        self.use_https = USE_HTTPS

    def _load(self, source):
        sumario = _fetch_sumario_tree(source)
        # Re-root the tree at <sumario> so XPath queries stay short and
        # work uniformly whether the source was the API response or a
        # local fixture saved as a bare <sumario>.
        self.xml = etree.ElementTree(sumario)

        meta_date = sumario.findtext("metadatos/fecha_publicacion")
        if not meta_date:
            raise BormeDoesntExistException("Missing metadatos/fecha_publicacion")
        self.date = _parse_yyyymmdd(meta_date)

        diario = sumario.find("diario")
        if diario is None:
            raise BormeDoesntExistException("Missing <diario>")
        self.nbo = int(diario.attrib["numero"])

        # La API datosabiertos no expone fechaAnt/fechaSig; se calculan
        # bajo demanda con prev_borme / next_borme.
        self._prev_borme = None
        self._next_borme = None
        self.is_final = True

    @property
    def url(self):
        if not self._url:
            self._url = get_url_xml(self.date, secure=self.use_https)
        return self._url

    @property
    def prev_borme(self):
        if self._prev_borme is None:
            self._prev_borme = _find_adjacent_borme(self.date, step=-1)
        return self._prev_borme

    @property
    def next_borme(self):
        if self._next_borme is None:
            self._next_borme = _find_adjacent_borme(self.date, step=1)
        return self._next_borme

    @staticmethod
    def from_file(path, secure=USE_HTTPS):
        bxml = BormeXML()
        bxml.use_https = secure
        if not str(path).startswith("http"):
            if not os.path.exists(path):
                raise IOError(path)
            bxml.filename = path
        bxml._load(path)
        return bxml

    @staticmethod
    def from_date(date, secure=USE_HTTPS):
        if isinstance(date, tuple):
            date = datetime.date(year=date[0], month=date[1], day=date[2])
        bxml = BormeXML()
        bxml.use_https = secure
        bxml._url = get_url_xml(date, secure=secure)
        bxml._load(bxml._url)
        assert date == bxml.date
        return bxml

    def get_urls_cve(self, seccion=None, provincia=None):
        return {
            item.findtext("identificador"): item.findtext("url_pdf")
            for item in self._iter_items(seccion=seccion, provincia=provincia)
        }

    def get_url_pdfs(self, seccion=None, provincia=None):
        """URLs para descargar PDFs. Debe especificarse sección, provincia o ambas.

        Para ``seccion == SECCION.C``, ``provincia`` se ignora.
        """
        if seccion == SECCION.C:
            if provincia:
                logger.warning('provincia parameter makes no sense when seccion="C"')
            return self._get_url_borme_c(format="xml")
        return self._get_url_borme_a(seccion=seccion, provincia=provincia)

    def get_cves(self, seccion=None, provincia=None):
        """Devuelve los CVEs (identificadores BORME) de los anuncios."""
        cves = [
            cve
            for item in self._iter_items(seccion=seccion, provincia=provincia)
            for cve in [item.findtext("identificador")]
            if cve and not cve.endswith("-99")
        ]
        if len(cves) == 1:
            return cves[0]
        return cves

    def get_sizes(self, seccion=None, provincia=None):
        """Diccionario ``{cve: bytes}`` con el tamaño declarado de cada PDF."""
        sizes = {}
        for item in self._iter_items(seccion=seccion, provincia=provincia):
            cve = item.findtext("identificador")
            if cve is None or cve.endswith("-99"):
                continue
            url_pdf = item.find("url_pdf")
            if url_pdf is not None and "szBytes" in url_pdf.attrib:
                sizes[cve] = int(url_pdf.attrib["szBytes"])
        return sizes

    def get_url_cve(self, cve):
        """URL de descarga del PDF identificado por ``cve``."""
        for item in self._all_items():
            if item.findtext("identificador") == cve:
                return item.findtext("url_pdf")
        raise AttributeError("CVE not found in this BORME XML")

    def get_provincias(self, seccion):
        provincias = [
            item.findtext("titulo")
            for item in self._iter_items(seccion=seccion)
        ]
        return [p for p in provincias if p and p != _PROVINCIA_INDEX_TITLE]

    def _all_items(self):
        yield from self.xml.iterfind("diario/seccion/item")
        yield from self.xml.iterfind("diario/seccion/apartado/item")

    def _iter_items(self, seccion=None, provincia=None):
        """Itera los ``<item>`` del sumario filtrando por sección/provincia."""
        if seccion == SECCION.C:
            base = self.xml.iterfind('diario/seccion[@codigo="C"]/apartado/item')
        elif seccion:
            base = self.xml.iterfind(
                'diario/seccion[@codigo="{}"]/item'.format(seccion)
            )
        else:
            base = self._all_items()

        for item in base:
            if provincia and item.findtext("titulo") != provincia:
                continue
            yield item

    def _get_url_borme_c(self, format="xml"):
        """URLs de la sección C en el formato indicado (``xml``/``html``/``pdf``)."""
        if format == "xml":
            tag = "url_xml"
        elif format in ("htm", "html"):
            tag = "url_html"
        elif format == "pdf":
            tag = "url_pdf"
        else:
            raise ValueError('format must be "xml", "html" or "pdf"')

        urls = {}
        for item in self.xml.iterfind('diario/seccion[@codigo="C"]/apartado/item'):
            cve = item.findtext("identificador")
            url = item.findtext(tag)
            if cve and url:
                urls["{}.{}".format(cve, format)] = url
        return urls

    def _get_url_borme_a(self, seccion=None, provincia=None):
        """URLs de la sección A/B según el filtro indicado."""
        if not seccion and not provincia:
            raise AttributeError(
                "You must specify either provincia or seccion or both"
            )

        urls = {}
        for item in self._iter_items(seccion=seccion, provincia=provincia):
            url_pdf = item.findtext("url_pdf")
            if not url_pdf:
                continue
            if seccion and provincia:
                key = item.findtext("identificador")
            elif seccion:
                key = item.findtext("titulo")
            else:
                key = item.getparent().get("codigo")
            urls[key] = url_pdf
        return urls

    def download_borme(self, path, provincia=None, seccion=None):
        urls = self.get_url_pdfs(provincia=provincia, seccion=seccion)
        if seccion == SECCION.C:
            files = download_urls_multi_names(urls, path)
        else:
            files = download_urls_multi(urls, path)
        return True, files

    def download_single_borme(self, filename, seccion, provincia):
        return download_pdf(self.date, filename, seccion, provincia)

    def save_to_file(self, path):
        """Persiste el sumario XML en disco."""
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        self.xml.write(path, encoding="utf-8", pretty_print=True, xml_declaration=True)
        return True


def _find_adjacent_borme(date, step):
    """Encuentra la fecha del BORME publicado más próximo a ``date`` (pasada o futura).

    Itera día a día hasta encontrar un sumario válido (HTTP 200 ``<status>``),
    con un tope de 14 días para evitar bucles infinitos en festivos largos.
    """
    candidate = date
    for _ in range(14):
        candidate = candidate + datetime.timedelta(days=step)
        try:
            BormeXML.from_date(candidate)
        except BormeDoesntExistException:
            continue
        else:
            return candidate
    return None


class Borme:

    def __init__(self, date, seccion, provincia, num, cve, anuncios=None,
                 filename=None, lazy=True):
        if isinstance(date, tuple):
            date = datetime.date(year=date[0], month=date[1], day=date[2])
        self.date = date
        self.seccion = seccion
        self.provincia = provincia
        self.num = num
        self.cve = cve
        self.filename = filename
        self._set_anuncios(anuncios)
        self._url = None
        if not lazy:
            self._set_url()

    @classmethod
    def from_file(cls, filename):
        # TODO: Create instance directly from filename
        raise NotImplementedError

    def _set_anuncios(self, anuncios):
        """
            anuncios: [BormeAnuncio]
        """
        self.anuncios = {}
        for anuncio in anuncios:
            self.anuncios[anuncio.id] = anuncio
        self.anuncios_rango = (min(self.anuncios.keys()),
                               max(self.anuncios.keys()))

    def _set_url(self):
        xml_path = get_borme_xml_filepath(self.date)
        if os.path.isfile(xml_path):
            self._url = get_url_pdf_from_xml(self.date, self.seccion,
                                             self.provincia, xml_path)
        else:
            self._url = get_url_pdf(self.date, self.seccion, self.provincia)

    @property
    def url(self):
        if not self._url:
            self._set_url()
        return self._url

    def get_anuncio(self, anuncio_id):
        try:
            return self.anuncios[anuncio_id]
        except KeyError:
            raise BormeAnuncioNotFound(
                'Anuncio {} not found in BORME {}'.format(
                    anuncio_id, str(self)))

    def get_anuncios_ids(self):
        """
        [BormeAnuncio]
        """
        return sorted(self.anuncios.keys())

    def get_anuncios(self):
        """
        [BormeAnuncio]
        """
        return list(self.anuncios.values())

    def download(self, filename):
        if self.filename is not None:
            raise BormeAlreadyDownloadedException(filename)
        downloaded = download_pdf(self.date, filename, self.seccion,
                                  self.provincia)
        if downloaded:
            self.filename = filename
        return downloaded

    def _to_dict(self, set_url=True):
        doc = {
            'cve': self.cve,
            'date': self.date.isoformat(),
            'seccion': self.seccion,
            'provincia': self.provincia,
            'num': self.num,
            'from_anuncio': self.anuncios_rango[0],
            'to_anuncio': self.anuncios_rango[1],
            'anuncios': {}
        }

        num_anuncios = 0
        for id, anuncio in self.anuncios.items():
            doc['anuncios'][anuncio.id] = {
                'empresa': anuncio.empresa,
                'registro': anuncio.registro,
                'sucursal': anuncio.sucursal,
                'liquidacion': anuncio.liquidacion,
                'datos registrales': anuncio.datos_registrales,
                'actos': [],
                'num_actos': 0
            }
            for acto in anuncio.actos:
                acto_dict = {acto.name: acto.value}
                doc['anuncios'][anuncio.id]['num_actos'] += 1
                doc['anuncios'][anuncio.id]['actos'].append(acto_dict)
            num_anuncios += 1

        doc['num_anuncios'] = num_anuncios

        # For compatibility with other parsers
        doc['raw_version'] = RAW_FILE_VERSION
        doc['version'] = FILE_VERSION

        # Note that it requires Internet connection the first time
        if set_url:
            doc['url'] = self.url

        logger.debug(doc)
        return doc

    def to_json(self, path=None, overwrite=True, pretty=True,
                include_url=True):
        """Genera BORME-JSON a partir del archivo PDF

        Nota: Requiere conexión a Internet si include_url=True
        path: directorio o archivo
        overwrite: Sobreescribe el archivo si ya existe
        pretty: Genera el BORME-JSON con indentación para que sea más legible
        include_url: Incluir la URL para descargar el BORME de su fuente
                     oficial posteriormente.
        """
        def set_default(obj):
            """ serialize Python sets as lists
                http://stackoverflow.com/a/22281062
            """
            if isinstance(obj, set):
                return sorted(obj)
            elif isinstance(obj, Provincia):
                return str(obj)
            raise TypeError(type(obj))

        if path is None:
            path = re.sub(r'(\.pdf)$', '.json', os.path.basename(self.filename))
        if os.path.isfile(path) and not overwrite:
            return False
        if os.path.isdir(path):
            path = os.path.join(path, self.cve + '.json')

        doc = self._to_dict(include_url)
        indent = 2 if pretty else None
        with open(path, 'w') as fp:
            json.dump(doc, fp, default=set_default, indent=indent,
                      sort_keys=True)
        return path

    @classmethod
    def from_json(self, filename):
        """Crea una instancia Borme a partir de un BORME-JSON.

        El parámetro filename puede ser la ruta a un archivo o un objeto file
        de un fichero JSON ya abierto.
        """

        if isinstance(filename, io.IOBase):
            d = json.loads(filename.read())
            filename = filename.name
        else:
            with open(filename) as fp:
                d = json.load(fp)

        if d["version"] < FILE_VERSION:
            logger.warning(
                "This JSON was generated with an older version of bormeparser")
            logger.warning(
                "Current version is {0}, file version is {1}.".format(
                    FILE_VERSION, d["version"]))
        cve = d['cve']
        date = datetime.datetime.strptime(d['date'], '%Y-%m-%d').date()
        seccion = d['seccion']  # TODO: SECCION.from_borme()
        provincia = PROVINCIA.from_title(d['provincia'].upper())
        num = d['num']
        url = d.get('url')  # No obligatorio
        bormeanuncios = []
        anuncios = sorted(d['anuncios'].items(), key=lambda t: t[0])
        for id_anuncio, data in anuncios:
            extra = {
                "liquidacion": data["liquidacion"],
                "sucursal": data["sucursal"],
                "registro": data["registro"]
            }
            a = BormeAnuncio(int(id_anuncio), data['empresa'], data['actos'],
                             extra, data['datos registrales'])
            bormeanuncios.append(a)
        borme = Borme(date, seccion, provincia, num, cve, bormeanuncios,
                      filename)
        borme._url = url
        return borme

    def __lt__(self, other):
        return self.anuncios_rango[1] < other.anuncios_rango[0]

    def __repr__(self):
        return "<Borme({}) seccion:{} provincia:{}>".format(
                    self.date, self.seccion, self.provincia)
