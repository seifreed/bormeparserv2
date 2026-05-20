#!/usr/bin/env python

from setuptools import find_packages, setup

VERSION = "0.5.1.dev0"


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
    version=VERSION,
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
    license="GPLv3+",
    include_package_data=True,
    zip_safe=False,
    install_requires=get_install_requires(),
)
