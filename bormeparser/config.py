#!/usr/bin/env python
#
# bormeparser.config - Configuración del proyecto (lectura perezosa).
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Resuelve los parámetros de configuración del paquete.

La configuración se lee la primera vez que se solicita (no al importar),
así un test o un servicio que nunca toque disco no necesita un
``~/.bormecfg``. El uso típico es::

    from bormeparser.config import get_config
    root = get_config()["borme_root"]

El nombre histórico ``bormeparser.CONFIG`` sigue funcionando: se resuelve
de forma diferida vía ``__getattr__`` del módulo.
"""

import configparser
import os

CONFIG_FILE = os.path.expanduser("~/.bormecfg")
DEFAULTS = {
    "borme_root": os.path.expanduser("~/.bormes"),
}

_cached_config = None


def get_config():
    """Devuelve la configuración efectiva (defaults + ``~/.bormecfg``).

    Se cachea tras la primera lectura. Llamar a :func:`reload_config`
    para forzar una nueva lectura (útil en tests).
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    merged = dict(DEFAULTS)
    if os.path.isfile(CONFIG_FILE):
        parser = configparser.ConfigParser()
        parser.read(CONFIG_FILE)
        # El fichero histórico usa la sección [general]; si no está,
        # caer en los defaults antes que reventar con KeyError.
        if parser.has_section("general"):
            merged.update(parser["general"])
    _cached_config = merged
    return _cached_config


def reload_config():
    """Invalida el cache y vuelve a leer ``~/.bormecfg`` en la próxima llamada."""
    global _cached_config
    _cached_config = None


def __getattr__(name):
    # Backwards compatibility: ``from bormeparser.config import CONFIG``
    # sigue funcionando, pero el fichero solo se lee si CONFIG se usa.
    if name == "CONFIG":
        return get_config()
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
