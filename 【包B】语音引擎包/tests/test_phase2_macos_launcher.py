from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
LAUNCHER_PATH = PACKAGE_ROOT / "_internal" / "macos_launcher.py"
for item in (PACKAGE_ROOT, SRC_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

SPEC = importlib.util.spec_from_file_location("package_b_macos_launcher", LAUNCHER_PATH)
launcher = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(launcher)


class AtomicStateTests(unittest.TestCase):
    def test_atomic_state_round_trip_supports_chinese_and_spaces(self):
        with tempfile.TemporaryDirectory(prefix="包 B Phase 2 空格 ") as temp:
            runtime = Path(temp) / ".runtime"
            state_file = runtime / "state.json"
            pid_file = runtime / "dots.pid"
            state = {
                "pid": 321,
                "process_start_time": "Sun Aug 10 12:34:56 2026",
                "command": ["/路径 含空格/python", "serve"],
                "workdir": str(Path(temp)),
                "port": 7860,
                "api_version": launcher.API_VERSION,
                "model": "dots-tts-mf",
                "device": "auto",
                "precision": "auto",
            }
            launcher.write_state(state, state_file=state_file, pid_file=pid_file)
            loaded, error = launcher.load_state(state_file)
            self.assertIsNone(error)
            self.assertEqual(loaded, state)
            self.assertEqual(pid_file.read_text(encoding="ascii"), "321\n")
            self.assertFalse(list(runtime.glob("*.tmp-*")))

    def test_corrupt_state_is_archived_as_stale_without_signalling(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp) / ".runtime"
            runtime.mkdir()
            state_file = runtime / "state.json"
            pid_file = runtime / "dots.pid"
            state_file.write_text("{broken", encoding="utf-8")
            pid_file.write_text("999\n", encoding="ascii")
            target = launcher._retire_state("损坏", state_file=state_file, pid_file=pid_file)
            self.assertFalse(state_file.exists())
            self.assertFalse(pid_file.exists())
            archived = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(archived["status"], "stale")
            self.assertIn("损坏", archived["stale_reason"])


class IdentityValidationTests(unittest.TestCase):
    def _state(self):
        return {
            "pid": 4321,
            "process_start_time": "Sun Aug 10 12:34:56 2026",
            "command": [sys.executable, str(launcher.LAUNCHER_PATH), "serve"],
            "workdir": str(launcher.PACKAGE_ROOT),
            "port": 7860,
            "api_version": launcher.API_VERSION,
            "model": "dots-tts-mf",
            "device": "auto",
            "precision": "auto",
            "status": "ready",
        }

    def test_missing_process_and_pid_reuse_are_stale(self):
        state = self._state()
        with mock.patch.object(launcher, "process_snapshot", return_value=None):
            ok, reasons, _ = launcher.validate_state_identity(state)
        self.assertFalse(ok)
        self.assertIn("不存在", " ".join(reasons))

        snapshot = {
            "pid": 4321,
            "process_start_time": "different",
            "command_text": f"{launcher.LAUNCHER_PATH} serve",
            "workdir": str(launcher.PACKAGE_ROOT),
        }
        with mock.patch.object(launcher, "process_snapshot", return_value=snapshot), \
                mock.patch.object(launcher, "port_owner_pids", return_value={4321}):
            ok, reasons, _ = launcher.validate_state_identity(state, require_port=True)
        self.assertFalse(ok)
        self.assertIn("PID 已被复用", " ".join(reasons))

    def test_command_workdir_and_port_must_all_match(self):
        state = self._state()
        snapshot = {
            "pid": 4321,
            "process_start_time": state["process_start_time"],
            "command_text": "/usr/bin/python unrelated.py",
            "workdir": "/tmp/unrelated",
        }
        with mock.patch.object(launcher, "process_snapshot", return_value=snapshot), \
                mock.patch.object(launcher, "port_owner_pids", return_value={9999}):
            ok, reasons, _ = launcher.validate_state_identity(state, require_port=True)
        self.assertFalse(ok)
        joined = " ".join(reasons)
        self.assertIn("命令", joined)
        self.assertIn("工作目录", joined)
        self.assertIn("其他进程", joined)

    def test_stop_never_signals_identity_mismatch(self):
        state = self._state()
        with mock.patch.object(launcher, "launch_lock", return_value=mock.MagicMock(
                __enter__=lambda _self: None, __exit__=lambda *_args: False
            )), mock.patch.object(launcher, "load_state", return_value=(state, None)), \
                mock.patch.object(
                    launcher,
                    "validate_state_identity",
                    return_value=(False, ["PID 已被复用"], None),
                ), mock.patch.object(launcher, "_retire_state", return_value=Path("stale.json")), \
                mock.patch.object(launcher.os, "killpg") as killpg:
            result = launcher.stop_service(timeout=0.01)
        self.assertFalse(result["stopped"])
        self.assertIn("未发送信号", result["reason"])
        killpg.assert_not_called()

    def test_verified_stop_uses_process_group_and_is_bounded(self):
        state = self._state()
        context = mock.MagicMock(__enter__=lambda _self: None, __exit__=lambda *_args: False)
        with tempfile.TemporaryDirectory() as temp:
            state_file = Path(temp) / "state.json"
            pid_file = Path(temp) / "dots.pid"
            state_file.write_text("{}", encoding="utf-8")
            pid_file.write_text("4321\n", encoding="ascii")
            with mock.patch.object(launcher, "launch_lock", return_value=context), \
                    mock.patch.object(launcher, "load_state", return_value=(state, None)), \
                    mock.patch.object(launcher, "validate_state_identity", return_value=(True, [], {})), \
                mock.patch.object(launcher.os, "getpgid", return_value=4321), \
                mock.patch.object(launcher.os, "killpg") as killpg, \
                mock.patch.object(launcher, "_pid_alive", return_value=False), \
                    mock.patch.object(launcher, "STATE_FILE", state_file), \
                    mock.patch.object(launcher, "PID_FILE", pid_file):
                result = launcher.stop_service(timeout=0.01)
        self.assertTrue(result["stopped"])
        killpg.assert_called_once_with(4321, signal.SIGTERM)


class LockingAndRecoveryTests(unittest.TestCase):
    def test_launch_lock_serializes_concurrent_starts(self):
        with tempfile.TemporaryDirectory() as temp:
            lock_file = Path(temp) / "launch.lock"
            first_entered = threading.Event()
            release_first = threading.Event()
            order = []

            def first():
                with launcher.launch_lock(lock_file):
                    order.append("first-enter")
                    first_entered.set()
                    release_first.wait(2)
                    order.append("first-exit")

            def second():
                first_entered.wait(2)
                with launcher.launch_lock(lock_file):
                    order.append("second-enter")

            one = threading.Thread(target=first)
            two = threading.Thread(target=second)
            one.start()
            two.start()
            self.assertTrue(first_entered.wait(1))
            time.sleep(0.05)
            self.assertNotIn("second-enter", order)
            release_first.set()
            one.join(2)
            two.join(2)
            self.assertEqual(order, ["first-enter", "first-exit", "second-enter"])

    def test_status_reclaims_stale_crash_state(self):
        state = {"pid": 222}
        with mock.patch.object(launcher, "load_state", return_value=(state, None)), \
                mock.patch.object(
                    launcher,
                    "validate_state_identity",
                    return_value=(False, ["记录的进程不存在"], None),
                ), mock.patch.object(launcher, "_retire_state", return_value=Path("stale.json")) as retire:
            result = launcher.query_service(reclaim=True)
        self.assertFalse(result["running"])
        self.assertTrue(result["stale"])
        retire.assert_called_once()

    def test_repeated_start_reuses_verified_service(self):
        args = mock.Mock(open_browser=False)
        state = {"pid": 123, "port": 7860}
        context = mock.MagicMock(__enter__=lambda _self: None, __exit__=lambda *_args: False)
        with mock.patch.object(launcher, "launch_lock", return_value=context), \
                mock.patch.object(
                    launcher,
                    "query_service",
                    return_value={"running": True, "ready": True, "state": state},
                ), mock.patch.object(launcher, "collect_preflight") as preflight, \
                mock.patch.object(launcher.subprocess, "Popen") as popen:
            result = launcher.start_service(args)
        self.assertTrue(result["reused"])
        preflight.assert_not_called()
        popen.assert_not_called()

    def test_start_releases_lock_before_waiting_for_health(self):
        inside_lock = {"value": False}

        class Context:
            def __enter__(self):
                inside_lock["value"] = True

            def __exit__(self, *_args):
                inside_lock["value"] = False

        process = mock.Mock(pid=2468)
        process.poll.return_value = None
        snapshot = {
            "pid": 2468,
            "process_start_time": "Sun Aug 10 12:34:56 2026",
            "command_text": f"{launcher.LAUNCHER_PATH} serve",
            "workdir": str(launcher.PACKAGE_ROOT),
        }
        args = mock.Mock(
            model="dots-tts-mf",
            device="auto",
            precision="auto",
            port=7860,
            log_file="",
            timeout=1.0,
            open_browser=False,
        )
        with tempfile.TemporaryDirectory() as temp:
            args.log_file = str(Path(temp) / "gradio.log")

            def ready(_port):
                self.assertFalse(inside_lock["value"])
                return True

            with mock.patch.object(launcher, "launch_lock", return_value=Context()), \
                    mock.patch.object(launcher, "query_service", return_value={"running": False}), \
                    mock.patch.object(launcher, "collect_preflight", return_value={"ok": True}), \
                    mock.patch.object(launcher.subprocess, "Popen", return_value=process), \
                    mock.patch.object(launcher, "process_snapshot", return_value=snapshot), \
                    mock.patch.object(launcher, "write_state"), \
                    mock.patch.object(launcher, "health", side_effect=ready):
                result = launcher.start_service(args)
        self.assertTrue(result["ready"])

    def test_process_probe_uses_stable_utf8_locale(self):
        completed = mock.Mock(returncode=0, stdout="Sun Aug 10 12:34:56 2026\n")
        with mock.patch.object(launcher.subprocess, "run", return_value=completed) as run:
            value = launcher._ps_field(12, "lstart")
        self.assertEqual(value, "Sun Aug 10 12:34:56 2026")
        self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "en_US.UTF-8")
        self.assertEqual(run.call_args.kwargs["env"]["LANG"], "en_US.UTF-8")


class PreflightTests(unittest.TestCase):
    def _collect(self, root: Path, *, port_owners=None):
        model = root / "pretrained_models" / "dots-tts-mf"
        model.mkdir(parents=True, exist_ok=True)
        (root / "src").mkdir(exist_ok=True)
        tool = mock.Mock()
        tool.as_dict.return_value = {"path": "/portable/bin/tool", "source": "package"}
        with mock.patch.object(launcher.platform, "system", return_value="Darwin"), \
                mock.patch.object(launcher.platform, "machine", return_value="arm64"), \
                mock.patch.object(launcher.sys, "version_info", (3, 12, 13)), \
                mock.patch.object(launcher, "verify_model", return_value={"checked_files": ["config.json"]}), \
                mock.patch("dots_tts.external_tools.resolve_external_tool", return_value=tool), \
                mock.patch.object(launcher, "port_owner_pids", return_value=set(port_owners or [])), \
                mock.patch.object(launcher.shutil, "disk_usage", return_value=mock.Mock(free=20 * 1024**3)):
            return launcher.collect_preflight(
                model="dots-tts-mf",
                device="auto",
                precision="auto",
                port=7860,
                root=root,
                import_modules=(),
                require_bundled_python=False,
            )

    def test_port_conflict_fails_before_model_load(self):
        with tempfile.TemporaryDirectory(prefix="包 B 空格 ") as temp:
            report = self._collect(Path(temp), port_owners={991})
        self.assertFalse(report["ok"])
        self.assertIn("端口 7860 已被占用", " ".join(report["failures"]))

    def test_special_path_preflight_succeeds_with_packaged_tools(self):
        with tempfile.TemporaryDirectory(prefix="包 B 中文 空格 ") as temp:
            report = self._collect(Path(temp))
        self.assertTrue(report["ok"], report)

    def test_missing_model_and_ffmpeg_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "pretrained_models" / "dots-tts-mf"
            model.mkdir(parents=True)
            (root / "src").mkdir()
            with mock.patch.object(launcher.platform, "system", return_value="Darwin"), \
                    mock.patch.object(launcher.platform, "machine", return_value="arm64"), \
                    mock.patch.object(launcher.sys, "version_info", (3, 12, 13)), \
                    mock.patch.object(launcher, "verify_model", side_effect=launcher.LaunchError("模型文件缺失")), \
                    mock.patch(
                        "dots_tts.external_tools.resolve_external_tool",
                        side_effect=RuntimeError("ffmpeg：未找到"),
                    ), mock.patch.object(launcher, "port_owner_pids", return_value=set()), \
                    mock.patch.object(launcher.shutil, "disk_usage", return_value=mock.Mock(free=20 * 1024**3)):
                report = launcher.collect_preflight(
                    model="dots-tts-mf",
                    device="auto",
                    precision="auto",
                    port=7860,
                    root=root,
                    import_modules=(),
                    require_bundled_python=False,
                )
        failures = " ".join(report["failures"])
        self.assertIn("模型文件缺失", failures)
        self.assertIn("ffmpeg", failures)

    def test_model_manifest_detects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "dots-tts-mf"
            model.mkdir()
            artifact = model / "config.json"
            artifact.write_text("actual", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "model": "dots-tts-mf",
                "files": [{"path": "config.json", "size": 6, "sha256": "0" * 64}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(launcher.LaunchError, "SHA-256"):
                launcher.verify_model(model, manifest)

    def test_model_manifest_path_selects_mf_and_soar(self):
        root = Path("/tmp/package-b")
        self.assertEqual(
            launcher.model_manifest_path(Path("dots-tts-mf"), root),
            root.resolve() / "manifests" / "macos-mf-model.json",
        )
        self.assertEqual(
            launcher.model_manifest_path(Path("dots-tts-soar"), root),
            root.resolve() / "manifests" / "macos-soar-model.json",
        )
        with self.assertRaisesRegex(launcher.LaunchError, "没有 macOS 验证清单"):
            launcher.model_manifest_path(Path("unknown-model"), root)


class StaticEntrypointTests(unittest.TestCase):
    def test_command_wrappers_are_thin_portable_argument_only_entries(self):
        for name, model in (
            ("启动-快速版.command", "dots-tts-mf"),
            ("启动-质量版.command", "dots-tts-soar"),
        ):
            source = (PACKAGE_ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertTrue(source.startswith("#!/bin/zsh\n"))
                self.assertIn('${0:A:h}', source)
                self.assertIn("runtime/python/bin/python3.12", source)
                self.assertIn("_internal/macos_launcher.py", source)
                self.assertIn(f"--model {model}", source)
                self.assertIn("--device auto --precision auto --port 7860", source)
                self.assertNotIn("/Users/", source)
                self.assertNotIn("192.168.", source)
                self.assertNotIn("curl ", source)
                self.assertNotIn("kill ", source)

    def test_lock_is_exact_and_contains_accepted_versions(self):
        lock = (PACKAGE_ROOT / "constraints" / "macos-arm64-py312.lock").read_text(encoding="utf-8")
        self.assertIn("torch==2.8.0", lock)
        self.assertIn("torchaudio==2.8.0", lock)
        self.assertIn("transformers==4.57.0", lock)
        self.assertIn("gradio==6.3.0", lock)
        for line in lock.splitlines():
            if line and not line.startswith("#"):
                self.assertIn("==", line)


if __name__ == "__main__":
    unittest.main()
