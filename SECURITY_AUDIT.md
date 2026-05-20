# Auditoría de seguridad

Estado: pase final completado
Fecha: 2026-05-20
Rama auditada: `master`

## Alcance actual

Se está auditando el árbol completo rastreado por git: 96 ficheros. La
aplicación tiene estas superficies de riesgo:

- Entradas no confiables: XML/HTML del BOE, PDFs BORME, JSON de roundtrip.
- Red: `requests` contra `boe.es` y URLs recibidas desde sumarios.
- Ficheros: descargas PDF/XML, serialización JSON, layout local `pdf/`/`xml/`.
- CLI: scripts en `scripts/`.
- Supply chain: `requirements*.txt`, Dockerfile y GitHub Actions.
- Artefactos no ejecutables: documentación, traducciones `.po/.mo`, licencia,
  changelog y fixtures de ejemplo.

## Técnicas ejecutadas

- Revisión manual dirigida de entradas XML/HTML/PDF, red, rutas y escrituras.
- Búsquedas estáticas con `rg` de sinks: `requests`, `open`, `os.path.join`,
  XML/lxml, JSON, subprocess/eval/exec/pickle/yaml/tar/zip y secretos.
- Inventario completo con `git ls-files | sort`: 96 ficheros rastreados.
- Revisión de tipos y hashes de fixtures PDF/XML/HTML de `bormeparserv2/examples`.
- Revisión de documentación, traducciones `.po`, catálogos `.mo`, licencia,
  changelog y metadatos de empaquetado.
- `bandit -r bormeparserv2 scripts -x bormeparserv2/tests -f txt`: 0 hallazgos.
- `pip-audit -r requirements.txt`: 0 vulnerabilidades conocidas.
- `pip-audit -r requirements_dev.txt`: 0 vulnerabilidades conocidas.
- `pip-audit -r requirements_doc.txt`: 0 vulnerabilidades conocidas.
- `pip-audit` del entorno: 0 vulnerabilidades conocidas; el paquete local no
  existe en PyPI y se omite como esperado.
- `ruff check .`: OK.
- `black --check .`: OK tras formateo.
- `mypy bormeparserv2`: OK.
- `python -m unittest discover -s bormeparserv2/tests -p 'test*.py'`: 252 tests
  OK, 27 omitidos.
- `make -C docs html SPHINXOPTS='-W'`: OK.
- `docker build --progress=plain -t bormeparserv2-security-audit:final .`: OK.
- `docker run --rm bormeparserv2-security-audit:final id -u`: `1000`.
- `docker run --rm bormeparserv2-security-audit:final sh -lc 'pwd && whoami'`:
  `/home/borme`, `borme`.

## Hallazgos corregidos

1. XXE / entidades externas en XML con `lxml`.
   - Riesgo: parsear sumarios o sección C con parser por defecto podía quedar
     expuesto a expansión de entidades externas.
   - Fix: parser XML centralizado con `resolve_entities=False`,
     `load_dtd=False`, `no_network=True`; parser HTML con `no_network=True`.
   - Commit: `a31cd3a fix(security): harden XML parsing and download paths`.

2. Path traversal en nombres derivados de XML/PDF.
   - Riesgo: identificadores CVE o nombres explícitos de descarga podían usarse
     como nombres de fichero fuera del directorio esperado.
   - Fix: `safe_filename`, `safe_join`, extracción validada de nombre desde URL;
     aplicada a descargas, JSON y `check_bormes.py`.
   - Commit: `a31cd3a fix(security): harden XML parsing and download paths`.

3. Contexto Docker enviaba estado local al daemon.
   - Riesgo: `COPY . /build` sin `.dockerignore` podía enviar `.git`, `venv`,
     caches, cobertura o ficheros locales sensibles al daemon de Docker.
   - Fix: `.dockerignore` con exclusiones de estado local y patrones de secretos.
   - Commit: `1d06b4c fix(docker): exclude local state from build context`.

4. Descargas no atómicas.
   - Riesgo: una descarga cortada podía dejar un PDF/XML parcial en la ruta final;
     llamadas posteriores lo trataban como existente y no reintentaban.
   - Fix: escritura a temporal en el mismo directorio y `os.replace` sólo al
     completar; limpieza de temporales si falla el stream.
   - Commit: `ea1038d fix(download): write downloads atomically`.

5. `GITHUB_TOKEN` sin permisos mínimos explícitos.
   - Riesgo: el workflow heredaba permisos por defecto del repositorio.
   - Fix: `permissions: contents: read` a nivel workflow.
   - Commit: `42451b7 fix(ci): restrict workflow token permissions`.

6. Imagen Docker final ejecutaba como root.
   - Riesgo: las CLIs parsean PDF/XML potencialmente no confiables con privilegios
     root dentro del contenedor.
   - Fix: usuario `borme`, `WORKDIR /home/borme`, `USER borme`.
   - Commit: `94ee28c fix(docker): run final image as non-root`.

7. Formato incompatible con Black tras los fixes.
   - Riesgo: CI podía fallar y bloquear gates de seguridad.
   - Fix: Black aplicado a ficheros tocados.
   - Commit: `d61b9af style: apply black formatting`.

## Estado por superficie

- Código de librería `bormeparserv2/*.py`: revisado con foco en red, XML/PDF,
  JSON, rutas, excepciones y serialización. Hallazgos corregidos.
- Backends `bormeparserv2/backends/**`: revisados para XML/HTML y PDF. Hallazgos
  XML corregidos; PDF queda cubierto por tests de fixtures y ejecución no-root
  en Docker.
- Scripts `scripts/*.py`: revisados para red, rutas y escritura. `check_bormes.py`
  endurecido con `safe_join`.
- Tests `bormeparserv2/tests/*.py`: usados como evidencia y ampliados con
  regresiones de XXE, traversal, descargas parciales, Docker context y non-root.
- Packaging/Docker/CI: revisados y endurecidos.
- Dependencias: sin vulnerabilidades conocidas por `pip-audit`.
- Documentación y traducciones: revisadas. Los `.rst`, `.md` y `.po` son texto;
  los `.mo` son catálogos gettext compilados y no forman parte de la ejecución
  runtime de la librería. Sphinx compila con warnings tratados como error.
- Fixtures `bormeparserv2/examples/*`: revisados por tipo y hash; se usan en
  tests de parsing y roundtrip. No contienen código ejecutable.

## Cierre

No quedan hallazgos de seguridad abiertos en los 96 ficheros rastreados tras el
pase final. Las defensas añadidas están cubiertas por regresiones específicas y
las comprobaciones automáticas listadas arriba pasan en árbol limpio.
