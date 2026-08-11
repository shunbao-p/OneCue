# -*- coding: utf-8 -*-
"""Phase 4 macOS 启动、预检、诊断和发布锁合同。"""

import hashlib
import importlib
import json
import os
import socket
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"
SCRIPTS_DIR = PACKAGE_ROOT / "scripts"

if str(PROG_DIR) not in sys.path:
    sys.path.insert(0, str(PROG_DIR))


WINDOWS_LAUNCHER_HASHES = {
    "①开始使用.bat": "d16bb86c029546fc3d38ee87a4e9988602da5cf4a4a729b791ecc1ebaf69d566",
    "②连接语音引擎.bat": "afc7f9d726f63bdfc026a490dc3ee478c05f42b7e1b199fd5bc5e5b5ff71b11f",
    "③出问题了点我.bat": "35c83c89e8de3dcf4c9f6632fc33653cb4b1f6af9e9532a6ea1709a11069cade",
}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class StaticLauncherContracts(unittest.TestCase):
    def test_windows_launchers_are_byte_for_byte_unchanged(self):
        for name, expected in WINDOWS_LAUNCHER_HASHES.items():
            with self.subTest(name=name):
                self.assertEqual(_sha256(PACKAGE_ROOT / name), expected)

    def test_command_is_executable_minimal_and_has_no_machine_path(self):
        launcher = PACKAGE_ROOT / "①开始使用.command"
        source = launcher.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/bin/zsh\n"))
        self.assertIn("${0:A:h}", source)
        self.assertIn("程序文件/runtime/bin/python3", source)
        self.assertIn('"$PYTHON_RUNTIME" -B', source)
        self.assertIn("mac_launcher.py", source)
        self.assertNotIn("/Users/", source)
        self.assertNotIn("192.168.", source)
        self.assertNotIn("eval ", source)
        self.assertNotIn("bash -c", source)
        if os.name != "nt":
            self.assertTrue(os.stat(launcher).st_mode & stat.S_IXUSR)

    def test_release_builder_includes_package_b_connection_contract(self):
        source = (SCRIPTS_DIR / "build_macos_release.py").read_text(encoding="utf-8")
        for required in (
            "②连接语音引擎.command",
            "connect_dots.py",
            "dots_control.py",
            "dots_synth.py",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        self.assertIn('root =\\nport = 7860', source)
        self.assertNotIn('_copy_file(PACKAGE_ROOT / "程序文件" / "config.ini"', source)

    def test_runtime_lock_is_arm64_auditable_and_forbids_nonfree(self):
        lock = json.loads((SCRIPTS_DIR / "macos-runtime-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["schema_version"], 1)
        self.assertEqual(lock["target"], "aarch64-apple-darwin")
        self.assertRegex(lock["python"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("aarch64-apple-darwin", lock["python"]["asset"])
        names = {item["name"] for item in lock["ffmpeg_sources"]}
        self.assertTrue({"ffmpeg", "x264", "libass", "freetype", "fribidi", "harfbuzz"} <= names)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in lock["ffmpeg_sources"]))
        configure = " ".join(lock["ffmpeg_configure"])
        self.assertIn("--enable-gpl", configure)
        self.assertIn("--enable-libx264", configure)
        self.assertIn("--enable-libass", configure)
        self.assertIn("--enable-zlib", configure)
        self.assertNotIn("--enable-nonfree", configure)
        self.assertNotIn("libfdk", configure)


class PreflightContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = importlib.import_module("mac_launcher")

    def _healthy_dependencies(self, root):
        runtime = root / "程序文件" / "runtime" / "bin" / "python3"
        ffmpeg = root / "程序文件" / "bin" / "ffmpeg"
        ffprobe = root / "程序文件" / "bin" / "ffprobe"
        font = root / "程序文件" / "fonts" / "simhei.ttf"
        for path in (runtime, ffmpeg, ffprobe, font):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"probe")
            path.chmod(0o755)
        for name in ("临时文件", "日志"):
            (root / "程序文件" / name).mkdir(parents=True)
        for name in ("我的素材", "成片"):
            (root / name).mkdir(parents=True)
        return runtime, ffmpeg, ffprobe

    def test_release_preflight_reports_arch_tools_capabilities_font_writes_and_package_b(self):
        with tempfile.TemporaryDirectory(prefix="Phase 4 中文 空格 ") as temp:
            root = Path(temp)
            runtime, ffmpeg, ffprobe = self._healthy_dependencies(root)
            with mock.patch.object(self.launcher.platform, "system", return_value="Darwin"), \
                    mock.patch.object(self.launcher.platform, "machine", return_value="arm64"), \
                    mock.patch.object(self.launcher, "_python_version", return_value={
                        "version": "3.13.13", "machine": "arm64", "executable": str(runtime),
                    }), \
                    mock.patch.object(self.launcher, "tool_architectures", return_value=["arm64"]), \
                    mock.patch.object(self.launcher, "probe_ffmpeg", return_value={
                        "version": "ffmpeg version 8.1.2",
                        "configuration": "--enable-gpl --enable-libx264 --enable-libass --enable-zlib",
                        "subtitles": True, "libx264": True, "aac": True, "png": True,
                    }), \
                    mock.patch.object(self.launcher, "probe_ffprobe", return_value="ffprobe version 8.1.2"), \
                    mock.patch.object(self.launcher, "resolve_tools", return_value={
                        "python": str(runtime), "ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe),
                    }), \
                    mock.patch.object(self.launcher.paths, "dots_info", return_value={"installed": True}), \
                    mock.patch.object(self.launcher.shutil, "disk_usage", return_value=(10**12, 1, 10**11)):
                report = self.launcher.collect_preflight(root, mode="release")
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["architecture"], "arm64")
        self.assertTrue(report["checks"]["ffmpeg_capabilities"]["ok"])
        self.assertTrue(report["checks"]["font"]["ok"])
        self.assertTrue(report["checks"]["directories"]["ok"])
        self.assertEqual(report["package_b"]["state"], "installed")

    def test_missing_tool_error_says_missing_detected_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.object(self.launcher.platform, "system", return_value="Darwin"), \
                mock.patch.object(self.launcher.platform, "machine", return_value="arm64"), \
                mock.patch.object(self.launcher, "resolve_tools", side_effect=RuntimeError("ffmpeg：未找到")):
            report = self.launcher.collect_preflight(Path(temp), mode="release")
        self.assertFalse(report["ok"])
        message = self.launcher.format_failures(report)
        self.assertIn("缺少", message)
        self.assertIn("检测到", message)
        self.assertIn("恢复", message)
        self.assertIn("ffmpeg", message)

    def test_non_arm64_and_nonfree_ffmpeg_are_hard_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime, ffmpeg, ffprobe = self._healthy_dependencies(root)
            with mock.patch.object(self.launcher.platform, "system", return_value="Darwin"), \
                    mock.patch.object(self.launcher.platform, "machine", return_value="x86_64"), \
                    mock.patch.object(self.launcher, "_python_version", return_value={
                        "version": "3.13.13", "machine": "x86_64", "executable": str(runtime),
                    }), \
                    mock.patch.object(self.launcher, "tool_architectures", return_value=["x86_64"]), \
                    mock.patch.object(self.launcher, "probe_ffmpeg", return_value={
                        "version": "ffmpeg version 6.0", "configuration": "--enable-nonfree",
                        "subtitles": True, "libx264": True, "aac": True, "png": True,
                    }), \
                    mock.patch.object(self.launcher, "probe_ffprobe", return_value="ffprobe version 6.0"), \
                    mock.patch.object(self.launcher, "resolve_tools", return_value={
                        "python": str(runtime), "ffmpeg": str(ffmpeg), "ffprobe": str(ffprobe),
                    }), \
                    mock.patch.object(self.launcher.shutil, "disk_usage", return_value=(10**12, 1, 10**11)):
                report = self.launcher.collect_preflight(root, mode="release")
        self.assertFalse(report["ok"])
        failures = " ".join(report["failures"])
        self.assertIn("arm64", failures)
        self.assertIn("nonfree", failures)


class LifecycleAndDiagnosticsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = importlib.import_module("mac_launcher")

    def test_repeated_start_reuses_healthy_actual_port_without_spawning(self):
        with mock.patch.object(self.launcher, "find_running_service", return_value={
            "pid": 1234, "port": 8891, "url": "http://127.0.0.1:8891/",
        }), mock.patch.object(self.launcher.subprocess, "Popen") as popen, \
                mock.patch.object(self.launcher.platform_support, "open_browser", return_value=True) as opened:
            result = self.launcher.start_service(mode="development", open_browser=True)
        self.assertTrue(result["reused"])
        self.assertEqual(result["port"], 8891)
        popen.assert_not_called()
        opened.assert_called_once_with("http://127.0.0.1:8891/")

    def test_stale_port_health_is_not_reused_without_verified_current_state(self):
        with mock.patch.object(self.launcher, "load_state", return_value={}), \
                mock.patch.object(self.launcher, "read_port", return_value=8788), \
                mock.patch.object(self.launcher, "health", return_value={"status": "ok"}) as health:
            self.assertIsNone(self.launcher.find_running_service())
        health.assert_not_called()

    def test_running_service_requires_current_script_and_matching_pid(self):
        state = {"pid": 1234, "port": 8891, "script": str(self.launcher.WEB_SCRIPT.resolve())}
        with mock.patch.object(self.launcher, "load_state", return_value=state), \
                mock.patch.object(self.launcher, "process_matches", return_value=True), \
                mock.patch.object(self.launcher, "health", return_value={"status": "ok"}):
            running = self.launcher.find_running_service()
        self.assertEqual(running["pid"], 1234)
        self.assertEqual(running["port"], 8891)

    def test_port_reader_rejects_stale_or_invalid_values(self):
        with tempfile.TemporaryDirectory() as temp:
            port_file = Path(temp) / ".port"
            for value in ("", "0", "65536", "not-a-port"):
                port_file.write_text(value, encoding="utf-8")
                with self.subTest(value=value):
                    self.assertIsNone(self.launcher.read_port(port_file))
            port_file.write_text("8789", encoding="utf-8")
            self.assertEqual(self.launcher.read_port(port_file), 8789)

    def test_diagnostics_are_machine_readable_and_redact_home_and_config_values(self):
        home = Path.home()
        payload = {
            "system": "Darwin",
            "architecture": "arm64",
            "tools": {"ffmpeg": str(home / "秘密目录" / "ffmpeg")},
            "directories": {"output": str(home / "客户A" / "成片")},
            "port": 8789,
            "package_b": {"state": "not_installed"},
            "recent_service_log": ["tool=" + str(home / "秘密目录" / "ffmpeg")],
        }
        sanitized = self.launcher.sanitize_report(payload, home=home)
        encoded = json.dumps(sanitized, ensure_ascii=False)
        self.assertNotIn(str(home), encoded)
        normalized = encoded.replace("\\\\", "/")
        self.assertIn("~/秘密目录/ffmpeg", normalized)
        self.assertEqual(sanitized["package_b"]["state"], "not_installed")
        self.assertNotIn("password", encoded.lower())
        self.assertNotIn("token", encoded.lower())
        self.assertIn("tool=~/秘密目录/ffmpeg", normalized)

    def test_stop_refuses_unverified_pid_and_uses_bounded_verified_process_group(self):
        state = {"pid": 4321, "port": 8789}
        with mock.patch.object(self.launcher, "load_state", return_value=state), \
                mock.patch.object(self.launcher, "process_matches", return_value=False), \
                mock.patch.object(self.launcher.os, "killpg", create=True) as killpg:
            result = self.launcher.stop_service(timeout=0.01)
        self.assertFalse(result["stopped"])
        killpg.assert_not_called()

        with mock.patch.object(self.launcher, "load_state", return_value=state), \
                mock.patch.object(self.launcher, "process_matches", side_effect=[True, False]), \
                mock.patch.object(self.launcher.os, "getpgid", return_value=4321, create=True), \
                mock.patch.object(self.launcher.os, "killpg", create=True) as killpg:
            result = self.launcher.stop_service(timeout=0.01)
        self.assertTrue(result["stopped"])
        killpg.assert_called_once()

    def test_service_process_disables_runtime_bytecode_writes(self):
        source = (PROG_DIR / "mac_launcher.py").read_text(encoding="utf-8")
        self.assertIn('command = [tools["python"], "-B", str(WEB_SCRIPT)]', source)


class DocumentationContracts(unittest.TestCase):
    def test_macos_documentation_separates_user_development_build_and_troubleshooting(self):
        text = (PACKAGE_ROOT / "macOS使用与构建说明.md").read_text(encoding="utf-8")
        for heading in ("最终用户启动", "开发启动", "构建发布包", "首次运行", "故障排除", "已知限制"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
        self.assertIn("不需要 Homebrew", text)
        self.assertIn("Developer ID", text)
        self.assertIn("notarytool", text)
        self.assertIn("包 B", text)


if __name__ == "__main__":
    unittest.main()
