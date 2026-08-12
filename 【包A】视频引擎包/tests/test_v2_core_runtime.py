# -*- coding: utf-8 -*-
"""计划 03：运行时、外部进程、媒体与原子产物契约。"""

from __future__ import annotations

import ast
import io
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
ENGINE_DIR = PACKAGE_ROOT / "程序文件" / "引擎"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


class RuntimeContractTests(unittest.TestCase):
    def test_runtime_uses_plain_standard_library_subprocess_import(self):
        runtime_path = ENGINE_DIR / "video_v2" / "runtime.py"
        tree = ast.parse(runtime_path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertIn("subprocess", imported)

        from video_v2 import runtime

        self.assertIs(runtime.subprocess, subprocess)

    def test_runtime_error_has_stable_payload(self):
        from video_v2.errors import RenderError

        error = RenderError("media.decode_failed", "media_decode", "无法完整解码", shot_id="shot-003")
        self.assertEqual(error.to_dict()["code"], "media.decode_failed")
        self.assertEqual(error.to_dict()["shot_id"], "shot-003")
        self.assertFalse(error.retryable)

    def test_runner_accepts_only_argv_and_never_interprets_shell_text(self):
        from video_v2.runtime import CommandRunner

        marker = Path(tempfile.gettempdir()) / "v2-shell-marker-must-not-exist"
        marker.unlink(missing_ok=True)
        result = CommandRunner().run(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", f"中文 空格 ; $() `touch {marker}`"]
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("中文 空格", result.stdout)
        self.assertFalse(marker.exists())
        with self.assertRaises(TypeError):
            CommandRunner().run("echo unsafe")
        with self.assertRaises(TypeError):
            CommandRunner().run(("echo", "unsafe"))

    def test_runner_passes_exact_argv_with_shell_disabled(self):
        from video_v2.runtime import CommandRunner

        class CompletedProcess:
            stdout = io.StringIO("")
            stderr = io.StringIO("")

            @staticmethod
            def poll():
                return 0

            @staticmethod
            def wait(timeout=None):
                return 0

        captured = {}

        def factory(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return CompletedProcess()

        requested = ["tool", "中文 空格", ";", "$(literal)"]
        result = CommandRunner(popen_factory=factory).run(requested)
        self.assertEqual(captured["argv"], requested)
        self.assertIs(captured["kwargs"]["shell"], False)
        self.assertEqual(result.argv, tuple(requested))

    def test_runner_honours_pre_cancelled_event(self):
        from video_v2.errors import PipelineCancelled
        from video_v2.runtime import CommandRunner

        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(PipelineCancelled):
            CommandRunner(cancel_event=cancelled).run([sys.executable, "-c", "print('never')"])

    def test_runner_drains_large_stdout_and_stderr_without_deadlock(self):
        from video_v2.runtime import CommandRunner

        result = CommandRunner(log_limit=20_000).run([
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('o'*200000); sys.stderr.write('e'*200000)",
        ])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout), 20_000)
        self.assertEqual(len(result.stderr), 20_000)

    def test_runner_cancellation_terminates_live_process(self):
        from video_v2.errors import PipelineCancelled
        from video_v2.runtime import CommandRunner

        cancelled = threading.Event()
        timer = threading.Timer(0.1, cancelled.set)
        timer.start()
        started = time.monotonic()
        try:
            with self.assertRaises(PipelineCancelled):
                CommandRunner(cancel_event=cancelled, terminate_grace=0.1).run([
                    sys.executable, "-c", "import time; time.sleep(20)",
                ])
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - started, 3.0)

    def test_runner_escalates_from_terminate_to_kill(self):
        from video_v2.errors import PipelineCancelled
        from video_v2.runtime import CommandRunner

        class FlipEvent:
            calls = 0

            def is_set(self):
                self.calls += 1
                return self.calls > 1

        class StubbornProcess:
            def __init__(self):
                self.stdout = io.StringIO("")
                self.stderr = io.StringIO("")
                self.terminated = False
                self.killed = False
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True

            def kill(self):
                self.killed = True
                self.returncode = -9

            def wait(self, timeout=None):
                if timeout is not None and self.returncode is None:
                    raise subprocess.TimeoutExpired("fake", timeout)
                return self.returncode

        process = StubbornProcess()
        captured = {}

        def factory(argv, **kwargs):
            captured.update(kwargs)
            return process

        with self.assertRaises(PipelineCancelled):
            CommandRunner(
                cancel_event=FlipEvent(), popen_factory=factory,
                poll_interval=0.005, terminate_grace=0.005,
            ).run(["fake", "argument"])
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertIs(captured["shell"], False)

    def test_runner_converts_keyboard_interrupt_after_stopping_child(self):
        from video_v2.errors import PipelineCancelled
        from video_v2.runtime import CommandRunner

        class InterruptedProcess:
            def __init__(self):
                self.stdout = io.StringIO("")
                self.stderr = io.StringIO("")
                self.returncode = None
                self.poll_calls = 0
                self.terminated = False

            def poll(self):
                self.poll_calls += 1
                if self.poll_calls == 1:
                    raise KeyboardInterrupt()
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            def kill(self):
                self.returncode = -9

            def wait(self, timeout=None):
                return self.returncode

        process = InterruptedProcess()
        with self.assertRaises(PipelineCancelled):
            CommandRunner(popen_factory=lambda *_args, **_kwargs: process).run(["fake"])
        self.assertTrue(process.terminated)

    def test_progress_observer_failure_does_not_change_runtime_result(self):
        from video_v2.runtime import RuntimeContext

        with tempfile.TemporaryDirectory() as temporary:
            context = RuntimeContext.resolve(
                temporary,
                on_event=lambda _event: (_ for _ in ()).throw(RuntimeError("observer failed")),
            )
            context.emit({"code": "test.event"})

    def test_atomic_commit_preserves_old_target_on_validation_failure(self):
        from video_v2.state import atomic_commit_file

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "artifact.bin"
            target.write_bytes(b"old-valid")
            part = root / "artifact.bin.part-run-1"
            part.write_bytes(b"new-invalid")
            with self.assertRaises(ValueError):
                atomic_commit_file(part, target, validate=lambda _path: (_ for _ in ()).throw(ValueError("bad")))
            self.assertEqual(target.read_bytes(), b"old-valid")

    def test_media_probe_decode_spec_hash_and_atomic_helpers(self):
        from video_v2.errors import MediaValidationError
        from video_v2.media import (
            MediaSpec,
            atomic_replace_validated,
            cleanup_run_parts,
            part_path,
            validate_media,
        )
        from video_v2.runtime import CommandRunner, RuntimeContext

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = RuntimeContext.resolve(root, run_id="unit")
            target = root / "中文 小媒体.mp4"
            temporary_media = part_path(target, context.run_id)
            result = CommandRunner().run([
                str(context.ffmpeg), "-v", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=30:d=0.4",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.4",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", str(temporary_media),
            ])
            self.assertEqual(result.returncode, 0, result.stderr)
            spec = MediaSpec(
                require_video=True, require_audio=True, video_codec="h264",
                width=160, height=120, pixel_format="yuv420p", frame_rate=30,
                audio_codec="aac", sample_rate=48_000, channels=2,
            )
            validated = validate_media(
                temporary_media, ffmpeg=context.ffmpeg, ffprobe=context.ffprobe,
                spec=spec, expected_duration=0.4, duration_tolerance=0.12,
            )
            self.assertEqual(len(validated.sha256), 64)
            atomic_replace_validated(temporary_media, target, validate=lambda _path: validated)
            self.assertTrue(target.is_file())

            rejected = part_path(target, "rejected")
            rejected.write_bytes(b"invalid replacement")
            old_hash = validated.sha256
            with self.assertRaises(ValueError):
                atomic_replace_validated(
                    rejected, target,
                    validate=lambda _path: (_ for _ in ()).throw(ValueError("reject")),
                )
            self.assertFalse(rejected.exists())
            self.assertEqual(validate_media(
                target, ffmpeg=context.ffmpeg, ffprobe=context.ffprobe, spec=spec,
            ).sha256, old_hash)

            with self.assertRaises(MediaValidationError) as caught:
                validate_media(
                    target, ffmpeg=context.ffmpeg, ffprobe=context.ffprobe,
                    spec=MediaSpec(require_video=True, width=1920),
                )
            self.assertEqual(caught.exception.code, "media.spec_mismatch")

            bad = root / "bad.mp4"
            bad.write_bytes(b"not-media")
            with self.assertRaises(MediaValidationError) as caught:
                validate_media(bad, ffmpeg=context.ffmpeg, ffprobe=context.ffprobe)
            self.assertEqual(caught.exception.code, "media.probe_failed")

            own_part = part_path(target, "cleanup")
            foreign_part = part_path(target, "foreign")
            own_part.write_bytes(b"own")
            foreign_part.write_bytes(b"foreign")
            cleanup_run_parts([target], "cleanup")
            self.assertFalse(own_part.exists())
            self.assertTrue(foreign_part.exists())


if __name__ == "__main__":
    unittest.main()
