#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# bormeparserv2._serialization - (Des)serialización JSON del modelo Borme.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Conversión entre objetos :class:`~bormeparserv2.borme.Borme` y JSON.

La (de)serialización vive aparte del dominio para que ``borme.py`` no
tenga que conocer formatos persistentes ni el sistema de ficheros.
"""

import datetime
import io
import json
import logging
import os
import re

from .provincia import PROVINCIA, Provincia
from ._security import safe_join

logger = logging.getLogger(__name__)


def _json_default(obj):
    """Serializa tipos no nativos: ``set`` como lista ordenada,
    :class:`Provincia` como su representación canónica."""
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, Provincia):
        return str(obj)
    raise TypeError(type(obj))


def borme_to_dict(borme, *, include_url=True):
    """Construye un ``dict`` JSON-serializable a partir de un :class:`Borme`."""
    # Import diferido para evitar ciclo borme ⇄ _serialization.
    from .borme import FILE_VERSION, RAW_FILE_VERSION

    rango_from, rango_to = borme.anuncios_rango
    doc = {
        "cve": borme.cve,
        "date": borme.date.isoformat(),
        "seccion": borme.seccion,
        "provincia": borme.provincia,
        "num": borme.num,
        "from_anuncio": rango_from,
        "to_anuncio": rango_to,
        "anuncios": {},
    }

    for anuncio in borme.anuncios.values():
        anuncio_doc = {
            "empresa": anuncio.empresa,
            "registro": anuncio.registro,
            "sucursal": anuncio.sucursal,
            "liquidacion": anuncio.liquidacion,
            "datos registrales": anuncio.datos_registrales,
            "actos": [{acto.name: acto.value} for acto in anuncio.actos],
        }
        anuncio_doc["num_actos"] = len(anuncio_doc["actos"])
        doc["anuncios"][anuncio.id] = anuncio_doc

    doc["num_anuncios"] = len(doc["anuncios"])
    doc["raw_version"] = RAW_FILE_VERSION
    doc["version"] = FILE_VERSION

    if include_url:
        # Property may hit the network the first time; el caller debe
        # asumirlo si pide include_url=True.
        doc["url"] = borme.url

    logger.debug(doc)
    return doc


def borme_to_json(borme, path=None, *, overwrite=True, pretty=True, include_url=True):
    """Persiste ``borme`` como JSON en ``path``.

    Args:
        path: ruta a un fichero o directorio. Si es ``None`` se infiere
            del ``filename`` original del PDF reemplazando la extensión.
        overwrite: sobreescribe si el fichero ya existe.
        pretty: indentación de 2 espacios para legibilidad.
        include_url: incluye la URL oficial en el documento (requiere red
            la primera vez si ``borme`` aún no la conocía).

    Returns:
        La ruta donde se escribió, o ``False`` si el fichero existía y
        ``overwrite`` era ``False``.
    """
    if path is None:
        if not borme.filename:
            raise ValueError("path is required when borme.filename is unset")
        # El BOE publica los PDFs con extensión en minúscula, pero los
        # mirrors locales y los renombrados manuales pueden conservar
        # ``.PDF``; la sustitución debe ser insensible a mayúsculas para
        # no terminar serializando a un fichero ``foo.PDF``.
        path = re.sub(
            r"\.pdf$", ".json", os.path.basename(borme.filename), flags=re.IGNORECASE
        )

    if os.path.isfile(path) and not overwrite:
        return False
    if os.path.isdir(path):
        path = safe_join(path, borme.cve + ".json")

    doc = borme_to_dict(borme, include_url=include_url)
    indent = 2 if pretty else None
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(doc, fp, default=_json_default, indent=indent, sort_keys=True)
    return path


def borme_from_json(source):
    """Reconstruye un :class:`Borme` desde un fichero o handle JSON."""
    # Import diferido para evitar ciclo.
    from .borme import Borme, BormeAnuncio, FILE_VERSION

    if isinstance(source, io.IOBase):
        data = json.loads(source.read())
        # Buffers en memoria (io.StringIO, io.BytesIO) no exponen ``name``;
        # un Borme reconstruido desde ellos simplemente no tiene ``filename``.
        filename = getattr(source, "name", None)
    else:
        with open(source, encoding="utf-8") as fp:
            data = json.load(fp)
        filename = source

    # FILE_VERSION es un entero codificado como cadena ("2001", "10001",
    # ...). Comparar como cadena fallaría con orden lexicográfico
    # ("10001" < "2001"); fuerza la comparación numérica.
    if int(data["version"]) < int(FILE_VERSION):
        logger.warning("This JSON was generated with an older version of bormeparserv2")
        logger.warning(
            "Current version is %s, file version is %s",
            FILE_VERSION,
            data["version"],
        )

    cve = data["cve"]
    date = datetime.datetime.strptime(data["date"], "%Y-%m-%d").date()
    seccion = data["seccion"]
    provincia = PROVINCIA.from_title(data["provincia"].upper())
    num = data["num"]
    url = data.get("url")

    anuncios = []
    for id_anuncio, payload in sorted(data["anuncios"].items(), key=lambda t: t[0]):
        extra = {
            "liquidacion": payload["liquidacion"],
            "sucursal": payload["sucursal"],
            "registro": payload["registro"],
        }
        anuncios.append(
            BormeAnuncio(
                int(id_anuncio),
                payload["empresa"],
                payload["actos"],
                extra,
                payload["datos registrales"],
            )
        )

    borme = Borme(date, seccion, provincia, num, cve, anuncios, filename)
    borme._url = url
    return borme
