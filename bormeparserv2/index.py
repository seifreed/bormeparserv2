# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""Indexación de JSON BORME en bases relacionales y vector stores.

La capa persistente parte de la estructura local:

``pdf/`` conserva los PDFs originales, ``json/`` contiene el parseo
estructurado, y este módulo construye índices consultables a partir de esos
JSON sin volver a parsear PDFs.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from .utils import remove_accents

DEFAULT_SQLITE_FILENAME = "borme.sqlite"
DEFAULT_QDRANT_COLLECTION = "borme_anuncios"
DEFAULT_VECTOR_SIZE = 384
HTTP_TIMEOUT = 30
RELATIONAL_INSERT_BATCH_SIZE = 500
_QDRANT_COLLECTION = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}$")


def normalize_text(value: object) -> str:
    """Normaliza texto para búsquedas case/accent-insensitive."""
    if value is None:
        return ""
    text = remove_accents(str(value)).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def iter_json_paths(json_root: str) -> Iterable[str]:
    """Recorre ``json/`` en orden estable y devuelve ficheros ``.json``."""
    for root, _dirs, files in os.walk(json_root):
        for filename in sorted(files):
            if filename.endswith(".json"):
                yield os.path.join(root, filename)


def infer_pdf_path(json_path: str, borme_root: str | None = None) -> str | None:
    """Infere el PDF original correspondiente a ``json/AAAA/MM/DD/foo.json``."""
    parts = os.path.normpath(json_path).split(os.sep)
    try:
        json_index = len(parts) - 1 - parts[::-1].index("json")
    except ValueError:
        return None

    if len(parts) < json_index + 5:
        return None

    relative = parts[json_index + 1 :]
    relative[-1] = relative[-1][:-5] + ".pdf"
    if borme_root is None:
        base = os.sep.join(parts[:json_index]) or os.curdir
    else:
        base = borme_root
    return os.path.join(base, "pdf", *relative)


def _date_or_none(value: str | None) -> str | None:
    if not value:
        return None
    # Valida ISO date y devuelve el string original para SQLite/MariaDB.
    _dt.date.fromisoformat(value)
    return value


def _as_json_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _iter_names(value: object) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return (str(item) for item in value if item)
    return (str(value),)


@dataclass(frozen=True)
class IndexStats:
    documents: int = 0
    anuncios: int = 0
    actos: int = 0

    def __add__(self, other: "IndexStats") -> "IndexStats":
        return IndexStats(
            self.documents + other.documents,
            self.anuncios + other.anuncios,
            self.actos + other.actos,
        )


@dataclass(frozen=True)
class SearchResult:
    date: str
    provincia: str
    seccion: str
    cve: str
    anuncio_id: int
    empresa: str
    actos: str
    json_path: str | None
    pdf_path: str | None


@dataclass(frozen=True)
class VectorRecord:
    id: str
    text: str
    payload: dict[str, object]


def load_json_document(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fp:
        data = json.load(fp)
    if "cve" not in data or "anuncios" not in data:
        raise ValueError(f"{path} no parece un JSON BORME válido")
    return data


def build_vector_records(data: dict[str, Any], json_path: str) -> list[VectorRecord]:
    records: list[VectorRecord] = []
    for anuncio_id, anuncio in sorted(
        data["anuncios"].items(), key=lambda item: int(item[0])
    ):
        actos_text = []
        for acto_doc in anuncio.get("actos", []):
            for acto, value in acto_doc.items():
                actos_text.append(f"{acto}: {_as_json_text(value)}")
        text = "\n".join(
            part
            for part in (
                anuncio.get("empresa"),
                anuncio.get("datos registrales"),
                "\n".join(actos_text),
            )
            if part
        )
        payload = {
            "cve": data["cve"],
            "anuncio_id": int(anuncio_id),
            "empresa": anuncio.get("empresa", ""),
            "date": data.get("date"),
            "provincia": data.get("provincia"),
            "seccion": data.get("seccion"),
            "json_path": json_path,
        }
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{data['cve']}:{anuncio_id}"))
        records.append(VectorRecord(point_id, text, payload))
    return records


def hash_embedding(text: str, *, size: int = DEFAULT_VECTOR_SIZE) -> list[float]:
    """Embedding local determinista basado en hashing léxico.

    No pretende sustituir a un modelo semántico, pero permite agrupar y buscar
    anuncios parecidos sin depender de servicios externos.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    vector = [0.0] * size
    tokens = re.findall(r"[A-Z0-9]{2,}", normalize_text(text))
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % size
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


class QdrantVectorSink:
    """Cliente HTTP mínimo para Qdrant."""

    def __init__(
        self,
        url: str,
        collection: str = DEFAULT_QDRANT_COLLECTION,
        *,
        api_key: str | None = None,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
        self.url = _validate_qdrant_url(url)
        self.collection = _validate_qdrant_collection(collection)
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        self.vector_size = vector_size
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["api-key"] = api_key

    def ensure_collection(self) -> None:
        response = requests.put(
            f"{self.url}/collections/{self.collection}",
            headers=self.headers,
            json={"vectors": {"size": self.vector_size, "distance": "Cosine"}},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()

    def upsert(self, records: Iterable[VectorRecord], *, batch_size: int = 64) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.ensure_collection()
        batch: list[dict[str, Any]] = []
        total = 0
        for record in records:
            batch.append(
                {
                    "id": record.id,
                    "vector": hash_embedding(record.text, size=self.vector_size),
                    "payload": record.payload | {"text": record.text},
                }
            )
            if len(batch) >= batch_size:
                total += self._flush(batch)
                batch = []
        if batch:
            total += self._flush(batch)
        return total

    def _flush(self, points: list[dict[str, Any]]) -> int:
        response = requests.put(
            f"{self.url}/collections/{self.collection}/points",
            headers=self.headers,
            params={"wait": "true"},
            json={"points": points},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return len(points)


def _validate_qdrant_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Qdrant URL must be http(s)://host[:port]")
    return url.rstrip("/")


def _validate_qdrant_collection(collection: str) -> str:
    if not _QDRANT_COLLECTION.match(collection):
        raise ValueError(
            "Qdrant collection must be 1-255 chars: letters, digits, '_', '-' or '.'"
        )
    return collection


class RelationalBormeIndex:
    def __init__(self, connection) -> None:
        self.connection = connection

    def close(self) -> None:
        self.connection.close()

    def init_schema(self) -> None:
        raise NotImplementedError

    def index_json_file(
        self, path: str, *, borme_root: str | None = None, commit: bool = True
    ) -> IndexStats:
        data = load_json_document(path)
        pdf_path = infer_pdf_path(path, borme_root)
        document = {
            "cve": data["cve"],
            "date": _date_or_none(data.get("date")),
            "seccion": data.get("seccion", ""),
            "provincia": data.get("provincia", ""),
            "num": data.get("num"),
            "from_anuncio": data.get("from_anuncio"),
            "to_anuncio": data.get("to_anuncio"),
            "num_anuncios": data.get("num_anuncios"),
            "url": data.get("url"),
            "json_path": path,
            "pdf_path": pdf_path,
        }
        self._upsert_document(document)
        self._delete_document_children(data["cve"])

        anuncios = [
            (int(anuncio_id), anuncio)
            for anuncio_id, anuncio in sorted(
                data["anuncios"].items(), key=lambda item: int(item[0])
            )
        ]
        anuncio_rows = [
            self._build_anuncio_row(data["cve"], anuncio_id, anuncio)
            for anuncio_id, anuncio in anuncios
        ]

        self._insert_anuncio_rows(anuncio_rows)

        acto_count = 0
        acto_rows = []
        for anuncio_id, anuncio in anuncios:
            for row in self._iter_acto_rows(data["cve"], anuncio_id, anuncio):
                acto_rows.append(row)
                acto_count += 1
                if len(acto_rows) >= RELATIONAL_INSERT_BATCH_SIZE:
                    self._insert_acto_rows(acto_rows)
                    acto_rows = []
        self._insert_acto_rows(acto_rows)

        if commit:
            self.connection.commit()
        return IndexStats(1, len(anuncio_rows), acto_count)

    def index_json_root(
        self, json_root: str, *, borme_root: str | None = None
    ) -> IndexStats:
        stats = IndexStats()
        try:
            for path in iter_json_paths(json_root):
                stats += self.index_json_file(path, borme_root=borme_root, commit=False)
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
            raise
        self.connection.commit()
        return stats

    def search(
        self,
        *,
        empresa: str | None = None,
        acto: str | None = None,
        cargo: str | None = None,
        nombre: str | None = None,
        provincia: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        empresa_pattern = f"%{normalize_text(empresa)}%" if empresa else None
        acto_pattern = f"%{normalize_text(acto)}%" if acto else None
        cargo_pattern = f"%{normalize_text(cargo)}%" if cargo else None
        nombre_norm = normalize_text(nombre) if nombre else ""
        nombre_pattern = f"%{nombre_norm}%" if nombre_norm else None
        nombre_parts = nombre_norm.split()
        nombre_borme_order = " ".join(nombre_parts[1:] + nombre_parts[:1])
        nombre_borme_pattern = (
            f"%{nombre_borme_order}%" if len(nombre_parts) > 1 else nombre_pattern
        )
        provincia_pattern = f"%{normalize_text(provincia)}%" if provincia else None
        date_from_value = _date_or_none(date_from)
        date_to_value = _date_or_none(date_to)
        params = (
            empresa_pattern,
            empresa_pattern,
            acto_pattern,
            acto_pattern,
            cargo_pattern,
            cargo_pattern,
            nombre_pattern,
            nombre_pattern,
            nombre_borme_pattern,
            provincia_pattern,
            provincia_pattern,
            date_from_value,
            date_from_value,
            date_to_value,
            date_to_value,
            limit,
        )
        cursor = self.connection.execute(self._search_sql(), params)
        return [
            SearchResult(
                date=str(row[0]) if row[0] is not None else "",
                provincia=row[1],
                seccion=row[2],
                cve=row[3],
                anuncio_id=row[4],
                empresa=row[5],
                actos=row[6] or "",
                json_path=row[7],
                pdf_path=row[8],
            )
            for row in cursor.fetchall()
        ]

    def _search_sql(self) -> str:
        raise NotImplementedError

    def _upsert_document(self, document: dict[str, object]) -> None:
        raise NotImplementedError

    def _delete_document_children(self, cve: str) -> None:
        self.connection.execute("DELETE FROM actos WHERE cve = ?", (cve,))
        self.connection.execute("DELETE FROM anuncios WHERE cve = ?", (cve,))

    def _executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        if not rows:
            return
        executemany = getattr(self.connection, "executemany", None)
        if executemany is not None:
            executemany(sql, rows)
            return
        for row in rows:
            self.connection.execute(sql, row)

    def _build_anuncio_row(
        self, cve: str, anuncio_id: int, anuncio: dict[str, Any]
    ) -> tuple[object, ...]:
        return (
            cve,
            anuncio_id,
            anuncio.get("empresa", ""),
            normalize_text(anuncio.get("empresa", "")),
            anuncio.get("registro", ""),
            int(bool(anuncio.get("sucursal"))),
            int(bool(anuncio.get("liquidacion"))),
            anuncio.get("datos registrales", ""),
        )

    def _insert_anuncio_rows(self, rows: list[tuple[object, ...]]) -> None:
        sql = (
            "INSERT INTO anuncios "
            "(cve, anuncio_id, empresa, empresa_norm, registro, sucursal, "
            "liquidacion, datos_registrales) "
            "VALUES (?,?,?,?,?,?,?,?)"
        )
        self._executemany(sql, rows)

    def _iter_acto_rows(
        self, cve: str, anuncio_id: int, anuncio: dict[str, Any]
    ) -> Iterable[tuple[object, ...]]:
        for acto_doc in anuncio.get("actos", []):
            for acto, value in acto_doc.items():
                if isinstance(value, dict):
                    for cargo, nombres in value.items():
                        for nombre in sorted(_iter_names(nombres)):
                            yield self._build_acto_row(
                                cve, anuncio_id, acto, value, cargo, nombre
                            )
                else:
                    yield self._build_acto_row(cve, anuncio_id, acto, value, None, None)

    def _build_acto_row(
        self,
        cve: str,
        anuncio_id: int,
        acto: str,
        value: object,
        cargo: str | None,
        nombre: str | None,
    ) -> tuple[object, ...]:
        valor_text = (
            "" if cargo is not None or nombre is not None else _as_json_text(value)
        )
        return (
            cve,
            anuncio_id,
            acto,
            normalize_text(acto),
            valor_text,
            cargo,
            normalize_text(cargo),
            nombre,
            normalize_text(nombre),
        )

    def _insert_acto_rows(self, rows: list[tuple[object, ...]]) -> None:
        sql = (
            "INSERT INTO actos "
            "(cve, anuncio_id, acto, acto_norm, valor_text, cargo, cargo_norm, "
            "nombre, nombre_norm) "
            "VALUES (?,?,?,?,?,?,?,?,?)"
        )
        self._executemany(sql, rows)


class SQLiteBormeIndex(RelationalBormeIndex):
    @classmethod
    def open(cls, path: str) -> "SQLiteBormeIndex":
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys = ON")
        return cls(connection)

    def init_schema(self) -> None:
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
              cve TEXT PRIMARY KEY,
              date TEXT,
              seccion TEXT,
              provincia TEXT,
              provincia_norm TEXT,
              num INTEGER,
              from_anuncio INTEGER,
              to_anuncio INTEGER,
              num_anuncios INTEGER,
              url TEXT,
              json_path TEXT,
              pdf_path TEXT
            );

            CREATE TABLE IF NOT EXISTS anuncios (
              row_id INTEGER PRIMARY KEY AUTOINCREMENT,
              cve TEXT NOT NULL,
              anuncio_id INTEGER NOT NULL,
              empresa TEXT NOT NULL,
              empresa_norm TEXT NOT NULL,
              registro TEXT,
              sucursal INTEGER NOT NULL DEFAULT 0,
              liquidacion INTEGER NOT NULL DEFAULT 0,
              datos_registrales TEXT,
              UNIQUE (cve, anuncio_id),
              FOREIGN KEY (cve) REFERENCES documents(cve) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS actos (
              row_id INTEGER PRIMARY KEY AUTOINCREMENT,
              cve TEXT NOT NULL,
              anuncio_id INTEGER NOT NULL,
              acto TEXT NOT NULL,
              acto_norm TEXT NOT NULL,
              valor_text TEXT,
              cargo TEXT,
              cargo_norm TEXT,
              nombre TEXT,
              nombre_norm TEXT,
              FOREIGN KEY (cve, anuncio_id)
                REFERENCES anuncios(cve, anuncio_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_documents_date ON documents(date);
            CREATE INDEX IF NOT EXISTS idx_documents_provincia ON documents(provincia_norm);
            CREATE INDEX IF NOT EXISTS idx_anuncios_empresa ON anuncios(empresa_norm);
            CREATE INDEX IF NOT EXISTS idx_actos_acto ON actos(acto_norm);
            CREATE INDEX IF NOT EXISTS idx_actos_cargo ON actos(cargo_norm);
            CREATE INDEX IF NOT EXISTS idx_actos_nombre ON actos(nombre_norm);
            """)
        self.connection.commit()

    def _search_sql(self) -> str:
        return (
            "SELECT d.date, d.provincia, d.seccion, a.cve, a.anuncio_id, "
            "a.empresa, group_concat(DISTINCT ac.acto), d.json_path, d.pdf_path "
            "FROM anuncios a "
            "JOIN documents d ON d.cve = a.cve "
            "LEFT JOIN actos ac ON ac.cve = a.cve AND ac.anuncio_id = a.anuncio_id "
            "WHERE (? IS NULL OR a.empresa_norm LIKE ?) "
            "AND (? IS NULL OR ac.acto_norm LIKE ?) "
            "AND (? IS NULL OR ac.cargo_norm LIKE ?) "
            "AND (? IS NULL OR ac.nombre_norm LIKE ? OR ac.nombre_norm LIKE ?) "
            "AND (? IS NULL OR d.provincia_norm LIKE ?) "
            "AND (? IS NULL OR d.date >= ?) "
            "AND (? IS NULL OR d.date <= ?) "
            "GROUP BY d.date, d.provincia, d.seccion, a.cve, a.anuncio_id, "
            "a.empresa, d.json_path, d.pdf_path "
            "ORDER BY d.date DESC, a.anuncio_id ASC "
            "LIMIT ?"
        )

    def _upsert_document(self, document: dict[str, object]) -> None:
        sql = (
            "INSERT INTO documents "
            "(cve, date, seccion, provincia, provincia_norm, num, from_anuncio, "
            "to_anuncio, num_anuncios, url, json_path, pdf_path) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(cve) DO UPDATE SET "
            "date=excluded.date, seccion=excluded.seccion, provincia=excluded.provincia, "
            "provincia_norm=excluded.provincia_norm, num=excluded.num, "
            "from_anuncio=excluded.from_anuncio, to_anuncio=excluded.to_anuncio, "
            "num_anuncios=excluded.num_anuncios, url=excluded.url, "
            "json_path=excluded.json_path, pdf_path=excluded.pdf_path"
        )
        self.connection.execute(
            sql,
            (
                document["cve"],
                document["date"],
                document["seccion"],
                document["provincia"],
                normalize_text(document["provincia"]),
                document["num"],
                document["from_anuncio"],
                document["to_anuncio"],
                document["num_anuncios"],
                document["url"],
                document["json_path"],
                document["pdf_path"],
            ),
        )


class MariaDBBormeIndex(RelationalBormeIndex):
    @classmethod
    def open(cls, url: str) -> "MariaDBBormeIndex":
        try:
            import pymysql  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("MariaDB requiere instalar PyMySQL") from exc

        parsed = urlparse(url)
        if parsed.scheme not in {"mariadb", "mysql"}:
            raise ValueError("URL esperada: mariadb://user:pass@host:3306/database")
        database = parsed.path.lstrip("/")
        if not database:
            raise ValueError("La URL MariaDB debe incluir una base de datos")
        raw_connection = pymysql.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=database,
            charset="utf8mb4",
            autocommit=False,
        )
        return cls(_MariaDBConnection(raw_connection))

    def init_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS documents (
              cve VARCHAR(64) PRIMARY KEY,
              date DATE,
              seccion VARCHAR(8),
              provincia VARCHAR(128),
              provincia_norm VARCHAR(128),
              num INTEGER,
              from_anuncio INTEGER,
              to_anuncio INTEGER,
              num_anuncios INTEGER,
              url TEXT,
              json_path TEXT,
              pdf_path TEXT,
              INDEX idx_documents_date (date),
              INDEX idx_documents_provincia (provincia_norm)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS anuncios (
              row_id BIGINT AUTO_INCREMENT PRIMARY KEY,
              cve VARCHAR(64) NOT NULL,
              anuncio_id INTEGER NOT NULL,
              empresa TEXT NOT NULL,
              empresa_norm TEXT NOT NULL,
              registro TEXT,
              sucursal BOOLEAN NOT NULL DEFAULT 0,
              liquidacion BOOLEAN NOT NULL DEFAULT 0,
              datos_registrales TEXT,
              UNIQUE KEY uq_anuncio (cve, anuncio_id),
              INDEX idx_anuncios_empresa (empresa_norm(255)),
              CONSTRAINT fk_anuncios_documents
                FOREIGN KEY (cve) REFERENCES documents(cve) ON DELETE CASCADE
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS actos (
              row_id BIGINT AUTO_INCREMENT PRIMARY KEY,
              cve VARCHAR(64) NOT NULL,
              anuncio_id INTEGER NOT NULL,
              acto TEXT NOT NULL,
              acto_norm TEXT NOT NULL,
              valor_text LONGTEXT,
              cargo TEXT,
              cargo_norm TEXT,
              nombre TEXT,
              nombre_norm TEXT,
              INDEX idx_actos_anuncio (cve, anuncio_id),
              INDEX idx_actos_acto (acto_norm(255)),
              INDEX idx_actos_cargo (cargo_norm(255)),
              INDEX idx_actos_nombre (nombre_norm(255)),
              CONSTRAINT fk_actos_anuncios
                FOREIGN KEY (cve, anuncio_id)
                REFERENCES anuncios(cve, anuncio_id) ON DELETE CASCADE
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """,
        ]
        for statement in statements:
            self.connection.execute(statement)
        self.connection.commit()

    def _search_sql(self) -> str:
        return (
            "SELECT d.date, d.provincia, d.seccion, a.cve, a.anuncio_id, "
            "a.empresa, GROUP_CONCAT(DISTINCT ac.acto SEPARATOR ', '), "
            "d.json_path, d.pdf_path "
            "FROM anuncios a "
            "JOIN documents d ON d.cve = a.cve "
            "LEFT JOIN actos ac ON ac.cve = a.cve AND ac.anuncio_id = a.anuncio_id "
            "WHERE (? IS NULL OR a.empresa_norm LIKE ?) "
            "AND (? IS NULL OR ac.acto_norm LIKE ?) "
            "AND (? IS NULL OR ac.cargo_norm LIKE ?) "
            "AND (? IS NULL OR ac.nombre_norm LIKE ? OR ac.nombre_norm LIKE ?) "
            "AND (? IS NULL OR d.provincia_norm LIKE ?) "
            "AND (? IS NULL OR d.date >= ?) "
            "AND (? IS NULL OR d.date <= ?) "
            "GROUP BY d.date, d.provincia, d.seccion, a.cve, a.anuncio_id, "
            "a.empresa, d.json_path, d.pdf_path "
            "ORDER BY d.date DESC, a.anuncio_id ASC "
            "LIMIT ?"
        )

    def _upsert_document(self, document: dict[str, object]) -> None:
        sql = (
            "INSERT INTO documents "
            "(cve, date, seccion, provincia, provincia_norm, num, from_anuncio, "
            "to_anuncio, num_anuncios, url, json_path, pdf_path) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON DUPLICATE KEY UPDATE "
            "date=VALUES(date), seccion=VALUES(seccion), provincia=VALUES(provincia), "
            "provincia_norm=VALUES(provincia_norm), num=VALUES(num), "
            "from_anuncio=VALUES(from_anuncio), to_anuncio=VALUES(to_anuncio), "
            "num_anuncios=VALUES(num_anuncios), url=VALUES(url), "
            "json_path=VALUES(json_path), pdf_path=VALUES(pdf_path)"
        )
        self.connection.execute(
            sql,
            (
                document["cve"],
                document["date"],
                document["seccion"],
                document["provincia"],
                normalize_text(document["provincia"]),
                document["num"],
                document["from_anuncio"],
                document["to_anuncio"],
                document["num_anuncios"],
                document["url"],
                document["json_path"],
                document["pdf_path"],
            ),
        )


class _MariaDBConnection:
    """Adaptador mínimo para usar PyMySQL con la misma interfaz que sqlite3."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def execute(self, sql: str, params: Iterable[object] = ()):
        cursor = self._connection.cursor()
        sql = sql.replace("?", "%s")
        cursor.execute(sql, tuple(params))
        return cursor

    def executemany(self, sql: str, params: Iterable[Iterable[object]]):
        cursor = self._connection.cursor()
        sql = sql.replace("?", "%s")
        cursor.executemany(sql, [tuple(row) for row in params])
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()
