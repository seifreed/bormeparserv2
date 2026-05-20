#!/usr/bin/env python
#
# test_fetch_sumario_http.py - Cubre ramas HTTP de _fetch_sumario_tree.
# Copyright (C) 2015-2026 Marc Rivero López <mriverolopez@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Ejercita ``_fetch_sumario_tree`` contra un servidor HTTP local real.

Las ramas defensivas de ``download._fetch_sumario_tree`` (líneas 78-79,
101, 109) solo se disparan cuando el endpoint responde con XML
malformado o con el wrapper ``<response>`` en estado no-200 o sin
``<data><sumario>``. La API real del BOE no produce esas respuestas
fácilmente, así que levantamos un mini-servidor con
``http.server.ThreadingHTTPServer`` (parte de stdlib) que devuelve
exactamente la respuesta que queremos.

NO es mocking: es código real (servidor real, requests real, parser real)
contra un endpoint local controlado por el test.
"""

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bormeparserv2.download import _fetch_sumario_tree
from bormeparserv2.exceptions import BormeDoesntExistException


class _CannedResponseHandler(BaseHTTPRequestHandler):
    """HTTP handler que devuelve la respuesta pre-cargada en ``self.server.canned``.

    Se monta una instancia distinta por cada test; el contenido y status
    code se inyectan a través del atributo ``canned`` del server.
    """

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        status, content_type, body = self.server.canned  # type: ignore[attr-defined]
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args, **_kwargs):  # noqa: N802
        # Silencia el logging por defecto que ensucia la salida de unittest.
        pass


def _serve(status: int, content_type: str, body: bytes):
    """Levanta un servidor HTTP local con una respuesta canned y devuelve
    ``(server, url)``. Llamar a ``server.shutdown()`` para detenerlo."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CannedResponseHandler)
    server.canned = (status, content_type, body)  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    return server, f"http://127.0.0.1:{port}/sumario"


class HttpFetchMalformedXmlTestCase(unittest.TestCase):
    """Respuesta 200 con XML malformado ⇒ ``BormeDoesntExistException``
    (líneas 78-79)."""

    def test_truncated_xml_raises_domain_error(self):
        server, url = _serve(
            200, "application/xml", b"<?xml version='1.0'?><not_closed"
        )
        try:
            with self.assertRaises(BormeDoesntExistException) as ctx:
                _fetch_sumario_tree(url)
            self.assertIn("Malformed sumario XML", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()


class HttpFetchResponseWithoutSumarioDataTestCase(unittest.TestCase):
    """Respuesta ``<response>`` con status code != 200 ⇒ BormeDoesntExist
    (línea 101)."""

    def test_response_with_500_status_raises(self):
        body = (
            b'<?xml version="1.0"?>'
            b"<response>"
            b"<status><code>500</code><text>Server Error</text></status>"
            b"</response>"
        )
        server, url = _serve(200, "application/xml", body)
        try:
            with self.assertRaises(BormeDoesntExistException) as ctx:
                _fetch_sumario_tree(url)
            self.assertIn("500", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()

    def test_response_with_missing_status_code_element_raises(self):
        # ``code_elem is None`` activa la rama "status unknown".
        body = (
            b'<?xml version="1.0"?>'
            b"<response><status><text>oops</text></status></response>"
        )
        server, url = _serve(200, "application/xml", body)
        try:
            with self.assertRaises(BormeDoesntExistException) as ctx:
                _fetch_sumario_tree(url)
            self.assertIn("unknown", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()

    def test_response_200_without_data_sumario_raises(self):
        """``<response><status><code>200</code></status></response>`` sin
        ``<data><sumario>`` ⇒ BormeDoesntExistException (línea 109)."""
        body = (
            b'<?xml version="1.0"?>'
            b"<response>"
            b"<status><code>200</code></status>"
            b"<data/>"
            b"</response>"
        )
        server, url = _serve(200, "application/xml", body)
        try:
            with self.assertRaises(BormeDoesntExistException) as ctx:
                _fetch_sumario_tree(url)
            self.assertIn("<data><sumario>", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()


class HttpFetch404RaisesTestCase(unittest.TestCase):
    """Respuesta 404 ⇒ "BOE has no BORME for ..." (línea 74).
    Esa rama ya está cubierta por los tests live; este test la repite
    contra el servidor local para hacerla determinista."""

    def test_404_raises_borme_doesnt_exist(self):
        server, url = _serve(404, "text/plain", b"not found")
        try:
            with self.assertRaises(BormeDoesntExistException) as ctx:
                _fetch_sumario_tree(url)
            self.assertIn("BOE has no BORME", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()
