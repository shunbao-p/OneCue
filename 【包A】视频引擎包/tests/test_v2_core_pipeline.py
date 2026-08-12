# -*- coding: utf-8 -*-
"""计划 03：字幕、运镜、时间线、缓存、TTS 注入与管线契约。"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
ENGINE_DIR = PACKAGE_ROOT / "程序文件" / "引擎"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


class CorePipelineContractTests(unittest.TestCase):
    def test_caption_modes_and_ass_escape(self):
        from video_v2.captions import escape_ass, select_caption_text, split_caption_cards

        self.assertEqual(select_caption_text(True, "speech", "风起。", None), "风起。")
        self.assertEqual(select_caption_text(True, "custom", "风起。", "自定义"), "自定义")
        self.assertIsNone(select_caption_text(False, "speech", "风起。", None))
        self.assertIn(r"\{", escape_ass(r"\{危险}"))
        self.assertGreaterEqual(len(split_caption_cards("风起城门，信使疾行。山雨将至，警灯亮起。")), 1)

    def test_all_motion_presets_have_three_deterministic_strengths(self):
        from video_v2.motion import MOTION_PRESETS, MOTION_STRENGTHS, build_motion_filter

        self.assertEqual(len(MOTION_PRESETS), 8)
        self.assertEqual(MOTION_STRENGTHS, ("low", "medium", "high"))
        for preset in MOTION_PRESETS:
            for strength in MOTION_STRENGTHS:
                first = build_motion_filter(preset, strength, 0.5, 0.5, 1.0, 30, 320, 568)
                second = build_motion_filter(preset, strength, 0.5, 0.5, 1.0, 30, 320, 568)
                self.assertEqual(first, second)

    def test_timeline_math_accounts_for_crossfade_and_last_transition(self):
        from video_v2.timeline import build_timeline

        timeline = build_timeline(
            [3.0, 4.0, 5.0],
            [("crossfade", 0.25), ("cut", 0.0), ("crossfade", 0.25)],
        )
        self.assertAlmostEqual(timeline.expected_duration, 11.75)
        self.assertTrue(timeline.last_transition_ignored)

    def test_caption_cards_split_wrap_and_cover_speech_interval(self):
        from video_v2.captions import build_caption_cards, split_caption_cards

        text = "城门即将关闭，但守军还在等待最后一名信使带回消息。山雨将至，警灯亮起！"
        raw_cards = split_caption_cards(text)
        self.assertGreaterEqual(len(raw_cards), 2)
        self.assertTrue(all(0 < len(card) <= 32 for card in raw_cards))

        cards = build_caption_cards(text, 0.2, 4.8)
        self.assertAlmostEqual(cards[0].start_sec, 0.2)
        self.assertAlmostEqual(cards[-1].end_sec, 4.8)
        self.assertTrue(all(card.end_sec > card.start_sec for card in cards))
        self.assertTrue(all("\n" not in card.text or card.text.count("\n") == 1 for card in cards))
        for card in cards:
            self.assertTrue(all(len(line) <= 16 for line in card.text.splitlines()))
        self.assertTrue(all(left.end_sec == right.start_sec for left, right in zip(cards, cards[1:])))

    def test_caption_extremely_short_interval_merges_tiny_cards(self):
        from video_v2.captions import build_caption_cards

        cards = build_caption_cards("风起。雨落。灯亮。", 0.1, 0.4)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].text, "风起。雨落。灯亮。")
        self.assertAlmostEqual(cards[0].duration_sec, 0.3)

    def test_caption_modes_none_invalid_mode_and_ass_safety(self):
        from video_v2.captions import CaptionCard, build_ass, escape_ass, select_caption_text

        self.assertIsNone(select_caption_text(True, "none", "不可见", None))
        self.assertIsNone(select_caption_text(False, "custom", "旁白", "不可见"))
        with self.assertRaises(ValueError):
            select_caption_text(True, "karaoke", "旁白", None)
        escaped = escape_ass("{\\pos(1,2)}\n换行")
        self.assertEqual(escaped, r"\{\\pos(1,2)\}\N换行")

        empty_ass = build_ass((), title="镜头\n注入")
        self.assertNotIn("Dialogue:", empty_ass)
        self.assertIn("Title: 镜头 注入", empty_ass)
        self.assertNotIn("\n注入", empty_ass)
        ass = build_ass((CaptionCard("{\\b1}安全\n两行", 0.15, 1.25),))
        self.assertIn(r"\{\\b1\}安全\N两行", ass)
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)

    def test_motion_focus_is_clamped_and_filter_reserves_overscan(self):
        from video_v2.motion import build_motion_filter

        low = build_motion_filter("pan_right", "low", -2.0, 3.0, 1.25, 30, 320, 568)
        high = build_motion_filter("pan_right", "high", -2.0, 3.0, 1.25, 30, 320, 568)
        self.assertIn("zoompan=", low)
        self.assertIn("min(max(", low)
        self.assertIn("0.000000", low)
        self.assertIn("1.000000", low)
        self.assertIn("s=320x568:fps=30", low)
        self.assertNotEqual(low, high)

        static = build_motion_filter("static", "high", 0.5, 0.5, 1.25, 30, 320, 568)
        self.assertTrue(static.startswith("scale=320:568:"))

    def test_motion_rejects_unknown_or_non_finite_inputs(self):
        import math

        from video_v2.motion import build_motion_filter

        with self.assertRaises(ValueError):
            build_motion_filter("orbit", "low", 0.5, 0.5, 1.0, 30, 320, 568)
        with self.assertRaises(ValueError):
            build_motion_filter("static", "extreme", 0.5, 0.5, 1.0, 30, 320, 568)
        with self.assertRaises(ValueError):
            build_motion_filter("static", "low", math.nan, 0.5, 1.0, 30, 320, 568)
        with self.assertRaises(ValueError):
            build_motion_filter("static", "low", 0.5, 0.5, 0.0, 30, 320, 568)

    def test_timeline_all_cut_and_consecutive_crossfades(self):
        from video_v2.timeline import build_timeline

        cuts = build_timeline([1.0, 2.0], [("cut", 0.0), ("cut", 0.0)])
        self.assertEqual(cuts.expected_duration, 3.0)
        self.assertEqual([shot.start_sec for shot in cuts.shots], [0.0, 1.0])
        self.assertFalse(cuts.last_transition_ignored)

        fades = build_timeline(
            [3.0, 4.0, 5.0],
            [("crossfade", 0.5), ("crossfade", 0.25), ("cut", 0.0)],
        )
        self.assertAlmostEqual(fades.expected_duration, 11.25)
        self.assertEqual([shot.start_sec for shot in fades.shots], [0.0, 2.5, 6.25])
        self.assertEqual([shot.cumulative_offset_sec for shot in fades.shots], [0.0, 0.5, 0.75])

    def test_timeline_rejects_unbearable_crossfade(self):
        from video_v2.timeline import TimelineError, build_timeline

        with self.assertRaises(TimelineError) as context:
            build_timeline([0.5, 2.0], [("crossfade", 0.5), ("cut", 0.0)])
        self.assertEqual(context.exception.code, "timeline.invalid")
        self.assertEqual(context.exception.shot_index, 0)

    def test_last_crossfade_is_ignored_and_reported(self):
        from video_v2.timeline import LAST_TRANSITION_WARNING, build_timeline

        timeline = build_timeline([1.0], [("crossfade", 0.9)])
        self.assertEqual(timeline.expected_duration, 1.0)
        self.assertEqual(timeline.shots[0].transition_type, "cut")
        self.assertEqual(timeline.shots[0].overlap_sec, 0.0)
        self.assertEqual(timeline.warnings, (LAST_TRANSITION_WARNING,))

    def test_public_pipeline_is_tts_provider_injectable(self):
        from video_v2.pipeline import render_job

        self.assertIn("tts_provider", render_job.__annotations__)

    def test_render_cache_key_invalidation_matrix(self):
        from video_v2.pipeline import _final_key, _shot_key

        project = SimpleNamespace(caption_style_preset="default_lower_third", width=1080, height=1920, fps=30)
        bundle = SimpleNamespace(project=project)
        shot = SimpleNamespace(
            keyframe_sha256="a" * 64,
            focus_x=0.5,
            focus_y=0.4,
            motion_preset="slow_push_in",
            motion_strength="low",
            head_pad_sec=0.15,
            tail_pad_sec=0.25,
            purpose="只进报告",
            motion_intent="只进报告",
            hero=False,
        )
        audio = SimpleNamespace(sha256="b" * 64, duration_sec=2.17)
        base = _shot_key(bundle, shot, audio, "风起。")
        for field, value in (
            ("keyframe_sha256", "c" * 64),
            ("focus_x", 0.6),
            ("motion_preset", "pan_left"),
            ("motion_strength", "high"),
            ("head_pad_sec", 0.30),
        ):
            original = getattr(shot, field)
            setattr(shot, field, value)
            self.assertNotEqual(_shot_key(bundle, shot, audio, "风起。"), base, field)
            setattr(shot, field, original)
        self.assertNotEqual(_shot_key(bundle, shot, SimpleNamespace(sha256="d" * 64, duration_sec=2.17), "风起。"), base)
        self.assertNotEqual(_shot_key(bundle, shot, audio, "雨至。"), base)

        # purpose / intent / hero / target_duration_sec 不参与像素与声音键。
        shot.purpose = "另一段报告文字"
        shot.motion_intent = "另一段运镜意图"
        shot.hero = True
        project.target_duration_sec = 99.0
        self.assertEqual(_shot_key(bundle, shot, audio, "风起。"), base)

        final_base = _final_key(["1" * 64, "2" * 64], [("crossfade", 0.25), ("cut", 0.0)])
        self.assertNotEqual(final_base, _final_key(["1" * 64, "2" * 64], [("cut", 0.0), ("cut", 0.0)]))
        self.assertNotEqual(final_base, _final_key(["1" * 64, "3" * 64], [("crossfade", 0.25), ("cut", 0.0)]))

    def test_cache_hash_and_manifest_corruption_never_hit(self):
        from video_v2.errors import RenderError
        from video_v2.state import cache_entry_matches, empty_manifest, load_manifest, save_manifest, update_cache_entry

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "audio" / "shot-001.wav"
            artifact.parent.mkdir()
            artifact.write_bytes(b"valid")
            manifest = empty_manifest()
            update_cache_entry(
                manifest,
                layer="audio",
                entry_id="shot-001",
                key="expected",
                bundle_root=root,
                artifact=artifact,
            )
            hit, _, reason = cache_entry_matches(
                manifest["audio"]["shot-001"],
                expected_key="expected",
                bundle_root=root,
            )
            self.assertTrue(hit)
            self.assertIsNone(reason)
            artifact.write_bytes(b"tampered")
            hit, _, reason = cache_entry_matches(
                manifest["audio"]["shot-001"],
                expected_key="expected",
                bundle_root=root,
            )
            self.assertFalse(hit)
            self.assertEqual(reason, "artifact_mismatch")

            manifest_path = root / "cache" / "manifest.json"
            save_manifest(manifest_path, manifest, run_id="valid")
            manifest_path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(RenderError) as caught:
                load_manifest(manifest_path)
            self.assertEqual(caught.exception.code, "cache.invalid")

    def test_compose_handles_crossfade_cut_crossfade_timebases(self):
        from video_v2.media import probe_media
        from video_v2.pipeline import _compose_final
        from video_v2.runtime import RuntimeContext

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = RuntimeContext.resolve(root, run_id="mixed-timebase")
            runner = context.runner()
            shots = []
            durations = []
            for index, color in enumerate(("red", "green", "blue", "yellow")):
                target = root / f"shot-{index}.mp4"
                result = runner.run([
                    str(context.ffmpeg), "-hide_banner", "-v", "error", "-nostdin", "-y",
                    "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:r=30:d=0.6",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.6",
                    "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", str(target),
                ])
                self.assertEqual(result.returncode, 0, result.stderr)
                shots.append(target)
                durations.append(probe_media(target, ffprobe=context.ffprobe, runner=runner).duration)
            expected = sum(durations) - 0.2
            validated = _compose_final(
                shots,
                durations,
                [("crossfade", 0.1), ("cut", 0.0), ("crossfade", 0.1), ("cut", 0.0)],
                target=root / "final.mp4",
                expected_duration=expected,
                context=context,
                runner=runner,
            )
            self.assertLessEqual(abs(validated.duration - expected), 0.20)


class TtsCacheContractTests(unittest.TestCase):
    class FakeRunner:
        def __init__(self):
            self.calls = []

        def run(self, argv, **_kwargs):
            self.calls.append(tuple(argv))
            output = Path(argv[argv.index("--out") + 1])
            with wave.open(str(output), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(b"\x00\x00" * 4800)
            return type("Result", (), {"returncode": 0, "stdout": "PROGRESS 100/100\nDONE 0.10\n", "stderr": "", "cancelled": False})()

    @staticmethod
    def probe(path):
        with wave.open(str(path), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        return {"duration_sec": duration, "codec": "pcm_s16le", "sample_rate": 48000}

    def test_fake_provider_audio_cache_and_text_invalidation(self):
        from video_v2.state import empty_manifest
        from video_v2.tts import DotsTtsProvider, ensure_shot_audio

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "python3"
            script = root / "dots_synth.py"
            prompts = root / "prompts"
            prompts.mkdir()
            python.write_text("runtime", encoding="utf-8")
            script.write_text("adapter", encoding="utf-8")
            (prompts / "女播音.wav").write_bytes(b"voice")
            runner = self.FakeRunner()
            provider = DotsTtsProvider(
                python_path=python,
                synth_script=script,
                prompts_dir=prompts,
                runner=runner,
            )
            manifest = empty_manifest()
            first = ensure_shot_audio(
                shot_id="shot-001", text="风起。", voice="女播音.wav",
                bundle_root=root, run_id="run1", manifest=manifest, provider=provider,
                probe_audio=self.probe, full_decode=lambda _path: True,
            )
            second = ensure_shot_audio(
                shot_id="shot-001", text="风起。", voice="女播音.wav",
                bundle_root=root, run_id="run2", manifest=manifest, provider=provider,
                probe_audio=self.probe, full_decode=lambda _path: True,
            )
            changed = ensure_shot_audio(
                shot_id="shot-001", text="雨至。", voice="女播音.wav",
                bundle_root=root, run_id="run3", manifest=manifest, provider=provider,
                probe_audio=self.probe, full_decode=lambda _path: True,
            )
            self.assertEqual((first.cache_status, second.cache_status, changed.cache_status), ("rebuilt", "hit", "rebuilt"))
            self.assertEqual(len(runner.calls), 2)
            self.assertEqual(runner.calls[0][0], str(python))
            self.assertNotIn("/api/tts", " ".join(runner.calls[0]))

    def test_unknown_voice_is_deterministic_and_not_retried(self):
        from video_v2.tts import DotsTtsProvider

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "python3"
            script = root / "dots_synth.py"
            prompts = root / "prompts"
            prompts.mkdir()
            python.write_text("runtime", encoding="utf-8")
            script.write_text("adapter", encoding="utf-8")
            runner = self.FakeRunner()
            provider = DotsTtsProvider(python_path=python, synth_script=script, prompts_dir=prompts, runner=runner)
            with self.assertRaises(Exception) as caught:
                provider.synthesize("风起。", "不存在.wav", root / "out.wav", shot_id="shot-001")
            self.assertEqual(getattr(caught.exception, "code", None), "tts.voice_unknown")
            self.assertEqual(runner.calls, [])

    def test_corrupted_cached_wav_is_rebuilt(self):
        from video_v2.state import empty_manifest
        from video_v2.tts import DotsTtsProvider, ensure_shot_audio

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python, script, prompts = root / "python3", root / "dots_synth.py", root / "prompts"
            prompts.mkdir()
            python.write_text("runtime", encoding="utf-8")
            script.write_text("adapter", encoding="utf-8")
            (prompts / "女播音.wav").write_bytes(b"voice")
            runner = self.FakeRunner()
            provider = DotsTtsProvider(python_path=python, synth_script=script, prompts_dir=prompts, runner=runner)
            manifest = empty_manifest()
            common = dict(
                shot_id="shot-001", text="风起。", voice="女播音.wav", bundle_root=root,
                manifest=manifest, provider=provider, probe_audio=self.probe, full_decode=lambda _path: True,
            )
            first = ensure_shot_audio(run_id="run1", **common)
            first.path.write_bytes(b"corrupt")
            rebuilt = ensure_shot_audio(run_id="run2", **common)
            self.assertEqual(rebuilt.cache_status, "rebuilt")
            self.assertEqual(len(runner.calls), 2)

    def test_retryable_not_ready_failure_retries_once(self):
        from video_v2.tts import DotsTtsProvider

        class RetryRunner(self.FakeRunner):
            def run(self, argv, **kwargs):
                if not self.calls:
                    self.calls.append(tuple(argv))
                    return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "connection refused", "cancelled": False})()
                return super().run(argv, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python, script, prompts = root / "python3", root / "dots_synth.py", root / "prompts"
            prompts.mkdir()
            python.write_text("runtime", encoding="utf-8")
            script.write_text("adapter", encoding="utf-8")
            (prompts / "女播音.wav").write_bytes(b"voice")
            runner = RetryRunner()
            provider = DotsTtsProvider(python_path=python, synth_script=script, prompts_dir=prompts, runner=runner)
            result = provider.synthesize("风起。", "女播音.wav", root / "out.wav", shot_id="shot-001")
            self.assertEqual(result.attempts, 2)
            self.assertEqual(len(runner.calls), 2)

    def test_forced_tts_failure_preserves_old_valid_wav(self):
        from video_v2.state import empty_manifest, sha256_file
        from video_v2.tts import DotsTtsProvider, ensure_shot_audio

        class FailingRunner(self.FakeRunner):
            def run(self, argv, **_kwargs):
                self.calls.append(tuple(argv))
                output = Path(argv[argv.index("--out") + 1])
                output.write_bytes(b"partial-invalid")
                return type("Result", (), {"returncode": 3, "stdout": "", "stderr": "fatal", "cancelled": False})()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python, script, prompts = root / "python3", root / "dots_synth.py", root / "prompts"
            prompts.mkdir()
            python.write_text("runtime", encoding="utf-8")
            script.write_text("adapter", encoding="utf-8")
            (prompts / "女播音.wav").write_bytes(b"voice")
            manifest = empty_manifest()
            good = DotsTtsProvider(python_path=python, synth_script=script, prompts_dir=prompts, runner=self.FakeRunner())
            common = dict(
                shot_id="shot-001", text="风起。", voice="女播音.wav", bundle_root=root,
                manifest=manifest, probe_audio=self.probe, full_decode=lambda _path: True,
            )
            first = ensure_shot_audio(run_id="good", provider=good, **common)
            old_hash = sha256_file(first.path)
            failing = DotsTtsProvider(python_path=python, synth_script=script, prompts_dir=prompts, runner=FailingRunner())
            with self.assertRaises(Exception) as caught:
                ensure_shot_audio(run_id="failed", provider=failing, force=True, **common)
            self.assertEqual(getattr(caught.exception, "code", None), "tts.failed")
            self.assertEqual(sha256_file(first.path), old_hash)
            self.assertFalse((root / "audio" / "shot-001.part-failed.wav").exists())


class CliContractTests(unittest.TestCase):
    @staticmethod
    def invoke(argv, *, result=None, error=None):
        from video_v2.__main__ import main

        stdout = io.StringIO()
        stderr = io.StringIO()
        replacement = mock.Mock(return_value=result, side_effect=error)
        with mock.patch("video_v2.pipeline.render_job", replacement):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_render_cli_exit_zero_has_one_json_stdout_object(self):
        result = SimpleNamespace(to_dict=lambda: {
            "ok": True,
            "status": "success",
            "final_path": "output/final.mp4",
            "final_sha256": "a" * 64,
            "final_duration_sec": 1.0,
            "shot_count": 1,
            "cache_summary": {},
            "warnings": [],
            "errors": [],
        })
        code, stdout, stderr = self.invoke(["render", "--job-dir", "/tmp/job", "--json"], result=result)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout)["ok"])
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        self.assertEqual(stderr, "")

    def test_render_cli_exit_two_for_contract_error(self):
        from video_v2.__main__ import main

        with tempfile.TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["render", "--job-dir", temporary, "--json"])
        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "contract_error")
        self.assertEqual(len(stdout.getvalue().strip().splitlines()), 1)
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_render_cli_exit_three_for_expected_runtime_error(self):
        from video_v2.errors import RenderError

        code, stdout, stderr = self.invoke(
            ["render", "--job-dir", "/tmp/job", "--json"],
            error=RenderError("pipeline.dependency_missing", "shot_render", "依赖缺失"),
        )
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "pipeline.dependency_missing")
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        self.assertNotIn("Traceback", stderr)

    def test_render_cli_exit_130_for_cancel(self):
        from video_v2.errors import PipelineCancelled

        code, stdout, stderr = self.invoke(
            ["render", "--job-dir", "/tmp/job", "--json"],
            error=PipelineCancelled(stage="compose"),
        )
        self.assertEqual(code, 130)
        self.assertEqual(json.loads(stdout)["status"], "cancelled")
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        self.assertNotIn("Traceback", stderr)

    def test_render_cli_exit_one_for_internal_error(self):
        code, stdout, stderr = self.invoke(
            ["render", "--job-dir", "/tmp/job", "--json"],
            error=RuntimeError("unexpected"),
        )
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout)["errors"][0]["code"], "pipeline.internal_error")
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        self.assertIn("video_v2 render internal error", stderr)
        self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main()
