#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# seccion.py -
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


class SECCION:
    A = "A"
    B = "B"
    C = "C"

    # Limitación conocida: la sección C llega comprimida en el PDF de
    # sumario y no se detecta desde from_borme — se identifica por el
    # CVE (BORME-C-…) en otra capa.
    @staticmethod
    def from_borme(seccion, subseccion):
        if seccion == "SECCIÓN PRIMERA":
            if subseccion == "Actos inscritos":
                return SECCION.A
            if subseccion == "Otros actos publicados en el Registro Mercantil":
                return SECCION.B
        raise ValueError(f"InvalidSeccion: {seccion!r} {subseccion!r}")


class SUBSECCION:
    # Actos inscritos
    ACTOS_INSCRITOS = "A"
    # Otros actos publicados en el Registro Mercantil
    OTROS_ACTOS = "B"
