#!/usr/bin/env python
#
# parser.py - Punto de entrada que enruta a un backend según la sección.
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

import importlib
import os

# Backends registrados por código de sección. Cada entrada es
# ``(módulo, nombre de la clase)`` y se importa de forma perezosa para
# evitar arrastrar dependencias opcionales (lxml, pypdf) cuando no se
# usan.
DEFAULT_PARSER = {
    "A": ("bormeparser.backends.pypdf.parser", "PyPDFParser"),
    "C": ("bormeparser.backends.seccion_c.lxml.parser", "LxmlBormeCParser"),
}


def parse(filename, seccion, **backend_kwargs):
    """Parsea el fichero local del BORME indicado y devuelve el resultado.

    ``filename`` debe ser una ruta a un archivo existente. El backend se elige
    a partir de ``seccion`` consultando :data:`DEFAULT_PARSER`. Los
    ``backend_kwargs`` se reenvían al constructor del backend (por ejemplo
    ``sanitize=True`` para :class:`PyPDFParser`).
    """
    try:
        module_path, class_name = DEFAULT_PARSER[seccion]
    except KeyError as exc:
        raise ValueError(
            "No backend registered for seccion={!r}".format(seccion)
        ) from exc

    if not os.path.isfile(filename):
        raise FileNotFoundError(filename)

    module = importlib.import_module(module_path)
    backend_cls = getattr(module, class_name)
    return backend_cls(filename, **backend_kwargs).parse()
