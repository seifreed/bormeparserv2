#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# bormeparserv2._security - Helpers de hardening para parseo y filesystem.

import ntpath
import os
from urllib.parse import urlsplit

from lxml import etree

_BOE_HOSTS = frozenset({"boe.es", "www.boe.es"})
_BOE_PATH_PREFIXES = ("/borme/", "/diario_borme/")


def secure_xml_parser():
    """Parser XML defensivo para entradas BOE locales o remotas."""
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


def parse_xml_bytes(content):
    return etree.fromstring(content, parser=secure_xml_parser())


def parse_xml_file(path):
    return etree.parse(path, parser=secure_xml_parser())


def parse_html_text(content):
    parser = etree.HTMLParser(no_network=True)
    return etree.HTML(content, parser=parser)


def safe_filename(filename):
    """Devuelve ``filename`` si es un nombre plano, no una ruta."""
    if not isinstance(filename, str):
        raise TypeError(f"filename must be str, got {type(filename).__name__}")
    if not filename or filename in (".", "..") or "\x00" in filename:
        raise ValueError(f"Unsafe filename: {filename!r}")
    if (
        os.path.basename(filename) != filename
        or ntpath.basename(filename) != filename
        or os.path.isabs(filename)
        or ntpath.isabs(filename)
        or ntpath.splitdrive(filename)[0]
    ):
        raise ValueError(f"Unsafe filename: {filename!r}")
    return filename


def safe_join(base_path, filename):
    """Une ``base_path`` y un nombre plano sin permitir salir del directorio."""
    filename = safe_filename(filename)
    base_abs = os.path.abspath(base_path)
    target = os.path.abspath(os.path.join(base_abs, filename))
    if os.path.commonpath([base_abs, target]) != base_abs:
        raise ValueError(f"Unsafe filename: {filename!r}")
    return target


def filename_from_url(url):
    """Extrae el último segmento del path de una URL y lo valida."""
    filename = urlsplit(url).path.rsplit("/", 1)[-1]
    return safe_filename(filename)


def validate_boe_url(url):
    """Devuelve ``url`` si apunta a un recurso BORME publicado por el BOE."""
    if not isinstance(url, str):
        raise TypeError(f"url must be str, got {type(url).__name__}")
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or parts.hostname not in _BOE_HOSTS
        or not parts.path.startswith(_BOE_PATH_PREFIXES)
    ):
        raise ValueError(f"Unexpected BOE URL: {url!r}")
    return url
