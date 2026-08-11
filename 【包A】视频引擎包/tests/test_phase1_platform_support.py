# -*- coding: utf-8 -*-
"""Phase 1 薄平台边界契约；不需要真实 macOS 工具或包 B。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"

if str(PROG_DIR) not in sys.path:
    sys.path.insert(0, str(PROG_DIR))

import diag  # noqa: E402
import paths  # noqa: E402
import platform_support  # noqa: E402


def _make_executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"tool")
    path.chmod(0o755)
    return path


class SystemIdentificationTests(unittest.TestCase):
    def test_normalizes_windows_darwin_and_wsl(self):
        self.assertEqual(platform_support.current_system("Windows", ""), "windows")
        self.assertEqual(platform_support.current_system("Darwin", ""), "darwin")
        self.assertEqual(platform_support.current_system("Linux"), "linux")
        self.assertEqual(
            platform_support.current_system("Linux", "5.15.0-microsoft-standard-WSL2"),
            "windows",
        )


class ToolResolutionTests(unittest.TestCase):
    def test_explicit_unicode_space_path_has_highest_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "中文 工具"
            explicit = _make_executable(root / "ffmpeg")
            bundled = _make_executable(root / "bin" / "ffmpeg")
            actual = platform_support.resolve_ffmpeg(
                root / "bin",
                explicit=explicit,
                env={},
                system="Darwin",
                which=lambda _name: str(bundled),
                required=True,
            )
        self.assertEqual(actual, str(explicit.resolve()))

    def test_invalid_explicit_configuration_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = _make_executable(root / "bin" / "ffmpeg")
            missing = root / "错误 路径" / "ffmpeg"
            with self.assertRaises(platform_support.ToolResolutionError) as caught:
                platform_support.resolve_ffmpeg(
                    root / "bin",
                    explicit=missing,
                    env={},
                    system="Darwin",
                    which=lambda _name: str(bundled),
                    required=True,
                )
        message = str(caught.exception)
        self.assertIn("显式配置不可用", message)
        self.assertIn(str(missing), message)

    def test_bundled_tool_wins_before_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = _make_executable(root / "bin" / "ffmpeg.exe")
            path_tool = _make_executable(root / "path" / "ffmpeg.exe")
            actual = platform_support.resolve_ffmpeg(
                root / "bin",
                env={},
                system="Windows",
                which=lambda _name: str(path_tool),
                required=True,
            )
        self.assertEqual(actual, str(bundled.resolve()))

    def test_path_wins_before_controlled_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path_tool = _make_executable(root / "path" / "ffmpeg")
            controlled = _make_executable(root / "controlled" / "ffmpeg")
            actual = platform_support.resolve_executable(
                "ffmpeg",
                bundled_paths=(root / "missing" / "ffmpeg",),
                path_names=("ffmpeg",),
                controlled_paths=(controlled,),
                env={},
                system="Darwin",
                which=lambda name: str(path_tool) if name == "ffmpeg" else None,
                required=True,
            )
        self.assertEqual(actual, str(path_tool.resolve()))

    def test_controlled_candidate_is_last_successful_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            controlled = _make_executable(Path(temp) / "受控" / "ffprobe")
            actual = platform_support.resolve_executable(
                "ffprobe",
                path_names=("ffprobe",),
                controlled_paths=(controlled,),
                env={},
                system="Darwin",
                which=lambda _name: None,
                required=True,
            )
        self.assertEqual(actual, str(controlled.resolve()))

    def test_missing_tool_error_lists_search_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(platform_support.ToolResolutionError) as caught:
                platform_support.resolve_ffprobe(
                    root / "bin",
                    env={},
                    system="Windows",
                    which=lambda _name: None,
                    required=True,
                )
        message = str(caught.exception)
        self.assertIn("ffprobe", message)
        self.assertIn("ffprobe.exe", message)
        self.assertIn("PATH:", message)

    def test_python_release_and_development_priorities(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            windows_bundle = _make_executable(root / "runtime" / "python.exe")
            path_python = _make_executable(root / "path" / "python.exe")
            release = platform_support.resolve_python_runtime(
                root / "runtime",
                env={},
                system="Windows",
                which=lambda _name: str(path_python),
                executable=str(path_python),
                required=True,
            )

            darwin_bundle = _make_executable(root / "darwin-runtime" / "bin" / "python3")
            development_python = _make_executable(root / "开发 Python" / "python3")
            development = platform_support.resolve_python_runtime(
                root / "darwin-runtime",
                development=True,
                executable=str(development_python),
                env={},
                system="Darwin",
                which=lambda _name: None,
                required=True,
            )
        self.assertEqual(release, str(windows_bundle.resolve()))
        self.assertEqual(development, str(development_python.resolve()))
        self.assertNotEqual(development, str(darwin_bundle.resolve()))

    def test_python_release_uses_path_before_controlled_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path_python = _make_executable(root / "PATH 工具" / "python3")
            controlled = _make_executable(root / "受控" / "python3")
            actual = platform_support.resolve_executable(
                "python",
                bundled_paths=(root / "runtime" / "bin" / "python3",),
                path_names=("python3",),
                controlled_paths=(controlled,),
                env={},
                system="Darwin",
                which=lambda name: str(path_python) if name == "python3" else None,
                required=True,
            )
        self.assertEqual(actual, str(path_python.resolve()))


class FontAndCommandTests(unittest.TestCase):
    def test_font_config_keeps_windows_environment_and_darwin_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            fonts = Path(temp) / "中文 字体"
            fonts.mkdir()
            (fonts / "simhei.ttf").write_bytes(b"font")
            windows = platform_support.font_config(fonts, env={}, system="Windows")
            darwin = platform_support.font_config(fonts, env={}, system="Darwin")
        self.assertEqual(windows["fonts_dir"], str(fonts))
        self.assertEqual(windows["font_name"], "SimHei")
        self.assertEqual(
            windows["environment"],
            {"FONTCONFIG_PATH": platform_support.WINDOWS_FONTCONFIG_PATH},
        )
        self.assertEqual(darwin["environment"], {})
        self.assertEqual(darwin["candidates"], [str(fonts)])

    def test_file_manager_commands_are_argument_arrays(self):
        target = Path("/tmp/项目 空格/成片.mp4")
        self.assertEqual(
            platform_support.build_open_command(target, select=True, system="Windows"),
            ["explorer", f"/select,{target}"],
        )
        self.assertEqual(
            platform_support.build_open_command(target, select=True, system="Darwin"),
            ["/usr/bin/open", "-R", str(target)],
        )
        self.assertEqual(
            platform_support.build_open_command(target.parent, system="Darwin"),
            ["/usr/bin/open", str(target.parent)],
        )

    def test_open_file_manager_passes_only_argument_list(self):
        calls = []

        def fake_popen(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        platform_support.open_in_file_manager(
            "/tmp/中文 文件.mp4",
            select=True,
            system="Darwin",
            popen=fake_popen,
        )
        self.assertEqual(
            calls,
            [((["/usr/bin/open", "-R", str(Path("/tmp/中文 文件.mp4"))],), {})],
        )

    def test_listener_and_process_commands_are_platform_specific_arrays(self):
        self.assertEqual(
            platform_support.listener_diagnostic_command(8787, system="Windows"),
            ["netstat", "-ano"],
        )
        self.assertEqual(
            platform_support.listener_diagnostic_command(8787, system="Darwin"),
            ["/usr/sbin/lsof", "-nP", "-iTCP:8787", "-sTCP:LISTEN"],
        )
        self.assertEqual(
            platform_support.process_termination_command(123, force=True, system="Windows"),
            ["taskkill", "/PID", "123", "/T", "/F"],
        )
        self.assertEqual(
            platform_support.process_termination_command(123, system="Darwin"),
            ["kill", "-TERM", "123"],
        )

    def test_port_candidates_preserve_production_retry_contract(self):
        self.assertEqual(list(platform_support.iter_ports(8787, 3)), [8787, 8788, 8789])
        with self.assertRaises(ValueError):
            list(platform_support.iter_ports(0, 3))

    def test_browser_boundary_is_injectable(self):
        opened = []
        result = platform_support.open_browser(
            "http://127.0.0.1:8787/",
            opener=lambda url: opened.append(url) or True,
        )
        self.assertTrue(result)
        self.assertEqual(opened, ["http://127.0.0.1:8787/"])


class PathsAndDiagnosticsIntegrationTests(unittest.TestCase):
    def test_current_windows_bundle_paths_remain_compatible(self):
        self.assertEqual(Path(paths.FFMPEG), PROG_DIR / "bin" / "ffmpeg.exe")
        self.assertEqual(Path(paths.RUNTIME_PYTHON), PROG_DIR / "runtime" / "python.exe")
        self.assertEqual(paths.FONTNAME, "SimHei")
        self.assertEqual(
            paths.FONT_ENV,
            {"FONTCONFIG_PATH": platform_support.WINDOWS_FONTCONFIG_PATH},
        )
        self.assertEqual(paths.resolve_ffmpeg(required=True), paths.FFMPEG)

    def test_darwin_forces_package_b_unavailable_even_with_windows_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "伪包B"
            _make_executable(root / "wzf" / "python.exe")
            (root / "pretrained_models" / "prompts").mkdir(parents=True)

            def config(_section, key, default=""):
                return str(root) if key == "root" else default

            with mock.patch.object(paths, "cfg_get", side_effect=config), \
                    mock.patch.object(paths, "APP_ROOT", Path(temp) / "独立包A"), \
                    mock.patch.object(paths.platform_support, "is_windows", return_value=False):
                info = paths.dots_info()
                found = paths.scan_for_dots()
        self.assertFalse(info["installed"])
        self.assertEqual(info["python"], "")
        self.assertEqual(info["prompts"], PROG_DIR / "_语音引擎未安装")
        self.assertEqual(found, [])

    def test_diagnostics_report_tools_without_cmd_date(self):
        fake = {
            "system": "darwin",
            "release": "25.5.0",
            "machine": "arm64",
            "python_version": "3.9.6",
            "tools": {
                "python": {"available": True, "path": "/usr/bin/python3", "error": ""},
                "ffmpeg": {"available": False, "path": "", "error": "ffmpeg：未找到"},
                "ffprobe": {"available": False, "path": "", "error": "ffprobe：未找到"},
            },
            "font": {
                "font_file": "simhei.ttf",
                "environment": {},
            },
        }
        missing_dots = {
            "root": None,
            "python": "",
            "prompts": PROG_DIR / "_语音引擎未安装",
            "port": 7860,
            "url": "http://127.0.0.1:7860",
            "installed": False,
        }
        with mock.patch.object(diag.platform_support, "runtime_diagnostics", return_value=fake), \
                mock.patch.object(diag.paths, "dots_info", return_value=missing_dots):
            report = diag.build_report()
        self.assertIn("系统: darwin 25.5.0", report)
        self.assertIn("ffmpeg: 不可用", report)
        self.assertIn("ffprobe: 不可用", report)
        self.assertIn("[语音引擎] 状态: not_installed", report)
        self.assertNotIn("--- config.ini 内容 ---", report)
        self.assertNotIn("cmd /c", report)


class ScopeBoundaryTests(unittest.TestCase):
    def test_business_modules_do_not_add_platform_detection(self):
        for relative in ("引擎/kt_video.py", "网站/kt_web.py"):
            source = (PROG_DIR / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertNotIn("sys.platform", source)
                self.assertNotIn("platform.system", source)
                self.assertNotIn("os.name", source)

    def test_platform_module_has_no_business_imports_or_shell_true(self):
        source = (PROG_DIR / "platform_support.py").read_text(encoding="utf-8")
        for forbidden in ("import kt_video", "import kt_web", "import dots_synth", "shell=True"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
