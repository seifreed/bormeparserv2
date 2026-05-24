#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2015-2022 Pablo Castellano <pablo@anche.no>
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# bormeparserv2.backends.base - Clases base para los backends de parseo.
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

import os

from bormeparserv2 import PROVINCIA, SECCION
from bormeparserv2.borme import Borme, BormeAnuncio
from bormeparserv2.regex import regex_fecha


class _FileBackend:
    """Base común: valida que ``filename`` existe y lo deja guardado."""

    def __init__(self, filename):
        if not os.path.isfile(filename):
            raise FileNotFoundError(filename)
        self.filename = filename


class BormeAParserBackend(_FileBackend):
    """Backend para BORME secciones A y B (actos inscritos en PDF)."""

    def parse(self):
        raw = self._parse()
        anuncios = [
            BormeAnuncio(
                id_anuncio,
                data["Empresa"],
                data["Actos"],
                data["Extra"],
            )
            for id_anuncio, data in raw.items()
            if isinstance(id_anuncio, int)
        ]
        fecha = regex_fecha(raw["borme_fecha"])
        seccion = SECCION.from_borme(raw["borme_seccion"], raw["borme_subseccion"])
        provincia = PROVINCIA.from_title(raw["borme_provincia"])
        return Borme(
            fecha,
            seccion,
            provincia,
            raw["borme_num"],
            raw["borme_cve"],
            anuncios,
            filename=self.filename,
        )

    def _parse(self):
        """Devuelve un diccionario plano con la información extraída del PDF.

        Cada clave entera corresponde al ``id`` de un anuncio y mapea a
        ``{'Empresa': str, 'Actos': list, 'Extra': dict}``. Las claves
        de cadena (``borme_fecha``, ``borme_num``, …) contienen los
        metadatos del boletín.
        """
        raise NotImplementedError


class BormeCParserBackend(_FileBackend):
    """Backend para BORME sección C (anuncios y avisos legales).

    ``parse()`` devuelve un diccionario con los campos del anuncio.
    El formato esperado es::

        {
            'id_anuncio': 'A110044738',
            'numero_anuncio': '44738',
            'cve': 'BORME-C-2011-20488',
            'departamento': 'CONVOCATORIAS DE JUNTAS',
            'empresa': 'DESARROLLOS ESPECIALES DE SISTEMAS DE ANCLAJE, S.A.',
            'diario_numero': '101',
            'publication_date': datetime.date(2011, 5, 27),
            'cifs': {'B31136005', 'A58348038', 'A31017494', 'A31067218'},
            'pagina_inicial': '22110',
            'pagina_final': '22116',
            'texto': '...'
        }
    """

    def parse(self):
        raise NotImplementedError
