# -*- coding: utf-8 -*-
"""冻结包 A 在 macOS 改造前的 Windows 行为契约。"""

import contextlib
import io
import json
import queue
import socket
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"
ENGINE_DIR = PROG_DIR / "引擎"
WEB_DIR = PROG_DIR / "网站"
FIXTURES = TESTS_DIR / "fixtures"

for path in (PROG_DIR, ENGINE_DIR, WEB_DIR):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

import paths  # noqa: E402
import kt_align  # noqa: E402
import kt_video  # noqa: E402

# kt_web 当前在 import 时清理旧缓存。Phase 0 只测试契约，禁止测试导入删除用户数据。
with mock.patch("shutil.rmtree"):
    import kt_web  # noqa: E402


def _dots_missing():
    return {
        "root": None,
        "python": "",
        "prompts": PROG_DIR / "_语音引擎未安装",
        "port": 7860,
        "url": "http://127.0.0.1:7860",
        "installed": False,
    }


class FixtureContractTests(unittest.TestCase):
    def test_packaged_demo_wav_and_text_are_a_matched_pair(self):
        demo = PACKAGE_ROOT / "示范素材"
        result = kt_align.run_align(
            demo / "示范配音_梁文峰音色.wav",
            demo / "文稿.txt",
        )
        self.assertTrue(result["matched"])
        self.assertEqual(result["n_text_chunks"], 1)
        self.assertEqual(result["n_audio_spans"], 1)

    def test_wav_fixtures_are_small_pcm_files(self):
        expected = {
            "one_block.wav": (8_000, 1, 2, 9_600),
            "two_blocks.wav": (8_000, 1, 2, 6_800),
        }
        for name, contract in expected.items():
            with self.subTest(name=name):
                path = FIXTURES / name
                self.assertLess(path.stat().st_size, 25_000)
                with wave.open(str(path), "rb") as wav:
                    actual = (
                        wav.getframerate(),
                        wav.getnchannels(),
                        wav.getsampwidth(),
                        wav.getnframes(),
                    )
                self.assertEqual(actual, contract)

    def test_text_fixtures_are_utf8(self):
        self.assertEqual((FIXTURES / "one_block.txt").read_text(encoding="utf-8"), "你好，世界。\n")
        self.assertIn("M1 Pro", (FIXTURES / "mixed_utf8.txt").read_text(encoding="utf-8"))

    def test_damaged_wav_is_rejected_by_wave(self):
        with self.assertRaises((wave.Error, EOFError)):
            wave.open(str(FIXTURES / "damaged.wav"), "rb")


class AlignmentContractTests(unittest.TestCase):
    def test_build_chunks_preserves_joined_text_and_sentence_limit(self):
        text, chunks = kt_align.build_chunks("第一。\n第二。\n第三。", chunk=6)
        self.assertEqual(text, "第一。 第二。 第三。")
        self.assertEqual(chunks, ["第一。第二。", "第三。"])

    def test_one_block_fixture_matches(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = kt_align.run_align(FIXTURES / "one_block.wav", FIXTURES / "one_block.txt")
        self.assertTrue(result["matched"])
        self.assertEqual(result["n_text_chunks"], 1)
        self.assertEqual(result["n_audio_spans"], 1)
        self.assertAlmostEqual(result["audio_sec"], 1.2, places=3)

    def test_exact_quarter_second_silence_splits_two_blocks(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = kt_align.run_align(
                FIXTURES / "two_blocks.wav", FIXTURES / "two_blocks.txt", chunk=3
            )
        self.assertTrue(result["matched"])
        self.assertEqual(result["n_text_chunks"], 2)
        self.assertEqual(result["n_audio_spans"], 2)
        self.assertEqual([item["text"] for item in result["chunks"]], ["甲。", "乙。"])
        self.assertAlmostEqual(result["chunks"][0]["end"], 0.3, places=3)
        self.assertAlmostEqual(result["chunks"][1]["start"], 0.55, places=3)

    def test_audio_text_block_mismatch_is_explicit(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = kt_align.run_align(FIXTURES / "two_blocks.wav", FIXTURES / "mismatch.txt")
        self.assertFalse(result["matched"])
        self.assertEqual(result["n_text_chunks"], 1)
        self.assertEqual(result["n_audio_spans"], 2)


class TypographyContractTests(unittest.TestCase):
    def test_clean_text_removes_only_current_cjk_spacing_cases(self):
        self.assertEqual(kt_video.clean_text("你 好 ，  世 界  ! "), "你好，世界 !")

    def test_tokenize_mixed_text(self):
        self.assertEqual(
            kt_video.tokenize("A1.5，你。"),
            [
                ("A1.5", 2.2, False),
                ("，", 0.0, True),
                ("你", 1.0, False),
                ("。", 0.0, True),
            ],
        )

    def test_build_timeline_includes_zero_duration_punctuation(self):
        align = {"chunks": [{"start": 0.0, "end": 2.0, "text": "AB。CD。"}]}
        self.assertEqual(
            kt_video.build_timeline(align, pauses=[]),
            [
                ["AB", 0.0, 1.0, False, 0],
                ["。", 1.0, 1.0, True, 0],
                ["CD", 1.0, 2.0, False, 1],
                ["。", 2.0, 2.0, True, 1],
            ],
        )

    def test_build_cards_preserves_sentence_boundaries(self):
        timeline = [
            ["你", 0.0, 0.4, False, 0],
            ["，", 0.4, 0.4, True, 0],
            ["好", 0.4, 0.8, False, 0],
            ["世", 1.0, 1.4, False, 1],
            ["界", 1.4, 1.8, False, 1],
        ]
        cards = kt_video.build_cards(timeline)
        self.assertEqual(len(cards), 2)
        self.assertEqual("".join(token[0] for token in cards[0]), "你，好")
        self.assertEqual("".join(token[0] for token in cards[1]), "世界")

    def test_make_ass_matches_fixed_seed_snapshot(self):
        cards = [[
            ["你", 0.0, 0.5, False, 0],
            ["好", 0.5, 1.0, False, 0],
            ["。", 1.0, 1.0, True, 0],
        ]]
        actual = kt_video.make_ass(cards, offset=0.0, tmax=1.2, seed=7)
        expected = (FIXTURES / "expected_ass_seed7.ass").read_text(encoding="utf-8")
        self.assertEqual(actual, expected)
        self.assertIn(r"{\k50", actual)
        self.assertEqual(actual.count("Dialogue: "), 1)

    def test_ass_time_clamps_negative_values(self):
        self.assertEqual(kt_video.ass_time(-1.0), "0:00:00.00")
        self.assertEqual(kt_video.ass_time(61.25), "0:01:01.25")


class WebContractTests(unittest.TestCase):
    def test_valid_mp4_current_mdat_scan_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            small = root / "small.mp4"
            small.write_bytes(b"mdat")
            self.assertFalse(kt_web.valid_mp4(small))

            valid = root / "valid.mp4"
            valid.write_bytes(b"\x00" * 1_500 + b"mdat" + b"\x01" * 20)
            self.assertTrue(kt_web.valid_mp4(valid))

            missing = root / "missing.mp4"
            missing.write_bytes(b"\x00" * 1_600)
            self.assertFalse(kt_web.valid_mp4(missing))

            late = root / "late.mp4"
            late.write_bytes(b"\x00" * 524_288 + b"mdat")
            self.assertFalse(kt_web.valid_mp4(late))

    def test_invalid_wav_fails_before_video_generation(self):
        job_id = "invalid-wav"
        kt_web.jobs[job_id] = {"queue": queue.Queue(), "status": "running", "out": ""}
        try:
            with tempfile.TemporaryDirectory() as temp, \
                    mock.patch.object(kt_web, "WORK", Path(temp)), \
                    mock.patch.object(kt_web.kt_video, "generate") as generate:
                kt_web.run_job(job_id, b"not-a-wave", "测试", {})
            event = kt_web.jobs[job_id]["queue"].get_nowait()
            self.assertEqual(event["type"], "error")
            self.assertIn("录音文件不是有效的 WAV", event["msg"])
            generate.assert_not_called()
        finally:
            kt_web.jobs.pop(job_id, None)

    def test_dots_status_is_not_installed_without_package_b(self):
        handler = object.__new__(kt_web.Handler)
        with mock.patch.object(kt_web, "_dots", side_effect=_dots_missing), \
                mock.patch.object(handler, "dots_pid", return_value=None), \
                mock.patch.object(handler, "_send") as send:
            handler.handle_dots_status()
        code, body = send.call_args.args[:2]
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(code, 200)
        self.assertEqual(payload["state"], "not_installed")
        self.assertFalse(payload["installed"])

    def test_tts_request_fails_friendly_without_package_b(self):
        job_id = "tts-missing"
        kt_web.jobs[job_id] = {"queue": queue.Queue(), "status": "running", "out": ""}
        try:
            with tempfile.TemporaryDirectory() as temp, \
                    mock.patch.object(kt_web, "WORK", Path(temp)), \
                    mock.patch.object(kt_web, "_dots", side_effect=_dots_missing):
                kt_web.run_tts(job_id, "测试", "", {})
            event = kt_web.jobs[job_id]["queue"].get_nowait()
            self.assertEqual(event["type"], "error")
            self.assertIn("未检测到语音引擎", event["msg"])
            self.assertEqual(kt_web.jobs[job_id]["status"], "error")
        finally:
            kt_web.jobs.pop(job_id, None)


class WindowsBoundaryContractTests(unittest.TestCase):
    def test_current_packaged_tool_paths_and_missing_dots(self):
        self.assertEqual(Path(paths.FFMPEG), PROG_DIR / "bin" / "ffmpeg.exe")
        self.assertEqual(paths.FONTNAME, "SimHei")
        self.assertTrue((PROG_DIR / "runtime" / "python.exe").is_file())
        self.assertTrue(Path(paths.FFMPEG).is_file())
        with mock.patch.object(paths, "cfg_get", side_effect=lambda _s, _k, default="": default):
            self.assertFalse(paths.dots_info()["installed"])

    def test_windows_launcher_contract(self):
        launcher = (PACKAGE_ROOT / "①开始使用.bat").read_text(encoding="utf-8-sig")
        for fragment in (
            r"程序文件\runtime\python.exe",
            r"程序文件\bin\ffmpeg.exe",
            r"程序文件\fonts\simhei.ttf",
            r"程序文件\网站\kt_web.py",
            "http://127.0.0.1:8787",
        ):
            self.assertIn(fragment, launcher)

    def test_render_video_keeps_current_ffmpeg_contract(self):
        captured = {}

        class FakeProcess:
            def __init__(self, command, **kwargs):
                captured["command"] = command
                captured["environment"] = kwargs["env"]
                self.stdout = io.StringIO("")
                self.stderr = io.StringIO("")
                self.returncode = 0

            def wait(self):
                return 0

        staged = contextlib.nullcontext((Path("stage"), "subtitle.ass", "fonts"))
        with mock.patch.object(kt_video, "stage_render_assets", return_value=staged), \
                mock.patch.object(kt_video.subprocess, "Popen", FakeProcess):
            kt_video.render_video(
                Path("字幕.ass"), Path("输入.wav"), Path("输出.mp4"), 1.25, 2.5, crf="20"
            )

        command = captured["command"]
        self.assertEqual(command[0], paths.FFMPEG)
        self.assertIn("color=c=black:s=1080x1920:r=25", command)
        self.assertIn("subtitles=", command[command.index("-filter_complex") + 1])
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertEqual(command[command.index("-preset") + 1], "medium")
        self.assertEqual(command[command.index("-crf") + 1], "20")
        self.assertEqual(command[command.index("-c:a") + 1], "aac")
        self.assertEqual(command[command.index("-ar") + 1], "48000")
        self.assertIn("[v]", command)
        self.assertIn("1:a", command)
        self.assertEqual(command[-1], str(Path("输出.mp4").resolve()))
        self.assertEqual(captured["environment"]["FONTCONFIG_PATH"], "C:/Windows/Fonts")

    def test_web_main_retries_next_port_and_records_actual_port(self):
        attempts = []

        class FakeServer:
            served = False

            def serve_forever(self):
                self.served = True

        server = FakeServer()

        def bind(address, _handler):
            attempts.append(address)
            if len(attempts) == 1:
                raise OSError("occupied")
            return server

        original_port = kt_web.PORT
        kt_web.PORT = 10_000
        try:
            with mock.patch.object(kt_web, "ThreadingHTTPServer", side_effect=bind), \
                    mock.patch.object(Path, "write_text", return_value=5) as write_port, \
                    mock.patch.object(socket, "socket", side_effect=OSError), \
                    contextlib.redirect_stdout(io.StringIO()):
                kt_web.main()
            self.assertEqual(attempts, [("0.0.0.0", 10_000), ("0.0.0.0", 10_001)])
            self.assertEqual(kt_web.PORT, 10_001)
            self.assertTrue(server.served)
            write_port.assert_called_once_with("10001", encoding="utf-8")
        finally:
            kt_web.PORT = original_port


if __name__ == "__main__":
    unittest.main()
