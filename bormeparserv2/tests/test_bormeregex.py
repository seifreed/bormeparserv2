#!/usr/bin/env python
#
# test_bormeregexp.py -
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

import unittest

from bormeparserv2.regex import regex_cargos, regex_empresa, regex_bold_acto, is_company
from bormeparserv2.regex import (
    is_acto_cargo_entrante,
    regex_argcolon,
    regex_empresa_tipo,
    regex_noarg,
    borme_c_separa_empresas_titulo,
)


class BormeparserIsCompanyTestCase(unittest.TestCase):

    def test_is_company(self):
        # Company names
        self.assertTrue(is_company("PATATAS SL"))
        self.assertTrue(is_company("HAMBURGUESAS AIE"))
        self.assertTrue(is_company("ZANAHORIAS SA"))
        self.assertTrue(is_company("COA-COA BARBACOA SRL"))
        self.assertTrue(is_company("FRALVAL S.L"))
        self.assertTrue(is_company("HUPRECESA SA EN LIQUIDACION"))
        self.assertTrue(is_company("CARGLASS B.V. SUCURSAL EN ESPAÑA"))
        self.assertTrue(is_company("SOCIEDAD COOPERATIVA ANDALUZA BEDMARENSE"))

        # Person names
        self.assertFalse(is_company("JOHN DOE"))


class BormeparserRegexEmpresaTestCase(unittest.TestCase):
    acto1 = "57344 - ALDARA CATERING SL."
    acto2 = "57344 - ALDARA CATERING SL"
    acto3 = "473700 - SA COVA PLAÇA MAJOR SL(R.M. PALMA DE MALLORCA)"
    acto4 = "111141 - CAMAPLAS, S.L.(R.M. LAS PALMAS)."
    acto5 = "114033 - PARTEI VALENCIA SOCIEDAD LIMITADA EN LIQUIDACION"
    acto6 = "106606 - PLANTRONICS BV SUCURSAL EN ESPAÑA."
    empresa1 = "ALDARA CATERING SL"
    empresa2 = "ALDARA CATERING"

    def test_regex_empresa(self):
        acto_id, empresa, extra = regex_empresa(self.acto1)
        self.assertEqual(acto_id, 57344)
        self.assertEqual(empresa, "ALDARA CATERING SL")
        self.assertEqual(extra["registro"], "")
        self.assertEqual(extra["liquidacion"], False)
        self.assertEqual(extra["sucursal"], False)

        acto_id, empresa, extra = regex_empresa(self.acto2)
        self.assertEqual(acto_id, 57344)
        self.assertEqual(empresa, "ALDARA CATERING SL")
        self.assertEqual(extra["registro"], "")
        self.assertEqual(extra["liquidacion"], False)
        self.assertEqual(extra["sucursal"], False)

        acto_id, empresa, extra = regex_empresa(self.acto3)
        self.assertEqual(acto_id, 473700)
        self.assertEqual(empresa, "SA COVA PLAÇA MAJOR SL")
        self.assertEqual(extra["registro"], "Palma de Mallorca")
        self.assertEqual(extra["liquidacion"], False)
        self.assertEqual(extra["sucursal"], False)

        acto_id, empresa, extra = regex_empresa(self.acto4)
        self.assertEqual(acto_id, 111141)
        self.assertEqual(empresa, "CAMAPLAS, SL")
        self.assertEqual(extra["registro"], "Las Palmas (Canarias)")
        self.assertEqual(extra["liquidacion"], False)
        self.assertEqual(extra["sucursal"], False)

        acto_id, empresa, extra = regex_empresa(self.acto5)
        self.assertEqual(acto_id, 114033)
        self.assertEqual(empresa, "PARTEI VALENCIA SL")
        self.assertEqual(extra["registro"], "")
        self.assertEqual(extra["liquidacion"], True)
        self.assertEqual(extra["sucursal"], False)

        acto_id, empresa, extra = regex_empresa(self.acto6)
        self.assertEqual(acto_id, 106606)
        self.assertEqual(empresa, "PLANTRONICS BV")
        self.assertEqual(extra["registro"], "")
        self.assertEqual(extra["liquidacion"], False)
        self.assertEqual(extra["sucursal"], True)

    def test_regex_empresa_tipo(self):
        empresa, tipo = regex_empresa_tipo(self.empresa1)
        self.assertEqual(empresa, "ALDARA CATERING")
        self.assertEqual(tipo, "SL")

        empresa, tipo = regex_empresa_tipo(self.empresa2)
        self.assertEqual(empresa, "ALDARA CATERING")
        self.assertEqual(tipo, "")


class BormeparserRegexCargosTestCase(unittest.TestCase):
    nombramientos1 = "Adm. Solid.: RAMA SANCHEZ JOSE PEDRO;RAMA SANCHEZ JAVIER JORGE."
    nombramientos2 = "Auditor: ACME AUDITORES SL. Aud.Supl.: MACIAS MUÑOZ FELIPE JOSE."
    nombramientos3 = (
        "Auditor: A.T.A AUDITORES SL. Aud.Supl.: CUEVAS MUÑOZ SILVIA MARIA."
    )
    nombramientos4 = "Adm. Solid.: ASDFG INVERSIONES S.L. Adm. Mancom.: ASDFG INVERSIONES S.L.;PEDRO PEREZ"
    nombramientos5 = "Apoderado: CASER PENSIONES ENTIDAD GESTORA DE FONDOS DE PENSI."

    ceses1 = "Adm. Mancom.: PEREZ;HILARIO"
    ceses2 = "Auditor: A.T.A AUDITORES SL. Adm. Mancom.: PEREZ;HILARIO"
    ceses3 = "Consejero: C1 C. Consejero: C2 -A- Secretario: C2 -B- Vicesecret.: C4 -D-"

    def test_regex_nombramientos(self):
        cargos1 = regex_cargos(self.nombramientos1)
        self.assertEqual(
            cargos1,
            {"Adm. Solid.": {"RAMA SANCHEZ JAVIER JORGE", "RAMA SANCHEZ JOSE PEDRO"}},
        )

        cargos2 = regex_cargos(self.nombramientos2)
        self.assertEqual(
            cargos2,
            {
                "Auditor": {"ACME AUDITORES SL"},
                "Aud.Supl.": {"MACIAS MUÑOZ FELIPE JOSE"},
            },
        )

        cargos3 = regex_cargos(self.nombramientos3)
        self.assertEqual(
            cargos3,
            {
                "Auditor": {"A.T.A AUDITORES SL"},
                "Aud.Supl.": {"CUEVAS MUÑOZ SILVIA MARIA"},
            },
        )

        cargos4 = regex_cargos(self.nombramientos4)
        self.assertEqual(
            cargos4,
            {
                "Adm. Solid.": {"ASDFG INVERSIONES SL"},
                "Adm. Mancom.": {"ASDFG INVERSIONES SL", "PEDRO PEREZ"},
            },
        )

        cargos4 = regex_cargos(self.nombramientos5)
        self.assertEqual(
            cargos4,
            {"Apoderado": {"CASER PENSIONES ENTIDAD GESTORA DE FONDOS DE PENSI"}},
        )

        ceses1 = regex_cargos(self.ceses1)
        self.assertEqual(ceses1, {"Adm. Mancom.": {"PEREZ", "HILARIO"}})

        ceses2 = regex_cargos(self.ceses2)
        self.assertEqual(
            ceses2,
            {"Auditor": {"A.T.A AUDITORES SL"}, "Adm. Mancom.": {"PEREZ", "HILARIO"}},
        )

        ceses3 = regex_cargos(self.ceses3)
        self.assertEqual(
            ceses3,
            {
                "Consejero": {"C1 C", "C2 -A-"},
                "Secretario": {"C2 -B-"},
                "Vicesecret.": {"C4 -D-"},
            },
        )

    def test_cargo_entrante(self):
        self.assertTrue(is_acto_cargo_entrante("Reelecciones"))
        self.assertTrue(is_acto_cargo_entrante("Nombramientos"))
        self.assertFalse(is_acto_cargo_entrante("Ceses/Dimisiones"))
        self.assertRaises(
            ValueError, is_acto_cargo_entrante, "Cambio de domicilio social"
        )


class BormeparserRegexBoldTestCase(unittest.TestCase):
    string1 = "Declaración de unipersonalidad. Socio único: GRUPO DE EMPRESAS E INVERSIONES YOLO S.L. Nombramientos"
    string2 = "Declaración de unipersonalidad. Socio único: JOHN DOE. Datos registrales"
    string3 = "Declaración de unipersonalidad. Socio único: FOO DOE. Pérdida del caracter de unipersonalidad. Cambio de domicilio social."
    string4 = "Declaración de unipersonalidad. Socio único: CORPOREISHON BLA BLA. Cif:B12345678.Ceses/Dimisiones."
    string5 = "Declaración de unipersonalidad. Socio único: ENGLOBA GRUPO DE COMUNICACION SL. Sociedad unipersonal. Cambio de identidad del socio único: GRUPO ANTALA MEDIA SL. Datos registrales."

    def test_regex_decl_unip(self):
        acto_colon, arg_colon, nombreacto = regex_bold_acto(self.string1)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(
            arg_colon, "Socio único: GRUPO DE EMPRESAS E INVERSIONES YOLO S.L"
        )
        self.assertEqual(nombreacto, "Nombramientos")

        acto_colon, arg_colon, nombreacto = regex_bold_acto(self.string2)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(arg_colon, "Socio único: JOHN DOE")
        self.assertEqual(nombreacto, "Datos registrales")

        acto_colon, arg_colon, nombreacto = regex_bold_acto(self.string3)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(arg_colon, "Socio único: FOO DOE")
        self.assertEqual(
            nombreacto,
            "Pérdida del caracter de unipersonalidad. Cambio de domicilio social.",
        )

        acto_colon, arg_colon, nombreacto = regex_bold_acto(self.string4)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(arg_colon, "Socio único: CORPOREISHON BLA BLA. Cif:B12345678")
        self.assertEqual(nombreacto, "Ceses/Dimisiones.")

        acto_colon, arg_colon, nombreacto = regex_bold_acto(self.string5)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(arg_colon, "Socio único: ENGLOBA GRUPO DE COMUNICACION SL")
        self.assertEqual(
            nombreacto,
            "Sociedad unipersonal. Cambio de identidad del socio único: GRUPO ANTALA MEDIA SL. Datos registrales.",
        )

    def test_regex_decl_unip_with_accented_object_extension(self):
        data = (
            "Declaración de unipersonalidad. Socio único: BONFILL SOROLLA OSCAR. "
            "Ampliación del objeto social"
        )
        acto_colon, arg_colon, nombreacto = regex_bold_acto(data)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(arg_colon, "Socio único: BONFILL SOROLLA OSCAR")
        self.assertEqual(nombreacto, "Ampliación del objeto social")

    def test_regex_decl_unip_with_hyphen_separator_before_next_act(self):
        data = (
            "Declaración de unipersonalidad. Socio único: "
            "PILATUS FLUGZEUGWERKE AG - PILATUS AIRCRAFT LTD- Nombramientos"
        )
        acto_colon, arg_colon, nombreacto = regex_bold_acto(data)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(
            arg_colon,
            "Socio único: PILATUS FLUGZEUGWERKE AG - PILATUS AIRCRAFT LTD",
        )
        self.assertEqual(nombreacto, "Nombramientos")

    def test_regex_decl_unip_with_cif_space_before_datos_registrales(self):
        data = (
            "Declaración de unipersonalidad. Socio único: LONGOFIN SOCIEDAD "
            "COMANDITARIA POR ACCIONES DE GIUSEPPE LONGO & C. Cif:077343510 "
            "Datos registrales"
        )
        acto_colon, arg_colon, nombreacto = regex_bold_acto(data)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(
            arg_colon,
            "Socio único: LONGOFIN SOCIEDAD COMANDITARIA POR ACCIONES DE "
            "GIUSEPPE LONGO & C. Cif:077343510",
        )
        self.assertEqual(nombreacto, "Datos registrales")

    def test_regex_soc_unip_with_cif_space_before_datos_registrales(self):
        data = (
            "Sociedad unipersonal. Cambio de identidad del socio único: GRUPO "
            "CORPORATIVO EMPRESARIAL DE LA CAJA DE AHORROS Y MONTE DE PI. "
            "Cif:A31691538 Datos registrales"
        )
        acto_colon, arg_colon, nombreacto = regex_bold_acto(data)
        self.assertEqual(acto_colon, "Sociedad unipersonal")
        self.assertEqual(
            arg_colon,
            "Cambio de identidad del socio único: GRUPO CORPORATIVO EMPRESARIAL "
            "DE LA CAJA DE AHORROS Y MONTE DE PI. Cif:A31691538",
        )
        self.assertEqual(nombreacto, "Datos registrales")

    def test_regex_decl_unip_with_cif_joined_to_next_act(self):
        data = (
            "Declaración de unipersonalidad. Socio único: GRUPO CORPORATIVO "
            "EMPRESARIAL DE LA CAJA DE AHORROS Y MONTE DE PI. "
            "Cif:A31691538Nombramientos"
        )
        acto_colon, arg_colon, nombreacto = regex_bold_acto(data)
        self.assertEqual(acto_colon, "Declaración de unipersonalidad")
        self.assertEqual(
            arg_colon,
            "Socio único: GRUPO CORPORATIVO EMPRESARIAL DE LA CAJA DE AHORROS "
            "Y MONTE DE PI. Cif:A31691538",
        )
        self.assertEqual(nombreacto, "Nombramientos")

    def test_regex_bold_act_can_be_followed_by_bold_act(self):
        data = (
            "Sociedad unipersonal. Cambio de identidad del socio único: "
            "ENVIROTECH POWER SOCIEDAD LIMITADA. Escisión total. "
            "Sociedades beneficiarias de la escisión"
        )
        acto_colon, arg_colon, nombreacto = regex_bold_acto(data)
        self.assertEqual(acto_colon, "Sociedad unipersonal")
        self.assertEqual(
            arg_colon,
            "Cambio de identidad del socio único: ENVIROTECH POWER SOCIEDAD LIMITADA",
        )
        self.assertEqual(
            nombreacto,
            "Escisión total. Sociedades beneficiarias de la escisión",
        )


class BormeparserRegexBormeC(unittest.TestCase):
    titulo1 = "PARQUE EMPRESARIAL OMEGA, S.L.U, SOCIEDAD ABSORBENTE\nFGLG OMEGA 2, S.L.U.\nFGLG OMEGA 5, S.L.U.(SOCIEDADES ABSORBIDAS)"
    titulo3 = "INDUSTRIAS TEVI, S.L.\n(SOCIEDAD ESCINDIDA)\nTEVIINMUEBLES 2009, S.L.\n(SOCIEDAD BENEFICIARIA)"
    titulo4 = "NAVES EN ALQUILER PARA LA INDUSTRIA, S.L.\nSOCIEDAD ABSORBENTE Y\nCOCINAS RONDA NORTE, S.L.\nSOCIEDAD ABSORBIDA"
    # titulo5 = 'TÉCNICA EN INSTALACIONES DE FLUIDOS, S.L. (SOCIEDAD ABSORBENTE), MONTAJES INOXIDABLES MOINOX, S.L. UNIPERSONAL (SOCIEDAD ABSORBIDA).'
    # titulo6 = 'SOCIEDAD ANONIMA\nINDUSTRIAS CELULOSA ARAGONESA\n(SOCIEDAD ABSORBENTE)\nCABALUR, SOCIEDAD LIMITADA UNIPERSONAL\n(SOCIEDAD ABSORBIDA)'
    # titulo7 = 'SICA, S.L. (SOCIEDAD ABSORBENTE), CAOLINA, S.L. DE CARÁCTER UNIPERSONAL\n(SOCIEDAD ABSORBIDA)'

    def test_separar_empresas_titulo(self):
        empresas1 = borme_c_separa_empresas_titulo(self.titulo1)
        self.assertEqual(
            empresas1,
            [
                "PARQUE EMPRESARIAL OMEGA, S.L.U",
                "FGLG OMEGA 2, S.L.U.",
                "FGLG OMEGA 5, S.L.U.",
            ],
        )
        empresas3 = borme_c_separa_empresas_titulo(self.titulo3)
        self.assertEqual(
            empresas3, ["INDUSTRIAS TEVI, S.L.", "TEVIINMUEBLES 2009, S.L."]
        )
        empresas4 = borme_c_separa_empresas_titulo(self.titulo4)
        self.assertEqual(
            empresas4,
            ["NAVES EN ALQUILER PARA LA INDUSTRIA, S.L.", "COCINAS RONDA NORTE, S.L."],
        )
        # empresas5 = borme_c_separa_empresas_titulo(self.titulo5)
        # self.assertEqual(empresas5, ['TÉCNICA EN INSTALACIONES DE FLUIDOS, S.L.', 'MONTAJES INOXIDABLES MOINOX, S.L. UNIPERSONAL'])
        # empresas6 = borme_c_separa_empresas_titulo(self.titulo6)
        # self.assertEqual(empresas6, ['SOCIEDAD ANONIMA INDUSTRIAS CELULOSA ARAGONESA', 'CABALUR, SOCIEDAD LIMITADA UNIPERSONAL'])
        # empresas7 = borme_c_separa_empresas_titulo(self.titulo7)
        # self.assertEqual(empresas7, ['SICA, S.L.', 'CAOLINA, S.L. DE CARÁCTER UNIPERSONAL'])


class BormeparserRegexNoMatchTestCase(unittest.TestCase):
    """Antes de la fix, todas estas funciones llamaban a ``.groups()`` o
    ``.group()`` sobre el resultado de ``re.match`` sin comprobar ``None``,
    de modo que un input no esperado provocaba ``AttributeError`` opaco
    en lugar de un error de dominio."""

    def test_regex_argcolon_no_match(self):
        with self.assertRaises(ValueError):
            regex_argcolon("entrada que no encaja con el patrón")

    def test_regex_noarg_no_match(self):
        with self.assertRaises(ValueError):
            regex_noarg("entrada que no encaja con el patrón")

    def test_regex_empresa_no_match(self):
        with self.assertRaises(ValueError):
            regex_empresa("entrada sin separador de id")

    def test_regex_bold_acto_no_match(self):
        with self.assertRaises(ValueError):
            regex_bold_acto("entrada que no encaja con el patrón")

    def test_regex_fecha_no_match(self):
        from bormeparserv2.regex import regex_fecha

        with self.assertRaises(ValueError):
            regex_fecha("no es una fecha BORME")


class BormeparserRegexCargosEmptyEntitiesTestCase(unittest.TestCase):
    """Regresión: cadenas como ``Auditor: SL;.`` colaban entradas vacías
    al set de entidades (al splitear por ``;`` y dejar el sufijo ``.``)."""

    def test_trailing_semicolon_does_not_add_empty(self):
        from bormeparserv2.regex import regex_cargos

        self.assertEqual(regex_cargos("Auditor: SL;."), {"Auditor": {"SL"}})

    def test_only_dot_yields_empty_set(self):
        from bormeparserv2.regex import regex_cargos

        self.assertEqual(regex_cargos("Auditor: ."), {"Auditor": set()})


class BormeparserRegexConstitucionTestCase(unittest.TestCase):
    """Regresión: en ``regex_constitucion`` los literales ``"Domicilio"``
    y ``"Capital"`` estaban escritos como ``"Domicilio" "Capital"`` —
    Python concatena cadenas adyacentes, así que la palabra clave
    real era ``"DomicilioCapital"`` y nunca aparecía en los textos.
    El lookahead del campo "Objeto social" no se cortaba en
    "Domicilio:" y arrastraba el resto del párrafo."""

    DATA = (
        "Comienzo de operaciones: 1.04.15. "
        "Objeto social: La actividad de blabla. "
        "Domicilio: C/ RANDOM 1 2 (MALAGA). "
        "Capital: 3.000,00 Euros."
    )

    def test_objeto_social_stops_at_domicilio(self):
        from bormeparserv2.regex import regex_constitucion

        _, activity, _, _ = regex_constitucion(self.DATA)
        # El "Objeto social" debe acabar antes de "Domicilio:"; un
        # bug previo dejaba aquí todo "blabla. Domicilio: ...".
        self.assertNotIn("Domicilio", activity)

    def test_capital_parsed(self):
        from bormeparserv2.regex import regex_constitucion

        _, _, _, capital = regex_constitucion(self.DATA)
        self.assertEqual(capital, 3000.0)


class PyPDFParserCleanDataTestCase(unittest.TestCase):
    """Regresión: ``_clean_data`` usaba ``str.replace('  ', ' ')`` que solo
    pasa una vez la cadena, dejando runs ≥3 espacios intactos."""

    def test_collapses_triple_space(self):
        from bormeparserv2.backends.pypdf.parser import PyPDFParser

        instance = PyPDFParser.__new__(PyPDFParser)
        self.assertEqual(instance._clean_data("a   b"), "a b")

    def test_collapses_long_runs(self):
        from bormeparserv2.backends.pypdf.parser import PyPDFParser

        instance = PyPDFParser.__new__(PyPDFParser)
        self.assertEqual(instance._clean_data("a     b    c"), "a b c")

    def test_unescapes_parentheses(self):
        from bormeparserv2.backends.pypdf.parser import PyPDFParser

        instance = PyPDFParser.__new__(PyPDFParser)
        self.assertEqual(instance._clean_data(r"foo \(bar\) baz"), "foo (bar) baz")
