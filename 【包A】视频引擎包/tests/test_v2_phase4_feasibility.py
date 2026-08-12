# -*- coding: utf-8 -*-
"""计划 04：隔离实验协议、评分模板与 FFmpeg 基线契约。"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
ENGINE_DIR = PACKAGE_ROOT / "程序文件" / "引擎"
EXPERIMENT_DIR = PACKAGE_ROOT / "experiments" / "short_video_v2_phase4"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Phase4FeasibilityContractTests(unittest.TestCase):
    def test_required_protocol_files_exist(self):
        for relative in (
            "README.md",
            "benchmark.py",
            "normalize_clip.py",
            "scorecard.py",
            "providers/ffmpeg_baseline.py",
            "providers/mflux_adapter.py",
            "providers/depthflow_adapter.py",
            "providers/hyperframes_adapter.py",
            "templates/image_prompt_template.md",
            "templates/visual_scorecard.json",
        ):
            self.assertTrue((EXPERIMENT_DIR / relative).is_file(), relative)

    def test_scorecard_template_defines_three_cases_and_six_metrics(self):
        template = json.loads(
            (EXPERIMENT_DIR / "templates" / "visual_scorecard.json").read_text(encoding="utf-8")
        )
        self.assertEqual(template["schema_version"], 1)
        self.assertEqual(template["benchmark_cases"], ["portrait", "architecture", "landscape"])
        self.assertEqual(
            list(template["metric_definitions"]),
            ["subject_identity", "edges", "background_geometry", "motion", "temporal_stability", "benefit"],
        )
        for definition in template["metric_definitions"].values():
            self.assertEqual(sorted(definition["scores"]), ["0", "1", "2", "3"])

    def test_run_layout_separates_raw_normalized_and_manifest(self):
        benchmark = load_module("phase4_benchmark", EXPERIMENT_DIR / "benchmark.py")
        with tempfile.TemporaryDirectory() as temporary:
            allowed = Path(temporary) / "phase4-image-motion"
            with mock.patch.object(benchmark, "PHASE4_WORK_ROOT", allowed):
                layout = benchmark.create_run_layout(
                    allowed / "unit", "ffmpeg", "portrait", "run-001",
                )
                self.assertEqual(layout.raw_output.parent.name, "raw")
                self.assertEqual(layout.normalized_output.parent.name, "normalized")
                self.assertEqual(layout.manifest.name, "manifest.json")
                self.assertNotIn("cache", layout.manifest.parts)
                with self.assertRaises(FileExistsError):
                    benchmark.create_run_layout(
                        allowed / "unit", "ffmpeg", "portrait", "run-001",
                    )

    def test_run_id_and_case_are_closed_inputs(self):
        benchmark = load_module("phase4_benchmark_inputs", EXPERIMENT_DIR / "benchmark.py")
        self.assertEqual(benchmark.validate_run_id("run-20260811-001"), "run-20260811-001")
        for unsafe in ("../escape", "with space", "", "a/b", "$(touch x)"):
            with self.assertRaises(ValueError):
                benchmark.validate_run_id(unsafe)
        with self.assertRaises(ValueError):
            benchmark.validate_case("other")

    def test_work_dir_must_stay_under_non_symlinked_phase4_root(self):
        benchmark = load_module("phase4_benchmark_workdir", EXPERIMENT_DIR / "benchmark.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = root / "phase4-image-motion"
            allowed.mkdir()
            with mock.patch.object(benchmark, "PHASE4_WORK_ROOT", allowed):
                self.assertEqual(
                    benchmark.validate_work_dir(allowed / "runs"),
                    allowed.resolve() / "runs",
                )
                with self.assertRaises(ValueError):
                    benchmark.validate_work_dir(root / "formal-job" / "cache")
                target = root / "outside"
                target.mkdir()
                link = allowed / "linked"
                link.symlink_to(target, target_is_directory=True)
                with self.assertRaises(ValueError):
                    benchmark.validate_work_dir(link / "run")

    def test_experiment_sources_do_not_use_shell_execution(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in EXPERIMENT_DIR.rglob("*.py"))
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("shell=True".replace("=", " = "), source)

    def test_shared_external_runner_enforces_timeout_and_cancel(self):
        from video_v2.errors import CommandFailed, PipelineCancelled
        from video_v2.runtime import CommandRunner

        with self.assertRaises(CommandFailed) as caught:
            CommandRunner(terminate_grace=0.05).run(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.05,
            )
        self.assertEqual(caught.exception.code, "runtime.command_timeout")

        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(PipelineCancelled):
            CommandRunner(cancel_event=cancelled).run([sys.executable, "-c", "print('never')"])

    def test_experiment_runner_applies_finite_timeout_to_every_command(self):
        benchmark = load_module("phase4_benchmark_timeout", EXPERIMENT_DIR / "benchmark.py")
        for invalid in (float("nan"), float("inf"), 0.0, -1.0):
            with self.assertRaises(ValueError):
                benchmark.ExperimentCommandRunner(default_timeout=invalid)
        runner = benchmark.ExperimentCommandRunner(default_timeout=7.0)
        fake_result = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        with mock.patch("video_v2.runtime.CommandRunner.run", return_value=fake_result) as parent_run:
            runner.run(["tool", "--version"])
        self.assertEqual(parent_run.call_args.kwargs["timeout"], 7.0)

    def test_ffmpeg_adapter_passes_list_argv_and_timeout(self):
        adapter = load_module(
            "phase4_ffmpeg_adapter",
            EXPERIMENT_DIR / "providers" / "ffmpeg_baseline.py",
        )

        class CapturingRunner:
            def __init__(self):
                self.argv = None
                self.kwargs = None

            def run(self, argv, **kwargs):
                self.argv = argv
                self.kwargs = kwargs
                return object()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.png"
            source.write_bytes(b"fixture")
            runner = CapturingRunner()
            adapter.render_ffmpeg_baseline(
                source,
                root / "output.mp4",
                ffmpeg=Path("/safe/ffmpeg"),
                runner=runner,
                duration_sec=4.0,
                preset="slow_push_in",
                strength="low",
                focus_x=0.5,
                focus_y=0.5,
                timeout_sec=9.0,
            )
            self.assertIsInstance(runner.argv, list)
            self.assertEqual(runner.argv[0], "/safe/ffmpeg")
            self.assertIn("zoompan=", runner.argv[runner.argv.index("-vf") + 1])
            self.assertIs(runner.kwargs["check"], True)
            self.assertEqual(runner.kwargs["timeout"], 9.0)

    def test_mflux_adapter_is_fixed_to_one_model_and_isolated_root(self):
        adapter = load_module(
            "phase4_mflux_adapter",
            EXPERIMENT_DIR / "providers" / "mflux_adapter.py",
        )

        class CapturingRunner:
            def run(self, argv, **kwargs):
                self.argv = argv
                self.kwargs = kwargs
                return object()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "mflux"
            executable = root / "venv" / "bin" / "mflux-generate-flux2"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"fixture")
            runner = CapturingRunner()
            adapter.run_mflux_generate(
                "rainy ancient gate without text",
                root / "output" / "architecture.png",
                runner=runner,
                root=root,
                executable=executable,
                seed=404001,
                width=448,
                height=768,
                timeout_sec=30.0,
            )
            self.assertIsInstance(runner.argv, list)
            self.assertEqual(
                runner.argv[runner.argv.index("--model") + 1],
                "mlx-community/flux2-klein-4b-4bit",
            )
            self.assertEqual(runner.argv[runner.argv.index("--guidance") + 1], "1.0")
            self.assertEqual(runner.kwargs["timeout"], 30.0)
            self.assertEqual(runner.kwargs["env"]["HF_HOME"], str(root.resolve() / "hf"))
            self.assertEqual(runner.kwargs["env"]["HF_HUB_DISABLE_XET"], "1")
            with self.assertRaises(ValueError):
                adapter.build_mflux_generate_argv(
                    "escape",
                    Path(temporary) / "outside.png",
                    executable=executable,
                    root=root,
                    seed=1,
                    width=448,
                    height=768,
                )

    def test_depthflow_adapter_uses_isolated_cache_and_fixed_visual_spec(self):
        adapter = load_module(
            "phase4_depthflow_adapter",
            EXPERIMENT_DIR / "providers" / "depthflow_adapter.py",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "depthflow"
            (root / "venv" / "bin").mkdir(parents=True)
            interpreter = Path(temporary) / "python3.11"
            interpreter.write_bytes(b"fixture")
            (root / "venv" / "bin" / "python").symlink_to(interpreter)
            (root / "project").mkdir()
            (root / "project" / "render_plan04.py").write_bytes(b"fixture")
            source = Path(temporary) / "input.png"
            source.write_bytes(b"fixture")
            layout = adapter.create_layout("landscape", "unit-001", root=root)
            argv = adapter.build_depthflow_argv(source, layout, root=root)
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[argv.index("--width") + 1], "1080")
            self.assertEqual(argv[argv.index("--height") + 1], "1920")
            self.assertEqual(argv[argv.index("--fps") + 1], "30")
            env = adapter.build_depthflow_env(root)
            self.assertEqual(env["HF_HOME"], str(root.resolve() / "hf"))
            self.assertEqual(env["XDG_CACHE_HOME"], str(root.resolve() / "xdg"))
            with self.assertRaises(FileExistsError):
                adapter.create_layout("landscape", "unit-001", root=root)

    def test_hyperframes_adapter_is_pinned_and_keeps_all_caches_isolated(self):
        adapter = load_module(
            "phase4_hyperframes_adapter",
            EXPERIMENT_DIR / "providers" / "hyperframes_adapter.py",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hyperframes"
            project = root / "project" / "rainy-messenger-motion"
            (project / "compositions").mkdir(parents=True)
            (project / "compositions" / "designed-info.html").write_text(
                "<html></html>", encoding="utf-8",
            )
            browser = (
                root / "chrome" / "chrome-headless-shell" / "mac_arm-152.0.7928.2"
                / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell"
            )
            browser.parent.mkdir(parents=True)
            browser.write_bytes(b"fixture")
            output = root / "output" / "designed-info.mp4"
            with mock.patch.object(adapter, "NODE_BIN", Path("/Users/yuh/.nvm/versions/node/v24.17.0/bin")):
                argv = adapter.build_hyperframes_render_argv(
                    "designed-info.html", output, root=root, quality="draft",
                )
                env = adapter.build_hyperframes_env(root)
            self.assertIsInstance(argv, list)
            self.assertIn("hyperframes@0.7.106", argv)
            self.assertEqual(argv[argv.index("--fps") + 1], "30")
            self.assertEqual(argv[argv.index("--workers") + 1], "1")
            self.assertEqual(env["npm_config_cache"], str(root.resolve() / "npm-cache"))
            self.assertEqual(env["XDG_CACHE_HOME"], str(root.resolve() / "chrome"))
            self.assertEqual(env["HYPERFRAMES_BROWSER_PATH"], str(browser.resolve()))
            self.assertEqual(env["HYPERFRAMES_NO_TELEMETRY"], "1")
            with self.assertRaises(ValueError):
                adapter.build_hyperframes_render_argv(
                    "../escape.html", output, root=root,
                )

    def test_symlink_input_is_rejected_before_layout_creation(self):
        benchmark = load_module("phase4_benchmark_symlink", EXPERIMENT_DIR / "benchmark.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.png"
            target.write_bytes(b"fixture")
            link = root / "input.png"
            link.symlink_to(target)
            args = SimpleNamespace(
                input=str(link), run_id="run-link", timeout=5.0,
                work_dir=str(root), provider="ffmpeg", case="portrait",
            )
            with self.assertRaises(ValueError):
                benchmark.run_ffmpeg(args)

    def test_visual_only_validation_rejects_audio_stream(self):
        benchmark = load_module("phase4_benchmark_audio", EXPERIMENT_DIR / "benchmark.py")
        from video_v2.errors import MediaValidationError

        validated = SimpleNamespace(
            summary=SimpleNamespace(audio_stream=object(), path=Path("candidate.mp4")),
        )
        with self.assertRaises(MediaValidationError) as caught:
            benchmark.ensure_visual_only(validated)
        self.assertEqual(caught.exception.code, "media.unexpected_audio")

    def test_failure_and_cancel_write_manifest_before_reraising(self):
        benchmark = load_module("phase4_benchmark_failure", EXPERIMENT_DIR / "benchmark.py")
        from video_v2.errors import CommandFailed, PipelineCancelled

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = root / "phase4-image-motion"
            source = root / "input.png"
            source.write_bytes(b"fixture")
            context = SimpleNamespace(ffmpeg=Path("/fake/ffmpeg"), ffprobe=Path("/fake/ffprobe"))
            for run_id, error, expected_status in (
                ("run-failed", CommandFailed("boom"), "failed"),
                ("run-cancelled", PipelineCancelled(), "cancelled"),
            ):
                args = SimpleNamespace(
                    input=str(source), run_id=run_id, timeout=5.0,
                    work_dir=str(allowed), provider="ffmpeg", case="portrait",
                    duration=4.0, preset="slow_push_in", strength="low",
                    focus_x=0.5, focus_y=0.5,
                )
                with (
                    mock.patch.object(benchmark, "PHASE4_WORK_ROOT", allowed),
                    mock.patch.object(benchmark.RuntimeContext, "resolve", return_value=context),
                    mock.patch.object(benchmark, "_tool_version", return_value="fake 1.0"),
                    mock.patch.object(benchmark, "render_ffmpeg_baseline", side_effect=error),
                    self.assertRaises(type(error)),
                ):
                    benchmark.run_ffmpeg(args)
                manifest_path = allowed / "ffmpeg" / f"portrait-{run_id}" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["status"], expected_status)
                self.assertEqual(manifest["last_stage"], "raw_render")
                self.assertEqual(manifest["errors"][0]["code"], error.code)
                self.assertIn("planned_raw", manifest["commands"])


if __name__ == "__main__":
    unittest.main()
