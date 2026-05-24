#!/usr/bin/env python
#
# test_sbom.py - Regressions for SBOM tooling.

"""Tests for the generated SBOM and rating helper."""

import json
import os
import tempfile
import unittest

from scripts import check_sbom_rating, generate_sbom

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class GenerateSbomTestCase(unittest.TestCase):
    """The SBOM generator should describe runtime dependencies, not dev tools."""

    def test_generates_cyclonedx_runtime_sbom(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "bormeparserv2.cdx.json")
            result = generate_sbom.main(
                [
                    "--source-root",
                    REPO_ROOT,
                    "--requirements",
                    os.path.join(REPO_ROOT, "requirements.txt"),
                    "--timestamp",
                    "2026-05-24T00:00:00Z",
                    "-o",
                    output,
                ]
            )
            self.assertEqual(result, 0)

            with open(output, encoding="utf-8") as fp:
                data = json.load(fp)

        self.assertEqual(data["bomFormat"], "CycloneDX")
        self.assertEqual(data["specVersion"], "1.7")
        self.assertEqual(
            data["metadata"]["component"]["licenses"][0]["license"]["id"],
            "GPL-3.0-or-later",
        )
        component_names = {
            component["name"].lower() for component in data["components"]
        }
        self.assertIn("requests", component_names)
        self.assertIn("pypdf", component_names)
        self.assertNotIn("black", component_names)
        self.assertNotIn("sphinx", component_names)
        self.assertTrue(data["dependencies"])
        self.assertEqual(data["compositions"][0]["aggregate"], "complete")


class CheckSbomRatingTestCase(unittest.TestCase):
    """The rating helper should parse sbom-tools JSON even with log noise."""

    def test_extracts_json_object_from_noisy_output(self):
        data = check_sbom_rating.extract_json_object(
            'INFO before\n{"overall_score": 91.25, "nested": {"x": "}"}}\nERROR after'
        )
        self.assertEqual(data["overall_score"], 91.25)

    def test_score_to_grade(self):
        self.assertEqual(check_sbom_rating.score_to_grade(100.0), "A+")
        self.assertEqual(check_sbom_rating.score_to_grade(90.0), "A")
        self.assertEqual(check_sbom_rating.score_to_grade(80.0), "B")
        self.assertTrue(check_sbom_rating.grade_at_least("A+", "A"))
        self.assertFalse(check_sbom_rating.grade_at_least("B", "A"))


if __name__ == "__main__":
    unittest.main()
