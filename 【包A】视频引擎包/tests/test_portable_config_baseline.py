# -*- coding: utf-8 -*-
"""Portable package-A configuration contracts for local development."""

import configparser
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
REPO_ROOT = PACKAGE_ROOT.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"

if str(PROG_DIR) not in sys.path:
    sys.path.insert(0, str(PROG_DIR))

import paths  # noqa: E402


class PortableConfigBaselineTests(unittest.TestCase):
    def test_missing_local_config_uses_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "config.ini"
            with mock.patch.object(paths, "CONFIG_FILE", missing):
                self.assertEqual(paths.cfg_get("server", "port", "8787"), "8787")
                self.assertEqual(paths.cfg_get("dots", "root", ""), "")

    def test_local_config_takes_priority_over_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp) / "config.ini"
            local.write_text(
                "[server]\nport = 9898\n\n[dots]\nroot = /portable/test/package-b\nport = 7979\n",
                encoding="utf-8",
            )
            with mock.patch.object(paths, "CONFIG_FILE", local):
                self.assertEqual(paths.cfg_get("server", "port", "8787"), "9898")
                self.assertEqual(paths.cfg_get("dots", "root", ""), "/portable/test/package-b")
                self.assertEqual(paths.cfg_get("dots", "port", "7860"), "7979")

    def test_public_template_contains_no_machine_specific_path(self):
        template = PROG_DIR / "config.example.ini"
        self.assertTrue(template.is_file())
        parser = configparser.ConfigParser()
        parser.read(template, encoding="utf-8")
        self.assertEqual(parser.get("server", "port"), "8787")
        self.assertEqual(parser.get("dots", "root"), "")
        self.assertEqual(parser.get("dots", "port"), "7860")
        text = template.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn("C:\\", text)

    def test_real_config_is_ignored_at_repository_boundary(self):
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("/【包A】视频引擎包/程序文件/config.ini", ignored)

if __name__ == "__main__":
    unittest.main()
