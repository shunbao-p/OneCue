# -*- coding: utf-8 -*-
"""计划 05：MVP 验收 runner 的短测试与安全边界。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
ENGINE_DIR = PACKAGE_ROOT / "程序文件" / "引擎"
RUNNER_PATH = TESTS_DIR / "run_v2_mvp_acceptance.py"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from video_v2.errors import PipelineCancelled, RenderError
from video_v2.pipeline import render_job
from video_v2.runtime import CommandResult, CommandRunner, RuntimeContext
from video_v2.tts import DotsTtsProvider


def load_runner():
    spec = importlib.util.spec_from_file_location("v2_mvp_acceptance_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载验收 runner：{RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ManifestContractTests(unittest.TestCase):
    def test_required_manifest_shape_and_bundle_relative_paths(self):
        runner = load_runner()
        manifest = runner.new_acceptance_manifest()
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(manifest["status"], "in_progress")
        self.assertEqual(manifest["overall_verdict"], "CONDITIONAL")
        self.assertEqual(set(manifest["projects"]), {"story-mail-car", "explainer-sponge-city"})
        for project in manifest["projects"].values():
            self.assertEqual(project["user_review"]["status"], "not_started")
            self.assertEqual(project["internal_revisions_used"], 0)
            self.assertEqual(project["user_revisions_used"], 0)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            safe = root / "story-mail-car" / "output" / "final.mp4"
            safe.parent.mkdir(parents=True)
            safe.write_bytes(b"final")
            self.assertEqual(
                runner.bundle_relative_path(root, safe),
                "story-mail-car/output/final.mp4",
            )
            with self.assertRaises(ValueError):
                runner.bundle_relative_path(root, root.parent / "outside.mp4")
            link = root / "linked.mp4"
            link.symlink_to(safe)
            with self.assertRaises(ValueError):
                runner.bundle_relative_path(root, link)

    def test_manifest_rejects_missing_fields_unsafe_paths_and_pass_before_user_review(self):
        runner = load_runner()
        valid = runner.new_acceptance_manifest()
        runner.validate_acceptance_manifest(valid)

        missing = json.loads(json.dumps(valid))
        del missing["known_motion_boundary"]
        with self.assertRaises(ValueError):
            runner.validate_acceptance_manifest(missing)

        unsafe = json.loads(json.dumps(valid))
        unsafe["projects"]["story-mail-car"]["job_dir"] = "../escape"
        with self.assertRaises(ValueError):
            runner.validate_acceptance_manifest(unsafe)

        premature = json.loads(json.dumps(valid))
        premature["overall_verdict"] = "PASS"
        with self.assertRaises(ValueError):
            runner.validate_acceptance_manifest(premature)


class MediaAuditTests(unittest.TestCase):
    def test_expected_media_spec_and_duration_gates(self):
        runner = load_runner()
        summary = {
            "duration": 35.050,
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1080,
                    "height": 1920,
                    "pixel_format": "yuv420p",
                    "frame_rate": 30.0,
                    "duration": 35.000,
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": 48000,
                    "channels": 2,
                    "duration": 35.050,
                },
            ],
        }
        audit = runner.evaluate_final_media(summary, report_expected_duration=35.0)
        self.assertTrue(audit["ok"], audit)
        self.assertAlmostEqual(audit["av_duration_delta_sec"], 0.05)
        self.assertAlmostEqual(audit["report_duration_error_sec"], 0.05)

        bad = json.loads(json.dumps(summary))
        bad["streams"][0]["width"] = 720
        bad["streams"][1]["duration"] = 35.2
        audit = runner.evaluate_final_media(bad, report_expected_duration=34.0)
        self.assertFalse(audit["ok"])
        self.assertIn("video.width", audit["failures"])
        self.assertIn("av.duration_delta", audit["failures"])
        self.assertIn("report.duration_error", audit["failures"])

    def test_contact_sheet_argv_is_list_and_output_isolated(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ffmpeg = root / "ffmpeg"
            source = root / "job" / "output" / "final.mp4"
            output = root / "job" / "evidence" / "contact sheet.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"media")
            argv = runner.build_contact_sheet_argv(
                ffmpeg=ffmpeg,
                source=source,
                output=output,
                duration_sec=35.0,
                columns=3,
                rows=3,
            )
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[0], str(ffmpeg))
            self.assertEqual(argv[-1], str(output))
            self.assertIn("tile=3x3", argv[argv.index("-vf") + 1])
            self.assertNotIn("drawtext", argv[argv.index("-vf") + 1])
            with self.assertRaises(ValueError):
                runner.build_contact_sheet_argv(
                    ffmpeg=ffmpeg,
                    source=source,
                    output=root / "outside.png",
                    duration_sec=35.0,
                    allowed_output_root=output.parent,
                )


class CacheAndProtectionTests(unittest.TestCase):
    def test_cache_summary_gates_full_hit_and_selected_rebuild(self):
        runner = load_runner()
        full = {"audio_hit": 8, "audio_rebuilt": 0, "shot_hit": 8, "shot_rebuilt": 0, "final_hit": 1, "final_rebuilt": 0}
        self.assertEqual(runner.classify_cache_summary(full, shot_count=8, mode="full-hit")["status"], "pass")
        self.assertEqual(
            runner.classify_cache_summary(full | {"shot_hit": 7, "shot_rebuilt": 1, "final_hit": 0, "final_rebuilt": 1}, shot_count=8, mode="selected-rerender")["status"],
            "pass",
        )
        self.assertEqual(runner.classify_cache_summary(full | {"audio_rebuilt": 1, "audio_hit": 7}, shot_count=8, mode="full-hit")["status"], "fail")

    def test_final_hash_guard_detects_and_reports_change(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "final.mp4"
            target.write_bytes(b"old")
            snapshot = runner.snapshot_file(target)
            runner.assert_file_unchanged(target, snapshot)
            target.write_bytes(b"new")
            with self.assertRaises(AssertionError):
                runner.assert_file_unchanged(target, snapshot)

    def test_real_command_runner_uses_list_shell_false_and_timeout(self):
        runner = load_runner()
        process = mock.Mock(returncode=0, stdout="{}", stderr="")
        with mock.patch.object(runner.subprocess, "run", return_value=process) as run:
            result = runner.run_command(["tool", "--json"], timeout_sec=9.0)
        self.assertIs(result, process)
        self.assertEqual(run.call_args.args[0], ["tool", "--json"])
        self.assertIs(run.call_args.kwargs["shell"], False)
        self.assertEqual(run.call_args.kwargs["timeout"], 9.0)
        with self.assertRaises(TypeError):
            runner.run_command("tool --json", timeout_sec=9.0)
        with self.assertRaises(ValueError):
            runner.run_command(["tool"], timeout_sec=0)

    def test_runner_orchestrates_existing_cli_without_importing_pipeline(self):
        runner = load_runner()
        argv = runner.build_video_v2_argv(
            python=Path("/safe/python3"),
            command="render",
            job_dir=Path("/safe/job"),
            selected_shots=("shot-003",),
            force=False,
        )
        self.assertEqual(argv[:5], ["/safe/python3", "-B", "-m", "video_v2", "render"])
        self.assertEqual(argv[-3:], ["--shot", "shot-003", "--json"])
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("from video_v2.pipeline import", source)
        self.assertNotIn("render_job(", source)


class FailureInjectionTests(unittest.TestCase):
    FIXTURE = TESTS_DIR / "fixtures" / "v2_job_bundle" / "valid_minimal"

    def _isolated_bundle_with_old_final(self, root: Path) -> tuple[Path, bytes]:
        job_dir = root / "job"
        shutil.copytree(self.FIXTURE, job_dir)
        old_final = b"plan05-protected-old-final"
        final_path = job_dir / "output" / "final.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(old_final)
        return job_dir, old_final

    def test_tts_unavailable_fails_structurally_and_preserves_old_final(self):
        with tempfile.TemporaryDirectory() as temporary:
            job_dir, old_final = self._isolated_bundle_with_old_final(Path(temporary))
            provider = DotsTtsProvider(
                installed=False,
                python_path=job_dir / "missing-python",
                synth_script=job_dir / "missing-dots-synth.py",
                prompts_dir=job_dir / "missing-prompts",
                runner=mock.Mock(),
            )
            with self.assertRaises(RenderError) as raised:
                render_job(job_dir, tts_provider=provider)
            self.assertEqual(raised.exception.code, "tts.not_installed")
            self.assertEqual((job_dir / "output" / "final.mp4").read_bytes(), old_final)
            report = json.loads((job_dir / "output" / "render_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["errors"][0]["code"], "tts.not_installed")
            self.assertFalse(list(job_dir.rglob(".part-*")))

    def test_pre_cancelled_pipeline_reports_cancelled_and_preserves_old_final(self):
        with tempfile.TemporaryDirectory() as temporary:
            job_dir, old_final = self._isolated_bundle_with_old_final(Path(temporary))
            cancelled = threading.Event()
            cancelled.set()
            with self.assertRaises(PipelineCancelled):
                render_job(job_dir, cancel_event=cancelled)
            self.assertEqual((job_dir / "output" / "final.mp4").read_bytes(), old_final)
            report = json.loads((job_dir / "output" / "render_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "cancelled")
            self.assertEqual(report["errors"][0]["code"], "pipeline.cancelled")
            self.assertFalse(list(job_dir.rglob(".part-*")))

    @unittest.skipUnless(os.environ.get("PLAN05_MOTION_FALLBACK_JOB"), "仅在计划 05 隔离副本上运行")
    def test_real_ffmpeg_motion_failure_falls_back_to_static(self):
        job_dir = Path(os.environ["PLAN05_MOTION_FALLBACK_JOB"]).resolve()
        base = RuntimeContext.resolve(job_dir, run_id="plan05-motion-fallback")
        manifest_path = job_dir / "cache" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["shots"]["shot-003"]["key"] = "plan05-explicit-fallback-probe-miss"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        class FailFirstMotionRunner:
            def __init__(self) -> None:
                self.delegate = CommandRunner()
                self.failures = 0

            def run(self, argv, **kwargs):
                graph = argv[argv.index("-filter_complex") + 1] if "-filter_complex" in argv else ""
                if self.failures == 0 and "zoompan" in graph:
                    self.failures += 1
                    return CommandResult(tuple(argv), 1, "", "plan05 injected motion failure", 0.0)
                return self.delegate.run(argv, **kwargs)

        injected_runner = FailFirstMotionRunner()

        class InjectedRuntime:
            job_dir = base.job_dir
            ffmpeg = base.ffmpeg
            ffprobe = base.ffprobe
            font_path = base.font_path
            font_name = base.font_name
            dots = base.dots
            run_id = base.run_id
            cancel_event = None

            @staticmethod
            def runner():
                return injected_runner

            @staticmethod
            def emit(_event):
                return None

        result = render_job(job_dir, selected_shot_ids=("shot-003",), runtime=InjectedRuntime())
        self.assertTrue(result.ok)
        self.assertEqual(injected_runner.failures, 1)
        self.assertEqual(result.cache_summary["shot_rebuilt"], 1)
        report = json.loads((job_dir / "output" / "render_report.json").read_text(encoding="utf-8"))
        shot = next(item for item in report["shots"] if item["id"] == "shot-003")
        self.assertTrue(shot["motion"]["fallback_used"])
        self.assertEqual(shot["motion"]["actual_preset"], "static")
        self.assertIn("render.motion_fallback", {item["code"] for item in report["warnings"]})
        self.assertFalse(list(job_dir.rglob(".part-*")))

    @unittest.skipUnless(os.environ.get("PLAN05_MOTION_DOUBLE_FAILURE_JOB"), "仅在计划 05 隔离副本上运行")
    def test_motion_and_static_double_failure_preserves_old_final(self):
        job_dir = Path(os.environ["PLAN05_MOTION_DOUBLE_FAILURE_JOB"]).resolve()
        base = RuntimeContext.resolve(job_dir, run_id="plan05-motion-double-failure")
        final_path = job_dir / "output" / "final.mp4"
        old_final = hashlib.sha256(final_path.read_bytes()).hexdigest()
        manifest_path = job_dir / "cache" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["shots"]["shot-003"]["key"] = "plan05-explicit-double-failure-probe-miss"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        class FailBothMotionAttemptsRunner:
            def __init__(self) -> None:
                self.delegate = CommandRunner()
                self.failures = 0

            def run(self, argv, **kwargs):
                if "-filter_complex" in argv and self.failures < 2:
                    self.failures += 1
                    return CommandResult(tuple(argv), 1, "", "plan05 injected double motion failure", 0.0)
                return self.delegate.run(argv, **kwargs)

        injected_runner = FailBothMotionAttemptsRunner()

        class InjectedRuntime:
            job_dir = base.job_dir
            ffmpeg = base.ffmpeg
            ffprobe = base.ffprobe
            font_path = base.font_path
            font_name = base.font_name
            dots = base.dots
            run_id = base.run_id
            cancel_event = None

            @staticmethod
            def runner():
                return injected_runner

            @staticmethod
            def emit(_event):
                return None

        with self.assertRaises(RenderError) as raised:
            render_job(job_dir, selected_shot_ids=("shot-003",), runtime=InjectedRuntime())
        self.assertEqual(raised.exception.code, "render.fallback_failed")
        self.assertEqual(injected_runner.failures, 2)
        self.assertEqual(hashlib.sha256(final_path.read_bytes()).hexdigest(), old_final)
        report = json.loads((job_dir / "output" / "render_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["errors"][0]["code"], "render.fallback_failed")
        self.assertFalse(list(job_dir.rglob(".part-*")))


if __name__ == "__main__":
    unittest.main()
