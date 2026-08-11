from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROG_DIR = PACKAGE_ROOT / "程序文件"
WEB_DIR = PROG_DIR / "网站"
for item in (PROG_DIR, WEB_DIR):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import dots_control
import dots_synth
import paths


def _make_macos_layout(root: Path):
    files = [
        root / "runtime" / "python" / "bin" / "python3.12",
        root / "_internal" / "macos_launcher.py",
        root / "manifests" / "macos-mf-model.json",
        root / "启动-快速版.command",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    (root / "pretrained_models" / "dots-tts-mf").mkdir(parents=True)
    (root / "pretrained_models" / "prompts").mkdir(parents=True)


class Result:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class PathsTests(unittest.TestCase):
    def test_valid_macos_layout_requires_arm64_python312(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "包 B 含空格"
            _make_macos_layout(root)

            def config(_section, key, default=""):
                return str(root) if key == "root" else default

            probe = Result(json.dumps({"system": "Darwin", "machine": "arm64", "version": [3, 12, 13]}))
            with mock.patch.object(paths, "cfg_get", side_effect=config), \
                    mock.patch.object(paths.platform_support, "is_windows", return_value=False), \
                    mock.patch.object(paths.platform_support, "is_darwin", return_value=True), \
                    mock.patch.object(paths.subprocess, "run", return_value=probe):
                info = paths.dots_info()
            self.assertTrue(info["installed"])
            self.assertEqual(info["layout"], "macos-arm64-py312")
            self.assertEqual(info["api_version"], dots_control.EXPECTED_API_VERSION)

    def test_windows_only_layout_is_rejected_on_darwin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "wzf").mkdir()
            (root / "wzf" / "python.exe").write_text("x", encoding="utf-8")

            def config(_section, key, default=""):
                return str(root) if key == "root" else default

            with mock.patch.object(paths, "cfg_get", side_effect=config), \
                    mock.patch.object(paths.platform_support, "is_windows", return_value=False), \
                    mock.patch.object(paths.platform_support, "is_darwin", return_value=True):
                info = paths.dots_info()
            self.assertFalse(info["installed"])
            self.assertIn("布局不完整", info["diagnostic"])


class ApiNegotiationTests(unittest.TestCase):
    def _client(self, endpoints):
        client = mock.Mock()
        client.view_api.return_value = {"named_endpoints": endpoints}
        return client

    @staticmethod
    def _endpoint(names):
        return {"parameters": [{"parameter_name": name} for name in names]}

    def test_v1_is_preferred_and_requires_one_json_parameter(self):
        client = self._client({
            dots_synth.LEGACY_ENDPOINT: self._endpoint(dots_synth.LEGACY9_PARAMETERS),
            dots_synth.V1_ENDPOINT: self._endpoint(("request",)),
        })
        self.assertEqual(dots_synth.negotiate_endpoint(client)["mode"], "v1")

    def test_exact_legacy9_is_allowed_but_unknown_shapes_fail_closed(self):
        good = self._client({dots_synth.LEGACY_ENDPOINT: self._endpoint(dots_synth.LEGACY9_PARAMETERS)})
        self.assertEqual(dots_synth.negotiate_endpoint(good)["mode"], "legacy9")
        bad = self._client({dots_synth.LEGACY_ENDPOINT: self._endpoint(("text", "mystery"))})
        with self.assertRaises(dots_synth.ContractError):
            dots_synth.negotiate_endpoint(bad)
        unknown = self._client({"/gen_clone": self._endpoint(("text",))})
        with self.assertRaises(dots_synth.ContractError):
            dots_synth.negotiate_endpoint(unknown)


class ControlTests(unittest.TestCase):
    def _info(self, root):
        launcher = root / "_internal" / "macos_launcher.py"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("x", encoding="utf-8")
        return {"installed": True, "python": "/python", "launcher": launcher}

    def test_missing_corrupt_stale_and_version_mismatch_are_reported_without_signals(self):
        with tempfile.TemporaryDirectory() as temp:
            info = self._info(Path(temp))
            offline = Result(json.dumps({"running": False, "stale": False, "reason": "没有状态文件"}), 3)
            self.assertEqual(dots_control.status(info, runner=lambda *a, **k: offline)["state"], "offline")
            corrupt = Result("not-json", 3, "broken")
            with self.assertRaises(dots_control.DotsControlError):
                dots_control.status(info, runner=lambda *a, **k: corrupt)
            stale = Result(json.dumps({"running": False, "stale": True, "reason": "PID 已被复用"}), 3)
            status = dots_control.status(info, runner=lambda *a, **k: stale)
            self.assertFalse(status["running"])
            self.assertIn("PID", status["reason"])

            calls = []
            mismatch = Result(json.dumps({
                "running": True, "ready": True,
                "state": {"pid": 9, "api_version": "future.v2"},
            }))
            result = dots_control.stop(info, runner=lambda argv, **kwargs: calls.append(argv) or mismatch)
            self.assertFalse(result["ok"])
            self.assertEqual(len(calls), 1)

    def test_verified_stop_delegates_to_launcher_without_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            info = self._info(Path(temp))
            calls = []
            responses = iter([
                Result(json.dumps({
                    "running": True, "ready": True,
                    "state": {"pid": 12, "api_version": dots_control.EXPECTED_API_VERSION},
                })),
                Result(json.dumps({"stopped": True, "pid": 12})),
            ])

            def runner(argv, **kwargs):
                calls.append((argv, kwargs))
                return next(responses)

            result = dots_control.stop(info, runner=runner)
            self.assertTrue(result["ok"])
            self.assertEqual(calls[1][0][-1], "stop")
            self.assertNotIn("shell", calls[1][1])

    def test_contract_probe_rejects_unknown_before_submission(self):
        info = {"python": "/python"}
        failed = Result("ERROR schema 不兼容\n", 5)
        with self.assertRaises(dots_control.DotsControlError):
            dots_control.probe_contract(info, "/dots_synth.py", runner=lambda *a, **k: failed)


if __name__ == "__main__":
    unittest.main()
