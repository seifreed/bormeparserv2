#!/usr/bin/env python
#
# test_utils.py -
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
import unittest

from bormeparser.clean import clean_empresa
from bormeparser.provincia import PROVINCIA
from bormeparser.utils import get_borme_website
from bormeparser.utils import acto_to_attr
from bormeparser.seccion import SECCION


class BormeparserUtilsTestCase(unittest.TestCase):

    def test_get_borme_website(self):
        date = datetime.date(2016, 4, 21)
        url = get_borme_website(date, SECCION.A)
        self.assertEqual(url, "https://www.boe.es/borme/dias/2016/04/21/index.php?s=A")
        url = get_borme_website(date, SECCION.C)
        self.assertEqual(url, "https://www.boe.es/borme/dias/2016/04/21/index.php?s=C")

    def test_acto_to_attr(self):
        attr1 = acto_to_attr("Nombramientos")
        attr2 = acto_to_attr("Ceses/Dimisiones")
        attr3 = acto_to_attr("Fusión por absorción")
        self.assertEqual(attr1, "nombramientos")
        self.assertEqual(attr2, "ceses_dimisiones")
        self.assertEqual(attr3, "fusion_absorcion")

    def test_acto_to_attr_preserves_digits(self):
        """Regresión: antes ``re.sub('[^A-Za-z_]+', '', attr)`` borraba
        los dígitos, colapsando dos actos distintos (``Adaptación Ley
        2/95`` y ``Adaptación Ley 44/2015``) al mismo slug."""
        self.assertEqual(acto_to_attr("Adaptación Ley 2/95"), "adaptacion_ley_2_95")
        self.assertEqual(
            acto_to_attr("Adaptación Ley 44/2015"), "adaptacion_ley_44_2015"
        )

    def test_acto_to_attr_collapses_underscores(self):
        self.assertEqual(
            acto_to_attr("Articulo 378.5 del Reglamento del Registro Mercantil"),
            "articulo_378_5_reglamento_registro_mercantil",
        )


class ProvinciaEqTestCase(unittest.TestCase):
    """Regresión: la comparación con cadenas debe ser insensible a
    mayúsculas Y a acentos (antes solo a mayúsculas, lo que hacía que
    ``PROVINCIA.CADIZ == "CADIZ"`` devolviera ``False``)."""

    def test_eq_accents(self):
        self.assertTrue(PROVINCIA.CADIZ == "Cádiz")
        self.assertTrue(PROVINCIA.CADIZ == "Cadiz")
        self.assertTrue(PROVINCIA.CADIZ == "CADIZ")
        self.assertTrue(PROVINCIA.CADIZ == "cadiz")
        self.assertTrue(PROVINCIA.LEON == "León")
        self.assertTrue(PROVINCIA.LEON == "LEON")

    def test_eq_distinct(self):
        self.assertFalse(PROVINCIA.MADRID == "Cádiz")
        self.assertFalse(PROVINCIA.CADIZ == "Sevilla")

    def test_eq_other_type(self):
        self.assertFalse(PROVINCIA.MADRID == 28)
        # Comparación con None: usamos __eq__ directo para evitar el
        # rewrite que hace pytest/ruff y comprobar el branch falso final.
        self.assertFalse(PROVINCIA.MADRID.__eq__(None))


class BormeToJsonExtensionTestCase(unittest.TestCase):
    """Regresión: ``borme_to_json`` derivaba el nombre del JSON con
    ``re.sub(r"(\\.pdf)$", ...)`` sensible a mayúsculas. Un PDF
    renombrado como ``BORME-A-2015-27-10.PDF`` salía como
    ``BORME-A-2015-27-10.PDF`` (sin extensión .json)."""

    def setUp(self):
        import os

        self._cwd = os.getcwd()

    def tearDown(self):
        import os

        os.chdir(self._cwd)

    def _run_to_json(self, pdf_filename):
        import os
        import tempfile
        from bormeparser.borme import Borme
        from bormeparser.provincia import PROVINCIA
        from bormeparser.seccion import SECCION

        borme = Borme(
            datetime.date(2015, 2, 10),
            SECCION.A,
            PROVINCIA.CACERES,
            27,
            "BORME-A-2015-27-10",
            anuncios=[],
            filename=pdf_filename,
        )
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            return borme.to_json(include_url=False)

    def test_lowercase_pdf(self):
        self.assertEqual(
            self._run_to_json("BORME-A-2015-27-10.pdf"), "BORME-A-2015-27-10.json"
        )

    def test_uppercase_pdf(self):
        self.assertEqual(
            self._run_to_json("BORME-A-2015-27-10.PDF"), "BORME-A-2015-27-10.json"
        )


class CleanEmpresaUTETestCase(unittest.TestCase):
    """Regresión: ``UNION TEMPORAL DE EMPRESAS [LEY 18 1982 …]`` se
    abreviaba a sí misma (no estaba en SIGLAS), produciendo nombres
    de empresa larguísimos en el JSON resultante."""

    def test_full_law_reference(self):
        cleaned = clean_empresa(
            "EJEMPLO UNION TEMPORAL DE EMPRESAS LEY 18 1982 DE 26 DE MAYO"
        )
        self.assertEqual(cleaned, "EJEMPLO UTE")

    def test_short_form(self):
        self.assertEqual(
            clean_empresa("EJEMPLO UNION TEMPORAL DE EMPRESAS"), "EJEMPLO UTE"
        )


if __name__ == "__main__":
    unittest.main()
