# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is **unmaintained** upstream (see `README.md`); for production use, the README points to LibreBOR. The local fork is being modernised — keep new work compatible with the policies and gates below rather than treating it as archival.

## Supported Python versions

The project supports **only Python 3.13 and 3.14**. Both are exercised in CI (`test` job matrix). Do not add fallbacks, compatibility shims, conditional imports, or `sys.version_info` branches for older interpreters. If you find legacy version-guard code, delete it.

- `setup.py` declares `python_requires='>=3.13,<3.15'` and matching classifiers.
- `Dockerfile` is pinned to `python:3.13-bookworm`.
- Lint/types/security CI jobs run on 3.13; tests run on 3.13 **and** 3.14.

Anything that only worked because of pre-3.13 syntax or stdlib behaviour must be rewritten — do not preserve it.

## What this code does

`bormeparser` is a Python 3 library that parses files from the BORME (Boletín Oficial del Registro Mercantil), Spain's daily official gazette of company registry events. The data comes from `boe.es/diario_borme/`. Section A/B data (company acts) is locked inside PDFs; section C is available in HTML/XML. The library downloads those files, parses them, and emits Python objects or JSON.

## Commands

Setup (requires system libs `python3-dev libxslt1-dev libffi-dev zlib1g-dev gcc`):

```
pip install -r requirements_dev.txt
./setup.py develop
```

A `venv/` already exists at the repo root — activate it with `source venv/bin/activate` rather than creating a new one.

Tests (unittest-based, no pytest):

```
python setup.py test                                    # full suite
python -m unittest bormeparser.tests.test_borme         # single module
python -m unittest bormeparser.tests.test_borme.BormeTestCase.test_method  # single test
coverage run --source=bormeparser setup.py test         # with coverage (matches CI)
```

CI (`.github/workflows/bormeparser_ci.yml`) has four jobs: `docs`, `lint` (ruff/black/mypy/bandit/pip-audit), `hadolint`, `actionlint`, and `test` (matrix across Python 3.13 and 3.14). All must pass before merge.

Quality gates — every change must pass these locally before pushing:

```
ruff check .                             # lint (replaces flake8/isort/pylint/pyupgrade)
black --check .                          # formatting
mypy bormeparser                         # static types
bandit -r bormeparser scripts            # Python security scan
pip-audit --strict -r requirements.txt   # dependency CVEs
cd docs && make html SPHINXOPTS="-W"     # Sphinx with warnings-as-errors
hadolint Dockerfile                      # Dockerfile lint
actionlint                               # GitHub Actions workflow lint
```

These are the gates for the rest of the stack too — there is no separate JS/Go/etc. code in this repo, so the Python toolchain plus `hadolint`/`actionlint`/Sphinx-`-W` covers everything that ships. If you add a new file type (shell, YAML config beyond Actions, Markdown docs the project ships, etc.), add the matching linter (`shellcheck`, `yamllint`, `markdownlint`) to the `lint` CI job in the same PR — do not introduce un-linted file types.

Docs (Sphinx):

```
cd docs && make html
cd docs && make -e SPHINXOPTS="-D language='en'" html   # English build
```

Scripts (installed into `/usr/local/bin/` by the Dockerfile, runnable directly from `scripts/` in dev):

```
python scripts/download_borme_pdfs.py -f init -p VALENCIA
python scripts/check_bormes.py -d /tmp/bormes -p MADRID -f 2016-06-01 -t 2016-06-30
python scripts/borme_to_json.py BORME-A-2015-27-10.pdf
python scripts/borme_json_all.py -d /tmp/bormes
```

## Architecture

The public surface is re-exported from `bormeparser/__init__.py`. The `parse(filename_or_url, seccion)` entry point in `bormeparser/parser.py` dispatches to a backend based on the BORME section letter.

### Backend dispatch (`bormeparser/parser.py`)

`DEFAULT_PARSER` maps section letters to backend module/class pairs and is imported dynamically:

- Section **A** (company acts, PDF) → `bormeparser.backends.pypdf.parser.PyPDFParser`
- Section **C** (convocatorias, HTML/XML) → `bormeparser.backends.seccion_c.lxml.parser.LxmlBormeCParser`

Backends are picked at runtime — adding a new backend means registering it in `DEFAULT_PARSER`, not subclassing in `__init__`. All section-A backends inherit `BormeAParserBackend` (in `backends/base.py`); section-C backends inherit `BormeCParserBackend`. The base's `parse()` method builds a `Borme` from the dict returned by the backend's `_parse()` — backends only implement `_parse()`, not the public `parse()`.

### Domain model (`bormeparser/borme.py`)

Object hierarchy:

- `Borme` — one daily issue for a (date, sección, provincia) tuple. Holds `BormeAnuncio` objects and knows how to `to_json()` itself.
- `BormeAnuncio` — one numbered announcement; carries `Empresa`, the list of `BormeActo`s, and free-text `Extra`.
- `BormeActo` → `BormeActoTexto` / `BormeActoCargo`. The `cargo` variant carries officer appointments/cessations as structured dicts; the text variant is everything else. `is_acto_cargo()` in `regex.py` decides which to instantiate.
- `BormeXML` — parses the BORME summary XML (the index for a given date) and is the source of truth for which PDFs exist on a date.

`FILE_VERSION` in `borme.py` is `RAW_FILE_VERSION + 1000 * TH_FILE_VERSION`. Bump `RAW_FILE_VERSION` when the parser-level JSON output changes; the thousands digit is reserved for upstream consumers. Generated JSON files embed this version, so changing it invalidates older caches.

### Enums and lookups

- `ACTO` (`bormeparser/acto.py`) — integer IDs for every act type plus a `ALL_KEYWORDS` set used to validate names coming out of the PDF.
- `CARGO`, `EMISOR`, `PROVINCIA`, `SECCION` — value objects with class-level constants and `from_*()` factories (e.g. `SECCION.from_borme(seccion, subseccion)`, `PROVINCIA.from_title(...)`). Always go through these factories — the strings as they appear in BORME PDFs are matched exactly.
- `bormeparser/regex.py` — central regex catalog (dates, CIFs, act keywords). New parsing patterns belong here, not in backends.

### Config and conventions

- `bormeparser.CONFIG` reads `~/.bormecfg` (INI format, `[general]` section) at import time; default `borme_root` is `~/.bormes`. Scripts read `bormeparser.CONFIG["borme_root"]` rather than taking a path argument.
- `backends/defaults.py` exposes a global `OPTIONS` dict (e.g. `SANITIZE_COMPANY_NAME`) that scripts mutate *before* calling `parse()`. This is the project's chosen mechanism for backend feature flags — don't replace it with constructor kwargs without checking callers in `scripts/`.
- `setup.py` symlinks `examples/` into `bormeparser/examples` during build (and removes it after); the symlink is the source of test fixtures referenced as `bormeparser/examples/BORME-*.pdf`.

## Policies (non-negotiable)

### No suppressions, no policy bypass

Findings from the quality gates above are **fixed at the source**, never silenced. The following are forbidden in this codebase, and a PR introducing any of them will be rejected:

- `# noqa`, `# noqa: <code>`, `# type: ignore`, `# type: ignore[<code>]`
- `# nosec`, `# nosec: <id>` (bandit)
- `# fmt: off` / `# fmt: on`, `# fmt: skip` (black)
- `# pragma: no cover`, `# pragma: nocover` (coverage)
- `@typing.no_type_check`, `@unittest.skip*` used to hide failing tests, `pytest.mark.skip`/`xfail` without a reproducible upstream-bug link
- Per-file or per-line exclusions added to `pyproject.toml` / `ruff.toml` / `mypy.ini` / `.bandit` / `.coveragerc` to make a finding disappear
- Pinning dependencies to vulnerable versions to dodge `pip-audit`; upgrade or remove the dependency instead

If a tool flags something that is genuinely a false positive, raise it with the user before silencing — do not commit a suppression unilaterally. The default answer is *fix the code*.

### Clean code and clean architecture

- Functions small and single-purpose; no nested helper soup, no god classes.
- Descriptive names in Spanish where the surrounding module uses Spanish (`fecha`, `provincia`, `seccion`, `anuncio`); do not translate selectively.
- No dead code, unused imports, commented-out blocks, or `TODO: legacy` markers — delete it.
- Domain logic (`Borme`, `BormeAnuncio`, `BormeActo*`, enums in `acto.py`/`cargo.py`/`seccion.py`/`provincia.py`) stays independent of infrastructure (PDF/XML/HTTP backends, filesystem layout, CLI scripts). Backends and scripts depend on the domain, not the other way round.
- Cross dependencies go through the public surface re-exported in `bormeparser/__init__.py` and the `BormeAParserBackend` / `BormeCParserBackend` abstractions in `backends/base.py`. Do not reach across backend modules to grab implementation details.
- Validate at the boundaries (`parse(...)` entry point, CLI arg parsing, HTTP/file ingest); inside the domain, trust the types and let exceptions from `exceptions.py` propagate.
- No premature abstractions — three similar lines is fine; do not refactor speculative shared bases until a third concrete caller actually exists.

### Regression tests are mandatory

- **Every feature** ships with at least one regression test in `bormeparser/tests/` exercising the new public behaviour end-to-end (PDF/XML fixture in `examples/` → parsed `Borme` object → asserted fields).
- **Every bug fix** ships with a failing-before / passing-after regression test that fails on `master` without the fix. No exceptions for "obviously trivial" fixes — those are the ones that regress most often.
- Tests use the existing `unittest` runner (`python setup.py test` / `python -m unittest ...`). Do not introduce `pytest` markers, plugin requirements, or alternative runners alongside.
- Coverage must not drop. If `coverage run --source=bormeparser setup.py test` shows lower coverage after the change, the change is incomplete.

### No legacy left behind

When a change replaces an existing implementation, delete the old one in the same commit/PR — do not leave parallel "v1 vs v2" paths, shims, deprecation wrappers, or `_old`/`_legacy` suffixes. Specifically:

- No "older parser kept around" entries (e.g. the deleted `backends/parser1`) — if you replace `pypdf` or `seccion_c/lxml`, remove the old module and its tests in the same change.
- No backwards-compatibility aliases (`OldName = NewName`); update all call sites in `scripts/`, `bormeparser/`, and the test suite as part of the same change.
- No conditional `try: import new ... except ImportError: import old`. Choose one and remove the other.
- No version-gated branches for Python <3.13 (see "Supported Python versions").
- `CHANGES.rst` records the removal under the current dev version — that is the record of the breaking change, not a kept-around stub.

If a change is too large to remove the legacy in one PR, split the *behaviour* across PRs, but never ship the new path without removing the old one in the final PR of the sequence.

## Working in this repo

- Spanish is the primary language for docstrings, comments, error messages, and identifiers. Keep new code in the same language as the surrounding module rather than translating selectively.
- Dependencies in `requirements.txt` use floor pins with major ceilings (`lxml>=5.3,<7`, `pypdf>=5.0,<7`, `pdfminer.six>=20250506`, `requests>=2.32,<3`). PDF parsers are sensitive to layout-extraction changes, so dependency bumps must run the full test suite against the `bormeparser/examples/` fixtures and clear `pip-audit`. If `pip-audit` flags a current pin, upgrade — do not pin lower.
