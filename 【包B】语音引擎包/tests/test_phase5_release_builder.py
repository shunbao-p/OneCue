from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = PACKAGE_ROOT / "_internal/build_macos_release.py"
SPEC = importlib.util.spec_from_file_location("package_b_release_builder", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class ReleaseCopyTests(unittest.TestCase):
    def test_browser_preview_uses_bundled_aac_encoder(self):
        source = (PACKAGE_ROOT / "apps/gradio/app.py").read_text(encoding="utf-8")

        self.assertIn('preview = cache_dir / f"preview_{fingerprint}.m4a"', source)
        self.assertIn('"-codec:a", "aac"', source)
        self.assertNotIn("libmp3lame", source)

    def test_copy_excludes_windows_runtime_transients_and_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "release" / "【包B】语音引擎包"
            fixtures = {
                "启动-快速版.command": b"#!/bin/zsh\n",
                "src/keep.py": b"pass\n",
                "pretrained_models/dots-tts-mf/config.json": b"{}\n",
                "wzf/python.exe": b"windows",
                "启动-快速版.bat": b"windows",
                "src/native.pyd": b"windows",
                "tests/test_sample.py": b"pass\n",
                "outputs/old.wav": b"old",
                "__pycache__/old.pyc": b"old",
            }
            for relative, content in fixtures.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            BUILDER.copy_release(source, destination)

            self.assertTrue((destination / "启动-快速版.command").is_file())
            self.assertTrue((destination / "src/keep.py").is_file())
            self.assertTrue((destination / "pretrained_models/dots-tts-mf/config.json").is_file())
            self.assertFalse((destination / "wzf").exists())
            self.assertFalse((destination / "启动-快速版.bat").exists())
            self.assertFalse((destination / "src/native.pyd").exists())
            self.assertFalse((destination / "tests").exists())
            self.assertFalse((destination / "__pycache__").exists())
            self.assertEqual(list((destination / "outputs").iterdir()), [])
            self.assertTrue((destination / "启动-快速版.command").stat().st_mode & 0o111)

    def test_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            destination = root / "release"
            source.mkdir()
            destination.mkdir()
            with self.assertRaises(BUILDER.BuildError):
                BUILDER.copy_release(source, destination)

    def test_source_parent_named_build_does_not_hide_release_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "build" / "source"
            destination = Path(temp) / "release" / "【包B】语音引擎包"
            root.mkdir(parents=True)
            (root / "启动-快速版.command").write_text("#!/bin/zsh\n", encoding="utf-8")

            BUILDER.copy_release(root, destination)

            self.assertTrue((destination / "启动-快速版.command").is_file())


if __name__ == "__main__":
    unittest.main()
