#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# check_sbom_rating.py - Gate sbom-tools quality score.

"""Check an SBOM quality score with sbom-tools and enforce a letter grade."""

import argparse
import json
import sys
from typing import Any

GRADE_ORDER = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4, "A+": 5}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="sbom-tools quality JSON report")
    parser.add_argument(
        "--profile", default="standard", help="sbom-tools quality profile"
    )
    parser.add_argument("--min-score", type=float, default=90.0)
    parser.add_argument("--min-grade", default="A", choices=sorted(GRADE_ORDER))
    return parser.parse_args(argv)


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise ValueError("sbom-tools did not emit JSON")

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("sbom-tools JSON output is incomplete")


def score_to_grade(score: float) -> str:
    if score >= 97.0:
        return "A+"
    if score >= 90.0:
        return "A"
    if score >= 80.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 60.0:
        return "D"
    return "F"


def grade_at_least(actual: str, expected: str) -> bool:
    return GRADE_ORDER[actual] >= GRADE_ORDER[expected]


def overall_score(report: dict[str, Any]) -> float:
    if "report" in report and isinstance(report["report"], dict):
        report = report["report"]
    score = report.get("overall_score")
    if score is None:
        score = report.get("overallScore")
    if score is None:
        raise KeyError("sbom-tools JSON does not contain overall_score")
    return float(score)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with open(args.report, encoding="utf-8") as fp:
        report = extract_json_object(fp.read())
    score = overall_score(report)
    grade = score_to_grade(score)
    print(f"SBOM quality ({args.profile}): {score:.1f}/{grade}")
    if score < args.min_score:
        print(
            f"Score {score:.1f} is below required minimum {args.min_score:.1f}",
            file=sys.stderr,
        )
        return 1
    if not grade_at_least(grade, args.min_grade):
        print(
            f"Grade {grade} is below required minimum {args.min_grade}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
