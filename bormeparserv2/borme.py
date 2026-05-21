#!/usr/bin/env python
#
# borme.py -
# Copyright (C) 2015-2022 Pablo Castellano <pablo@anche.no>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import annotations

import datetime
import logging
import os
import os.path
import re
from typing import Iterable

from .acto import ACTO
from .download import download_pdf, get_url_pdf_from_xml
from .exceptions import BormeAlreadyDownloadedException, BormeAnuncioNotFound
from .provincia import Provincia
from .regex import is_acto_cargo
from .utils import get_borme_xml_filepath

# Reconoce el prefijo del nombre estándar publicado por el BOE:
# ``BORME-A-2015-27-10.pdf`` ⇒ sección ``A``.
_REGEX_BORME_FILENAME = re.compile(r"^BORME-([A-Z])-")

logger = logging.getLogger(__name__)

# RAW_FILE_VERSION must be a positive integer string.
# Each new version adds 1 if the result file can change.
RAW_FILE_VERSION = "1"
# Thousands file version. It represents the file version part corresponding
# to this parser
TH_FILE_VERSION = "2"
# The file version depends on parser one and parser two. It is coded to avoid
# that the parser one changes and the parser two does not.
FILE_VERSION = "{}".format(int(RAW_FILE_VERSION) + 1000 * int(TH_FILE_VERSION))


def _standard_pdf_url(date: datetime.date, cve: str, *, secure: bool = True) -> str:
    protocol = "https" if secure else "http"
    return (
        f"{protocol}://www.boe.es/borme/dias/"
        f"{date.year}/{date.month:02d}/{date.day:02d}/pdfs/{cve}.pdf"
    )


class BormeActo:
    """Acto del Registro Mercantil. Clase abstracta — instanciar
    :class:`BormeActoTexto` o :class:`BormeActoCargo`.
    """

    name: str
    value: object

    def __init__(self, name: str, value: object) -> None:
        logger.debug("new %s(%s): %s", self.__class__.__name__, name, value)
        if name not in ACTO.ALL_KEYWORDS:
            logger.warning("Invalid acto found: %s", name)
        self._set_name(name)
        self._set_value(value)

    def _set_name(self, name: str) -> None:
        raise NotImplementedError

    def _set_value(self, value: object) -> None:
        raise NotImplementedError

    def __lt__(self, other: "BormeActo") -> bool:
        return self.name < other.name

    def __repr__(self) -> str:
        return "<{}({}): {}>".format(self.__class__.__name__, self.name, self.value)


class BormeActoTexto(BormeActo):
    """Acto del Registro Mercantil cuyo valor es una cadena de texto libre."""

    value: str | None

    def _set_name(self, name: str) -> None:
        if is_acto_cargo(name):
            raise ValueError(
                "BormeActoTexto no admite un acto de cargo: {}".format(name)
            )
        self.name = name

    def _set_value(self, value) -> None:
        if not (value is None or isinstance(value, str)):
            raise ValueError("value must be str or None: {!r}".format(value))
        self.value = value


class BormeActoCargo(BormeActo):
    """Acto del Registro Mercantil que asocia cargos a conjuntos de nombres."""

    value: dict[str, set[str]]

    def _set_name(self, name: str) -> None:
        if not is_acto_cargo(name):
            raise ValueError(
                "BormeActoCargo requiere un acto de cargo: {}".format(name)
            )
        self.name = name

    def _set_value(self, value) -> None:
        if not isinstance(value, dict):
            raise ValueError("value must be a dictionary: {!r}".format(value))

        for cargo, nombres in value.items():
            if isinstance(nombres, set):
                continue
            if isinstance(nombres, list):
                value[cargo] = set(nombres)
            else:
                raise ValueError(
                    "value[{!r}] must be a set, got {!r}".format(cargo, nombres)
                )

        self.value = value

    @property
    def cargos(self) -> dict[str, set[str]]:
        return self.value

    def get_nombres_cargos(self) -> list[str]:
        return list(self.value.keys())


class BormeAnuncio:
    """Anuncio del BORME con su conjunto de actos mercantiles
    (Constitución, Nombramientos, …)."""

    actos: list[BormeActo]

    def __init__(
        self,
        id: int,
        empresa: str,
        actos: Iterable[dict],
        extra: dict,
        datos_registrales: str | None = None,
    ) -> None:
        logger.debug("new BormeAnuncio(%s) %s (%s)", id, empresa, extra)
        self.id = id
        self.empresa = empresa
        self.registro = extra["registro"]
        self.sucursal = extra["sucursal"]
        self.liquidacion = extra["liquidacion"]
        self.datos_registrales = datos_registrales or ""
        self._set_actos(actos)

    def _set_actos(self, actos: Iterable[dict]) -> None:
        self.actos = []
        for acto in actos:
            for acto_nombre, valor in acto.items():
                if acto_nombre == "Datos registrales":
                    self.datos_registrales = valor
                    continue
                if is_acto_cargo(acto_nombre):
                    self.actos.append(BormeActoCargo(acto_nombre, valor))
                else:
                    self.actos.append(BormeActoTexto(acto_nombre, valor))

    def get_borme_actos(self) -> list[BormeActo]:
        return self.actos

    def get_actos(self):
        for acto in self.actos:
            yield acto.name, acto.value

    def __repr__(self) -> str:
        return "<BormeAnuncio({}) {} (r:{}, s:{}, l:{}) ({})>".format(
            self.id,
            self.empresa,
            self.registro,
            self.sucursal,
            self.liquidacion,
            len(self.actos),
        )


class Borme:
    """Una publicación BORME para una (fecha, sección, provincia) concreta."""

    anuncios: dict[int, BormeAnuncio]
    anuncios_rango: tuple[int, int]

    def __init__(
        self,
        date: datetime.date | tuple[int, int, int],
        seccion: str,
        provincia: Provincia,
        num: int,
        cve: str,
        anuncios: Iterable[BormeAnuncio] | None = None,
        filename: str | None = None,
        lazy: bool = True,
    ) -> None:
        if isinstance(date, tuple):
            date = datetime.date(year=date[0], month=date[1], day=date[2])
        self.date = date
        self.seccion = seccion
        self.provincia = provincia
        self.num = num
        self.cve = cve
        self.filename = filename
        self._set_anuncios(anuncios)
        self._url: str | None = None
        if not lazy:
            self._set_url()

    @classmethod
    def from_file(cls, filename: str) -> "Borme":
        """Construye un :class:`Borme` a partir de un PDF/XML del BORME.

        La sección se deduce del nombre del fichero
        (``BORME-A-…``, ``BORME-B-…``). Para sección C el backend
        actual devuelve un diccionario en lugar de un :class:`Borme`,
        de modo que esa entrada debe parsearse por medios distintos.
        """
        from .parser import DEFAULT_PARSER, parse

        basename = os.path.basename(filename)
        match = _REGEX_BORME_FILENAME.match(basename)
        if match is None:
            raise ValueError(
                f"Nombre de fichero BORME no reconocido: {basename!r}. "
                "Se espera 'BORME-<seccion>-...'"
            )
        seccion = match.group(1)
        if seccion not in DEFAULT_PARSER:
            raise ValueError(
                f"Sección {seccion!r} no soportada por Borme.from_file. "
                f"Secciones disponibles: {sorted(DEFAULT_PARSER)}"
            )
        result = parse(filename, seccion)
        if not isinstance(result, cls):
            raise TypeError(
                f"El backend de sección {seccion!r} devolvió "
                f"{type(result).__name__} en lugar de Borme; "
                "no representable como un único Borme."
            )
        return result

    def _set_anuncios(self, anuncios: Iterable[BormeAnuncio] | None) -> None:
        self.anuncios = {a.id: a for a in (anuncios or [])}
        ids = self.anuncios.keys()
        self.anuncios_rango = (min(ids), max(ids)) if ids else (0, 0)

    def _set_url(self):
        xml_path = get_borme_xml_filepath(self.date)
        if os.path.isfile(xml_path):
            self._url = get_url_pdf_from_xml(
                self.date, self.seccion, self.provincia, xml_path
            )
        else:
            self._url = _standard_pdf_url(self.date, self.cve)

    @property
    def url(self):
        if not self._url:
            self._set_url()
        return self._url

    def get_anuncio(self, anuncio_id):
        try:
            return self.anuncios[anuncio_id]
        except KeyError as exc:
            raise BormeAnuncioNotFound(
                "Anuncio {} not found in BORME {}".format(anuncio_id, str(self))
            ) from exc

    def get_anuncios_ids(self):
        """
        [BormeAnuncio]
        """
        return sorted(self.anuncios.keys())

    def get_anuncios(self):
        """
        [BormeAnuncio]
        """
        return list(self.anuncios.values())

    def download(self, filename):
        if self.filename is not None:
            # La excepción debe identificar el fichero ya existente, no
            # el que se ha intentado escribir ahora.
            raise BormeAlreadyDownloadedException(self.filename)
        downloaded = download_pdf(self.date, filename, self.seccion, self.provincia)
        if downloaded:
            self.filename = filename
        return downloaded

    def _to_dict(self, set_url=True):
        from ._serialization import borme_to_dict

        return borme_to_dict(self, include_url=set_url)

    def to_json(self, path=None, overwrite=True, pretty=True, include_url=True):
        """Genera BORME-JSON. Ver :func:`bormeparserv2._serialization.borme_to_json`."""
        from ._serialization import borme_to_json

        return borme_to_json(
            self,
            path,
            overwrite=overwrite,
            pretty=pretty,
            include_url=include_url,
        )

    @classmethod
    def from_json(cls, filename):
        """Crea una instancia Borme a partir de un BORME-JSON.

        El parámetro ``filename`` puede ser la ruta a un archivo o un
        objeto file-like ya abierto.
        """
        from ._serialization import borme_from_json

        return borme_from_json(filename)

    def __lt__(self, other):
        return self.anuncios_rango[1] < other.anuncios_rango[0]

    def __repr__(self):
        return "<Borme({}) seccion:{} provincia:{}>".format(
            self.date, self.seccion, self.provincia
        )
