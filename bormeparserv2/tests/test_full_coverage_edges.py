#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# test_full_coverage_edges.py - Offline edge coverage for production modules.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import datetime
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from bormeparserv2 import PROVINCIA, SECCION
from bormeparserv2.borme import Borme
from bormeparserv2.exceptions import BormeDoesntExistException

EXAMPLES = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "examples"))
PDF_FIXTURE = os.path.join(EXAMPLES, "BORME-A-2015-27-10.pdf")
SUMARIO_FIXTURE = os.path.join(EXAMPLES, "BORME-S-20150924.xml")


class _FakeResponse:
    def __init__(self, status_code=200, body=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size=8192):
        for index in range(0, len(self._body), chunk_size):
            yield self._body[index : index + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def close(self):
        self.closed = True


class SecurityEdgeTestCase(unittest.TestCase):
    def test_safe_filename_rejects_non_string(self):
        from bormeparserv2._security import safe_filename

        with self.assertRaises(TypeError):
            safe_filename(123)

    def test_safe_join_rechecks_common_path(self):
        from bormeparserv2._security import safe_join

        with tempfile.TemporaryDirectory() as tmp:
            with patch("bormeparserv2._security.os.path.commonpath", return_value="/x"):
                with self.assertRaises(ValueError):
                    safe_join(tmp, "file.pdf")

    def test_validate_boe_url_rejects_non_string(self):
        from bormeparserv2._security import validate_boe_url

        with self.assertRaises(TypeError):
            validate_boe_url(None)


class DownloadEdgeTestCase(unittest.TestCase):
    def test_get_with_retries_recovers_from_request_exception(self):
        from bormeparserv2.download import _get_with_retries

        attempts = [requests.Timeout("temporary"), _FakeResponse(200, b"ok")]

        def fake_get(*_args, **_kwargs):
            result = attempts.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with (
            patch("bormeparserv2.download.requests.get", side_effect=fake_get),
            patch("bormeparserv2.download._sleep_before_retry", return_value=None),
        ):
            response = _get_with_retries("https://www.boe.es/borme/test.xml")
        self.assertEqual(response.status_code, 200)

    def test_get_with_retries_reraises_final_request_exception(self):
        from bormeparserv2.download import _get_with_retries

        with (
            patch("bormeparserv2.download.HTTP_RETRIES", 0),
            patch(
                "bormeparserv2.download.requests.get",
                side_effect=requests.Timeout("final"),
            ),
        ):
            with self.assertRaises(requests.Timeout):
                _get_with_retries("https://www.boe.es/borme/test.xml")

    def test_download_xml_writes_new_file_and_closes_response(self):
        from bormeparserv2.download import download_xml

        body = (
            b'<?xml version="1.0"?>'
            b"<response><status><code>200</code></status>"
            b"<data><sumario><diario numero='1'/></sumario></data></response>"
        )
        response = _FakeResponse(200, body)
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "sumario.xml")
            with (
                patch("bormeparserv2.download.get_url_xml", return_value="http://x"),
                patch(
                    "bormeparserv2.download._get_with_retries", return_value=response
                ),
            ):
                self.assertTrue(download_xml(datetime.date(2024, 1, 2), target))
            self.assertTrue(os.path.exists(target))
            self.assertTrue(response.closed)

    def test_download_pdfs_delegates_to_url_listing_and_downloader(self):
        from bormeparserv2.download import download_pdfs

        with (
            patch(
                "bormeparserv2.download.get_url_pdfs",
                return_value={"doc": "https://www.boe.es/borme/doc.pdf"},
            ) as get_urls,
            patch("bormeparserv2.download.download_urls", return_value=["doc.pdf"]),
        ):
            ok, files = download_pdfs(
                datetime.date(2024, 1, 2), "/tmp", provincia="MADRID", seccion=SECCION.A
            )
        self.assertTrue(ok)
        self.assertEqual(files, ["doc.pdf"])
        self.assertEqual(get_urls.call_args.kwargs["provincia"], PROVINCIA.MADRID)

    def test_download_pdf_existing_file_can_parse(self):
        from bormeparserv2.download import download_pdf

        with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as fp:
            fp.write(b"%PDF-1.4")
            path = fp.name
        try:
            with patch("bormeparserv2.download.parse_borme", return_value="parsed"):
                self.assertEqual(
                    download_pdf(
                        datetime.date(2024, 1, 2),
                        path,
                        SECCION.A,
                        PROVINCIA.MADRID,
                        parse=True,
                    ),
                    "parsed",
                )
        finally:
            os.unlink(path)

    def test_download_pdf_new_file_downloads_and_parses(self):
        from bormeparserv2.download import download_pdf

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "new.pdf")
            with (
                patch("bormeparserv2.download.get_url_pdf", return_value="http://x"),
                patch("bormeparserv2.download.download_url", return_value=True),
                patch("bormeparserv2.download.parse_borme", return_value="parsed"),
            ):
                self.assertEqual(
                    download_pdf(
                        datetime.date(2024, 1, 2),
                        target,
                        SECCION.A,
                        PROVINCIA.MADRID,
                        parse=True,
                    ),
                    "parsed",
                )

    def test_download_pdf_new_file_reports_idempotent_downloader_result(self):
        from bormeparserv2.download import download_pdf

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "new.pdf")
            with (
                patch("bormeparserv2.download.get_url_pdf", return_value="http://x"),
                patch("bormeparserv2.download.download_url", return_value=False),
            ):
                self.assertFalse(
                    download_pdf(
                        datetime.date(2024, 1, 2),
                        target,
                        SECCION.A,
                        PROVINCIA.MADRID,
                    )
                )

    def test_url_helpers_read_local_sumario_when_url_xml_is_patched(self):
        from bormeparserv2.download import (
            get_url_pdf,
            get_url_pdfs,
            get_url_pdfs_provincia,
            get_url_pdfs_seccion,
            get_url_seccion_c,
        )

        with patch("bormeparserv2.download.get_url_xml", return_value=SUMARIO_FIXTURE):
            one_url = get_url_pdf(
                datetime.date(2015, 9, 24), SECCION.A, PROVINCIA.CACERES
            )
            by_provincia = get_url_pdfs_provincia(
                datetime.date(2015, 9, 24), PROVINCIA.MADRID
            )
            by_seccion = get_url_pdfs_seccion(datetime.date(2015, 9, 24), SECCION.A)
            c_urls = get_url_seccion_c(datetime.date(2015, 9, 24), format="html")
            only_section = get_url_pdfs(datetime.date(2015, 9, 24), seccion=SECCION.A)
            only_province = get_url_pdfs(
                datetime.date(2015, 9, 24), provincia=PROVINCIA.MADRID
            )
            combined = get_url_pdfs(
                datetime.date(2015, 9, 24),
                seccion=SECCION.A,
                provincia=PROVINCIA.CACERES,
            )

        self.assertTrue(one_url.endswith("BORME-A-2015-183-10.pdf"))
        self.assertIn(SECCION.A, by_provincia)
        self.assertIn("MADRID", by_seccion)
        self.assertTrue(c_urls)
        self.assertIn("MADRID", only_section)
        self.assertIn(SECCION.A, only_province)
        self.assertEqual(list(combined), ["BORME-A-2015-183-10"])

    def test_get_url_pdfs_provincia_skips_matching_items_without_url(self):
        from bormeparserv2.download import get_url_pdfs_provincia

        xml = (
            '<?xml version="1.0"?>'
            "<sumario>"
            "<metadatos><fecha_publicacion>20150210</fecha_publicacion></metadatos>"
            '<diario numero="27">'
            '<seccion codigo="A"><item><titulo>MADRID</titulo></item></seccion>'
            '<seccion codigo="B"><item><titulo>MADRID</titulo>'
            "<url_pdf>https://www.boe.es/borme/dias/2015/02/10/pdfs/"
            "BORME-B-2015-27-28.pdf</url_pdf>"
            "</item></seccion>"
            "</diario>"
            "</sumario>"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as fp:
            fp.write(xml)
            path = fp.name
        try:
            with patch("bormeparserv2.download.get_url_xml", return_value=path):
                urls = get_url_pdfs_provincia(
                    datetime.date(2015, 2, 10), PROVINCIA.MADRID
                )
            self.assertEqual(list(urls), [SECCION.B])
        finally:
            os.unlink(path)

    def test_download_size_helpers_cover_invalid_and_unbounded_inputs(self):
        from bormeparserv2.download import (
            _raise_if_response_too_large,
            _validate_max_bytes,
        )

        with self.assertRaises(ValueError):
            _validate_max_bytes(0)
        response = _FakeResponse(headers={"Content-Length": "not-an-int"})
        _raise_if_response_too_large(response, None)
        _raise_if_response_too_large(response, 10)

    def test_atomic_write_bytes_removes_temporary_file_on_replace_error(self):
        from bormeparserv2.download import _atomic_write_bytes

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "out.xml")
            with patch(
                "bormeparserv2.download.os.replace", side_effect=OSError("boom")
            ):
                with self.assertRaises(OSError):
                    _atomic_write_bytes(target, b"data")
            self.assertEqual(os.listdir(tmp), [])

    def test_download_urls_records_successful_downloads(self):
        from bormeparserv2.download import download_urls

        with tempfile.TemporaryDirectory() as tmp:
            with patch("bormeparserv2.download.download_url", return_value=True):
                files = download_urls(
                    {"x": "https://www.boe.es/borme/dias/2024/01/02/pdfs/x.pdf"},
                    tmp,
                )
            self.assertEqual(files, [os.path.join(tmp, "x.pdf")])

    def test_multithread_download_records_successful_worker_download(self):
        from bormeparserv2.download import download_urls_multi

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("bormeparserv2.download.download_url", return_value=True),
                patch("bormeparserv2.download.time.sleep", return_value=None),
            ):
                files = download_urls_multi(
                    {"x": "https://www.boe.es/borme/dias/2024/01/02/pdfs/x.pdf"},
                    tmp,
                    threads=1,
                )
            self.assertEqual(files, [os.path.join(tmp, "x.pdf")])


class BormeDownloadSuccessTestCase(unittest.TestCase):
    def test_download_sets_filename_after_success(self):
        borme = Borme(
            (2024, 1, 2),
            SECCION.A,
            PROVINCIA.MADRID,
            1,
            "BORME-A-2024-1-28",
        )
        with patch("bormeparserv2.borme.download_pdf", return_value=True):
            self.assertTrue(borme.download("/tmp/BORME-A-2024-1-28.pdf"))
        self.assertEqual(borme.filename, "/tmp/BORME-A-2024-1-28.pdf")


class IndexEdgeTestCase(unittest.TestCase):
    def _write_document(self, root, *, cve="BORME-A-2024-1-28"):
        from bormeparserv2.tests.test_index import _sample_document

        json_dir = os.path.join(root, "json", "2024", "01", "02")
        os.makedirs(json_dir)
        document = _sample_document()
        document["cve"] = cve
        document["anuncios"]["101"] = {
            "empresa": "Otra SA",
            "registro": "Madrid",
            "sucursal": False,
            "liquidacion": False,
            "datos registrales": "",
            "actos": [{"Extinción": None}, {"Cambio de domicilio social": "Madrid"}],
        }
        json_path = os.path.join(json_dir, f"{cve}.json")
        with open(json_path, "w", encoding="utf-8") as fp:
            json.dump(document, fp)
        return json_path

    def test_small_index_helpers_cover_none_invalid_and_scalar_inputs(self):
        from bormeparserv2.index import (
            _as_json_text,
            _iter_names,
            hash_embedding,
            infer_pdf_path,
            load_json_document,
        )

        self.assertIsNone(infer_pdf_path(os.path.join("/tmp", "plain.json")))
        self.assertIsNone(infer_pdf_path(os.path.join("/tmp", "json", "2024.json")))
        self.assertEqual(_as_json_text(None), "")
        self.assertEqual(tuple(_iter_names(None)), ())
        self.assertEqual(tuple(_iter_names("Ana")), ("Ana",))
        self.assertEqual(tuple(_iter_names(7)), ("7",))
        with self.assertRaises(ValueError):
            hash_embedding("text", size=0)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fp:
            json.dump({"cve": "BORME-A-1"}, fp)
            path = fp.name
        try:
            with self.assertRaises(ValueError):
                load_json_document(path)
        finally:
            os.unlink(path)

    def test_qdrant_sink_upserts_batches_with_api_key(self):
        from bormeparserv2.index import QdrantVectorSink, VectorRecord

        response = Mock()
        response.raise_for_status.return_value = None
        with patch("bormeparserv2.index.requests.put", return_value=response) as put:
            sink = QdrantVectorSink(
                "http://localhost:6333/", api_key="secret", vector_size=4
            )
            total = sink.upsert(
                [
                    VectorRecord("00000000-0000-0000-0000-000000000001", "uno", {}),
                    VectorRecord("00000000-0000-0000-0000-000000000002", "dos", {}),
                ],
                batch_size=1,
            )
        self.assertEqual(total, 2)
        self.assertEqual(put.call_count, 3)
        self.assertEqual(sink.headers["api-key"], "secret")

    def test_qdrant_sink_flushes_final_partial_batch(self):
        from bormeparserv2.index import QdrantVectorSink, VectorRecord

        response = Mock()
        response.raise_for_status.return_value = None
        with patch("bormeparserv2.index.requests.put", return_value=response) as put:
            sink = QdrantVectorSink("http://localhost:6333", vector_size=4)
            total = sink.upsert(
                [VectorRecord("00000000-0000-0000-0000-000000000003", "tres", {})],
                batch_size=64,
            )
        self.assertEqual(total, 1)
        self.assertEqual(put.call_count, 2)

    def test_relational_base_abstract_and_executemany_fallbacks(self):
        from bormeparserv2.index import RelationalBormeIndex

        class ExecuteOnlyConnection:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((sql, params))

            def close(self):
                pass

        connection = ExecuteOnlyConnection()
        index = RelationalBormeIndex(connection)
        with self.assertRaises(NotImplementedError):
            index.init_schema()
        with self.assertRaises(NotImplementedError):
            index._search_sql()
        with self.assertRaises(NotImplementedError):
            index._upsert_document({})
        index._executemany("SQL ?", [])
        index._executemany("SQL ?", [(1,), (2,)])
        self.assertEqual(len(connection.calls), 2)

    def test_index_json_file_commits_and_flushes_small_batches(self):
        from bormeparserv2 import index as index_module
        from bormeparserv2.index import SQLiteBormeIndex

        with tempfile.TemporaryDirectory() as tmp:
            json_path = self._write_document(tmp)
            raw = sqlite3.connect(os.path.join(tmp, "borme.sqlite"))
            raw.execute("PRAGMA foreign_keys = ON")
            index = SQLiteBormeIndex(raw)
            try:
                index.init_schema()
                with patch.object(index_module, "RELATIONAL_INSERT_BATCH_SIZE", 1):
                    stats = index.index_json_file(json_path)
                self.assertEqual(stats.documents, 1)
                self.assertEqual(stats.anuncios, 2)
                self.assertGreaterEqual(stats.actos, 4)
            finally:
                index.close()

    def test_index_json_root_rolls_back_when_document_loading_fails(self):
        from bormeparserv2.index import RelationalBormeIndex

        class RollbackConnection:
            def __init__(self):
                self.rollbacks = 0

            def rollback(self):
                self.rollbacks += 1

            def commit(self):
                raise AssertionError("commit should not run")

        with tempfile.TemporaryDirectory() as tmp:
            json_dir = os.path.join(tmp, "json")
            os.makedirs(json_dir)
            with open(os.path.join(json_dir, "bad.json"), "w", encoding="utf-8") as fp:
                json.dump({"cve": "missing anuncios"}, fp)
            connection = RollbackConnection()
            index = RelationalBormeIndex(connection)
            with self.assertRaises(ValueError):
                index.index_json_root(json_dir)
            self.assertEqual(connection.rollbacks, 1)

    def test_mariadb_open_validates_import_scheme_database_and_connects(self):
        from bormeparserv2.index import MariaDBBormeIndex

        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "pymysql":
                raise ImportError("no pymysql")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(RuntimeError):
                MariaDBBormeIndex.open("mariadb://u:p@localhost/db")

        fake_raw = Mock()
        fake_pymysql = SimpleNamespace(connect=Mock(return_value=fake_raw))
        with patch.dict(sys.modules, {"pymysql": fake_pymysql}):
            with self.assertRaises(ValueError):
                MariaDBBormeIndex.open("postgres://u:p@localhost/db")
            with self.assertRaises(ValueError):
                MariaDBBormeIndex.open("mariadb://u:p@localhost:3307/")
            index = MariaDBBormeIndex.open("mysql://u:p@db.example:3307/borme")

        self.assertIsInstance(index, MariaDBBormeIndex)
        fake_pymysql.connect.assert_called_once_with(
            host="db.example",
            port=3307,
            user="u",
            password="p",
            database="borme",
            charset="utf8mb4",
            autocommit=False,
        )

    def test_mariadb_sql_and_connection_adapter(self):
        from bormeparserv2.index import MariaDBBormeIndex, _MariaDBConnection

        class Cursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append(("execute", sql, params))
                return self

            def executemany(self, sql, params):
                self.calls.append(("executemany", sql, params))
                return self

        class RawConnection:
            def __init__(self):
                self.cursor_obj = Cursor()
                self.commits = 0
                self.rollbacks = 0
                self.closed = False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.commits += 1

            def rollback(self):
                self.rollbacks += 1

            def close(self):
                self.closed = True

        raw = RawConnection()
        adapter = _MariaDBConnection(raw)
        adapter.execute("SELECT ?", [1])
        adapter.executemany("INSERT ?", [[1], [2]])
        adapter.commit()
        adapter.rollback()
        adapter.close()

        self.assertEqual(raw.commits, 1)
        self.assertEqual(raw.rollbacks, 1)
        self.assertTrue(raw.closed)
        self.assertIn("%s", raw.cursor_obj.calls[0][1])

        connection = Mock()
        index = MariaDBBormeIndex(connection)
        self.assertIn("GROUP_CONCAT", index._search_sql())
        index._upsert_document(
            {
                "cve": "BORME-A-2024-1-28",
                "date": "2024-01-02",
                "seccion": "A",
                "provincia": "Madrid",
                "num": 1,
                "from_anuncio": 1,
                "to_anuncio": 2,
                "num_anuncios": 2,
                "url": "https://www.boe.es/borme/doc.pdf",
                "json_path": "/json/doc.json",
                "pdf_path": "/pdf/doc.pdf",
            }
        )
        self.assertTrue(connection.execute.called)


class SumarioEdgeTestCase(unittest.TestCase):
    def test_prev_next_borme_are_computed_lazily(self):
        from bormeparserv2.sumario import BormeXML

        bxml = BormeXML.from_file(SUMARIO_FIXTURE)
        with patch(
            "bormeparserv2.sumario._find_adjacent_borme",
            side_effect=[datetime.date(2015, 9, 23), datetime.date(2015, 9, 25)],
        ) as adjacent:
            self.assertEqual(bxml.prev_borme, datetime.date(2015, 9, 23))
            self.assertEqual(bxml.next_borme, datetime.date(2015, 9, 25))
            self.assertEqual(bxml.prev_borme, datetime.date(2015, 9, 23))
        self.assertEqual(adjacent.call_count, 2)

    def test_from_date_accepts_tuple_without_network_when_loader_is_patched(self):
        from bormeparserv2.sumario import BormeXML

        def fake_load(self, _source):
            self.date = datetime.date(2015, 2, 10)
            self.nbo = 27
            self._prev_borme = None
            self._next_borme = None

        with patch.object(BormeXML, "_load", fake_load):
            bxml = BormeXML.from_date((2015, 2, 10), secure=False)
        self.assertEqual(bxml.date, datetime.date(2015, 2, 10))
        self.assertTrue(bxml.url.startswith("http://"))

    def test_download_borme_uses_named_downloader_for_section_c_only(self):
        from bormeparserv2.sumario import BormeXML

        bxml = BormeXML.from_file(SUMARIO_FIXTURE)
        with (
            patch.object(bxml, "get_url_pdfs", return_value={"x": "http://x"}),
            patch("bormeparserv2.sumario.download_urls_multi", return_value=["a.pdf"]),
        ):
            self.assertEqual(
                bxml.download_borme("/tmp", seccion=SECCION.A), (True, ["a.pdf"])
            )

        with (
            patch.object(bxml, "get_url_pdfs", return_value={"x.xml": "http://x"}),
            patch(
                "bormeparserv2.sumario.download_urls_multi_names",
                return_value=["x.xml"],
            ),
        ):
            self.assertEqual(
                bxml.download_borme("/tmp", seccion=SECCION.C), (True, ["x.xml"])
            )

    def test_find_adjacent_borme_can_skip_missing_days_and_return_none(self):
        from bormeparserv2.sumario import BormeXML, _find_adjacent_borme

        with patch.object(
            BormeXML,
            "from_date",
            side_effect=[BormeDoesntExistException("missing"), object()],
        ):
            self.assertEqual(
                _find_adjacent_borme(datetime.date(2024, 1, 1), step=1),
                datetime.date(2024, 1, 3),
            )
        with patch.object(
            BormeXML,
            "from_date",
            side_effect=BormeDoesntExistException("missing"),
        ):
            self.assertIsNone(_find_adjacent_borme(datetime.date(2024, 1, 1), step=1))


class PyPDFEdgeTestCase(unittest.TestCase):
    def _make_parser(self):
        from bormeparserv2.backends.pypdf.parser import PyPDFParser

        return PyPDFParser(PDF_FIXTURE)

    def test_parse_falls_back_to_extracted_text_layout_without_stream_metadata(self):
        parser = self._make_parser()
        with (
            patch.object(parser, "_iter_page_contents", return_value=["BT\nET"]),
            patch.object(
                parser,
                "_parse_extracted_text_layout",
                return_value={"fallback": True},
            ),
        ):
            self.assertEqual(parser._parse(), {"fallback": True})

    def test_company_header_re_raises_unparseable_header(self):
        parser = self._make_parser()
        with self.assertRaises(ValueError):
            parser._parse_company_header("cabecera sin formato")

    def test_extract_correction_act_number_returns_none_without_match(self):
        parser = self._make_parser()
        self.assertIsNone(parser._extract_correction_act_number("sin numero de acto"))

    def test_parse_extracted_text_layout_reads_pages_and_metadata(self):
        parser = self._make_parser()

        class Page:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        fake_reader = SimpleNamespace(
            pages=[Page("uno"), Page("")], metadata={"/Keywords": "kw"}
        )
        with (
            patch(
                "bormeparserv2.backends.pypdf.parser.PdfReader",
                return_value=fake_reader,
            ),
            patch.object(
                parser,
                "_parse_extracted_text_document",
                return_value={"ok": True},
            ) as parse_doc,
        ):
            self.assertEqual(parser._parse_extracted_text_layout(), {"ok": True})
        parse_doc.assert_called_once_with("uno\n", {"/Keywords": "kw"})

    def test_metadata_keywords_invalid_input_raises(self):
        parser = self._make_parser()
        with self.assertRaises(ValueError):
            parser._metadata_from_keywords({"/Keywords": "not borme metadata"})

    def test_section_from_extracted_text_default_and_missing_section(self):
        parser = self._make_parser()
        section, subsection, province = parser._section_from_extracted_text(
            "SECCIÓN PRIMERA\nEmpresarios\nNúm. 1\ncve: BORME-A-2024-1-28",
            "MADRID",
        )
        self.assertEqual(section, "SECCIÓN PRIMERA")
        self.assertEqual(subsection, "Actos inscritos")
        self.assertEqual(province, "MADRID")
        with self.assertRaises(ValueError):
            parser._section_from_extracted_text("sin marcador de seccion", "MADRID")

    def test_plain_actos_cover_empty_unknown_prefix_and_empty_cargo_warning(self):
        parser = self._make_parser()
        self.assertEqual(parser._fallback_anuncio_id("not-a-cve"), 0)
        self.assertEqual(parser._parse_plain_actos(""), [])
        self.assertEqual(
            parser._parse_plain_actos("texto libre"),
            [{"Otros conceptos": "texto libre"}],
        )
        prefixed = parser._parse_plain_actos(
            "Texto introductorio. Nombramientos. Adm. Unico: ANA PEREZ."
        )
        self.assertEqual(prefixed[0], {"Otros conceptos": "Texto introductorio."})
        self.assertIn("Nombramientos", prefixed[1])
        with self.assertLogs(
            "bormeparserv2.backends.pypdf.parser", level="WARNING"
        ) as cap:
            parsed = parser._parse_plain_actos("Nombramientos. sin cargos validos.")
        self.assertEqual(parsed, [{"Nombramientos": {}}])
        self.assertTrue(any("No se encontraron cargos" in msg for msg in cap.output))
        self.assertEqual(parser._unknown_plain_acto("   "), {"Otros conceptos": None})
