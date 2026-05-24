#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# provincia.py -
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

from bormeparserv2.utils import remove_accents


class Provincia:
    def __init__(self, name, code):
        self.name = name
        self._code = code

    @property
    def code(self):
        return f"{self._code:02d}"

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"{self.__class__}: {self.name}"

    def __lt__(self, other):
        return self.name < other.name

    def __eq__(self, other):
        """Hace posible comparar la clase con una cadena (nombre de provincia).
        La comparación con cadenas es insensible a mayúsculas y acentos
        para tolerar variantes como ``CADIZ`` ↔ ``Cádiz``."""
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        elif isinstance(other, str):
            return remove_accents(self.name).upper() == remove_accents(other).upper()
        else:
            return False

    def __hash__(self):
        return hash((self.name, self._code))


class PROVINCIA:
    ALAVA = Provincia("Álava", 1)
    ARABA = ALAVA
    ALBACETE = Provincia("Albacete", 2)
    ALICANTE = Provincia("Alicante", 3)
    ALMERIA = Provincia("Almería", 4)
    AVILA = Provincia("Ávila", 5)
    BADAJOZ = Provincia("Badajoz", 6)
    ISLAS_BALEARES = Provincia("Islas Baleares", 7)
    ILLES_BALEARS = ISLAS_BALEARES
    BARCELONA = Provincia("Barcelona", 8)
    BURGOS = Provincia("Burgos", 9)
    CACERES = Provincia("Cáceres", 10)
    CADIZ = Provincia("Cádiz", 11)
    CASTELLON = Provincia("Castellón", 12)
    CIUDAD_REAL = Provincia("Ciudad Real", 13)
    CORDOBA = Provincia("Córdoba", 14)
    LA_CORUNA = Provincia("La Coruña", 15)
    A_CORUNA = LA_CORUNA
    CUENCA = Provincia("Cuenca", 16)
    GERONA = Provincia("Gerona", 17)
    GIRONA = GERONA
    GRANADA = Provincia("Granada", 18)
    GUADALAJARA = Provincia("Guadalajara", 19)
    GUIPUZCOA = Provincia("Guipúzcoa", 20)
    GIPUZKOA = GUIPUZCOA
    HUELVA = Provincia("Huelva", 21)
    HUESCA = Provincia("Huesca", 22)
    JAEN = Provincia("Jaén", 23)
    LEON = Provincia("León", 24)
    LERIDA = Provincia("Lérida", 25)
    LLEIDA = LERIDA
    LA_RIOJA = Provincia("La Rioja", 26)
    LUGO = Provincia("Lugo", 27)
    MADRID = Provincia("Madrid", 28)
    MALAGA = Provincia("Málaga", 29)
    MURCIA = Provincia("Murcia", 30)
    NAVARRA = Provincia("Navarra", 31)
    ORENSE = Provincia("Orense", 32)
    OURENSE = ORENSE
    ASTURIAS = Provincia("Asturias", 33)
    PALENCIA = Provincia("Palencia", 34)
    LAS_PALMAS = Provincia("Las Palmas", 35)
    PONTEVEDRA = Provincia("Pontevedra", 36)
    SALAMANCA = Provincia("Salamanca", 37)
    SANTA_CRUZ_DE_TENERIFE = Provincia("Santa Cruz de Tenerife", 38)
    CANTABRIA = Provincia("Cantabria", 39)
    SEGOVIA = Provincia("Segovia", 40)
    SEVILLA = Provincia("Sevilla", 41)
    SORIA = Provincia("Soria", 42)
    TARRAGONA = Provincia("Tarragona", 43)
    TERUEL = Provincia("Teruel", 44)
    TOLEDO = Provincia("Toledo", 45)
    VALENCIA = Provincia("Valencia", 46)
    VALLADOLID = Provincia("Valladolid", 47)
    VIZCAYA = Provincia("Vizcaya", 48)
    BIZKAIA = VIZCAYA
    ZAMORA = Provincia("Zamora", 49)
    ZARAGOZA = Provincia("Zaragoza", 50)
    CEUTA = Provincia("Ceuta", 51)
    MELILLA = Provincia("Melilla", 52)

    @staticmethod
    def from_title(title):
        for candidate in str(title).split("/"):
            normalized = remove_accents(candidate).upper().replace(" ", "_")
            prov = getattr(PROVINCIA, normalized, None)
            if isinstance(prov, Provincia):
                return prov
        raise ValueError(f"InvalidProvince: {title}")

    @staticmethod
    def coerce(value):
        """Devuelve una :class:`Provincia` a partir de ``value``.

        Acepta tanto un objeto :class:`Provincia` (passthrough) como
        cualquier forma textual que aparezca en el ecosistema BORME:

        - Atributo ASCII de :class:`PROVINCIA` (``"CACERES"``,
          ``"MADRID"``), tal como lo expone ``ALL_PROVINCIAS`` a
          ``argparse choices``.
        - Mismo nombre en minúsculas o con acentos.
        - Forma acentuada en mayúsculas que emite el sumario
          (``"CÁCERES"``, ``"VALENCIA/VALÈNCIA"``).

        Lanza ``ValueError`` si el valor no corresponde a ninguna
        provincia conocida.
        """
        if isinstance(value, Provincia):
            return value
        if not isinstance(value, str):
            raise TypeError(
                f"provincia must be Provincia or str, got {type(value).__name__}"
            )

        def _attr_lookup(text):
            cand = remove_accents(text).upper().replace(" ", "_")
            prov = getattr(PROVINCIA, cand, None)
            return prov if isinstance(prov, Provincia) else None

        # 1) Coincidencia directa con un atributo de PROVINCIA.
        if (prov := _attr_lookup(value)) is not None:
            return prov
        # 2) Forma bilingüe del sumario (``"VALENCIA/VALÈNCIA"``,
        # ``"ARABA/ÁLAVA"``): probar cada lado del "/".
        if "/" in value:
            for part in value.split("/"):
                if (prov := _attr_lookup(part)) is not None:
                    return prov
        # 3) Coincidencia por el nombre legible (``"Cáceres"``, etc.).
        try:
            return PROVINCIA.from_title(value)
        except ValueError:
            pass
        raise ValueError(f"Unknown provincia: {value!r}")


ALL_PROVINCIAS = list(
    filter(
        lambda x: not x.startswith("__") and x not in ("from_title", "coerce"),
        vars(PROVINCIA),
    )
)
