#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""计划 03 的显式真实运行与媒体验收脚本（不参与默认 test discovery）。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import wave
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
ENGINE_DIR = PACKAGE_ROOT / "程序文件" / "引擎"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


def tts_smoke(work_dir: Path) -> dict:
    from video_v2.media import decode_media, probe_media
    from video_v2.runtime import RuntimeContext
    from video_v2.state import empty_manifest, save_manifest
    from video_v2.tts import DotsTtsProvider, ensure_shot_audio

    root = work_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    context = RuntimeContext.resolve(root)
    runner = context.runner()
    calls = {"count": 0}

    class CountingRunner:
        def run(self, argv, **kwargs):
            calls["count"] += 1
            return runner.run(argv, **kwargs)

    dots = dict(context.dots)
    provider = DotsTtsProvider(
        python_path=dots.get("python"),
        synth_script=PACKAGE_ROOT / "程序文件" / "网站" / "dots_synth.py",
        prompts_dir=dots.get("prompts"),
        runner=CountingRunner(),
        installed=bool(dots.get("installed")),
    )
    manifest = empty_manifest()
    manifest_path = root / "cache" / "manifest.json"

    def probe_audio(path: Path):
        return probe_media(path, ffprobe=context.ffprobe, runner=runner)

    def full_decode(path: Path):
        decode_media(path, ffmpeg=context.ffmpeg, runner=runner)
        return True

    common = {
        "shot_id": "shot-smoke",
        "text": "风起城门，灯火初明。",
        "voice": "女播音.wav",
        "bundle_root": root,
        "manifest": manifest,
        "provider": provider,
        "probe_audio": probe_audio,
        "full_decode": full_decode,
        "manifest_path": manifest_path,
    }
    first = ensure_shot_audio(run_id="tts-smoke-1", **common)
    first_provider_calls = calls["count"]
    second = ensure_shot_audio(run_id="tts-smoke-2", **common)
    save_manifest(manifest_path, manifest, run_id="tts-smoke-final")

    silence = runner.run([
        str(context.ffmpeg), "-hide_banner", "-nostdin", "-i", str(second.path),
        "-af", "silencedetect=noise=-45dB:d=0.1", "-f", "null", "-",
    ])
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", silence.stderr)]
    tail_silence = max(0.0, second.duration_sec - starts[-1]) if starts else 0.0
    return {
        "ok": True,
        "work_dir": str(root),
        "voice": "女播音.wav",
        "text": common["text"],
        "first_cache_status": first.cache_status,
        "second_cache_status": second.cache_status,
        "provider_calls_after_first": first_provider_calls,
        "provider_calls_total": calls["count"],
        "wav": second.relative_path,
        "sha256": second.sha256,
        "duration_sec": second.duration_sec,
        "tail_silence_sec_observed": tail_silence,
        "attempts": first.attempts,
        "provider_version": second.provider_version,
        "options_version": second.options_version,
    }


def seed_audio_cache(job_dir: Path) -> dict:
    """把已由前序硬门验证的 WAV 登记为可复用音频缓存。"""

    from video_v2.contract import load_job_bundle
    from video_v2.media import decode_media, probe_media
    from video_v2.runtime import PIPELINE_VERSION, RuntimeContext
    from video_v2.state import empty_manifest, load_manifest, save_manifest, update_cache_entry
    from video_v2.tts import OPTIONS_VERSION, PROVIDER_NAME, PROVIDER_VERSION, audio_cache_key

    bundle = load_job_bundle(job_dir)
    context = RuntimeContext.resolve(bundle.root)
    runner = context.runner()
    manifest_path = bundle.root / "cache" / "manifest.json"
    manifest = load_manifest(manifest_path) if manifest_path.exists() else empty_manifest(
        implementation_version=PIPELINE_VERSION
    )
    seeded: list[dict] = []
    for shot in bundle.shots:
        audio_path = bundle.root / "audio" / f"{shot.id}.wav"
        summary = probe_media(audio_path, ffprobe=context.ffprobe, runner=runner)
        decode_media(audio_path, ffmpeg=context.ffmpeg, runner=runner)
        if summary.audio_stream is None or summary.duration <= 0:
            raise ValueError(f"{shot.id} 缺少有效音频流")
        media = summary.to_dict()
        media.pop("path", None)
        key = audio_cache_key(
            shot.speech_text,
            shot.voice,
            provider_name=PROVIDER_NAME,
            provider_version=PROVIDER_VERSION,
            options_version=OPTIONS_VERSION,
        )
        entry = update_cache_entry(
            manifest,
            layer="audio",
            entry_id=shot.id,
            key=key,
            bundle_root=bundle.root,
            artifact=audio_path,
            media_summary=media,
            duration_sec=summary.duration,
            implementation_version=PROVIDER_VERSION,
        )
        seeded.append({"shot_id": shot.id, "path": entry["path"], "sha256": entry["sha256"], "duration_sec": summary.duration})
    save_manifest(manifest_path, manifest, run_id="seed-audio-cache")
    return {"ok": True, "job_dir": str(bundle.root), "seeded": seeded}


def fake_three_shot(work_dir: Path) -> dict:
    """用短 WAV fake Provider 实跑三镜头正式规格端到端与二次全命中。"""

    from video_v2.pipeline import render_job
    from video_v2.runtime import RuntimeContext
    from video_v2.state import atomic_write_json, sha256_file
    from video_v2.tts import ProviderRun

    root = work_dir.resolve()
    if root.exists():
        raise FileExistsError(f"fake 三镜头目录须为新目录: {root}")
    keyframes = root / "assets" / "keyframes"
    keyframes.mkdir(parents=True)
    source_dir = PACKAGE_ROOT / "成片" / "短视频V2样片" / "phase1-three-shot" / "assets" / "keyframes"
    image_hashes: list[str] = []
    for index in range(1, 4):
        target = keyframes / f"shot-{index:03d}.png"
        shutil.copy2(source_dir / target.name, target)
        image_hashes.append(sha256_file(target))
    project = {
        "schema_version": 1,
        "project_id": "phase3-core-fake-three-shot",
        "title": "fake 三镜头端到端",
        "language": "zh-CN",
        "target_duration_sec": 1.4,
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "defaults": {"voice": "女播音.wav", "timing": {"head_pad_sec": 0.15, "tail_pad_sec": 0.25}},
        "captions": {"enabled": True, "style_preset": "default_lower_third"},
    }
    motions = (("slow_push_in", "low"), ("pan_left", "medium"), ("slow_pull_out", "low"))
    shots = []
    for index, (preset, strength) in enumerate(motions, 1):
        shots.append({
            "id": f"shot-{index:03d}",
            "purpose": "fake Provider 短媒体端到端",
            "speech": {"kind": "narration", "text": f"第{index}镜。"},
            "visual": {
                "keyframe": {"path": f"assets/keyframes/shot-{index:03d}.png", "sha256": image_hashes[index - 1]},
                "focus": {"x": 0.5, "y": 0.45},
            },
            "motion": {"preset": preset, "strength": strength, "intent": "短媒体验证"},
            "caption": {"mode": "speech"},
            "transition_out": {"type": "crossfade" if index == 1 else "cut", "duration_sec": 0.1 if index == 1 else 0},
            "hero": index == 2,
        })
    atomic_write_json(root / "project.json", project, run_id="fake-input")
    atomic_write_json(root / "storyboard.json", {"schema_version": 1, "project_id": project["project_id"], "shots": shots}, run_id="fake-input")

    class FakeProvider:
        name = "fake-tts"
        version = "fake-short-v1"
        options_version = "pcm48k-0.20s-v1"

        def __init__(self):
            self.calls: list[str] = []

        def synthesize(self, text, voice, output_path, *, shot_id=None, on_progress=None):
            self.calls.append(str(shot_id))
            with wave.open(str(output_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(b"\x00\x00" * 9600)
            if on_progress is not None:
                on_progress(100)
            return ProviderRun(1, 0.0, "PROGRESS 100/100\nDONE 0.20\n", "", (100,), 0.2)

    provider = FakeProvider()
    first = render_job(root, tts_provider=provider, runtime=RuntimeContext.resolve(root))
    calls_after_first = len(provider.calls)
    second = render_job(root, tts_provider=provider, runtime=RuntimeContext.resolve(root))
    return {
        "ok": True,
        "job_dir": str(root),
        "provider_calls_after_first": calls_after_first,
        "provider_calls_total": len(provider.calls),
        "first_cache_summary": dict(first.cache_summary),
        "second_cache_summary": dict(second.cache_summary),
        "final_path": second.final_path,
        "final_sha256": second.final_sha256,
        "final_duration_sec": second.final_duration,
    }


def fake_selective_force(job_dir: Path) -> dict:
    """在既有 fake Bundle 上验证选择性 force 只触及所选镜头。"""

    from video_v2.pipeline import render_job
    from video_v2.runtime import RuntimeContext
    from video_v2.tts import ProviderRun

    class FakeProvider:
        name = "fake-tts"
        version = "fake-short-v1"
        options_version = "pcm48k-0.20s-v1"

        def __init__(self):
            self.calls: list[str] = []

        def synthesize(self, text, voice, output_path, *, shot_id=None, on_progress=None):
            self.calls.append(str(shot_id))
            with wave.open(str(output_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(b"\x00\x00" * 9600)
            if on_progress is not None:
                on_progress(100)
            return ProviderRun(1, 0.0, "PROGRESS 100/100\nDONE 0.20\n", "", (100,), 0.2)

    root = job_dir.resolve()
    provider = FakeProvider()
    result = render_job(
        root,
        selected_shot_ids=["shot-002"],
        force=True,
        tts_provider=provider,
        runtime=RuntimeContext.resolve(root),
    )
    return {
        "ok": True,
        "job_dir": str(root),
        "selected": ["shot-002"],
        "provider_calls": provider.calls,
        "cache_summary": dict(result.cache_summary),
        "final_sha256": result.final_sha256,
    }


def verify_render(job_dir: Path) -> dict:
    """对六镜头等正式 Bundle 逐项 probe、完整解码、规格与时长复核。"""

    from video_v2.contract import load_job_bundle
    from video_v2.media import SHOT_MEDIA_SPEC, decode_media, probe_media, validate_media
    from video_v2.runtime import RuntimeContext
    from video_v2.state import atomic_write_json, read_json, sha256_file

    bundle = load_job_bundle(job_dir)
    root = bundle.root
    report = read_json(root / "output" / "render_report.json")
    context = RuntimeContext.resolve(root)
    runner = context.runner()
    report_shots = {item["id"]: item for item in report.get("shots", [])}
    shots: list[dict] = []
    audio: list[dict] = []
    for shot in bundle.shots:
        report_shot = report_shots[shot.id]
        audio_path = root / "audio" / f"{shot.id}.wav"
        audio_summary = probe_media(audio_path, ffprobe=context.ffprobe, runner=runner)
        decode_media(audio_path, ffmpeg=context.ffmpeg, runner=runner)
        audio.append({
            "id": shot.id,
            "path": audio_path.relative_to(root).as_posix(),
            "sha256": sha256_file(audio_path),
            "duration_sec": audio_summary.duration,
            "probe_exit": 0,
            "full_decode_exit": 0,
        })
        shot_path = root / "shots" / f"{shot.id}.mp4"
        expected = float(report_shot["timing"]["target_duration_sec"])
        validated = validate_media(
            shot_path,
            ffmpeg=context.ffmpeg,
            ffprobe=context.ffprobe,
            spec=SHOT_MEDIA_SPEC,
            expected_duration=expected,
            duration_tolerance=0.15,
            runner=runner,
        )
        shots.append({
            "id": shot.id,
            "path": shot_path.relative_to(root).as_posix(),
            "sha256": validated.sha256,
            "duration_sec": validated.duration,
            "expected_duration_sec": expected,
            "duration_error_sec": validated.duration - expected,
            "probe_exit": 0,
            "full_decode_exit": 0,
            "media": validated.summary.to_dict(),
        })
    final_report = report["final"]
    final_path = root / "output" / "final.mp4"
    final_validated = validate_media(
        final_path,
        ffmpeg=context.ffmpeg,
        ffprobe=context.ffprobe,
        spec=SHOT_MEDIA_SPEC,
        expected_duration=float(report["timeline"]["expected_duration"]),
        duration_tolerance=0.20,
        runner=runner,
    )
    payload = {
        "ok": True,
        "project_id": bundle.project.project_id,
        "verified_report_run_id": report.get("run_id"),
        "audio": audio,
        "shots": shots,
        "final": {
            "path": "output/final.mp4",
            "sha256": final_validated.sha256,
            "duration_sec": final_validated.duration,
            "expected_duration_sec": float(report["timeline"]["expected_duration"]),
            "duration_error_sec": final_validated.duration - float(report["timeline"]["expected_duration"]),
            "probe_exit": 0,
            "full_decode_exit": 0,
            "media": final_validated.summary.to_dict(),
            "report_sha256_matches": final_validated.sha256 == final_report.get("sha256"),
        },
    }
    evidence_path = root / "evidence" / "media-verification.json"
    atomic_write_json(evidence_path, payload, run_id="media-verification")
    payload["evidence_path"] = evidence_path.relative_to(root).as_posix()
    return payload


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    smoke = commands.add_parser("tts-smoke")
    smoke.add_argument("--work-dir", required=True, type=Path)
    seed = commands.add_parser("seed-audio-cache")
    seed.add_argument("--job-dir", required=True, type=Path)
    fake = commands.add_parser("fake-three-shot")
    fake.add_argument("--work-dir", required=True, type=Path)
    selective = commands.add_parser("fake-selective-force")
    selective.add_argument("--job-dir", required=True, type=Path)
    verify = commands.add_parser("verify-render")
    verify.add_argument("--job-dir", required=True, type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "tts-smoke":
            payload = tts_smoke(args.work_dir)
        elif args.command == "seed-audio-cache":
            payload = seed_audio_cache(args.job_dir)
        elif args.command == "fake-three-shot":
            payload = fake_three_shot(args.work_dir)
        elif args.command == "fake-selective-force":
            payload = fake_selective_force(args.job_dir)
        else:
            payload = verify_render(args.job_dir)
    except Exception as exc:
        payload = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
            "message": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 1
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
