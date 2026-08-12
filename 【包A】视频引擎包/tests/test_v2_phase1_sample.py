# -*- coding: utf-8 -*-
"""计划 01 临时三镜头契约与实验渲染器测试。"""

import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
MODULE_PATH = (
    PACKAGE_ROOT / "experiments" / "short_video_v2_phase1" / "render_sample.py"
)

SPEC = importlib.util.spec_from_file_location("v2_phase1_render_sample", MODULE_PATH)
render_sample = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_sample)


def valid_storyboard():
    shots = []
    for number, preset in enumerate(
        ("slow_push_in", "gentle_drift", "slow_pull_out"), start=1
    ):
        shot_id = f"shot-{number:03d}"
        shots.append(
            {
                "id": shot_id,
                "narration": f"第{number}段旁白。",
                "image": f"assets/keyframes/{shot_id}.png",
                "motion_preset": preset,
                "focus": {"x": 0.5, "y": 0.45},
                "head_pad_sec": 0.15,
                "tail_pad_sec": 0.25,
                "caption": f"第{number}段旁白。",
            }
        )
    return {
        "sample_version": "phase1-experimental-1",
        "title": "测试样片",
        "resolution": {"width": 1080, "height": 1920},
        "fps": 30,
        "package_a_url": "http://127.0.0.1:8787",
        "voice": "女播音.wav",
        "shots": shots,
    }


class StoryboardValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job_dir = Path(self.temp.name).resolve()
        for number in range(1, 4):
            image = self.job_dir / "assets" / "keyframes" / f"shot-{number:03d}.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"not-decoded-in-unit-tests")

    def load(self, payload=None):
        storyboard = self.job_dir / "storyboard.sample.json"
        storyboard.write_text(
            json.dumps(payload or valid_storyboard(), ensure_ascii=False),
            encoding="utf-8",
        )
        return render_sample.load_storyboard(self.job_dir, storyboard)

    def test_valid_contract_resolves_only_job_local_images(self):
        document = self.load()
        self.assertEqual(len(document["shots"]), 3)
        for shot in document["shots"]:
            image = shot["image_path"]
            self.assertTrue(image.is_relative_to(self.job_dir))
            self.assertTrue(image.is_file())

    def test_rejects_unknown_top_level_and_shot_fields(self):
        payload = valid_storyboard()
        payload["provider_registry"] = {}
        with self.assertRaisesRegex(ValueError, "未知顶层字段"):
            self.load(payload)

        payload = valid_storyboard()
        payload["shots"][0]["filtergraph"] = "arbitrary"
        with self.assertRaisesRegex(ValueError, "未知镜头字段"):
            self.load(payload)

    def test_requires_exactly_three_unique_shot_ids(self):
        payload = valid_storyboard()
        payload["shots"].pop()
        with self.assertRaisesRegex(ValueError, "恰有 3 个镜头"):
            self.load(payload)

        payload = valid_storyboard()
        payload["shots"][1]["id"] = "shot-001"
        with self.assertRaisesRegex(ValueError, "镜头 ID"):
            self.load(payload)

    def test_rejects_escape_path_symlink_and_absolute_path(self):
        outside = self.job_dir.parent / "outside.png"
        outside.write_bytes(b"outside")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))

        for unsafe in ("../outside.png", str(outside)):
            payload = valid_storyboard()
            payload["shots"][0]["image"] = unsafe
            with self.subTest(unsafe=unsafe), self.assertRaisesRegex(ValueError, "任务目录"):
                self.load(payload)

        link = self.job_dir / "assets" / "keyframes" / "escape.png"
        link.symlink_to(outside)
        payload = valid_storyboard()
        payload["shots"][0]["image"] = "assets/keyframes/escape.png"
        with self.assertRaisesRegex(ValueError, "任务目录"):
            self.load(payload)

    def test_rejects_empty_narration_unknown_preset_and_bad_focus(self):
        payload = valid_storyboard()
        payload["shots"][0]["narration"] = "  "
        with self.assertRaisesRegex(ValueError, "旁白不能为空"):
            self.load(payload)

        payload = valid_storyboard()
        payload["shots"][0]["motion_preset"] = "run_any_shell"
        with self.assertRaisesRegex(ValueError, "运镜预设"):
            self.load(payload)

        for value in (-0.1, 1.1, math.inf, math.nan):
            payload = valid_storyboard()
            payload["shots"][0]["focus"]["x"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "focus"):
                self.load(payload)


class RenderingContractTests(unittest.TestCase):
    def test_motion_filters_are_fixed_and_duration_aware(self):
        for preset in render_sample.MOTION_PRESETS:
            result = render_sample.build_video_filter(
                preset=preset,
                focus={"x": 0.5, "y": 0.45},
                duration=4.0,
                fps=30,
                subtitle_name="caption.ass",
            )
            self.assertIn("zoompan=", result)
            self.assertIn("s=1080x1920", result)
            self.assertIn("subtitles=", result)
            self.assertNotIn("run_any_shell", result)

    def test_ass_escaping_and_timing(self):
        ass = render_sample.render_ass(
            [(0.15, 2.35, "大雨{将至}\\城门")], title="字幕测试"
        )
        self.assertIn("0:00:00.15", ass)
        self.assertIn("0:00:02.35", ass)
        self.assertIn(r"大雨\{将至\}\\城门", ass)
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)

    def test_long_chinese_caption_wraps_once_near_punctuation(self):
        text = "城门闭合前，守军认出了信物，第一盏警灯终于亮起。"
        wrapped = render_sample.wrap_caption(text)
        self.assertEqual(wrapped.count("\n"), 1)
        first, second = wrapped.splitlines()
        self.assertLessEqual(len(first), 16)
        self.assertLessEqual(len(second), 16)
        ass = render_sample.render_ass([(0.15, 2.35, text)], title="两行字幕")
        self.assertIn(r"守军认出了信物，\N第一盏警灯", ass)

    def test_base_report_has_required_trace_fields(self):
        report = render_sample.base_report(
            job_dir=Path("/tmp/sample").resolve(),
            storyboard_sha256="abc",
            git_info={"head": "deadbeef", "status": []},
            tools={"python": "3.x", "ffmpeg": {}, "ffprobe": {}},
        )
        for key in (
            "sample_version",
            "status",
            "started_at",
            "job_dir",
            "storyboard_sha256",
            "git",
            "tools",
            "services",
            "shots",
            "warnings",
            "errors",
            "output",
        ):
            self.assertIn(key, report)

    def test_source_never_enables_shell_execution(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)


if __name__ == "__main__":
    unittest.main()
