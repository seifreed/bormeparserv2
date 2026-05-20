#!/usr/bin/env python
#
# bormeparser.sumario - Parseo del sumario diario del BORME.
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Lectura y consulta del sumario XML que publica el BOE en su API de
datos abiertos (``boe.es/datosabiertos/api/borme/sumario``).

Esta capa es **infraestructura**: traduce el XML del BOE en estructuras
manejables (`BormeXML`) sin saber nada del modelo de dominio
(:class:`bormeparser.borme.Borme` y compañía).
"""

import datetime
import logging
import os

from lxml import etree

from .download import (
    USE_HTTPS,
    _fetch_sumario_tree,
    download_pdf,
    download_urls_multi,
    download_urls_multi_names,
    get_url_xml,
)
from .exceptions import (
    BormeDoesntExistException,
    CveNotFound,
    MissingFilterException,
)
from .seccion import SECCION

logger = logging.getLogger(__name__)

_PROVINCIA_INDEX_TITLE = "ÍNDICE ALFABÉTICO DE SOCIEDADES"
_C_URL_TAGS = {
    "xml": "url_xml",
    "htm": "url_html",
    "html": "url_html",
    "pdf": "url_pdf",
}


def _parse_yyyymmdd(text):
    return datetime.datetime.strptime(text, "%Y%m%d").date()


class BormeXML:
    """Sumario diario del BORME (XML).

    La instancia almacena el árbol XML y expone consultas declarativas
    contra él (`get_url_pdfs`, `get_cves`, `get_sizes`, …). Toda la I/O
    de descarga vive en :mod:`bormeparser.download`.
    """

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
        if date != bxml.date:
            raise BormeDoesntExistException(
                f"El sumario devuelto por el BOE corresponde a {bxml.date}, "
                f"se pidió {date}"
            )
        return bxml

    def get_urls_cve(self, seccion=None, provincia=None):
        return {
            item.findtext("identificador"): item.findtext("url_pdf")
            for item in self._iter_items(seccion=seccion, provincia=provincia)
        }

    def get_url_pdfs(self, seccion=None, provincia=None):
        """URLs para descargar PDFs.

        Debe especificarse ``seccion``, ``provincia`` o ambas. Para
        ``seccion == SECCION.C``, ``provincia`` se ignora.
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
        """URL de descarga del PDF identificado por ``cve``.

        Lanza :class:`CveNotFound` si el identificador no aparece en el sumario.
        """
        for item in self._all_items():
            if item.findtext("identificador") == cve:
                return item.findtext("url_pdf")
        raise CveNotFound(
            "CVE {!r} not found in BORME sumario {}".format(cve, self.date)
        )

    def get_provincias(self, seccion):
        provincias = [
            item.findtext("titulo") for item in self._iter_items(seccion=seccion)
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
        """URLs de la sección C en el formato indicado."""
        try:
            tag = _C_URL_TAGS[format]
        except KeyError as exc:
            raise ValueError('format must be "xml", "html" or "pdf"') from exc

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
            raise MissingFilterException(
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
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.xml.write(path, encoding="utf-8", pretty_print=True, xml_declaration=True)
        return True


def _find_adjacent_borme(date, step):
    """Fecha del BORME publicado más próximo a ``date`` (pasada o futura).

    Itera día a día hasta encontrar un sumario válido, con un tope de
    14 días para evitar bucles infinitos en festivos largos.
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
