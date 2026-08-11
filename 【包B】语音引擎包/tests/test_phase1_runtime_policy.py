from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
for import_root in (PACKAGE_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from dots_tts.external_tools import (  # noqa: E402
    ExternalToolNotFoundError,
    resolve_external_tool,
)
from dots_tts.runtime_device import (  # noqa: E402
    RuntimeDeviceError,
    configure_torch_runtime,
    inference_autocast,
    install_windows_asyncio_cleanup_patch,
    resolve_runtime_device_policy,
)


class _FlagBackend:
    def __init__(self, *, built: bool = False, available: bool = False):
        self.built = built
        self.available = available

    def is_built(self):
        return self.built

    def is_available(self):
        return self.available


class _CudaBackend:
    def __init__(self):
        self.calls: list[tuple[str, bool]] = []

    def enable_flash_sdp(self, enabled):
        self.calls.append(("flash", enabled))

    def enable_cudnn_sdp(self, enabled):
        self.calls.append(("cudnn_sdp", enabled))


class _FakeTorch:
    float32 = "float32"
    float16 = "float16"
    bfloat16 = "bfloat16"

    def __init__(self, *, cuda: bool = False, mps_built: bool = False, mps: bool = False):
        self.cuda = _FlagBackend(available=cuda)
        self.backends = type("Backends", (), {})()
        self.backends.mps = _FlagBackend(built=mps_built, available=mps)
        self.backends.cuda = _CudaBackend()
        self.backends.cudnn = type("Cudnn", (), {})()
        self.thread_count = None
        self.matmul_precision = None

    def set_num_threads(self, count):
        self.thread_count = count

    def set_float32_matmul_precision(self, precision):
        self.matmul_precision = precision


class RuntimePolicyTests(unittest.TestCase):
    def test_auto_selects_native_mps_float32(self):
        torch = _FakeTorch(mps_built=True, mps=True)
        with mock.patch.dict(os.environ, {"PYTORCH_ENABLE_MPS_FALLBACK": "0"}, clear=False):
            policy = resolve_runtime_device_policy(
                torch,
                requested_device="auto",
                requested_precision="auto",
                platform_name="darwin",
                machine="arm64",
            )
        self.assertEqual(policy.actual_device, "mps")
        self.assertEqual(policy.actual_precision, "float32")
        self.assertFalse(policy.fallback_used)
        self.assertTrue(policy.as_dict()["native_mps"])

    def test_mps_rejects_unvalidated_reduced_precision(self):
        torch = _FakeTorch(mps_built=True, mps=True)
        for precision in ("float16", "bfloat16"):
            with self.subTest(precision=precision), self.assertRaises(RuntimeDeviceError):
                resolve_runtime_device_policy(
                    torch,
                    requested_device="mps",
                    requested_precision=precision,
                )

    def test_mps_is_never_selected_off_apple_silicon(self):
        torch = _FakeTorch(mps_built=True, mps=True)
        policy = resolve_runtime_device_policy(
            torch,
            platform_name="linux",
            machine="x86_64",
        )
        self.assertEqual(policy.actual_device, "cpu")
        self.assertTrue(policy.fallback_used)
        with self.assertRaises(RuntimeDeviceError):
            resolve_runtime_device_policy(
                torch,
                requested_device="mps",
                platform_name="linux",
                machine="x86_64",
            )

    def test_auto_cpu_reports_fallback_and_disables_compile(self):
        torch = _FakeTorch()
        policy = resolve_runtime_device_policy(torch)
        self.assertEqual(policy.actual_device, "cpu")
        self.assertEqual(policy.actual_precision, "float32")
        self.assertTrue(policy.fallback_used)
        self.assertEqual(policy.fallback_reason, "auto_no_cuda_or_mps")
        configure_torch_runtime(torch, policy)
        self.assertEqual(torch.thread_count, 1)
        with self.assertRaises(RuntimeDeviceError):
            resolve_runtime_device_policy(torch, optimize=True)

    def test_cuda_settings_run_only_for_cuda_policy(self):
        torch = _FakeTorch(cuda=True, mps_built=True, mps=True)
        mps_policy = resolve_runtime_device_policy(
            torch,
            requested_device="mps",
            requested_precision="float32",
            platform_name="darwin",
            machine="arm64",
        )
        configure_torch_runtime(torch, mps_policy)
        self.assertEqual(torch.backends.cuda.calls, [])
        cuda_policy = resolve_runtime_device_policy(
            torch,
            requested_device="cuda",
            requested_precision="float32",
        )
        configure_torch_runtime(torch, cuda_policy)
        self.assertEqual(torch.backends.cuda.calls, [("flash", True), ("cudnn_sdp", False)])
        self.assertEqual(torch.matmul_precision, "high")

    def test_mps_float32_does_not_construct_autocast(self):
        torch = _FakeTorch(mps_built=True, mps=True)
        torch.autocast = mock.Mock(side_effect=AssertionError("must not be called"))
        with inference_autocast(torch, "mps", torch.float32):
            pass
        torch.autocast.assert_not_called()

    def test_cuda_reduced_precision_without_autocast_has_clear_error(self):
        torch = _FakeTorch(cuda=True)
        with self.assertRaisesRegex(RuntimeDeviceError, "torch.autocast"):
            inference_autocast(torch, "cuda", torch.float16)

    def test_darwin_never_imports_windows_private_asyncio_module(self):
        with mock.patch("dots_tts.runtime_device.importlib.import_module") as importer:
            self.assertFalse(install_windows_asyncio_cleanup_patch(platform_name="darwin"))
            importer.assert_not_called()

    def test_missing_windows_private_asyncio_module_is_nonfatal(self):
        with mock.patch(
            "dots_tts.runtime_device.importlib.import_module",
            side_effect=ImportError("not present"),
        ):
            self.assertFalse(install_windows_asyncio_cleanup_patch(platform_name="win32"))


class ExternalToolResolutionTests(unittest.TestCase):
    def _executable(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_resolution_order_explicit_then_package_then_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = self._executable(root / "configured" / "ffmpeg")
            packaged = self._executable(root / "bin" / "ffmpeg")
            with mock.patch("dots_tts.external_tools.shutil.which", return_value="/path/ffmpeg"):
                result = resolve_external_tool(
                    "ffmpeg", explicit_path=explicit, package_root=root
                )
                self.assertEqual(result.source, "explicit")
                self.assertEqual(result.path, str(explicit.resolve()))
                explicit.unlink()
                result = resolve_external_tool(
                    "ffmpeg", explicit_path=explicit, package_root=root
                )
                self.assertEqual(result.source, "package")
                self.assertEqual(result.path, str(packaged.resolve()))

    def test_missing_required_tool_lists_locations_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "dots_tts.external_tools.shutil.which", return_value=None
        ):
            with self.assertRaises(ExternalToolNotFoundError) as caught:
                resolve_external_tool("ffprobe", package_root=tmp)
        message = str(caught.exception)
        self.assertIn("Checked locations", message)
        self.assertIn("DOTS_TTS_FFPROBE", message)
        self.assertIn("PATH:ffprobe", message)

    @unittest.skipIf(os.name == "nt", "POSIX-only package candidate rule")
    def test_posix_ignores_packaged_windows_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._executable(root / "wzf" / "ffmpeg" / "bin" / "ffmpeg.exe")
            path_tool = self._executable(root / "path" / "ffmpeg")
            with mock.patch(
                "dots_tts.external_tools.shutil.which", return_value=str(path_tool)
            ):
                result = resolve_external_tool("ffmpeg", package_root=root)
        self.assertEqual(result.source, "PATH")
        self.assertEqual(result.path, str(path_tool.resolve()))


class ArgumentContractTests(unittest.TestCase):
    def test_cli_accepts_explicit_mps_float32(self):
        from dots_tts.cli import parse_args

        args = parse_args(
            [
                "--model-name-or-path",
                "model",
                "--text",
                "测试",
                "--device",
                "mps",
                "--precision",
                "float32",
            ]
        )
        self.assertEqual((args.device, args.precision), ("mps", "float32"))

    def test_gradio_parser_defaults_to_auto_policy(self):
        from apps.gradio.app import parse_args

        args = parse_args([])
        self.assertEqual((args.device, args.precision), ("auto", "auto"))

    def test_diagnostics_and_benchmark_expose_explicit_mps_policy(self):
        from _internal.benchmark_rtf import BENCHMARK_FIXTURES, parse_args as benchmark_args
        from _internal.check_env import parse_args as check_env_args

        benchmark = benchmark_args(
            [
                "--device",
                "mps",
                "--precision",
                "float32",
                "--json-output",
                "report.json",
            ]
        )
        diagnostics = check_env_args(["--device", "mps", "--precision", "float32"])
        self.assertEqual((benchmark.device, benchmark.precision), ("mps", "float32"))
        self.assertFalse(benchmark.optimize)
        self.assertEqual(len(BENCHMARK_FIXTURES), 3)
        self.assertEqual((diagnostics.device, diagnostics.precision), ("mps", "float32"))


if __name__ == "__main__":
    unittest.main()
