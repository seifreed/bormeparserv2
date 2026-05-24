#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2026 Marc Rivero Lopez <mriverolopez@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# test_licensing.py - Regressions for fork licensing metadata.

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GPL_SPDX = "SPDX-License-Identifier: GPL-3.0-or-later"


def _python_files():
    for root in ("bormeparserv2", "scripts"):
        base = os.path.join(REPO_ROOT, root)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [name for name in dirnames if name != "__pycache__"]
            for filename in filenames:
                if filename.endswith(".py"):
                    yield os.path.join(dirpath, filename)
    yield os.path.join(REPO_ROOT, "setup.py")
    yield os.path.join(REPO_ROOT, "docs", "conf.py")


class LicensingMetadataTestCase(unittest.TestCase):
    def test_python_files_use_gpl_spdx_headers(self):
        missing_license = []
        missing_copyright = []
        mit_headers = []

        for path in sorted(_python_files()):
            with open(path, encoding="utf-8") as fp:
                head = "".join(fp.readlines()[:20])
            relative = os.path.relpath(path, REPO_ROOT)
            if GPL_SPDX not in head:
                missing_license.append(relative)
            if "SPDX-FileCopyrightText:" not in head:
                missing_copyright.append(relative)
            if "SPDX-License-Identifier: MIT" in head:
                mit_headers.append(relative)

        self.assertEqual(missing_license, [])
        self.assertEqual(missing_copyright, [])
        self.assertEqual(mit_headers, [])

    def test_readme_documents_fork_license_policy(self):
        with open(os.path.join(REPO_ROOT, "README.md"), encoding="utf-8") as fp:
            readme = fp.read()

        self.assertIn("GPL-3.0-or-later", readme)
        self.assertIn("PabloCastellano/bormeparser", readme)
        self.assertIn("No se relicencia a MIT", readme)


if __name__ == "__main__":
    unittest.main()
