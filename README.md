<p align="center">
  <img src="https://img.shields.io/badge/bormeparserv2-BORME%20Parser-blue?style=for-the-badge" alt="bormeparserv2">
</p>

<h1 align="center">bormeparserv2</h1>

<p align="center">
  <strong>Librería Python para parsear el Boletín Oficial del Registro Mercantil (BORME)</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/bormeparserv2/"><img src="https://img.shields.io/pypi/v/bormeparserv2?style=flat-square&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/bormeparserv2/"><img src="https://img.shields.io/pypi/pyversions/bormeparserv2?style=flat-square&logo=python&logoColor=white" alt="Versiones de Python"></a>
  <a href="https://github.com/seifreed/bormeparserv2/blob/master/LICENSE.txt"><img src="https://img.shields.io/badge/licencia-GPL--3.0--or--later-green?style=flat-square" alt="Licencia"></a>
  <a href="https://github.com/seifreed/bormeparserv2/actions"><img src="https://img.shields.io/github/actions/workflow/status/seifreed/bormeparserv2/bormeparserv2_ci.yml?style=flat-square&logo=github&label=CI" alt="Estado CI"></a>
</p>

<p align="center">
  <a href="https://github.com/seifreed/bormeparserv2/stargazers"><img src="https://img.shields.io/github/stars/seifreed/bormeparserv2?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/seifreed/bormeparserv2/issues"><img src="https://img.shields.io/github/issues/seifreed/bormeparserv2?style=flat-square" alt="Issues"></a>
  <a href="https://buymeacoffee.com/seifreed"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-apoyar-yellow?style=flat-square&logo=buy-me-a-coffee&logoColor=white" alt="Buy Me a Coffee"></a>
</p>

<p align="center">
  <a href="README_en.md">🇬🇧 English version</a>
</p>

---

## Resumen

**bormeparserv2** es una librería de Python para descargar, parsear y serializar el [Boletín Oficial del Registro Mercantil](https://www.boe.es/diario_borme/) (BORME) de España. Convierte los PDFs de la sección A/B (actos inscritos) y los XML/HTML de la sección C (convocatorias) en objetos Python tipados o en JSON listo para consumir desde otra aplicación.

Es un fork modernizado de [PabloCastellano/bormeparser](https://github.com/PabloCastellano/bormeparser), mantenido por [Marc Rivero López](https://github.com/seifreed). Ver la sección **[Agradecimientos](#agradecimientos)** para el contexto.

### Características principales

| Característica | Descripción |
|---|---|
| **API tipada** | Objetos `Borme`, `BormeAnuncio`, `BormeActo`, `Empresa`, enums `PROVINCIA`/`SECCION`/`ACTO`/`CARGO` |
| **Sección A/B (PDF)** | Backend `pypdf` que extrae actos inscritos por anuncio |
| **Sección C (XML/HTML)** | Backend `lxml` para convocatorias y avisos legales |
| **API de descarga** | Cliente HTTP contra `boe.es/datosabiertos/api/borme/sumario`, multi-thread, idempotente |
| **Serialización JSON** | Roundtrip `Borme ↔ JSON` con versionado de esquema |
| **CLI** | Scripts `borme_to_json`, `borme_info`, `check_bormes`, `download_borme_pdfs`, … |
| **Validación en frontera** | `PROVINCIA.coerce(...)` acepta atributo ASCII, nombre acentuado o forma bilingüe del sumario |
| **Soporte oficial** | Python 3.13 y 3.14 |

---

## Instalación

### Desde PyPI

```bash
pip install bormeparserv2
```

### Desde código fuente

```bash
git clone https://github.com/seifreed/bormeparserv2.git
cd bormeparserv2
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

Dependencias del sistema (Debian/Ubuntu):

```bash
sudo apt-get install python3-dev libxslt1-dev libffi-dev zlib1g-dev gcc
```

### Docker

```bash
docker build -t bormeparserv2 .
docker run --rm bormeparserv2 borme_info.py /ruta/al/BORME-A-2015-27-10.pdf
```

---

## Inicio rápido

```python
import datetime
import bormeparserv2

# 1) Resolver la URL del PDF de una provincia y descargarlo
date = datetime.date(2015, 2, 10)
url = bormeparserv2.get_url_pdf(date, bormeparserv2.SECCION.A, "CACERES")
bormeparserv2.download_pdf(date, "/tmp/cc.pdf", bormeparserv2.SECCION.A, "CACERES")

# 2) Parsear el PDF a objetos Python
borme = bormeparserv2.parse("/tmp/cc.pdf", bormeparserv2.SECCION.A, sanitize=True)
print(borme.cve, borme.date, borme.provincia, len(borme.anuncios))

# 3) Serializar a JSON
borme.to_json("/tmp/cc.json")
```

CLI equivalente:

```bash
download_borme_pdfs.py -d /tmp/bormes -f 2015-02-10 -t 2015-02-10 -p CACERES
borme_to_json.py -o /tmp /tmp/bormes/pdf/2015/02/10/BORME-A-2015-27-10.pdf
borme_info.py -n 57315 /tmp/bormes/pdf/2015/02/10/BORME-A-2015-27-10.pdf
```

---

## CLI

| Comando | Descripción |
|---|---|
| `download_borme_pdfs.py` | Descarga PDFs por rango de fechas, sección y/o provincia |
| `check_bormes.py` | Verifica que todos los PDFs esperados están en disco y con el tamaño correcto |
| `borme_to_json.py` | Convierte un PDF en JSON canónico |
| `borme_info.py` | Imprime los anuncios de un BORME (filtrable con `-n <id>`) |
| `borme_json_all.py` | Convierte recursivamente toda una jerarquía `pdf/AAAA/MM/DD/` |
| `borme_json_date.py` | Convierte solo el rango de fechas indicado |
| `debug_content_pdf.py` | Vuelca el content stream del PDF (debug del backend pypdf) |
| `borme_poller.py` | Daemon que espera a que el sumario del día esté publicado |

Cada script acepta `--help` para ver todas sus opciones.

---

## Uso como librería

### API básica

```python
import bormeparserv2
from bormeparserv2 import parse, SECCION, PROVINCIA, BormeXML

# Parsear PDF (sección A/B)
borme = parse("BORME-A-2015-27-10.pdf", SECCION.A, sanitize=True)

# Parsear XML del sumario diario
bxml = BormeXML.from_file("BORME-S-20150924.xml")
provincias = bxml.get_provincias(SECCION.A)
url = bxml.get_url_pdfs(seccion=SECCION.A, provincia=PROVINCIA.MADRID)

# Parsear sección C (XML o HTML)
data = parse("BORME-C-2011-20488.xml", SECCION.C)
print(data["empresa"], data["cifs"])
```

### `PROVINCIA.coerce` — acepta todas las formas

```python
from bormeparserv2 import PROVINCIA

PROVINCIA.coerce("CACERES")              # → PROVINCIA.CACERES
PROVINCIA.coerce("Cáceres")              # → PROVINCIA.CACERES
PROVINCIA.coerce("CÁCERES")              # → PROVINCIA.CACERES
PROVINCIA.coerce("VALENCIA/VALÈNCIA")    # → PROVINCIA.VALENCIA  (forma bilingüe del sumario)
PROVINCIA.coerce(PROVINCIA.MADRID)       # passthrough
```

### Roundtrip JSON

```python
from bormeparserv2 import Borme

borme.to_json("/tmp/out.json")
borme2 = Borme.from_json("/tmp/out.json")
assert borme2.cve == borme.cve
```

---

## Calidad y tests

El proyecto sigue un conjunto estricto de _quality gates_ que se ejecutan en cada commit:

```bash
ruff check .                                         # lint
black --check .                                      # formato
mypy bormeparserv2                                   # tipos
bandit -r bormeparserv2 scripts                      # seguridad
pip-audit --strict -r requirements.txt               # CVEs en dependencias
hadolint Dockerfile                                  # lint Dockerfile
actionlint                                           # lint workflows
cd docs && make html SPHINXOPTS="-W"                 # docs sin warnings
python -m unittest discover bormeparserv2.tests      # suite offline
BORMEPARSERV2_LIVE=1 python -m unittest discover bormeparserv2.tests   # también contra boe.es
```

**Política de tests:** sin mocks. Todos los tests ejercitan código real contra fixtures reales (`bormeparserv2/examples/`) o contra los endpoints de `boe.es` bajo el decorador `@require_live`. Si una funcionalidad no se puede probar de forma reproducible, no se considera completa.

**Cobertura objetivo:** ≥ 88%, medida con `coverage run --source=bormeparserv2 -m unittest discover bormeparserv2.tests`.

---

## Requisitos

- Python 3.13 o 3.14
- `lxml >= 5.3`
- `pypdf >= 5.0`
- `pdfminer.six >= 20250506`
- `requests >= 2.32`

Ver [`requirements.txt`](requirements.txt) y [`setup.py`](setup.py) para la lista completa.

---

## Contribuir

1. Haz un fork del repositorio
2. Crea una rama (`git checkout -b feature/nombre`)
3. Asegúrate de que pasan **todos** los _quality gates_ y los tests, incluidos los live (`BORMEPARSERV2_LIVE=1`)
4. Añade un test de regresión por cada bug y al menos uno end-to-end por cada feature
5. Abre un Pull Request describiendo el _porqué_ del cambio

Ver [CLAUDE.md](CLAUDE.md) para el detalle de las políticas (no suprimir avisos, no mocks, regresiones obligatorias, sin código legacy).

---

## Apoya el proyecto

Si te resulta útil:

<a href="https://buymeacoffee.com/seifreed" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50">
</a>

---

## Licencia

Distribuido bajo licencia **GPL-3.0-or-later**. Ver [LICENSE.txt](LICENSE.txt).

**Atribución**
- Mantenedor del fork: **Marc Rivero López** | [mriverolopez@gmail.com](mailto:mriverolopez@gmail.com) | [@seifreed](https://github.com/seifreed)
- Repositorio: [github.com/seifreed/bormeparserv2](https://github.com/seifreed/bormeparserv2)

---

## Agradecimientos

bormeparserv2 es un fork directo de [**bormeparser**](https://github.com/PabloCastellano/bormeparser) de **Pablo Castellano** ([@_pablog](https://x.com/_pablog)). Todo el diseño original de los backends, el modelo de dominio (`Borme`, `BormeAnuncio`, `BormeActo`, enums `ACTO`/`CARGO`/`PROVINCIA`/`SECCION`), los regex de parsing y los fixtures de ejemplo son obra suya y son la base sobre la que está construido este proyecto.

Este fork se limita a:

- Modernizar el código a Python 3.13/3.14 y eliminar las ramas de compatibilidad con versiones antiguas.
- Migrar a los endpoints actuales del BOE (`datosabiertos/api/borme/sumario/`).
- Reforzar los _quality gates_ (ruff/black/mypy/bandit/pip-audit/hadolint/actionlint/sphinx `-W`) y la suite de tests sin mocks.
- Corregir regresiones latentes encontradas al ejercitar la API y los scripts contra datos reales.

Si bormeparserv2 te resulta útil, considera también ⭐ [el proyecto original](https://github.com/PabloCastellano/bormeparser) — sin él, nada de esto existiría.

---

<p align="center">
  <sub>Hecho para análisis de transparencia, OSINT y herramientas de inteligencia económica sobre el Registro Mercantil español</sub>
</p>
