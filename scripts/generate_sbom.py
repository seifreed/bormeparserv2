#!/usr/bin/env python
#
# generate_sbom.py - Generate a CycloneDX SBOM for bormeparserv2.

"""Generate a high-quality CycloneDX SBOM from installed package metadata."""

import argparse
import ast
import base64
import datetime as dt
import hashlib
import json
import os
import sys
import uuid
from collections import deque
from importlib import metadata
from pathlib import Path
from typing import AbstractSet, Any, cast

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PROJECT_NAME = "bormeparserv2"
PROJECT_DESCRIPTION = (
    "Python library for downloading, parsing, serializing and indexing BORME files"
)
PROJECT_AUTHOR = "Marc Rivero Lopez"
PROJECT_EMAIL = "mriverolopez@gmail.com"
PROJECT_URL = "https://github.com/seifreed/bormeparserv2"
PROJECT_LICENSE = "GPL-3.0-or-later"
TOOLING_MARKER = "# Development, test, lint, security and documentation tooling."
GENERATOR_VERSION = "1.0.0"

LICENSE_CLASSIFIERS = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)": (
        "GPL-3.0-or-later"
    ),
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "Python-2.0",
}

LICENSE_ALIASES = {
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "gplv3+": "GPL-3.0-or-later",
    "gpl-3.0-or-later": "GPL-3.0-or-later",
    "gnu general public license v3 or later (gplv3+)": "GPL-3.0-or-later",
    "isc": "ISC",
    "mit": "MIT",
    "mit license": "MIT",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "mpl-2.0": "MPL-2.0",
    "python software foundation license": "Python-2.0",
    "python-2.0": "Python-2.0",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        default="build/sbom/bormeparserv2.cdx.json",
        help="CycloneDX JSON output path",
    )
    parser.add_argument(
        "--requirements",
        default="requirements.txt",
        help="requirements.txt path used to find runtime dependencies",
    )
    parser.add_argument(
        "--source-root",
        default=".",
        help="repository root containing setup.py",
    )
    parser.add_argument(
        "--timestamp",
        help="RFC3339 timestamp override, mainly for reproducible tests",
    )
    return parser.parse_args(argv)


def runtime_requirements(requirements_path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    with requirements_path.open(encoding="utf-8") as fp:
        for raw in fp:
            line = raw.strip()
            if line == TOOLING_MARKER:
                break
            if not line or line.startswith(("#", "http://", "https://", "git+")):
                continue
            requirements.append(Requirement(line))
    return requirements


def project_version(source_root: Path) -> str:
    setup_py = source_root / "setup.py"
    tree = ast.parse(setup_py.read_text(encoding="utf-8"), filename=str(setup_py))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "VERSION"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    return node.value.value
    raise ValueError("VERSION not found in setup.py")


def applies(req: Requirement) -> bool:
    if req.marker is None:
        return True
    env: dict[str, str | AbstractSet[str]] = {
        key: str(value) for key, value in default_environment().items()
    }
    env["extra"] = ""
    return bool(req.marker.evaluate(env))


def distribution_for(name: str) -> metadata.Distribution:
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError as exc:
        raise SystemExit(
            f"Package {name!r} is required for the SBOM but is not installed. "
            "Run `python -m pip install -r requirements.txt && python -m pip install -e .`."
        ) from exc


def closure(
    direct_requirements: list[Requirement],
) -> tuple[dict[str, metadata.Distribution], dict[str, list[str]], list[str]]:
    queue: deque[str] = deque(req.name for req in direct_requirements if applies(req))
    distributions: dict[str, metadata.Distribution] = {}
    dependencies: dict[str, list[str]] = {}
    direct: list[str] = []

    while queue:
        requested_name = queue.popleft()
        dist = distribution_for(requested_name)
        dist_name = canonical_name(dist)
        if dist_name in distributions:
            continue
        distributions[dist_name] = dist

        child_names: list[str] = []
        for raw_req in dist.requires or ():
            child_req = Requirement(raw_req)
            if not applies(child_req):
                continue
            child_dist = distribution_for(child_req.name)
            child_name = canonical_name(child_dist)
            child_names.append(child_name)
            if child_name not in distributions:
                queue.append(child_req.name)
        dependencies[dist_name] = sorted(set(child_names))

    for req in direct_requirements:
        if not applies(req):
            continue
        direct_dist = distribution_for(req.name)
        direct.append(canonical_name(direct_dist))

    return distributions, dependencies, sorted(set(direct))


def canonical_name(dist: metadata.Distribution) -> str:
    return cast(str, canonicalize_name(dist.metadata.get("Name") or dist.name))


def canonical_key(name: str) -> str:
    return cast(str, canonicalize_name(name))


def metadata_name(dist: metadata.Distribution) -> str:
    return dist.metadata.get("Name") or dist.name


def package_purl(name: str, version: str) -> str:
    return f"pkg:pypi/{canonical_key(name)}@{version}"


def license_expression(msg: Any, fallback: str = "NOASSERTION") -> str:
    expression = (msg.get("License-Expression") or "").strip()
    if expression:
        return expression

    license_text = (msg.get("License") or "").strip()
    normalized = " ".join(license_text.split()).lower()
    if normalized in LICENSE_ALIASES:
        return LICENSE_ALIASES[normalized]

    for classifier in msg.get_all("Classifier", ()):
        if classifier in LICENSE_CLASSIFIERS:
            return LICENSE_CLASSIFIERS[classifier]

    return fallback


def supplier_name(msg: Any) -> str:
    for key in ("Maintainer", "Author", "Author-email", "Maintainer-email"):
        value = (msg.get(key) or "").strip()
        if value:
            return " ".join(value.split())
    name = (msg.get("Name") or "unknown").strip()
    return f"{name} maintainers"


def project_urls(msg: Any) -> dict[str, str]:
    urls: dict[str, str] = {}
    for raw in msg.get_all("Project-URL", ()):
        if "," not in raw:
            continue
        label, url = raw.split(",", 1)
        urls[label.strip().lower()] = url.strip()
    home_page = (msg.get("Home-page") or "").strip()
    if home_page:
        urls.setdefault("homepage", home_page)
    return urls


def external_references(msg: Any, package_name: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = [
        {"type": "website", "url": f"https://pypi.org/project/{package_name}/"}
    ]
    urls = project_urls(msg)
    for label, url in sorted(urls.items()):
        if not url:
            continue
        if any(token in label for token in ("source", "repository", "code")):
            refs.append({"type": "vcs", "url": url})
        elif "documentation" in label or "docs" in label:
            refs.append({"type": "documentation", "url": url})
        elif "bug" in label or "issue" in label:
            refs.append({"type": "issue-tracker", "url": url})
        elif label == "homepage":
            refs.append({"type": "website", "url": url})
    return unique_refs(refs)


def unique_refs(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for ref in refs:
        key = (ref["type"], ref["url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def distribution_hash(dist: metadata.Distribution) -> str:
    digest = hashlib.sha256()
    for package_file in sorted(dist.files or (), key=lambda item: item.as_posix()):
        path = Path(str(dist.locate_file(package_file)))
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = package_file.as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_tree_hash(source_root: Path) -> str:
    digest = hashlib.sha256()
    for base in ("bormeparserv2", "scripts", "setup.py", "requirements.txt"):
        path = source_root / base
        paths = [path] if path.is_file() else sorted(path.rglob("*"))
        for item in paths:
            if (
                not item.is_file()
                or "__pycache__" in item.parts
                or item.suffix == ".pyc"
            ):
                continue
            rel = item.relative_to(source_root).as_posix().encode("utf-8")
            digest.update(rel)
            digest.update(b"\0")
            digest.update(item.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def component(
    *,
    name: str,
    version: str,
    component_type: str,
    supplier: str,
    license_id: str,
    description: str | None,
    hashes: list[dict[str, str]],
    external_refs: list[dict[str, str]],
    author: str | None = None,
    purl: str | None = None,
) -> dict[str, Any]:
    bom_ref = purl or package_purl(name, version)
    data: dict[str, Any] = {
        "type": component_type,
        "bom-ref": bom_ref,
        "name": name,
        "version": version,
        "purl": bom_ref,
        "supplier": {"name": supplier},
        "licenses": [{"license": {"id": license_id}}],
        "hashes": hashes,
        "externalReferences": external_refs,
        "properties": [
            {"name": "bormeparserv2:hash-source", "value": "installed-files"}
        ],
    }
    if description:
        data["description"] = description
    if author:
        data["author"] = author
    return data


def dependency_component(dist: metadata.Distribution) -> dict[str, Any]:
    msg = dist.metadata
    name = metadata_name(dist)
    version = dist.version
    return component(
        name=name,
        version=version,
        component_type="library",
        supplier=supplier_name(msg),
        license_id=license_expression(msg),
        description=(msg.get("Summary") or "").strip() or None,
        hashes=[{"alg": "SHA-256", "content": distribution_hash(dist)}],
        external_refs=external_references(msg, name),
        author=(msg.get("Author") or msg.get("Author-email") or "").strip() or None,
    )


def project_component(source_root: Path, version: str) -> dict[str, Any]:
    return component(
        name=PROJECT_NAME,
        version=version,
        component_type="application",
        supplier=PROJECT_AUTHOR,
        license_id=PROJECT_LICENSE,
        description=PROJECT_DESCRIPTION,
        hashes=[{"alg": "SHA-256", "content": source_tree_hash(source_root)}],
        external_refs=[
            {"type": "website", "url": PROJECT_URL},
            {"type": "vcs", "url": PROJECT_URL},
            {"type": "issue-tracker", "url": f"{PROJECT_URL}/issues"},
            {"type": "advisories", "url": f"{PROJECT_URL}/security/advisories"},
            {"type": "security-contact", "url": f"mailto:{PROJECT_EMAIL}"},
            {"type": "license", "url": f"{PROJECT_URL}/blob/master/LICENSE.txt"},
        ],
        author=PROJECT_AUTHOR,
    )


def python_component() -> dict[str, Any]:
    executable = Path(sys.executable)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    version = ".".join(map(str, sys.version_info[:3]))
    return component(
        name="Python",
        version=version,
        component_type="platform",
        supplier="Python Software Foundation",
        license_id="Python-2.0",
        description="Python runtime used to install and execute bormeparserv2",
        hashes=[{"alg": "SHA-256", "content": digest}],
        external_refs=[
            {"type": "website", "url": "https://www.python.org/"},
            {"type": "vcs", "url": "https://github.com/python/cpython"},
        ],
        author="Python Software Foundation",
        purl=f"pkg:generic/python@{version}",
    )


def timestamp_value(explicit: str | None) -> str:
    if explicit:
        return explicit
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        timestamp = dt.datetime.fromtimestamp(
            int(source_date_epoch), tz=dt.timezone.utc
        )
    else:
        timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


def serial_number(seed: str) -> str:
    return "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def build_sbom(
    source_root: Path, requirements_path: Path, timestamp: str
) -> dict[str, Any]:
    version = project_version(source_root)
    direct_requirements = runtime_requirements(requirements_path)
    distributions, dependency_map, direct_dependencies = closure(direct_requirements)

    primary = project_component(source_root, version)
    runtime = python_component()
    components = [
        runtime,
        *(dependency_component(distributions[name]) for name in sorted(distributions)),
    ]
    all_refs = [primary["bom-ref"], *(comp["bom-ref"] for comp in components)]
    ref_by_name = {canonical_key(comp["name"]): comp["bom-ref"] for comp in components}
    project_ref = primary["bom-ref"]
    runtime_ref = runtime["bom-ref"]

    dependencies = [
        {
            "ref": project_ref,
            "dependsOn": [
                runtime_ref,
                *(ref_by_name[name] for name in direct_dependencies),
            ],
        }
    ]
    for name in sorted(dependency_map):
        dependencies.append(
            {
                "ref": ref_by_name[name],
                "dependsOn": [
                    runtime_ref,
                    *(
                        ref_by_name[child]
                        for child in dependency_map[name]
                        if child in ref_by_name
                    ),
                ],
            }
        )
    dependencies.append({"ref": runtime_ref, "dependsOn": []})

    seed = "|".join([project_ref, *(comp["bom-ref"] for comp in components)])
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": serial_number(seed),
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "bormeparserv2-sbom-generator",
                        "version": GENERATOR_VERSION,
                    }
                ]
            },
            "authors": [{"name": PROJECT_AUTHOR, "email": PROJECT_EMAIL}],
            "component": primary,
            "lifecycles": [{"phase": "build"}],
        },
        "components": components,
        "dependencies": dependencies,
        "compositions": [{"aggregate": "complete", "assemblies": all_refs}],
        "citations": [
            {
                "bom-ref": "bormeparserv2-sbom-source",
                "pointers": ["/metadata/component", "/components", "/dependencies"],
                "timestamp": timestamp,
                "attributedTo": "requirements.txt and installed Python package metadata",
                "process": "scripts/generate_sbom.py",
                "note": (
                    "Runtime dependency closure comes from requirements.txt and "
                    "importlib.metadata for the active Python environment."
                ),
            }
        ],
        "properties": [
            {
                "name": "bormeparserv2:sbom-runtime-dependencies",
                "value": base64.b64encode(
                    json.dumps(direct_dependencies, sort_keys=True).encode("utf-8")
                ).decode("ascii"),
            }
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_root = Path(args.source_root).resolve()
    output = Path(args.output)
    requirements_path = Path(args.requirements)
    timestamp = timestamp_value(args.timestamp)
    sbom = build_sbom(source_root, requirements_path, timestamp)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
