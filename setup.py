#!/usr/bin/env python

from setuptools import find_packages, setup

VERSION = "0.5.1.dev0"


def get_install_requires() -> list[str]:
    requirements: list[str] = []
    with open("requirements.txt", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip()
            if not line or line.startswith(("#", "http", "git")) or line == "-r base.txt":
                continue
            requirements.append(line)
    return requirements


setup(
    name="bormeparser",
    packages=find_packages(exclude=["*.tests"]),
    package_data={"bormeparser": ["examples/*"]},
    version=VERSION,
    description="bormeparser is a Python library for parsing BORME files",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Pablo Castellano",
    author_email="pablo@anche.no",
    url="https://github.com/PabloCastellano/bormeparser/",
    download_url="https://github.com/PabloCastellano/bormeparser/archive/master.zip",
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
    test_suite="bormeparser.tests",
)
