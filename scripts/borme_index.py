#!/usr/bin/env python3
#
# borme_index.py - Index/search BORME JSON datasets.

import argparse
import json
import os
import sys

import bormeparserv2
from bormeparserv2.index import (
    DEFAULT_QDRANT_COLLECTION,
    DEFAULT_SQLITE_FILENAME,
    MariaDBBormeIndex,
    QdrantVectorSink,
    SQLiteBormeIndex,
    build_vector_records,
    iter_json_paths,
    load_json_document,
)

BORME_ROOT = bormeparserv2.CONFIG["borme_root"]


def _json_root(directory: str, json_root: str | None) -> str:
    return json_root or os.path.join(directory, "json")


def _sqlite_path(directory: str, sqlite_path: str | None) -> str:
    return sqlite_path or os.path.join(directory, DEFAULT_SQLITE_FILENAME)


def _open_index(args):
    if args.backend == "sqlite":
        index = SQLiteBormeIndex.open(_sqlite_path(args.directory, args.sqlite))
    else:
        if not args.mariadb_url:
            raise SystemExit("--mariadb-url es obligatorio con --backend mariadb")
        index = MariaDBBormeIndex.open(args.mariadb_url)
    index.init_schema()
    return index


def _add_database_args(parser):
    parser.add_argument(
        "-d",
        "--directory",
        default=BORME_ROOT,
        help=f"Raíz con pdf/ y json/ (default: {BORME_ROOT})",
    )
    parser.add_argument(
        "--backend",
        choices=("sqlite", "mariadb"),
        default="sqlite",
        help="Base relacional a usar",
    )
    parser.add_argument(
        "--sqlite",
        help="Ruta del índice SQLite (default: <directory>/borme.sqlite)",
    )
    parser.add_argument(
        "--mariadb-url",
        help="URL MariaDB: mariadb://user:pass@host:3306/database",
    )


def _cmd_index(args) -> int:
    json_root = _json_root(args.directory, args.json_root)
    index = _open_index(args)
    try:
        stats = index.index_json_root(json_root, borme_root=args.directory)
    finally:
        index.close()
    print(
        "Indexed {documents} documents, {anuncios} anuncios, {actos} actos".format(
            documents=stats.documents,
            anuncios=stats.anuncios,
            actos=stats.actos,
        )
    )
    return 0


def _cmd_search(args) -> int:
    index = _open_index(args)
    try:
        results = index.search(
            empresa=args.empresa,
            acto=args.acto,
            cargo=args.cargo,
            provincia=args.provincia,
            date_from=args.fromdate,
            date_to=args.to,
            limit=args.limit,
        )
    finally:
        index.close()

    for result in results:
        if args.json:
            print(json.dumps(result.__dict__, ensure_ascii=False, sort_keys=True))
        else:
            print(
                "{date} {provincia} {cve} #{anuncio_id} {empresa} [{actos}]".format(
                    **result.__dict__
                )
            )
    return 0


def _iter_vector_records(json_root: str):
    for path in iter_json_paths(json_root):
        data = load_json_document(path)
        yield from build_vector_records(data, path)


def _cmd_vector_jsonl(args) -> int:
    json_root = _json_root(args.directory, args.json_root)
    count = 0
    with open(args.output, "w", encoding="utf-8") as fp:
        for record in _iter_vector_records(json_root):
            fp.write(
                json.dumps(
                    {
                        "id": record.id,
                        "text": record.text,
                        "payload": record.payload,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            fp.write("\n")
            count += 1
    print(f"Exported {count} vector records to {args.output}")
    return 0


def _cmd_qdrant_upsert(args) -> int:
    json_root = _json_root(args.directory, args.json_root)
    sink = QdrantVectorSink(
        args.qdrant_url,
        args.collection,
        api_key=args.api_key,
        vector_size=args.vector_size,
    )
    count = sink.upsert(
        _iter_vector_records(json_root),
        batch_size=args.batch_size,
    )
    print(f"Upserted {count} vector records into Qdrant collection {args.collection}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Indexa y busca BORME JSON en SQLite, MariaDB o Qdrant."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Indexa json/ en SQL")
    _add_database_args(index_parser)
    index_parser.add_argument("--json-root", help="Directorio JSON a indexar")
    index_parser.set_defaults(func=_cmd_index)

    search_parser = subparsers.add_parser("search", help="Busca anuncios indexados")
    _add_database_args(search_parser)
    search_parser.add_argument("--empresa", help="Filtro por nombre de empresa")
    search_parser.add_argument("--acto", help="Filtro por acto mercantil")
    search_parser.add_argument("--cargo", help="Filtro por cargo")
    search_parser.add_argument("--provincia", help="Filtro por provincia")
    search_parser.add_argument("-f", "--fromdate", help="Fecha mínima YYYY-MM-DD")
    search_parser.add_argument("-t", "--to", help="Fecha máxima YYYY-MM-DD")
    search_parser.add_argument("--limit", type=int, default=50)
    search_parser.add_argument("--json", action="store_true", help="Salida JSONL")
    search_parser.set_defaults(func=_cmd_search)

    vector_parser = subparsers.add_parser(
        "vector-jsonl", help="Exporta registros listos para vectorización"
    )
    vector_parser.add_argument(
        "-d",
        "--directory",
        default=BORME_ROOT,
        help=f"Raíz con json/ (default: {BORME_ROOT})",
    )
    vector_parser.add_argument("--json-root", help="Directorio JSON a exportar")
    vector_parser.add_argument("-o", "--output", required=True)
    vector_parser.set_defaults(func=_cmd_vector_jsonl)

    qdrant_parser = subparsers.add_parser(
        "qdrant-upsert", help="Sube anuncios a una colección Qdrant"
    )
    qdrant_parser.add_argument(
        "-d",
        "--directory",
        default=BORME_ROOT,
        help=f"Raíz con json/ (default: {BORME_ROOT})",
    )
    qdrant_parser.add_argument("--json-root", help="Directorio JSON a indexar")
    qdrant_parser.add_argument("--qdrant-url", required=True)
    qdrant_parser.add_argument(
        "--collection",
        default=DEFAULT_QDRANT_COLLECTION,
        help=f"Colección Qdrant (default: {DEFAULT_QDRANT_COLLECTION})",
    )
    qdrant_parser.add_argument("--api-key")
    qdrant_parser.add_argument("--vector-size", type=int, default=384)
    qdrant_parser.add_argument("--batch-size", type=int, default=64)
    qdrant_parser.set_defaults(func=_cmd_qdrant_upsert)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
