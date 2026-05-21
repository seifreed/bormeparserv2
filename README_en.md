<p align="center">
  <img src="https://img.shields.io/badge/bormeparserv2-BORME%20Parser-blue?style=for-the-badge" alt="bormeparserv2">
</p>

<h1 align="center">bormeparserv2</h1>

<p align="center">
  <strong>Python library for parsing Spain's Official Gazette of Companies Registry (BORME)</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/bormeparserv2/"><img src="https://img.shields.io/pypi/v/bormeparserv2?style=flat-square&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/bormeparserv2/"><img src="https://img.shields.io/pypi/pyversions/bormeparserv2?style=flat-square&logo=python&logoColor=white" alt="Python versions"></a>
  <a href="https://github.com/seifreed/bormeparserv2/blob/master/LICENSE.txt"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-green?style=flat-square" alt="License"></a>
  <a href="https://github.com/seifreed/bormeparserv2/actions"><img src="https://img.shields.io/github/actions/workflow/status/seifreed/bormeparserv2/bormeparserv2_ci.yml?style=flat-square&logo=github&label=CI" alt="CI"></a>
</p>

<p align="center">
  <a href="https://github.com/seifreed/bormeparserv2/stargazers"><img src="https://img.shields.io/github/stars/seifreed/bormeparserv2?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/seifreed/bormeparserv2/issues"><img src="https://img.shields.io/github/issues/seifreed/bormeparserv2?style=flat-square" alt="Issues"></a>
  <a href="https://buymeacoffee.com/seifreed"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-yellow?style=flat-square&logo=buy-me-a-coffee&logoColor=white" alt="Buy Me a Coffee"></a>
</p>

<p align="center">
  <a href="README.md">🇪🇸 Versión en español</a>
</p>

---

## Overview

**bormeparserv2** is a Python library to download, parse, serialise and index Spain's [Boletín Oficial del Registro Mercantil](https://www.boe.es/diario_borme/) (BORME). It turns section A/B PDFs (company acts) and section C XML/HTML (legal announcements) into typed Python objects, ready-to-consume JSON or searchable indexes for OSINT workflows.

The supported data flow uses `pdf/` as the cache for original documents, `json/` as structured data, SQLite/MariaDB as relational indexes and Qdrant as a vector store for similarity or relationship analysis across announcements.

It is a modernised fork of [PabloCastellano/bormeparser](https://github.com/PabloCastellano/bormeparser), maintained by [Marc Rivero López](https://github.com/seifreed). See the **[Acknowledgements](#acknowledgements)** section for context.

### Key features

| Feature | Description |
|---|---|
| **Typed API** | `Borme`, `BormeAnuncio`, `BormeActo`, `Empresa`, and `PROVINCIA`/`SECCION`/`ACTO`/`CARGO` enums |
| **Section A/B (PDF)** | `pypdf`-based backend extracting acts per announcement |
| **Section C (XML/HTML)** | `lxml`-based backend for legal notices and meeting calls |
| **Download API** | HTTP client against `boe.es/datosabiertos/api/borme/sumario`, multi-threaded, idempotent |
| **JSON serialisation** | `Borme ↔ JSON` roundtrip with schema versioning |
| **Local cache** | `pdf/YYYY/MM/DD/` for original files and `json/YYYY/MM/DD/` for structured data |
| **Relational search** | SQLite or MariaDB indexes for companies, acts, roles, provincias and dates |
| **Vector stores** | JSONL export and Qdrant upsert with company, act, provincia, date and CVE payloads |
| **CLI** | `borme_to_json`, `borme_info`, `check_bormes`, `download_borme_pdfs`, … |
| **Boundary validation** | `PROVINCIA.coerce(...)` accepts ASCII attribute, accented name, or bilingual XML form |
| **Officially supported** | Python 3.13 and 3.14 |

---

## Installation

### From PyPI

```bash
pip install bormeparserv2
```

### From source

```bash
git clone https://github.com/seifreed/bormeparserv2.git
cd bormeparserv2
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

System dependencies (Debian/Ubuntu):

```bash
sudo apt-get install python3-dev libxslt1-dev libffi-dev zlib1g-dev gcc
```

### Docker

```bash
docker build -t bormeparserv2 .
docker run --rm bormeparserv2 borme_info.py /path/to/BORME-A-2015-27-10.pdf
```

---

## Quick start

```python
import datetime
import bormeparserv2

# 1) Resolve the PDF URL for a date+provincia and download it
date = datetime.date(2015, 2, 10)
url = bormeparserv2.get_url_pdf(date, bormeparserv2.SECCION.A, "CACERES")
bormeparserv2.download_pdf(date, "/tmp/cc.pdf", bormeparserv2.SECCION.A, "CACERES")

# 2) Parse the PDF into Python objects
borme = bormeparserv2.parse("/tmp/cc.pdf", bormeparserv2.SECCION.A, sanitize=True)
print(borme.cve, borme.date, borme.provincia, len(borme.anuncios))

# 3) Serialise to JSON
borme.to_json("/tmp/cc.json")
```

CLI equivalent:

```bash
download_borme_pdfs.py -d /tmp/bormes -f 2015-02-10 -t 2015-02-10 -p CACERES
borme_to_json.py -o /tmp /tmp/bormes/pdf/2015/02/10/BORME-A-2015-27-10.pdf
borme_info.py -n 57315 /tmp/bormes/pdf/2015/02/10/BORME-A-2015-27-10.pdf
```

---

## CLI

| Command | Description |
|---|---|
| `download_borme_pdfs.py` | Download PDFs by date range, section and/or provincia |
| `check_bormes.py` | Verify expected PDFs are on disk with the correct byte size |
| `borme_to_json.py` | Convert a PDF into canonical JSON |
| `borme_info.py` | Print announcements (filter with `-n <id>`) |
| `borme_json_all.py` | Walk a full `pdf/YYYY/MM/DD/` tree and convert everything |
| `borme_json_date.py` | Convert only the requested date range |
| `borme_index.py` | Index `json/` into SQLite/MariaDB, search companies/acts/roles and export vectors |
| `debug_content_pdf.py` | Dump the PDF content stream (debug the pypdf backend) |
| `borme_poller.py` | Daemon that waits until the daily sumario is published |

Every script accepts `--help`.

### Storage and Indexing

The project works naturally with this local layout:

```text
data/
  pdf/     # cache of original BOE PDFs
  json/    # structured data produced from PDFs
  borme.sqlite
```

PDFs are kept as the original source, JSON files are the structured representation, and indexes are rebuilt from `json/` without reparsing PDFs. The relational index stores documents, announcements and acts, and supports filters by company, act, role, provincia and date range.

SQLite flow:

```bash
download_borme_pdfs.py -d ./data -f 2024-01-01 -t 2024-12-31
borme_json_all.py -d ./data
borme_index.py index -d ./data --sqlite ./data/borme.sqlite
borme_index.py search -d ./data --sqlite ./data/borme.sqlite --empresa "TECNICAS"
```

More searches:

```bash
borme_index.py search -d ./data --sqlite ./data/borme.sqlite --acto "Nombramientos"
borme_index.py search -d ./data --sqlite ./data/borme.sqlite --cargo "Adm. Unico"
borme_index.py search -d ./data --sqlite ./data/borme.sqlite --provincia Madrid -f 2024-01-01 -t 2024-03-31
```

The same index can live in MariaDB:

```bash
borme_index.py index -d ./data --backend mariadb \
  --mariadb-url 'mariadb://user:pass@localhost:3306/borme'

borme_index.py search -d ./data --backend mariadb \
  --mariadb-url 'mariadb://user:pass@localhost:3306/borme' \
  --empresa "TECNICAS"
```

For similarity or relationship analysis across announcements, records can be exported as JSONL or uploaded to Qdrant:

```bash
borme_index.py vector-jsonl -d ./data -o ./data/vectors.jsonl
borme_index.py qdrant-upsert -d ./data --qdrant-url http://localhost:6333
```

The Qdrant upsert uses a local deterministic lexical hashing embedding. It is
useful for grouping similar announcements without external services; for
high-quality semantic embeddings, export `vector-jsonl` and re-embed the text
with your preferred model.

Support services with Docker:

```bash
docker run -d --name borme-mariadb \
  -e MARIADB_ROOT_PASSWORD=rootpass \
  -e MARIADB_DATABASE=borme \
  -e MARIADB_USER=borme \
  -e MARIADB_PASSWORD=bormepass \
  mariadb:11.4

docker run -d --name borme-qdrant -p 6333:6333 qdrant/qdrant:latest
```

---

## Library usage

### Basic API

```python
import bormeparserv2
from bormeparserv2 import parse, SECCION, PROVINCIA, BormeXML

# Parse a PDF (section A/B)
borme = parse("BORME-A-2015-27-10.pdf", SECCION.A, sanitize=True)

# Parse the daily sumario XML
bxml = BormeXML.from_file("BORME-S-20150924.xml")
provincias = bxml.get_provincias(SECCION.A)
url = bxml.get_url_pdfs(seccion=SECCION.A, provincia=PROVINCIA.MADRID)

# Parse section C (XML or HTML)
data = parse("BORME-C-2011-20488.xml", SECCION.C)
print(data["empresa"], data["cifs"])
```

### `PROVINCIA.coerce` — accepts every form

```python
from bormeparserv2 import PROVINCIA

PROVINCIA.coerce("CACERES")              # → PROVINCIA.CACERES
PROVINCIA.coerce("Cáceres")              # → PROVINCIA.CACERES
PROVINCIA.coerce("CÁCERES")              # → PROVINCIA.CACERES
PROVINCIA.coerce("VALENCIA/VALÈNCIA")    # → PROVINCIA.VALENCIA  (bilingual sumario form)
PROVINCIA.coerce(PROVINCIA.MADRID)       # passthrough
```

### JSON roundtrip

```python
from bormeparserv2 import Borme

borme.to_json("/tmp/out.json")
borme2 = Borme.from_json("/tmp/out.json")
assert borme2.cve == borme.cve
```

---

## Requirements

- Python 3.13 or 3.14
- `lxml >= 5.3`
- `pypdf >= 5.0`
- `pdfminer.six >= 20250506`
- `requests >= 2.32`
- `PyMySQL >= 1.2` for MariaDB indexing

See [`requirements.txt`](requirements.txt) for runtime dependencies and tooling; `setup.py` uses only the runtime section when packaging.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/name`)
3. Make sure **all** quality gates and tests pass, including live tests (`BORMEPARSERV2_LIVE=1`)
4. Add a regression test per bug, and at least one end-to-end test per feature
5. Open a Pull Request describing _why_ the change is needed

See [CLAUDE.md](CLAUDE.md) for the full policies (no suppressions, no mocks, mandatory regression tests, no legacy code paths).

---

## Support the project

If you find it useful:

<a href="https://buymeacoffee.com/seifreed" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50">
</a>

---

## License

Distributed under the **GPL-3.0-or-later** license. See [LICENSE.txt](LICENSE.txt).

**Attribution**
- Fork maintainer: **Marc Rivero López** | [mriverolopez@gmail.com](mailto:mriverolopez@gmail.com) | [@seifreed](https://github.com/seifreed)
- Repository: [github.com/seifreed/bormeparserv2](https://github.com/seifreed/bormeparserv2)

---

## Acknowledgements

bormeparserv2 is a direct fork of [**bormeparser**](https://github.com/PabloCastellano/bormeparser) by **Pablo Castellano** ([@_pablog](https://x.com/_pablog)). The whole backend design, the domain model (`Borme`, `BormeAnuncio`, `BormeActo`, the `ACTO`/`CARGO`/`PROVINCIA`/`SECCION` enums), the parsing regexes and the example fixtures are his work and form the foundation this project is built on.

This fork limits itself to:

- Modernising the code to Python 3.13/3.14 and removing compatibility branches for old interpreters.
- Migrating to the current BOE endpoints (`datosabiertos/api/borme/sumario/`).
- Hardening the quality gates (ruff/black/mypy/bandit/pip-audit/hadolint/actionlint/sphinx `-W`) and the no-mocks test suite.
- Fixing latent regressions found while exercising the API and CLI against real data.

If bormeparserv2 is useful to you, please also ⭐ [the original project](https://github.com/PabloCastellano/bormeparser) — without it, none of this would exist.

---

<p align="center">
  <sub>Built for transparency analysis, OSINT and economic-intelligence tooling on the Spanish Companies Registry</sub>
</p>
