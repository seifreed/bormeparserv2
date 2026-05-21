#!/usr/bin/env python

import json
import os
import sqlite3
import tempfile
import unittest

from bormeparserv2.index import (
    MariaDBBormeIndex,
    SQLiteBormeIndex,
    build_vector_records,
    hash_embedding,
    infer_pdf_path,
)


def _sample_document():
    return {
        "cve": "BORME-A-2024-1-28",
        "date": "2024-01-02",
        "seccion": "A",
        "provincia": "Madrid",
        "num": 1,
        "from_anuncio": 100,
        "to_anuncio": 100,
        "num_anuncios": 1,
        "url": "https://www.boe.es/borme/dias/2024/01/02/pdfs/BORME-A-2024-1-28.pdf",
        "anuncios": {
            "100": {
                "empresa": "Técnicas Reunidas Internacional SA",
                "registro": "Madrid",
                "sucursal": False,
                "liquidacion": False,
                "datos registrales": "T 1, F 2, S 8",
                "num_actos": 2,
                "actos": [
                    {"Nombramientos": {"Adm. Unico": ["MARIA GARCIA"]}},
                    {"Objeto social": "Servicios de ingeniería industrial"},
                ],
            }
        },
        "raw_version": "1",
        "version": "2001",
    }


def _write_sample(root):
    json_dir = os.path.join(root, "json", "2024", "01", "02")
    pdf_dir = os.path.join(root, "pdf", "2024", "01", "02")
    os.makedirs(json_dir)
    os.makedirs(pdf_dir)
    json_path = os.path.join(json_dir, "BORME-A-2024-1-28.json")
    pdf_path = os.path.join(pdf_dir, "BORME-A-2024-1-28.pdf")
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(_sample_document(), fp)
    with open(pdf_path, "wb") as fp:
        fp.write(b"%PDF-1.4\n")
    return json_path, pdf_path


class _CountingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.commits = 0
        self.rollbacks = 0
        self.executemany_calls = 0

    def execute(self, *args, **kwargs):
        return self.connection.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        self.executemany_calls += 1
        return self.connection.executemany(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self.connection.executescript(*args, **kwargs)

    def commit(self):
        self.commits += 1
        self.connection.commit()

    def rollback(self):
        self.rollbacks += 1
        self.connection.rollback()

    def close(self):
        self.connection.close()


class _RecordingConnection:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def execute(self, sql, params=()):
        self.statements.append(sql)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


class BormeIndexTestCase(unittest.TestCase):
    def test_sqlite_index_supports_company_acto_and_cargo_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path, pdf_path = _write_sample(tmp)
            db_path = os.path.join(tmp, "borme.sqlite")
            index = SQLiteBormeIndex.open(db_path)
            try:
                index.init_schema()
                stats = index.index_json_root(os.path.join(tmp, "json"), borme_root=tmp)

                self.assertEqual(stats.documents, 1)
                self.assertEqual(stats.anuncios, 1)
                self.assertEqual(stats.actos, 2)

                company_results = index.search(empresa="tecnicas reunidas")
                self.assertEqual(len(company_results), 1)
                self.assertEqual(
                    company_results[0].empresa, "Técnicas Reunidas Internacional SA"
                )
                self.assertEqual(company_results[0].pdf_path, pdf_path)
                self.assertEqual(company_results[0].json_path, json_path)

                self.assertEqual(len(index.search(acto="nombramientos")), 1)
                self.assertEqual(len(index.search(cargo="adm unico")), 1)
                self.assertEqual(len(index.search(nombre="maria garcia")), 1)
                self.assertEqual(len(index.search(nombre="garcia maria")), 1)
                self.assertEqual(len(index.search(provincia="madrid")), 1)
                self.assertEqual(len(index.search(date_from="2024-01-03")), 0)

                structured_value = index.connection.execute(
                    "SELECT valor_text FROM actos WHERE cargo = ?", ("Adm. Unico",)
                ).fetchone()[0]
                text_value = index.connection.execute(
                    "SELECT valor_text FROM actos WHERE acto = ?", ("Objeto social",)
                ).fetchone()[0]
                self.assertEqual(structured_value, "")
                self.assertEqual(text_value, "Servicios de ingeniería industrial")
            finally:
                index.close()

    def test_sqlite_root_index_uses_batched_inserts_and_one_bulk_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_sample(tmp)
            second_dir = os.path.join(tmp, "json", "2024", "01", "03")
            os.makedirs(second_dir)
            second = _sample_document()
            second["cve"] = "BORME-A-2024-2-28"
            second["date"] = "2024-01-03"
            with open(
                os.path.join(second_dir, "BORME-A-2024-2-28.json"),
                "w",
                encoding="utf-8",
            ) as fp:
                json.dump(second, fp)

            raw = sqlite3.connect(os.path.join(tmp, "borme.sqlite"))
            raw.execute("PRAGMA foreign_keys = ON")
            connection = _CountingConnection(raw)
            index = SQLiteBormeIndex(connection)
            try:
                index.init_schema()
                connection.commits = 0
                stats = index.index_json_root(os.path.join(tmp, "json"))

                self.assertEqual(stats.documents, 2)
                self.assertEqual(connection.commits, 1)
                self.assertGreater(connection.executemany_calls, 0)
            finally:
                index.close()

    def test_mariadb_schema_allows_long_act_values(self):
        connection = _RecordingConnection()
        index = MariaDBBormeIndex(connection)

        index.init_schema()

        schema = "\n".join(connection.statements)
        self.assertIn("empresa_norm TEXT NOT NULL", schema)
        self.assertIn("INDEX idx_anuncios_empresa (empresa_norm(255))", schema)
        self.assertIn("acto_norm TEXT NOT NULL", schema)
        self.assertIn("valor_text LONGTEXT", schema)
        self.assertIn("INDEX idx_actos_acto (acto_norm(255))", schema)
        self.assertIn("cargo_norm TEXT", schema)
        self.assertIn("INDEX idx_actos_cargo (cargo_norm(255))", schema)
        self.assertIn("nombre_norm TEXT", schema)
        self.assertIn("INDEX idx_actos_nombre (nombre_norm(255))", schema)
        self.assertEqual(connection.commits, 1)

    def test_vector_records_are_stable_and_embed_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path, _pdf_path = _write_sample(tmp)
            records = build_vector_records(_sample_document(), json_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(
                records[0].payload["empresa"], "Técnicas Reunidas Internacional SA"
            )
            self.assertIn("Servicios de ingeniería", records[0].text)

            vector = hash_embedding(records[0].text, size=16)
            self.assertEqual(len(vector), 16)
            self.assertAlmostEqual(sum(v * v for v in vector), 1.0)

    def test_infer_pdf_path_from_canonical_json_layout(self):
        path = os.path.join(
            "/tmp", "bormes", "json", "2024", "01", "02", "BORME-A-2024-1-28.json"
        )
        expected = os.path.join(
            "/tmp", "bormes", "pdf", "2024", "01", "02", "BORME-A-2024-1-28.pdf"
        )
        self.assertEqual(infer_pdf_path(path), expected)
