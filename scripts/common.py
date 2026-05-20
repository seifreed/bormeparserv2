#!/usr/bin/env python
#
# common.py - Common functions for bormeparserv2 scripts
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

import os

_HASH_LEN = 7
_UNKNOWN = "Unknown"


def _resolve_ref(git_dir: str, ref: str) -> str | None:
    """Resuelve la SHA de una referencia git mirando primero el fichero
    suelto bajo ``.git/<ref>`` y, si no existe, en ``.git/packed-refs``."""
    loose = os.path.join(git_dir, ref)
    if os.path.exists(loose):
        with open(loose, "r", encoding="utf-8") as fp:
            return fp.read().strip() or None
    packed = os.path.join(git_dir, "packed-refs")
    if not os.path.exists(packed):
        return None
    with open(packed, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            sha, _, name = line.partition(" ")
            if name == ref:
                return sha
    return None


def get_git_revision_short_hash() -> str:
    """Devuelve el hash corto de la revisión git actual leyendo los ficheros
    bajo ``.git/`` directamente. Devuelve ``"Unknown"`` si no estamos en un
    repositorio o algo falla."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git_dir = os.path.join(repo_root, ".git")
    head_path = os.path.join(git_dir, "HEAD")
    if not os.path.exists(head_path):
        return _UNKNOWN
    try:
        with open(head_path, "r", encoding="utf-8") as fp:
            head = fp.read().strip()
        if head.startswith("ref: "):
            sha = _resolve_ref(git_dir, head[len("ref: ") :])
        else:
            sha = head
    except OSError:
        return _UNKNOWN
    if not sha:
        return _UNKNOWN
    return sha[:_HASH_LEN]
