#!/usr/bin/env python
#
# test_coverage_completeness.py - Cubre líneas que el resto de tests no tocan.
# Copyright (C) 2015-2026 Marc Rivero López <mriverolopez@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Tests que ejercitan ramas de error y atajos de la API.

Su único objetivo es elevar la cobertura sobre las líneas que el resto
del corpus no toca — typicamente raise NotImplementedError, branches
de validación y módulos pequeños cuyas funciones de utilidad nunca se
llamaron en los tests previos.

Las pruebas siguen la política del proyecto (sin mocks, ejecutan código
real contra fixtures o entradas reales).
"""

import datetime
import os
import tempfile
import unittest

EXAMPLES = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "examples"))


class PackageInitGetattrTestCase(unittest.TestCase):
    """``bormeparserv2.__getattr__`` resuelve CONFIG y rechaza el resto."""

    def test_config_attribute_returns_dict(self):
        import bormeparserv2

        # Forzar la rama "name == 'CONFIG'" sin usar el cache lazy del módulo
        # importado: borramos el cache de configparser primero.
        from bormeparserv2 import config

        config._cached_config = None
        cfg = bormeparserv2.CONFIG
        self.assertIsInstance(cfg, dict)
        self.assertIn("borme_root", cfg)

    def test_unknown_attribute_raises_attributeerror(self):
        import bormeparserv2

        with self.assertRaises(AttributeError) as ctx:
            getattr(bormeparserv2, "SOMETHING_THAT_DOES_NOT_EXIST")
        self.assertIn("SOMETHING_THAT_DOES_NOT_EXIST", str(ctx.exception))


class ConfigModuleGetattrTestCase(unittest.TestCase):
    """``bormeparserv2.config.__getattr__`` mantiene el alias CONFIG."""

    def test_config_alias_returns_dict(self):
        from bormeparserv2 import config

        config._cached_config = None
        cfg = config.CONFIG
        self.assertIsInstance(cfg, dict)
        self.assertIn("borme_root", cfg)

    def test_unknown_attribute_raises_attributeerror(self):
        from bormeparserv2 import config

        with self.assertRaises(AttributeError):
            getattr(config, "SOME_RANDOM_NAME")

    def test_reload_config_clears_cache(self):
        from bormeparserv2 import config

        # Ejecuta la rama de reload_config explícitamente.
        config._cached_config = {"borme_root": tempfile.gettempdir()}
        config.reload_config()
        self.assertIsNone(config._cached_config)


class BackendBaseAbstractsTestCase(unittest.TestCase):
    """Las clases base de backends rechazan rutas inexistentes y abstracts."""

    def test_file_backend_rejects_missing_file(self):
        from bormeparserv2.backends.base import BormeAParserBackend

        with self.assertRaises(FileNotFoundError):
            BormeAParserBackend("/no/such/file.pdf")

    def test_borme_a_backend_parse_raises_notimplemented(self):
        # Subclase mínima que no implementa _parse → ``parse()`` debe lanzar
        # NotImplementedError (línea 68 de backends/base.py).
        from bormeparserv2.backends.base import BormeAParserBackend

        # Usamos un PDF real para pasar la validación isfile del ctor.
        fixture = os.path.join(EXAMPLES, "BORME-A-2015-27-10.pdf")
        with self.assertRaises(NotImplementedError):
            BormeAParserBackend(fixture).parse()

    def test_borme_c_backend_parse_raises_notimplemented(self):
        from bormeparserv2.backends.base import BormeCParserBackend

        fixture = os.path.join(EXAMPLES, "BORME-C-2011-20488.xml")
        with self.assertRaises(NotImplementedError):
            BormeCParserBackend(fixture).parse()


class SeccionCParserEdgeCasesTestCase(unittest.TestCase):
    """``LxmlBormeCParser`` debe avisar de PDF / formatos desconocidos."""

    def _parse_with(self, suffix: str, content: str):
        from bormeparserv2.backends.seccion_c.lxml.parser import LxmlBormeCParser

        with tempfile.NamedTemporaryFile(
            "w", suffix=suffix, delete=False, encoding="iso-8859-1"
        ) as fp:
            fp.write(content)
            path = fp.name
        try:
            return LxmlBormeCParser(path).parse()
        finally:
            os.unlink(path)

    def test_pdf_extension_raises_notimplemented(self):
        with self.assertRaises(NotImplementedError):
            self._parse_with(".pdf", "%PDF-1.4 fake")

    def test_unknown_format_raises_valueerror(self):
        with self.assertRaises(ValueError):
            self._parse_with(".dat", "no xml, no html, no nada")

    def test_html_with_malformed_title_raises_valueerror(self):
        # HTML con la estructura mínima pero un título que no encaja con el
        # regex ``CONVOCATORIAS… \(BORME N de DD/MM/YYYY\)`` → rama line 143.
        html = (
            "<!DOCTYPE HTML PUBLIC '-//W3C//DTD HTML 4.01//EN'>"
            "<html><body>"
            '<div id="contenedor">'
            '<p class="documento-tit">EMPRESA SL</p>'
            '<div id="textoxslt"><p>texto</p></div>'
            '<div class="poolBdatos"><h3>NO MATCH HEADER</h3></div>'
            '<div class="contMigas"><ul><li class="destino">Documento BORME-C-2011-20488</li></ul></div>'
            "</div></body></html>"
        )
        with self.assertRaises(ValueError) as ctx:
            self._parse_with(".html", html)
        self.assertIn("BORME-C HTML", str(ctx.exception))


class ProvinciaEnumDunderMethodsTestCase(unittest.TestCase):
    """Cubre ``__str__``, ``__repr__``, ``__lt__``, ``__hash__`` de Provincia."""

    def test_str_returns_name(self):
        from bormeparserv2 import PROVINCIA

        self.assertEqual(str(PROVINCIA.MADRID), "Madrid")
        self.assertEqual(str(PROVINCIA.CACERES), "Cáceres")

    def test_repr_contains_classname_and_name(self):
        from bormeparserv2 import PROVINCIA

        rep = repr(PROVINCIA.MADRID)
        self.assertIn("Provincia", rep)
        self.assertIn("Madrid", rep)

    def test_provincias_are_orderable_by_name(self):
        from bormeparserv2 import PROVINCIA

        # __lt__ se ejecuta al ordenar.
        ordered = sorted([PROVINCIA.MADRID, PROVINCIA.BARCELONA, PROVINCIA.CACERES])
        self.assertEqual([str(p) for p in ordered], ["Barcelona", "Cáceres", "Madrid"])

    def test_provincia_is_hashable_and_usable_in_set(self):
        from bormeparserv2 import PROVINCIA

        s = {PROVINCIA.MADRID, PROVINCIA.MADRID, PROVINCIA.BARCELONA}
        self.assertEqual(len(s), 2)

    def test_from_title_explicit_araba_alava_alias(self):
        from bormeparserv2 import PROVINCIA

        # La rama explícita ``title == "ARABA/ÁLAVA"`` (línea 121).
        self.assertIs(PROVINCIA.from_title("ARABA/ÁLAVA"), PROVINCIA.ALAVA)


class SerializationEdgeCasesTestCase(unittest.TestCase):
    """Cubre ramas raras de ``_serialization``."""

    def test_json_default_rejects_unknown_type(self):
        from bormeparserv2._serialization import _json_default

        with self.assertRaises(TypeError):
            _json_default(object())

    def test_to_json_requires_path_when_filename_unset(self):
        from bormeparserv2._serialization import borme_to_json
        from bormeparserv2.borme import Borme

        borme = Borme(
            datetime.date(2015, 2, 10),
            "A",
            __import__("bormeparserv2").PROVINCIA.CACERES,
            27,
            "BORME-A-2015-27-10",
            [],
        )
        # filename queda en None y no se pasa path → ValueError.
        with self.assertRaises(ValueError):
            borme_to_json(borme, path=None, include_url=False)

    def test_to_json_returns_false_when_file_exists_and_no_overwrite(self):
        from bormeparserv2._serialization import borme_to_json
        from bormeparserv2.borme import Borme

        borme = Borme(
            datetime.date(2015, 2, 10),
            "A",
            __import__("bormeparserv2").PROVINCIA.CACERES,
            27,
            "BORME-A-2015-27-10",
            [],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.json")
            with open(path, "w", encoding="utf-8") as fp:
                fp.write("{}")
            ret = borme_to_json(borme, path=path, overwrite=False, include_url=False)
            self.assertFalse(ret)

    def test_from_json_warns_on_old_version(self):
        from bormeparserv2 import _serialization
        from bormeparserv2._serialization import borme_from_json
        from bormeparserv2.borme import Borme

        borme = Borme(
            datetime.date(2015, 2, 10),
            "A",
            __import__("bormeparserv2").PROVINCIA.CACERES,
            27,
            "BORME-A-2015-27-10",
            [],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            _serialization.borme_to_json(borme, path=path, include_url=False)
            # Reescribimos el version field a algo anterior y comprobamos
            # que ``from_json`` loguea el warning sin romperse.
            import json as _json

            with open(path, encoding="utf-8") as fp:
                data = _json.load(fp)
            data["version"] = 1  # mucho más antiguo que cualquier FILE_VERSION actual
            with open(path, "w", encoding="utf-8") as fp:
                _json.dump(data, fp)
            with self.assertLogs(
                "bormeparserv2._serialization", level="WARNING"
            ) as cap:
                back = borme_from_json(path)
            self.assertEqual(back.cve, "BORME-A-2015-27-10")
            self.assertTrue(
                any("older version" in m for m in cap.output),
                msg=f"captured={cap.output!r}",
            )


class SeccionCFusionesWarningTestCase(unittest.TestCase):
    """``LxmlBormeCParser`` debe loguear warning en fusiones/absorciones."""

    XML_FUSIONES = (
        '<?xml version="1.0" encoding="iso-8859-1"?>'
        "<documento>"
        "<metadatos>"
        "<identificador>BORME-C-2024-99999</identificador>"
        "<numero_anuncio>99999</numero_anuncio>"
        "<id_anuncio>A240099999</id_anuncio>"
        "<departamento>FUSIONES Y ABSORCIONES DE EMPRESAS</departamento>"
        "<titulo>EMPRESA UNICA SL</titulo>"  # solo una empresa → fuerza el warning
        "<diario_numero>10</diario_numero>"
        "<fecha_publicacion>20240115</fecha_publicacion>"
        "<pagina_inicial>1</pagina_inicial>"
        "<pagina_final>2</pagina_final>"
        "</metadatos>"
        "<texto><p>CIF n.º A12345678 sin mucho más</p></texto>"
        "</documento>"
    )

    def test_fusiones_with_single_empresa_logs_warning(self):
        from bormeparserv2.backends.seccion_c.lxml.parser import LxmlBormeCParser

        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="iso-8859-1"
        ) as fp:
            fp.write(self.XML_FUSIONES)
            path = fp.name
        try:
            with self.assertLogs(
                "bormeparserv2.backends.seccion_c.lxml.parser",
                level="WARNING",
            ) as cap:
                result = LxmlBormeCParser(path).parse()
            self.assertEqual(
                result["departamento"], "FUSIONES Y ABSORCIONES DE EMPRESAS"
            )
            self.assertTrue(
                any("fusiones" in m.lower() for m in cap.output),
                msg=f"captured={cap.output!r}",
            )
        finally:
            os.unlink(path)


class BormeActoDundersTestCase(unittest.TestCase):
    """``BormeActo`` abstract + sus subclases (repr, errores de validación)."""

    def test_acto_subclass_must_implement_set_name(self):
        from bormeparserv2.borme import BormeActo

        class _Bad(BormeActo):
            def _set_value(self, value):
                self.value = value

        with self.assertRaises(NotImplementedError):
            _Bad("Nombramientos", {"Adm. Unico": {"PEPE"}})

    def test_acto_subclass_must_implement_set_value(self):
        from bormeparserv2.borme import BormeActo

        class _Bad(BormeActo):
            def _set_name(self, name):
                self.name = name

        with self.assertRaises(NotImplementedError):
            _Bad("Reducción de capital", "1000")

    def test_borme_acto_texto_repr(self):
        from bormeparserv2.borme import BormeActoTexto

        acto = BormeActoTexto("Reducción de capital", "1000 Euros")
        rep = repr(acto)
        self.assertIn("BormeActoTexto", rep)
        self.assertIn("Reducción de capital", rep)

    def test_borme_acto_cargo_repr(self):
        from bormeparserv2.borme import BormeActoCargo

        acto = BormeActoCargo("Nombramientos", {"Adm. Unico": {"JUAN"}})
        rep = repr(acto)
        self.assertIn("BormeActoCargo", rep)

    def test_borme_acto_cargo_rejects_non_set_non_list_value(self):
        from bormeparserv2.borme import BormeActoCargo

        with self.assertRaises(ValueError):
            BormeActoCargo("Nombramientos", {"Adm. Unico": "no es set ni list"})

    def test_borme_acto_cargo_get_nombres_cargos(self):
        from bormeparserv2.borme import BormeActoCargo

        acto = BormeActoCargo(
            "Nombramientos",
            {"Adm. Unico": {"PEPE"}, "Auditor": {"AUDITORA SL"}},
        )
        self.assertEqual(set(acto.get_nombres_cargos()), {"Adm. Unico", "Auditor"})


class BormeAnuncioReprTestCase(unittest.TestCase):
    """``BormeAnuncio.__repr__`` para inspección manual."""

    def test_repr_contains_id_and_company(self):
        from bormeparserv2.borme import BormeAnuncio

        extra = {"registro": "", "sucursal": False, "liquidacion": False}
        a = BormeAnuncio(123, "TESTSL", [], extra)
        rep = repr(a)
        self.assertIn("123", rep)
        self.assertIn("TESTSL", rep)


class BormeFromFileWrongTypeTestCase(unittest.TestCase):
    """Sección C devuelve un dict, no un :class:`Borme` ⇒ ``from_file``
    debe lanzar ``TypeError`` claro en lugar de devolver el dict."""

    def test_from_file_seccion_c_raises_typeerror(self):
        from bormeparserv2.borme import Borme

        c_xml = os.path.join(EXAMPLES, "BORME-C-2011-20488.xml")
        with self.assertRaises(TypeError) as ctx:
            Borme.from_file(c_xml)
        self.assertIn("sección 'C'", str(ctx.exception))


def _make_empty_borme(cve, ids):
    from bormeparserv2 import PROVINCIA
    from bormeparserv2.borme import Borme, BormeAnuncio

    extra = {"registro": "", "sucursal": False, "liquidacion": False}
    anuncios = [BormeAnuncio(i, f"COMPANY-{i}", [], extra) for i in ids]
    return Borme(
        datetime.date(2015, 2, 10),
        "A",
        PROVINCIA.CACERES,
        27,
        cve,
        anuncios,
    )


class BormeDownloadAndCompareTestCase(unittest.TestCase):
    """Cubre ``Borme.download`` (rama BormeAlreadyDownloaded) y ``__lt__``."""

    def test_download_with_existing_filename_raises(self):
        from bormeparserv2.exceptions import BormeAlreadyDownloadedException

        b = _make_empty_borme("BORME-A-2015-27-10", [1])
        b.filename = os.path.join(tempfile.gettempdir(), "already.pdf")
        with self.assertRaises(BormeAlreadyDownloadedException):
            b.download(os.path.join(tempfile.gettempdir(), "new.pdf"))

    def test_lt_compares_anuncios_ranges(self):
        b1 = _make_empty_borme("BORME-A-2015-27-10", [10, 11, 12])
        b2 = _make_empty_borme("BORME-A-2015-27-11", [20, 21, 22])
        self.assertLess(b1, b2)
        self.assertFalse(b2 < b1)

    def test_to_dict_returns_serializable_doc(self):
        b = _make_empty_borme("BORME-A-2015-27-10", [1])
        doc = b._to_dict(set_url=False)
        self.assertEqual(doc["cve"], "BORME-A-2015-27-10")
        self.assertEqual(doc["num_anuncios"], 1)


class BormeLazyUrlResolutionTestCase(unittest.TestCase):
    """``Borme(lazy=False)`` con sumario XML disponible localmente."""

    def test_lazy_false_calls_set_url_with_local_xml(self):
        import shutil

        from bormeparserv2 import PROVINCIA, config
        from bormeparserv2.borme import Borme

        with tempfile.TemporaryDirectory() as tmp:
            previous = config._cached_config
            config._cached_config = {"borme_root": tmp}
            xml_dir = os.path.join(tmp, "xml", "2015", "09")
            os.makedirs(xml_dir)
            shutil.copy(
                os.path.join(EXAMPLES, "BORME-S-20150924.xml"),
                os.path.join(xml_dir, "BORME-S-20150924.xml"),
            )
            try:
                b = Borme(
                    datetime.date(2015, 9, 24),
                    "A",
                    PROVINCIA.MADRID,
                    183,
                    "BORME-A-2015-183-28",
                    [],
                    lazy=False,
                )
                self.assertIn("BORME-A-2015-183-28.pdf", b.url)
            finally:
                config._cached_config = previous


class RegexBranchesTestCase(unittest.TestCase):
    """Branches secundarias de ``regex.py``."""

    def test_is_acto_noarg_true(self):
        from bormeparserv2.acto import ACTO
        from bormeparserv2.regex import is_acto_noarg

        if not ACTO.NOARG_KEYWORDS:
            self.skipTest("No NOARG keywords definidos")
        sample = next(iter(ACTO.NOARG_KEYWORDS))
        self.assertTrue(is_acto_noarg(sample))

    def test_regex_empresa_unknown_registro_logs_warning(self):
        from bormeparserv2.regex import regex_empresa

        with self.assertLogs("bormeparserv2.regex", level="WARNING") as cap:
            _id, _emp, extra = regex_empresa(
                "12345 - FOOBAR SL(R.M. INVENTADO DE NUNCA JAMAS)"
            )
        self.assertTrue(
            any("Registro desconocido" in m for m in cap.output),
            msg=f"captured={cap.output!r}",
        )
        self.assertEqual(extra["registro"], "")

    def test_regex_constitucion_rejects_unknown_currency(self):
        from bormeparserv2.regex import regex_constitucion

        with self.assertRaises(ValueError) as ctx:
            regex_constitucion(
                "Comienzo de operaciones: 1.04.15. Capital: 3.000,00 Dracmas."
            )
        self.assertIn("Capital ni Ptas", str(ctx.exception))

    def test_regex_constitucion_without_comienzo_raises(self):
        from bormeparserv2.regex import regex_constitucion

        with self.assertRaises(ValueError):
            regex_constitucion("Sin la palabra clave esperada en absoluto")

    def test_regex_constitucion_capital_in_ptas(self):
        from bormeparserv2.regex import regex_constitucion

        date, _activity, _address, capital = regex_constitucion(
            "Comienzo de operaciones: 1.04.15. Capital: 500.000 Ptas."
        )
        self.assertEqual(capital, 500000)
        self.assertEqual(date, "2015-04-01")

    def test_regex_constitucion_date_slash_format(self):
        from bormeparserv2.regex import regex_constitucion

        date, *_ = regex_constitucion(
            "Comienzo de operaciones: 17/04/2013. Capital: 1,00 Euros."
        )
        self.assertEqual(date, "2013-04-17")

    def test_regex_constitucion_date_dash_format(self):
        from bormeparserv2.regex import regex_constitucion

        date, *_ = regex_constitucion(
            "Comienzo de operaciones: 2-10-2009. Capital: 1,00 Euros."
        )
        self.assertEqual(date, "2009-10-02")

    def test_regex_constitucion_date_textual_spanish(self):
        from bormeparserv2.regex import regex_constitucion

        date, *_ = regex_constitucion(
            "Comienzo de operaciones: 21 de febrero de 2006. Capital: 1,00 Euros."
        )
        self.assertEqual(date, "2006-02-21")

    def test_regex_constitucion_invalid_date_logs_error(self):
        from bormeparserv2.regex import regex_constitucion

        with self.assertLogs("bormeparserv2.regex", level="ERROR") as cap:
            regex_constitucion(
                "Comienzo de operaciones: 99/99/9999. Capital: 1,00 Euros."
            )
        self.assertTrue(
            any("Comienzo de operaciones" in m for m in cap.output),
            msg=f"captured={cap.output!r}",
        )

    def test_regex_constitucion_with_duration(self):
        from bormeparserv2.regex import regex_constitucion

        # Activa la rama ``if duration:`` (línea 340-341) sin importar el
        # valor exacto de retorno.
        regex_constitucion(
            "Comienzo de operaciones: 1.04.15. "
            "Duración: Indefinida. "
            "Capital: 1,00 Euros."
        )

    def test_capitalize_sentence_uppercases_input(self):
        from bormeparserv2.regex import capitalize_sentence

        out = capitalize_sentence("PRIMERA FRASE. SEGUNDA FRASE.")
        # Si el input estaba todo en mayúsculas se baja a minúsculas
        # antes de capitalizar (línea 426).
        self.assertEqual(out, "Primera frase. Segunda frase.")

    def test_regex_argcolon_returns_groups(self):
        from bormeparserv2.regex import regex_argcolon

        # ``Modificación de duración`` está en ``ACTO.COLON_KEYWORDS``.
        # Activa la rama de retorno (línea 167).
        groups = regex_argcolon("Modificación de duración: 99 años. Nombramientos")
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0], "Modificación de duración")

    def test_regex_constitucion_date_two_digit_day_period(self):
        from bormeparserv2.regex import regex_constitucion

        # Fecha tipo ``DD.MM.YY``: dos dígitos seguidos de '.' (línea 316).
        date, *_ = regex_constitucion(
            "Comienzo de operaciones: 10.04.15. Capital: 1,00 Euros."
        )
        self.assertEqual(date, "2015-04-10")

    def test_regex_constitucion_slash_wrong_segment_count_logs_error(self):
        from bormeparserv2.regex import regex_constitucion

        # date con "/" pero con un nº de segmentos distinto de 3 →
        # ValueError interno que el except convierte en log de error
        # (línea 324 + 336-337).
        with self.assertLogs("bormeparserv2.regex", level="ERROR"):
            regex_constitucion("Comienzo de operaciones: 17/04. Capital: 1,00 Euros.")

    def test_regex_constitucion_de_text_format_no_match_logs_error(self):
        from bormeparserv2.regex import regex_constitucion

        # date con " de " pero sin el patrón ``\d+ de \w+ de \d+`` →
        # raise ValueError dentro del try (línea 330) → log de error.
        with self.assertLogs("bormeparserv2.regex", level="ERROR"):
            regex_constitucion(
                "Comienzo de operaciones: el día de la marmota de 2020. "
                "Capital: 1,00 Euros."
            )


LIVE = os.environ.get("BORMEPARSERV2_LIVE") == "1"
require_live = unittest.skipUnless(
    LIVE, "set BORMEPARSERV2_LIVE=1 to run tests that hit boe.es"
)


@require_live
class BormeLiveDownloadTestCase(unittest.TestCase):
    """``Borme.download`` recupera el PDF real cuando ``filename`` no está set."""

    def test_download_populates_filename(self):
        from bormeparserv2 import PROVINCIA
        from bormeparserv2.borme import Borme

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "BORME-A-2015-27-10.pdf")
            b = Borme(
                datetime.date(2015, 2, 10),
                "A",
                PROVINCIA.CACERES,
                27,
                "BORME-A-2015-27-10",
                [],
            )
            ok = b.download(target)
            self.assertTrue(ok)
            self.assertEqual(b.filename, target)
            self.assertGreater(os.path.getsize(target), 10000)


if __name__ == "__main__":
    unittest.main()
