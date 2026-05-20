#!/usr/bin/env python
#
# download.py - Cliente HTTP y parsing del sumario BORME contra la API
# pública de datos abiertos del BOE (boe.es/datosabiertos/api/borme).
#
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import datetime
import logging
import os
import time
from queue import Queue
from threading import Thread

import requests
from lxml import etree

from .exceptions import BormeDoesntExistException, MissingFilterException
from .parser import parse as parse_borme
from .provincia import PROVINCIA
from .seccion import SECCION

requests.adapters.DEFAULT_RETRIES = 3

logger = logging.getLogger(__name__)

# Public API endpoint published by the BOE for the BORME diario sumario.
# Returns XML when called with Accept: application/xml.
BORME_SUMARIO_URL = (
    "{protocol}://www.boe.es/datosabiertos/api/borme/sumario/"
    "{year}{month:02d}{day:02d}"
)

USE_HTTPS = True
THREADS = 8
HTTP_TIMEOUT = 30
_API_HEADERS = {"Accept": "application/xml"}

# Kept for backwards compatibility — callers used to import it.
URL_BASE = "%s://www.boe.es"


def _coerce_date(date):
    if isinstance(date, tuple):
        return datetime.date(year=date[0], month=date[1], day=date[2])
    return date


def get_url_xml(date, secure=USE_HTTPS):
    """URL del sumario XML del día indicado."""
    date = _coerce_date(date)
    protocol = "https" if secure else "http"
    return BORME_SUMARIO_URL.format(
        protocol=protocol, year=date.year, month=date.month, day=date.day
    )


def _fetch_sumario_tree(source):
    """Carga el sumario desde una URL o ruta local y devuelve el elemento ``sumario``.

    Lanza ``BormeDoesntExistException`` si el día solicitado no tiene BORME
    publicado, o si la API devuelve un código de estado distinto de 200.
    """
    if isinstance(source, str) and source.startswith("http"):
        response = requests.get(source, headers=_API_HEADERS, timeout=HTTP_TIMEOUT)
        # La API responde con 404 cuando no hay BORME publicado en esa fecha
        # (festivos, domingos). Lo traducimos a una excepción de dominio.
        if response.status_code == 404:
            raise BormeDoesntExistException("BOE has no BORME for {}".format(source))
        response.raise_for_status()
        try:
            root = etree.fromstring(response.content)
        except etree.XMLSyntaxError as exc:
            raise BormeDoesntExistException(
                f"Malformed sumario XML from {source}: {exc}"
            ) from exc
    else:
        try:
            root = etree.parse(source).getroot()
        except etree.XMLSyntaxError as exc:
            raise BormeDoesntExistException(
                f"Malformed sumario XML at {source}: {exc}"
            ) from exc

    if root.tag == "sumario":
        # Local fixture stored directly as <sumario>... (no <response> wrapper).
        return root

    if root.tag != "response":
        raise BormeDoesntExistException(
            "Expected <response> or <sumario> root, got <{}>".format(root.tag)
        )

    code_elem = root.find("status/code")
    if code_elem is None or code_elem.text != "200":
        raise BormeDoesntExistException(
            "BOE API returned status {}".format(
                code_elem.text if code_elem is not None else "unknown"
            )
        )

    sumario = root.find("data/sumario")
    if sumario is None:
        raise BormeDoesntExistException("Response did not contain <data><sumario>")
    return sumario


def get_nbo_from_xml(source):
    """Número de Boletín Oficial (nbo) — atributo ``numero`` del ``<diario>``."""
    sumario = _fetch_sumario_tree(source)
    diario = sumario.find("diario")
    if diario is None:
        raise BormeDoesntExistException("Sumario has no <diario>")
    nbo = diario.attrib.get("numero")
    if nbo is None:
        raise BormeDoesntExistException("<diario> has no numero attribute")
    return nbo


def download_xml(date, filename, secure=USE_HTTPS):
    """Descarga el sumario XML del día indicado a ``filename``."""
    url = get_url_xml(date, secure=secure)
    if os.path.exists(filename):
        return False
    response = requests.get(url, headers=_API_HEADERS, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    with open(filename, "wb") as fp:
        fp.write(response.content)
    return True


def download_pdfs(date, path, provincia=None, seccion=None, secure=USE_HTTPS):
    """Descarga BORMEs PDF de la provincia/sección y la fecha indicadas."""
    if provincia is not None:
        provincia = PROVINCIA.coerce(provincia)
    urls = get_url_pdfs(date, provincia=provincia, seccion=seccion, secure=secure)
    files = download_urls(urls, path)
    return True, files


def download_pdf(date, filename, seccion, provincia, parse=False):
    """Descarga un único BORME-A/B PDF."""
    provincia = PROVINCIA.coerce(provincia)
    url = get_url_pdf(date, seccion, provincia)
    downloaded = download_url(url, filename)
    if downloaded:
        logger.debug("Downloaded: %s", filename)
    else:
        logger.debug("File already exists: %s", filename)
    if parse:
        return parse_borme(filename, seccion)
    return downloaded


def _find_pdf_entry_in_sumario(sumario, seccion, provincia_code):
    """Devuelve ``(identificador, url)`` del PDF correspondiente a una
    sección/provincia, o lanza ``BormeDoesntExistException`` si no aparece.

    Se busca por el sufijo ``-{nbo}-{provincia.code}`` del identificador
    BORME, que es estable y no depende del nombre (bilingüe) de la
    provincia. Es la única implementación de esta búsqueda: tanto
    :func:`_find_pdf_url_in_sumario` (que sólo necesita la URL) como el
    filtro combinado de :func:`get_url_pdfs` la reutilizan.
    """
    diario = sumario.find("diario")
    if diario is None:
        raise BormeDoesntExistException("Sumario has no <diario>")
    nbo = diario.attrib.get("numero")
    if nbo is None:
        raise BormeDoesntExistException("<diario> has no numero attribute")
    suffix = "-{}-{}".format(nbo, provincia_code)
    xpath = 'seccion[@codigo="{}"]/item'.format(seccion)
    for item in diario.iterfind(xpath):
        identificador = item.findtext("identificador") or ""
        if identificador.endswith(suffix):
            url = item.findtext("url_pdf")
            if url:
                return identificador, url
    raise BormeDoesntExistException(
        "No PDF for seccion={} provincia={} in this sumario".format(
            seccion, provincia_code
        )
    )


def _find_pdf_url_in_sumario(sumario, seccion, provincia_code):
    """Wrapper de compatibilidad: devuelve solo la URL del PDF.

    La validación real (``<diario>``, ``numero``, sufijo) vive en
    :func:`_find_pdf_entry_in_sumario`.
    """
    _, url = _find_pdf_entry_in_sumario(sumario, seccion, provincia_code)
    return url


def get_url_pdf(date, seccion, provincia, secure=USE_HTTPS):
    """URL absoluta del PDF BORME-A/B publicada en el sumario del día.

    La URL se lee directamente del sumario en lugar de reconstruirla, así
    seguimos funcionando si el BOE cambia el patrón de paths.
    """
    provincia = PROVINCIA.coerce(provincia)
    sumario = _fetch_sumario_tree(get_url_xml(date, secure=secure))
    return _find_pdf_url_in_sumario(sumario, seccion, provincia.code)


def get_url_pdf_from_xml(date, seccion, provincia, xml_path, secure=USE_HTTPS):
    """Variante de :func:`get_url_pdf` que toma el sumario de un fichero local."""
    provincia = PROVINCIA.coerce(provincia)
    sumario = _fetch_sumario_tree(xml_path)
    return _find_pdf_url_in_sumario(sumario, seccion, provincia.code)


def get_url_pdfs_provincia(date, provincia, secure=USE_HTTPS):
    """Diccionario ``{seccion: url_pdf}`` para una provincia y fecha."""
    provincia = PROVINCIA.coerce(provincia)
    sumario = _fetch_sumario_tree(get_url_xml(date, secure=secure))
    urls = {}
    for item in sumario.iterfind("diario/seccion/item"):
        titulo = item.findtext("titulo")
        if titulo != provincia:
            continue
        url = item.findtext("url_pdf")
        seccion = item.getparent().get("codigo")
        urls[seccion] = url
    return urls


def get_url_pdfs_seccion(date, seccion, secure=USE_HTTPS):
    """Diccionario ``{provincia: url_pdf}`` para una sección y fecha."""
    if seccion not in (SECCION.A, SECCION.B):
        raise ValueError("Section must be: A or B")

    sumario = _fetch_sumario_tree(get_url_xml(date, secure=secure))
    xpath = 'diario/seccion[@codigo="{}"]/item'.format(seccion)
    return {
        item.findtext("titulo"): item.findtext("url_pdf")
        for item in sumario.iterfind(xpath)
    }


_C_URL_TAGS = {
    "xml": "url_xml",
    "htm": "url_html",
    "html": "url_html",
    "pdf": "url_pdf",
}


def get_url_seccion_c(date, format="xml", secure=USE_HTTPS):
    """Devuelve ``{apartado: {titulo: url}}`` para los anuncios de la sección C."""
    try:
        tag = _C_URL_TAGS[format]
    except KeyError as exc:
        raise ValueError('format must be "xml", "htm" or "pdf"') from exc

    sumario = _fetch_sumario_tree(get_url_xml(date, secure=secure))
    urls = {}
    for apartado in sumario.iterfind('diario/seccion[@codigo="C"]/apartado'):
        nombre = apartado.get("nombre")
        urls[nombre] = {
            item.findtext("titulo"): item.findtext(tag)
            for item in apartado.iterfind("item")
        }
    return urls


def get_url_pdfs(date, seccion=None, provincia=None, secure=USE_HTTPS):
    if provincia is not None:
        provincia = PROVINCIA.coerce(provincia)
    if seccion and not provincia:
        return get_url_pdfs_seccion(date, seccion, secure=secure)
    if provincia and not seccion:
        return get_url_pdfs_provincia(date, provincia, secure=secure)
    if provincia and seccion:
        # Filtro combinado: ``_find_pdf_entry_in_sumario`` ya valida
        # ``<diario>`` y ``numero`` y devuelve ``(identificador, url)``;
        # lo reusamos para no duplicar la lógica defensiva.
        sumario = _fetch_sumario_tree(get_url_xml(date, secure=secure))
        identificador, url = _find_pdf_entry_in_sumario(
            sumario, seccion, provincia.code
        )
        return {identificador: url}
    raise MissingFilterException("You must specify either provincia or seccion or both")


def download_url(url, filename, try_again=0):
    """Descarga ``url`` y escribe el contenido en ``filename``. Si el fichero
    ya existe se considera idempotente y devuelve False sin volver a
    descargar. Reintenta hasta 3 veces ante errores transitorios."""
    logger.debug("Downloading URL: %s", url)
    if os.path.exists(filename):
        logger.debug("%s already exists!", os.path.basename(filename))
        return False
    try:
        response = requests.get(url, stream=True, timeout=HTTP_TIMEOUT)
    except requests.RequestException:
        if try_again < 3:
            return download_url(url, filename, try_again=try_again + 1)
        raise

    response.raise_for_status()
    with open(filename, "wb") as fp:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                fp.write(chunk)
    return True


def download_urls(urls, path):
    """Descarga las URLs a ``path``. Devuelve la lista de ficheros descargados."""
    files = []
    for url in urls.values():
        filename = url.split("/")[-1]
        full_path = os.path.join(path, filename)
        if download_url(url, full_path):
            files.append(full_path)
            logger.info("Downloaded %s", filename)
    return files


def _start_workers(queue, files, threads):
    workers = []
    for thread_id in range(threads):
        worker = _DownloadWorker(thread_id, queue, files)
        worker.daemon = True
        worker.start()
        workers.append(worker)
    return workers


def _stop_workers(queue, workers):
    """Envía un centinela a cada worker y espera a que terminen.

    Sin esto los hilos daemon quedarían bloqueados en ``queue.get()``
    para siempre; aunque el proceso los mata al salir, una llamada
    repetida acumularía hilos zombies en procesos largos."""
    for _ in workers:
        queue.put(None)
    for worker in workers:
        worker.join()


def download_urls_multi(urls, path, threads=THREADS):
    """Versión multihilo de :func:`download_urls`. ``urls`` es ``{_: url}``."""
    queue: Queue = Queue()
    files: list[str] = []
    workers = _start_workers(queue, files, threads)
    for url in urls.values():
        filename = url.split("/")[-1]
        queue.put((url, os.path.join(path, filename)))
    queue.join()
    _stop_workers(queue, workers)
    return files


def download_urls_multi_names(urls, path, threads=THREADS):
    """Variante con nombres explícitos: ``urls`` es ``{filename: url}``."""
    queue: Queue = Queue()
    files: list[str] = []
    workers = _start_workers(queue, files, threads)
    for filename, url in urls.items():
        queue.put((url, os.path.join(path, filename)))
    queue.join()
    _stop_workers(queue, workers)
    return files


class _DownloadWorker(Thread):
    """Worker thread que descarga URLs de una cola compartida hasta recibir
    el centinela ``None``."""

    def __init__(self, thread_id, queue, files):
        super().__init__()
        self.thread_id = thread_id
        self.queue = queue
        self.files = files

    def run(self):
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                return
            url, full_path = item
            time.sleep(0.6)
            try:
                if download_url(url, full_path):
                    self.files.append(full_path)
                    logger.info("Downloaded %s", os.path.basename(full_path))
            finally:
                self.queue.task_done()
