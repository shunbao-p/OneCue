from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.gradio.service import discover_prompt_presets, sync_default_prompt_library


class PromptLibrarySeedTests(unittest.TestCase):
    def test_seed_adds_missing_defaults_without_deleting_or_overwriting_user_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()

            (source / "女播音.wav").write_bytes(b"default-audio")
            (source / "prompt_text").write_text("女播音 | 默认文本\n", encoding="utf-8")
            (target / "用户音色.wav").write_bytes(b"user-audio")
            (target / "prompt_text").write_text("用户音色 | 用户文本\n", encoding="utf-8")

            sync_default_prompt_library(source, target)

            self.assertEqual((target / "用户音色.wav").read_bytes(), b"user-audio")
            self.assertEqual(
                (target / "prompt_text").read_text(encoding="utf-8"),
                "用户音色 | 用户文本\n",
            )
            self.assertEqual((target / "女播音.wav").read_bytes(), b"default-audio")

    def test_empty_library_is_seeded_with_discoverable_default_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "女播音.wav").write_bytes(b"default-audio")
            (source / "prompt_text").write_text("女播音 | 默认文本\n", encoding="utf-8")

            sync_default_prompt_library(source, target)
            presets = discover_prompt_presets(target, target / "prompt_text")

            self.assertEqual(len(presets), 1)
            self.assertEqual(presets[0].name, "女播音")
            self.assertEqual(presets[0].prompt_text, "默认文本")


if __name__ == "__main__":
    unittest.main()
