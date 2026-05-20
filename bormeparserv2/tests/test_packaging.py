#!/usr/bin/env python
#
# test_packaging.py - Regresiones sobre los artefactos publicables.
# Copyright (C) 2015-2026 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Comprueba que ``sdist`` y ``wheel`` se construyen e instalan limpios.

Los tests aquí no usan mocks: invocan el constructor de paquetes real
(``setuptools.build_meta``) contra el árbol de fuentes y verifican que
los ficheros producidos contienen lo que la API pública necesita en
tiempo de ejecución (fixtures de ``bormeparserv2/examples/`` para los
parsers) y en tiempo de instalación (``requirements.txt`` para
``setup.py:get_install_requires``).

No reinstalan los paquetes en venvs nuevos porque eso requeriría salida
a red para descargar dependencias en CI. Se inspecciona el contenido de
los artefactos generados, que es donde han aparecido las regresiones.
"""

import os
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from typing import Literal

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DistType = Literal["sdist", "wheel"]


def _build(distribution: DistType) -> str:
    """Construye ``sdist`` o ``wheel`` invocando ``build.ProjectBuilder``
    en proceso (no usa ``subprocess`` para no disparar B404/B603 en
    bandit). Devuelve la ruta absoluta del artefacto producido.
    """
    try:
        from build import ProjectBuilder
        from build.env import DefaultIsolatedEnv
    except ImportError:
        raise unittest.SkipTest("python-build no instalado")

    tmp = tempfile.mkdtemp(prefix="bormeparser_pkg_")
    with DefaultIsolatedEnv() as env:
        builder = ProjectBuilder.from_isolated_env(env, REPO_ROOT)
        env.install(builder.build_system_requires)
        env.install(builder.get_requires_for_build(distribution))
        return builder.build(distribution, tmp)


class SdistShipsAllBuildtimeRequirementsTestCase(unittest.TestCase):
    """``setup.py:get_install_requires`` lee ``requirements.txt``.

    Sin él en el sdist, ``pip install bormeparserv2-X.tar.gz`` falla con
    ``FileNotFoundError: requirements.txt`` en build-time.
    """

    @classmethod
    def setUpClass(cls):
        cls.sdist = _build("sdist")
        cls.addClassCleanup(shutil.rmtree, os.path.dirname(cls.sdist))

    def test_sdist_includes_requirements_txt(self):
        with tarfile.open(self.sdist) as tar:
            names = tar.getnames()
        self.assertTrue(
            any(n.endswith("/requirements.txt") for n in names),
            msg=f"sdist members: {names!r}",
        )

    def test_sdist_includes_setup_py_and_pkg_info(self):
        with tarfile.open(self.sdist) as tar:
            names = tar.getnames()
        for required in ("setup.py", "PKG-INFO", "README.md", "LICENSE.txt"):
            self.assertTrue(
                any(n.endswith("/" + required) for n in names),
                msg=f"missing {required} in {names!r}",
            )

    def test_sdist_ships_example_fixtures(self):
        with tarfile.open(self.sdist) as tar:
            names = tar.getnames()
        for fixture in (
            "examples/BORME-A-2015-27-10.pdf",
            "examples/BORME-C-2011-20488.html",
            "examples/BORME-C-2011-20488.xml",
            "examples/BORME-S-20150924.xml",
        ):
            self.assertTrue(
                any(n.endswith(fixture) for n in names),
                msg=f"missing fixture {fixture}",
            )


class WheelShipsRuntimeFixturesTestCase(unittest.TestCase):
    """La wheel debe contener los fixtures que ``parse()`` y los tests
    consumen, y NO debe contener el árbol de tests (``find_packages
    exclude=['*.tests']``)."""

    @classmethod
    def setUpClass(cls):
        cls.wheel = _build("wheel")
        cls.addClassCleanup(shutil.rmtree, os.path.dirname(cls.wheel))

    def test_wheel_ships_example_fixtures(self):
        with zipfile.ZipFile(self.wheel) as zf:
            names = zf.namelist()
        for fixture in (
            "bormeparserv2/examples/BORME-A-2015-27-10.pdf",
            "bormeparserv2/examples/BORME-C-2011-20488.html",
            "bormeparserv2/examples/BORME-C-2011-20488.xml",
            "bormeparserv2/examples/BORME-S-20150924.xml",
        ):
            self.assertIn(fixture, names, msg=f"missing {fixture}")

    def test_wheel_excludes_tests(self):
        with zipfile.ZipFile(self.wheel) as zf:
            names = zf.namelist()
        offenders = [n for n in names if "/tests/" in n]
        self.assertEqual(offenders, [], msg=f"tests leaked into wheel: {offenders!r}")


if __name__ == "__main__":
    unittest.main()
