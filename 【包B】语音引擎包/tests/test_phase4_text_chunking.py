from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
for import_root in (PACKAGE_ROOT, SRC_ROOT):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from dots_tts.runtime import split_text_chunks
from apps.gradio.service import chunk_chars_for_device


class Phase4TextChunkingTests(unittest.TestCase):
    def test_keeps_short_text_unchanged(self):
        self.assertEqual(split_text_chunks("短句不应被拆分。", 32), ["短句不应被拆分。"])

    def test_prefers_clause_boundaries_and_respects_hard_limit(self):
        text = "第一段包含逗号，第二段继续说明；第三段最后结束。"
        chunks = split_text_chunks(text, 12)

        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(0 < len(chunk) <= 12 for chunk in chunks))
        self.assertTrue(chunks[0].endswith("，"))

    def test_hard_splits_one_overlong_unpunctuated_unit(self):
        text = "甲" * 73
        chunks = split_text_chunks(text, 24)

        self.assertEqual([len(chunk) for chunk in chunks], [24, 24, 24, 1])
        self.assertEqual("".join(chunks), text)

    def test_rejects_non_positive_limit(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "max_chars_per_chunk"):
                    split_text_chunks("测试", limit)

    def test_mps_uses_evidence_backed_short_chunks_only_on_mps(self):
        self.assertEqual(chunk_chars_for_device("mps"), 32)
        self.assertEqual(chunk_chars_for_device("cpu"), 120)
        self.assertEqual(chunk_chars_for_device("cuda"), 120)



if __name__ == "__main__":
    unittest.main()
