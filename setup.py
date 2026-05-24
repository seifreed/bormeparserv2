#!/usr/bin/env python
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

import os
from pathlib import Path

from setuptools import find_packages, setup

VERSION = "0.5.1.dev0"
VERSION_ENV_VAR = "BORMEPARSERV2_VERSION"


def get_version() -> str:
    release_version = os.environ.get(VERSION_ENV_VAR)
    if release_version:
        return release_version

    pkg_info = Path(__file__).with_name("PKG-INFO")
    if pkg_info.is_file():
        for line in pkg_info.read_text(encoding="utf-8").splitlines():
            if line.startswith("Version: "):
                return line.removeprefix("Version: ").strip()

    return VERSION


def get_install_requires() -> list[str]:
    requirements: list[str] = []
    with open("requirements.txt", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip()
            if line == "# Development, test, lint, security and documentation tooling.":
                break
            if not line or line.startswith(("#", "http", "git")):
                continue
            requirements.append(line)
    return requirements


def _read_long_description() -> str:
    with open("README.md", encoding="utf-8") as fh:
        return fh.read()


setup(
    name="bormeparserv2",
    packages=find_packages(exclude=["*.tests"]),
    package_data={"bormeparserv2": ["examples/*"]},
    version=get_version(),
    description="bormeparserv2 is a Python library for parsing BORME files",
    long_description=_read_long_description(),
    long_description_content_type="text/markdown",
    author="Marc Rivero López",
    author_email="mriverolopez@gmail.com",
    maintainer="Marc Rivero López",
    maintainer_email="mriverolopez@gmail.com",
    url="https://github.com/seifreed/bormeparserv2",
    download_url="https://github.com/seifreed/bormeparserv2/archive/master.zip",
    project_urls={
        "Source": "https://github.com/seifreed/bormeparserv2",
        "Bug Tracker": "https://github.com/seifreed/bormeparserv2/issues",
        "Original project": "https://github.com/PabloCastellano/bormeparser",
    },
    keywords=[
        "BORME",
        "transparency",
        "opendata",
        "Spain",
        "Registro mercantil",
        "Boletín Oficial del Registro Mercantil",
    ],
    classifiers=[
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ],
    python_requires=">=3.13,<3.15",
    license="GPL-3.0-or-later",
    license_files=["LICENSE.txt", "AUTHORS"],
    include_package_data=True,
    zip_safe=False,
    install_requires=get_install_requires(),
)
