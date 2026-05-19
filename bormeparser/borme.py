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


import datetime
import logging
import os
import os.path

from .acto import ACTO
from .download import get_url_pdf
from .exceptions import BormeAnuncioNotFound
from .provincia import PROVINCIA
from .regex import is_acto_cargo
from .seccion import SECCION
from .utils import get_borme_xml_filepath

logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
logger.addHandler(ch)
logger.setLevel(logging.WARN)

# RAW_FILE_VERSION must be a positive integer string.
# Each new version adds 1 if the result file can change.
RAW_FILE_VERSION = "1"
# Thousands file version. It represents the file version part corresponding
# to this parser
TH_FILE_VERSION = "2"
# The file version depends on parser one and parser two. It is coded to avoid
# that the parser one changes and the parser two does not.
FILE_VERSION = "{}".format(int(RAW_FILE_VERSION) + 1000 * int(TH_FILE_VERSION))


class BormeActo:
    """Representa un Acto del Registro Mercantil. Instanciar BormeActoTexto
       o BormeActoCargo
    """
    def __init__(self, name, value):
        logger.debug("new %s(%s): %s", self.__class__.__name__, name, value)
        if name not in ACTO.ALL_KEYWORDS:
            logger.warning("Invalid acto found: %s", name)
        self._set_name(name)
        self._set_value(value)

    def _set_name(self, name):
        raise NotImplementedError

    def _set_value(self, value):
        raise NotImplementedError

    def __lt__(self, other):
        return self.name < other.name

    def __repr__(self):
        return "<{}({}): {}>".format(
            self.__class__.__name__, self.name, self.value
        )


class BormeActoTexto(BormeActo):
    """
    Representa un Acto del Registro Mercantil con atributo de cadena de texto.
    """

    def _set_name(self, name):
        if is_acto_cargo(name):
            raise ValueError(
                'No se puede BormeActoTexto con un acto de cargo: %s' % name)
        self.name = name

    def _set_value(self, value):
        if not (value is None or isinstance(value, str)):
            raise ValueError('value must be str or None: %s' % value)
        self.value = value


class BormeActoCargo(BormeActo):
    """Representa un Acto del Registro Mercantil con atributo de lista de
       cargos y nombres.
    """

    def _set_name(self, name):
        if not is_acto_cargo(name):
            raise ValueError(
                'No se puede BormeActoCargo sin un acto de cargo: %s' % name)
        self.name = name

    def _set_value(self, value):
        if not isinstance(value, dict):
            raise ValueError('value must be a dictionary: %s' % value)

        for k, v in value.items():
            if not isinstance(v, set):
                if isinstance(v, list):
                    value[k] = set(v)
                else:
                    raise ValueError('v must be a set: %s' % v)

        self.value = value

    @property
    def cargos(self):
        return self.value

    def get_nombres_cargos(self):
        return list(self.value.keys())


class BormeAnuncio:
    """Representa un anuncio con un conjunto de actos mercantiles
       (Constitucion, Nombramientos, ...)
    """

    def __init__(self, id, empresa, actos, extra, datos_registrales=None):
        logger.debug("new BormeAnuncio(%s) %s (%s)", id, empresa, extra)
        self.id = id
        self.empresa = empresa
        self.registro = extra["registro"]
        self.sucursal = extra["sucursal"]
        self.liquidacion = extra["liquidacion"]
        self.datos_registrales = datos_registrales or ""
        self._set_actos(actos)

    def _set_actos(self, actos):
        self.actos = []
        for acto in actos:
            for acto_nombre, valor in acto.items():
                if acto_nombre == 'Datos registrales':
                    self.datos_registrales = valor
                    continue

                if is_acto_cargo(acto_nombre):
                    a = BormeActoCargo(acto_nombre, valor)
                else:
                    a = BormeActoTexto(acto_nombre, valor)
                self.actos.append(a)

    def get_borme_actos(self):
        return self.actos

    def get_actos(self):
        for acto in self.actos:
            yield acto.name, acto.value

    def __repr__(self):
        return "<BormeAnuncio({}) {} (r:{}, s:{}, l:{}) ({})>".format(
                    self.id, self.empresa, self.registro, self.sucursal,
                    self.liquidacion, len(self.actos))



class Borme:

    def __init__(self, date, seccion, provincia, num, cve, anuncios=None,
                 filename=None, lazy=True):
        if isinstance(date, tuple):
            date = datetime.date(year=date[0], month=date[1], day=date[2])
        self.date = date
        self.seccion = seccion
        self.provincia = provincia
        self.num = num
        self.cve = cve
        self.filename = filename
        self._set_anuncios(anuncios)
        self._url = None
        if not lazy:
            self._set_url()

    @classmethod
    def from_file(cls, filename):
        # TODO: Create instance directly from filename
        raise NotImplementedError

    def _set_anuncios(self, anuncios):
        """
            anuncios: [BormeAnuncio]
        """
        self.anuncios = {}
        for anuncio in anuncios:
            self.anuncios[anuncio.id] = anuncio
        self.anuncios_rango = (min(self.anuncios.keys()),
                               max(self.anuncios.keys()))

    def _set_url(self):
        xml_path = get_borme_xml_filepath(self.date)
        if os.path.isfile(xml_path):
            self._url = get_url_pdf_from_xml(self.date, self.seccion,
                                             self.provincia, xml_path)
        else:
            self._url = get_url_pdf(self.date, self.seccion, self.provincia)

    @property
    def url(self):
        if not self._url:
            self._set_url()
        return self._url

    def get_anuncio(self, anuncio_id):
        try:
            return self.anuncios[anuncio_id]
        except KeyError:
            raise BormeAnuncioNotFound(
                'Anuncio {} not found in BORME {}'.format(
                    anuncio_id, str(self)))

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
            raise BormeAlreadyDownloadedException(filename)
        downloaded = download_pdf(self.date, filename, self.seccion,
                                  self.provincia)
        if downloaded:
            self.filename = filename
        return downloaded

    def _to_dict(self, set_url=True):
        from ._serialization import borme_to_dict
        return borme_to_dict(self, include_url=set_url)

    def to_json(self, path=None, overwrite=True, pretty=True, include_url=True):
        """Genera BORME-JSON. Ver :func:`bormeparser._serialization.borme_to_json`."""
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
                    self.date, self.seccion, self.provincia)
