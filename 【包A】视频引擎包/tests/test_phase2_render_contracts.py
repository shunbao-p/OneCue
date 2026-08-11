# -*- coding: utf-8 -*-
"""Phase 2 渲染命令、路径转义和字体环境契约。"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"
ENGINE_DIR = PROG_DIR / "引擎"

for directory in (PROG_DIR, ENGINE_DIR):
    value = str(directory)
    if value not in sys.path:
        sys.path.insert(0, value)

import kt_video  # noqa: E402
import platform_support  # noqa: E402


class FilterPathTests(unittest.TestCase):
    def test_stage_accepts_special_source_paths_and_exposes_safe_filter_names(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = "中文 空格 引号'"
            if os.name != "nt":
                directory += " 冒号: 反斜杠\\"
            source = Path(temp) / directory
            fonts = source / "字体 目录"
            fonts.mkdir(parents=True)
            ass = source / "字幕.ass"
            ass.write_text("subtitle", encoding="utf-8")
            (fonts / "simhei.ttf").write_bytes(b"font")

            with kt_video.stage_render_assets(ass, fonts) as staged:
                cwd, staged_ass, staged_fonts = staged
                self.assertEqual(staged_ass, "subtitle.ass")
                self.assertEqual(staged_fonts, "fonts")
                self.assertEqual((cwd / staged_ass).read_text(encoding="utf-8"), "subtitle")
                self.assertEqual((cwd / staged_fonts / "simhei.ttf").read_bytes(), b"font")
            self.assertFalse(cwd.exists())

    def test_build_command_keeps_paths_as_single_arguments(self):
        command = kt_video.build_ffmpeg_command(
            "/opt/tool chain/ffmpeg",
            "subtitle.ass",
            Path("音频 目录") / "中文 输入.wav",
            Path("输出 目录") / "成片.mp4",
            "fonts",
            1.25,
            2.5,
            crf="20",
        )

        self.assertEqual(command[0], "/opt/tool chain/ffmpeg")
        self.assertIn(str((Path("音频 目录") / "中文 输入.wav").resolve()), command)
        self.assertEqual(command[-1], str((Path("输出 目录") / "成片.mp4").resolve()))
        filter_graph = command[command.index("-filter_complex") + 1]
        self.assertEqual(
            filter_graph,
            "[0:v]subtitles=filename='subtitle.ass':fontsdir='fonts'[v]",
        )
        self.assertNotIn("C:/Windows/Fonts", filter_graph)
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertEqual(command[command.index("-preset") + 1], "medium")
        self.assertEqual(command[command.index("-c:a") + 1], "aac")
        self.assertEqual(command[command.index("-ar") + 1], "48000")
        self.assertNotIn("h264_videotoolbox", command)

    def test_build_command_rejects_invalid_ranges(self):
        common = ("ffmpeg", "a.ass", "a.wav", "a.mp4", "fonts")
        for start, duration, crf in ((-0.1, 1.0, "20"), (0.0, 0.0, "20"), (0.0, 1.0, "52")):
            with self.subTest(start=start, duration=duration, crf=crf):
                with self.assertRaises(ValueError):
                    kt_video.build_ffmpeg_command(*common, start, duration, crf=crf)

    def test_build_command_rejects_unstaged_filter_paths(self):
        with self.assertRaisesRegex(ValueError, "暂存"):
            kt_video.build_ffmpeg_command(
                "ffmpeg", "导演's:字幕.ass", "a.wav", "a.mp4", "fonts", 0, 1
            )


class RenderEnvironmentTests(unittest.TestCase):
    def test_darwin_font_environment_removes_stale_windows_value(self):
        result = kt_video.build_ffmpeg_environment(
            {"FONTCONFIG_PATH": "C:/Windows/Fonts", "KEEP": "yes"},
            {},
        )
        self.assertEqual(result, {"KEEP": "yes"})

    def test_windows_font_environment_is_reapplied_from_platform_config(self):
        result = kt_video.build_ffmpeg_environment(
            {"FONTCONFIG_PATH": "stale", "KEEP": "yes"},
            {"FONTCONFIG_PATH": platform_support.WINDOWS_FONTCONFIG_PATH},
        )
        self.assertEqual(result["FONTCONFIG_PATH"], "C:/Windows/Fonts")
        self.assertEqual(result["KEEP"], "yes")


class RenderExecutionTests(unittest.TestCase):
    def test_direct_wav_text_generation_rejects_unmatched_alignment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wav = root / "input.wav"
            txt = root / "input.txt"
            wav.write_bytes(b"RIFF" + b"\0" * 64)
            txt.write_text("不匹配。", encoding="utf-8")
            with mock.patch.object(
                kt_video.kt_align,
                "run_align",
                return_value={"matched": False, "n_text_chunks": 2, "n_audio_spans": 1, "chunks": []},
            ), self.assertRaisesRegex(ValueError, "音频与文本块数不匹配"):
                kt_video.generate(wav_path=wav, txt_path=txt, out=root / "out.mp4")

    class FakeProcess:
        def __init__(self, command, returncode=0, error_text="", **kwargs):
            self.command = command
            self.kwargs = kwargs
            self.stdout = io.StringIO("")
            self.stderr = io.StringIO(error_text)
            self.returncode = returncode

        def wait(self):
            return self.returncode

    def test_render_resolves_tool_at_call_time_and_uses_platform_font_environment(self):
        captured = {}

        def popen(command, **kwargs):
            captured["command"] = command
            captured["environment"] = kwargs["env"]
            captured["cwd"] = kwargs["cwd"]
            return self.FakeProcess(command, **kwargs)

        with mock.patch.object(kt_video._paths, "resolve_ffmpeg", return_value="/opt/homebrew/bin/ffmpeg"), \
                mock.patch.object(kt_video._paths, "FONTSDIR", "/tmp/中文 字体"), \
                mock.patch.object(kt_video._paths, "FONT_ENV", {}), \
                mock.patch.object(
                    kt_video,
                    "stage_render_assets",
                    return_value=contextlib.nullcontext((Path("/tmp/stage"), "subtitle.ass", "fonts")),
                ), \
                mock.patch.object(kt_video.subprocess, "Popen", side_effect=popen), \
                mock.patch.dict(kt_video.os.environ, {"FONTCONFIG_PATH": "C:/Windows/Fonts"}, clear=True):
            kt_video.render_video("a.ass", "a.wav", "a.mp4", 0.0, 1.0)

        self.assertEqual(captured["command"][0], "/opt/homebrew/bin/ffmpeg")
        self.assertNotIn("FONTCONFIG_PATH", captured["environment"])
        self.assertEqual(captured["cwd"], str(Path("/tmp/stage")))

    def test_detect_pauses_reports_missing_ffmpeg_before_spawning(self):
        error = platform_support.ToolResolutionError("ffmpeg", ["PATH:ffmpeg"])
        with mock.patch.object(kt_video._paths, "resolve_ffmpeg", side_effect=error), \
                mock.patch.object(kt_video.subprocess, "run") as run:
            with self.assertRaisesRegex(platform_support.ToolResolutionError, "ffmpeg"):
                kt_video.detect_pauses("a.wav")
        run.assert_not_called()

    def test_render_preserves_actionable_ffmpeg_error(self):
        process = self.FakeProcess([], returncode=1, error_text="Unknown encoder 'libx264'\n")
        with mock.patch.object(kt_video._paths, "resolve_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(
                    kt_video,
                    "stage_render_assets",
                    return_value=contextlib.nullcontext((Path("/tmp/stage"), "subtitle.ass", "fonts")),
                ), \
                mock.patch.object(kt_video.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "Unknown encoder.*libx264"):
                kt_video.render_video("a.ass", "a.wav", "a.mp4", 0.0, 1.0)


if __name__ == "__main__":
    unittest.main()
