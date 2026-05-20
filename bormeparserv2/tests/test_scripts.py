#!/usr/bin/env python
#
# test_scripts.py - Regresiones de los scripts CLI bajo ``scripts/``.
# Copyright (C) 2015-2026 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Pruebas reales (sin mocks) de los scripts de la carpeta ``scripts/``.

Cada test invoca el ``main()`` real del script con argumentos reales y
fixtures reales del paquete ``bormeparserv2/examples/``. No se monkeypatchean
parsers, ni se simulan stdin/stdout: cada script se ejecuta tal cual lo
haría un usuario, pero en el mismo proceso para no depender de subprocess
(que dispararía B404/B603 en bandit) y poder asertar sobre stdout/stderr
capturados.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from dataclasses import dataclass
from types import ModuleType

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
EXAMPLES_DIR = os.path.join(REPO_ROOT, "bormeparserv2", "examples")
PDF_FIXTURE = os.path.join(EXAMPLES_DIR, "BORME-A-2015-27-10.pdf")


@dataclass
class ScriptResult:
    """Resultado de invocar ``main()`` de un script CLI."""

    returncode: int
    stdout: str
    stderr: str


def _load_script(script_name: str) -> ModuleType:
    """Carga ``scripts/<script_name>`` como módulo.

    Los scripts no son un paquete instalado y dependen de ``import
    common`` (``scripts/common.py``). Añadimos ``scripts/`` a
    ``sys.path`` antes de importarlos para que esa dependencia resuelva.
    """
    if SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    mod_name = "_bormeparser_script_" + script_name[:-3]
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(SCRIPTS_DIR, script_name)
    )
    # spec_from_file_location nunca devuelve None para un fichero .py
    # existente bajo ``SCRIPTS_DIR``; el ``assert`` documenta la
    # invariante y satisface al typechecker.
    assert spec is not None and spec.loader is not None, script_name
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _systemexit_to_returncode(exc: SystemExit) -> int:
    """Mapea el ``code`` de ``SystemExit`` a un entero exit code.

    ``sys.exit()`` sin argumento pasa ``None`` (éxito), ``sys.exit("msg")``
    pasa un string (fallo con mensaje en stderr), y ``sys.exit(N)`` pasa
    el entero directamente — esta función normaliza los tres casos.
    """
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1


def run_main(script_name: str, *argv: str) -> ScriptResult:
    """Invoca ``main(list(argv))`` del script y captura stdout/stderr.

    Cubre tanto el camino de retorno normal (``return N``) como las
    salidas vía ``SystemExit`` que dispara ``argparse`` con ``--help``
    o argumentos inválidos.
    """
    mod = _load_script(script_name)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            returncode = mod.main(list(argv))
        except SystemExit as exc:
            returncode = _systemexit_to_returncode(exc)
    return ScriptResult(
        returncode=returncode, stdout=out.getvalue(), stderr=err.getvalue()
    )


class BormeToJsonScriptTestCase(unittest.TestCase):
    """``scripts/borme_to_json.py`` debe escribir un JSON válido del fixture."""

    def test_pdf_to_json_creates_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_main("borme_to_json.py", "-o", tmp, PDF_FIXTURE)
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out_path = os.path.join(tmp, "BORME-A-2015-27-10.json")
            self.assertTrue(os.path.isfile(out_path), msg=f"stdout={result.stdout!r}")
            with open(out_path, encoding="utf-8") as fp:
                data = json.load(fp)
            self.assertEqual(data["cve"], "BORME-A-2015-27-10")
            self.assertEqual(data["provincia"], "Cáceres")


class BormeInfoScriptTestCase(unittest.TestCase):
    """``scripts/borme_info.py`` debe imprimir información del PDF.

    Regresión: con ``-n`` declarado como ``nargs='*' type=int`` argparse
    devoraba el positional ``filename``. Comprobamos que ``-n 57315
    <PDF>`` separa correctamente el número del fichero.
    """

    def test_dumps_full_borme(self):
        result = run_main("borme_info.py", PDF_FIXTURE)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        self.assertIn("CVE: BORME-A-2015-27-10", result.stdout)
        self.assertIn("Provincia: Cáceres", result.stdout)
        self.assertIn("Anuncio 57315", result.stdout)

    def test_filter_by_anuncio_number(self):
        result = run_main("borme_info.py", "-n", "57315", PDF_FIXTURE)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        self.assertIn("Anuncio 57315", result.stdout)
        # Cuando se filtra por número no se imprime la sección "Otros datos".
        self.assertNotIn("CVE: BORME-A-2015-27-10", result.stdout)

    def test_unknown_anuncio_returns_error(self):
        result = run_main("borme_info.py", "-n", "999999", PDF_FIXTURE)
        self.assertEqual(result.returncode, 1)
        self.assertIn("No existe el anuncio 999999", result.stdout)


class DebugContentPdfScriptTestCase(unittest.TestCase):
    """``scripts/debug_content_pdf.py`` debe volcar el stream del PDF.

    Regresión: el ``with open(...)`` se cerraba antes de que pypdf
    llamara a ``page.get_contents()``, que reabre el stream para
    resolver objetos indirectos → ``ValueError: seek of closed file``.
    """

    def test_dumps_pdf_stream(self):
        result = run_main("debug_content_pdf.py", PDF_FIXTURE)
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        # El stream contiene operadores PDF estándar (BT = Begin Text).
        self.assertIn("BT", result.stdout)
        self.assertNotIn("seek of closed file", result.stderr)


class BormeJsonAllScriptTestCase(unittest.TestCase):
    """``scripts/borme_json_all.py`` debe recorrer ``pdf/YYYY/MM/DD/``.

    Regresión: ``next(os.walk(missing_dir))`` lanza ``StopIteration``,
    que dentro de un generador PEP 479 se transforma en
    ``RuntimeError``. El script debe avisar con un mensaje claro
    y salir con código distinto de 0 sin trazar.
    """

    def test_missing_pdf_root_reports_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Sin subcarpeta ``pdf/`` ⇒ debe fallar con mensaje legible.
            result = run_main("borme_json_all.py", "-d", tmp)
            self.assertNotEqual(result.returncode, 0, msg=f"stdout={result.stdout!r}")
            combined = result.stdout + result.stderr
            self.assertNotIn("RuntimeError", combined)
            self.assertNotIn("StopIteration", combined)
            self.assertIn("Estructura esperada", combined)

    def test_converts_pdf_under_expected_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = os.path.join(tmp, "pdf", "2015", "02", "10")
            os.makedirs(day_dir)
            shutil.copy(PDF_FIXTURE, day_dir)
            result = run_main("borme_json_all.py", "-d", tmp)
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            # ``json_<git-sha>/2015/02/10/BORME-A-2015-27-10.json`` debe existir.
            produced = []
            for root, _dirs, files in os.walk(tmp):
                for fname in files:
                    if fname.endswith(".json"):
                        produced.append(os.path.join(root, fname))
            self.assertEqual(len(produced), 1, msg=f"produced={produced!r}")
            with open(produced[0], encoding="utf-8") as fp:
                data = json.load(fp)
            self.assertEqual(data["cve"], "BORME-A-2015-27-10")


class BormeJsonDateScriptTestCase(unittest.TestCase):
    """``scripts/borme_json_date.py`` debe convertir solo el rango pedido."""

    def test_converts_single_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = os.path.join(tmp, "pdf", "2015", "02", "10")
            os.makedirs(day_dir)
            shutil.copy(PDF_FIXTURE, day_dir)
            result = run_main(
                "borme_json_date.py",
                "-d",
                tmp,
                "-f",
                "2015-02-10",
                "-t",
                "2015-02-10",
            )
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out_path = os.path.join(
                tmp, "json", "2015", "02", "10", "BORME-A-2015-27-10.json"
            )
            self.assertTrue(os.path.isfile(out_path), msg=f"stdout={result.stdout!r}")
            with open(out_path, encoding="utf-8") as fp:
                data = json.load(fp)
            self.assertEqual(data["cve"], "BORME-A-2015-27-10")

    def test_missing_day_dir_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "pdf"))
            result = run_main(
                "borme_json_date.py",
                "-d",
                tmp,
                "-f",
                "2015-02-10",
                "-t",
                "2015-02-10",
            )
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            self.assertIn("No existe", result.stdout)


class CheckBormesScriptTestCase(unittest.TestCase):
    """``scripts/check_bormes.py`` debe avisar (no trazar) si falta el XML."""

    def test_missing_xml_without_download_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            # ``check_bormes`` enruta los mensajes por su propio logger, no
            # por stdout/stderr. ``assertLogs`` engancha un handler propio,
            # así que es indiferente que el script tenga el suyo configurado.
            with self.assertLogs("check_bormes", level="INFO") as captured:
                result = run_main(
                    "check_bormes.py",
                    "-d",
                    tmp,
                    "-f",
                    "2015-02-10",
                    "-t",
                    "2015-02-10",
                    "-p",
                    "MADRID",
                )
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            self.assertTrue(
                any(
                    "If you want to continue use --download-xml" in m
                    for m in captured.output
                ),
                msg=f"captured={captured.output!r}",
            )


class DownloadBormePdfsScriptTestCase(unittest.TestCase):
    """``scripts/download_borme_pdfs.py`` debe responder a --help offline."""

    def test_help_prints_usage_and_exits(self):
        result = run_main("download_borme_pdfs.py", "--help")
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        self.assertIn("usage:", result.stdout)
        self.assertIn("BORME PDF files", result.stdout)


class BormePollerScriptTestCase(unittest.TestCase):
    """``scripts/borme_poller.py --help`` debe imprimir uso y salir.

    Regresión: el script no tenía argparse, así que ``--help`` lo
    ignoraba y se quedaba ejecutando el bucle de polling indefinidamente.
    """

    def test_help_prints_usage_and_exits(self):
        result = run_main("borme_poller.py", "--help")
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        self.assertIn("usage:", result.stdout)
        self.assertIn("sumario", result.stdout)


class SystemExitToReturncodeTestCase(unittest.TestCase):
    """``_systemexit_to_returncode`` normaliza los tres tipos de ``code``."""

    def test_none_maps_to_zero(self):
        # ``sys.exit()`` sin arg ⇒ code=None ⇒ éxito.
        self.assertEqual(_systemexit_to_returncode(SystemExit()), 0)

    def test_int_maps_to_itself(self):
        self.assertEqual(_systemexit_to_returncode(SystemExit(0)), 0)
        self.assertEqual(_systemexit_to_returncode(SystemExit(2)), 2)

    def test_string_message_maps_to_one(self):
        # ``sys.exit("msg")`` ⇒ code="msg" ⇒ fallo (exit 1).
        self.assertEqual(_systemexit_to_returncode(SystemExit("oops")), 1)
