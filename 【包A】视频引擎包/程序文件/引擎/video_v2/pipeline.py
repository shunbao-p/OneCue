"""短视频 V2 包 A 本地核心管线。"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .captions import CAPTION_IMPLEMENTATION_VERSION, build_ass, build_caption_cards, select_caption_text
from .contract import load_job_bundle
from .errors import PipelineCancelled, RenderError
from .media import SHOT_MEDIA_SPEC, MediaSummary, decode_media, part_path, probe_media, validate_media
from .motion import MOTION_IMPLEMENTATION_VERSION, build_motion_filter
from .runtime import PIPELINE_VERSION, CommandRunner, RuntimeContext
from .state import (
    atomic_commit_file,
    atomic_write_json,
    cache_entry_matches,
    content_key,
    empty_manifest,
    load_manifest,
    save_manifest,
    sha256_file,
    update_cache_entry,
)
from .timeline import TIMELINE_IMPLEMENTATION_VERSION, TimelineError, build_timeline
from .tts import DotsTtsProvider, audio_cache_key, ensure_shot_audio


SHOT_RENDERER_VERSION = "ffmpeg-shot-v1"
COMPOSER_VERSION = "ffmpeg-compose-v2-timebase"
REPORT_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _text_hash(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _media_dict(summary: MediaSummary) -> dict[str, Any]:
    payload = summary.to_dict()
    payload.pop("path", None)
    return payload


@dataclass(frozen=True)
class RenderResult:
    ok: bool
    status: str
    run_id: str
    project_id: str
    shot_count: int
    final_path: str
    final_sha256: str
    final_duration: float
    cache_summary: Mapping[str, int]
    warnings: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    errors: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "shot_count": self.shot_count,
            "final_path": self.final_path,
            "final_sha256": self.final_sha256,
            "final_duration_sec": self.final_duration,
            "cache_summary": dict(self.cache_summary),
            "warnings": [dict(item) for item in self.warnings],
            "errors": [dict(item) for item in self.errors],
        }


def _write_text_atomic(target: Path, text: str, run_id: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.stem}.part-{run_id}{target.suffix}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_commit_file(temporary, target, validate=lambda path: path.read_text(encoding="utf-8"))
    finally:
        temporary.unlink(missing_ok=True)


def _audio_validate(context: RuntimeContext, runner: CommandRunner, path: Path) -> MediaSummary:
    summary = probe_media(path, ffprobe=context.ffprobe, runner=runner)
    if summary.audio_stream is None or summary.duration <= 0:
        raise RenderError("media.spec_invalid", "tts", "WAV 缺少有效音频流")
    decode_media(path, ffmpeg=context.ffmpeg, runner=runner)
    return summary


def _shot_key(bundle, shot, audio, caption_text: str | None) -> str:
    return content_key(
        "shot",
        SHOT_RENDERER_VERSION,
        {
            "image_sha256": shot.keyframe_sha256,
            "audio_sha256": audio.sha256,
            "audio_duration_sec": round(audio.duration_sec, 6),
            "focus": [shot.focus_x, shot.focus_y],
            "motion": [shot.motion_preset, shot.motion_strength, MOTION_IMPLEMENTATION_VERSION],
            "caption_text_sha256": _text_hash(caption_text),
            "caption_style": bundle.project.caption_style_preset,
            "caption_version": CAPTION_IMPLEMENTATION_VERSION,
            "pads": [shot.head_pad_sec, shot.tail_pad_sec],
            "output": [bundle.project.width, bundle.project.height, bundle.project.fps, "h264", "yuv420p", "aac", 48000, 2],
        },
    )


def _render_shot(
    *,
    bundle,
    shot,
    audio,
    caption_text: str | None,
    caption_path: Path,
    target: Path,
    context: RuntimeContext,
    runner: CommandRunner,
) -> tuple[Any, bool, str]:
    duration = audio.duration_sec + shot.head_pad_sec + shot.tail_pad_sec
    cards = () if caption_text is None else build_caption_cards(
        caption_text,
        shot.head_pad_sec,
        shot.head_pad_sec + audio.duration_sec,
    )
    ass = build_ass(
        cards,
        width=bundle.project.width,
        height=bundle.project.height,
        style_preset=bundle.project.caption_style_preset,
        title=f"{bundle.project.project_id}-{shot.id}",
    )
    _write_text_atomic(caption_path, ass, context.run_id)

    def attempt(preset: str) -> Any:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = part_path(target, context.run_id)
        temporary_output.unlink(missing_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix=f"v2-{shot.id}-") as raw_stage:
                stage = Path(raw_stage)
                image_suffix = shot.keyframe_path.suffix.lower()
                image_name = f"image{image_suffix}"
                shutil.copy2(shot.keyframe_path, stage / image_name)
                shutil.copy2(audio.path, stage / "voice.wav")
                shutil.copy2(caption_path, stage / "caption.ass")
                (stage / "fonts").mkdir()
                shutil.copy2(context.font_path, stage / "fonts" / "font.ttf")
                motion = build_motion_filter(
                    preset,
                    shot.motion_strength,
                    shot.focus_x,
                    shot.focus_y,
                    duration,
                    bundle.project.fps,
                    bundle.project.width,
                    bundle.project.height,
                )
                video_chain = motion
                if caption_text is not None:
                    video_chain += ",subtitles=filename='caption.ass':fontsdir='fonts'"
                head_ms = int(round(shot.head_pad_sec * 1000))
                audio_chain = (
                    f"[1:a]adelay={head_ms}:all=1,apad=pad_dur={shot.tail_pad_sec:.6f},"
                    f"atrim=duration={duration:.6f},aresample=48000[a]"
                )
                command = [
                    str(context.ffmpeg), "-hide_banner", "-v", "error", "-nostdin", "-y",
                    "-loop", "1", "-framerate", str(bundle.project.fps), "-i", image_name,
                    "-i", "voice.wav",
                    "-filter_complex", f"[0:v]{video_chain}[v];{audio_chain}",
                    "-map", "[v]", "-map", "[a]", "-t", f"{duration:.6f}",
                    "-r", str(bundle.project.fps), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                    "-movflags", "+faststart", str(temporary_output),
                ]
                result = runner.run(command, cwd=stage)
                if result.returncode != 0:
                    raise RenderError(
                        "render.shot_failed", "shot_render", f"镜头 {shot.id} FFmpeg 失败",
                        shot_id=shot.id, details={"stderr": result.stderr, "returncode": result.returncode},
                    )
            validated = validate_media(
                temporary_output,
                ffmpeg=context.ffmpeg,
                ffprobe=context.ffprobe,
                spec=SHOT_MEDIA_SPEC,
                expected_duration=duration,
                duration_tolerance=0.15,
                runner=runner,
            )
            atomic_commit_file(temporary_output, target)
            return validated
        finally:
            temporary_output.unlink(missing_ok=True)

    fallback = False
    actual_preset = shot.motion_preset
    try:
        validated = attempt(actual_preset)
    except PipelineCancelled:
        raise
    except Exception as first_error:
        if actual_preset == "static":
            raise
        fallback = True
        actual_preset = "static"
        try:
            validated = attempt(actual_preset)
        except Exception as second_error:
            raise RenderError(
                "render.fallback_failed", "shot_render", f"镜头 {shot.id} static 回退失败",
                shot_id=shot.id,
                details={"original_error": str(first_error), "fallback_error": str(second_error)},
            ) from second_error
    return validated, fallback, actual_preset


def _final_key(shot_hashes: Sequence[str], transitions: Sequence[tuple[str, float]]) -> str:
    return content_key(
        "final",
        COMPOSER_VERSION,
        {"shot_sha256": list(shot_hashes), "transitions": [[kind, duration] for kind, duration in transitions], "spec": [1080, 1920, 30, "h264", "yuv420p", "aac", 48000, 2]},
    )


def _compose_final(
    shots: Sequence[Path],
    durations: Sequence[float],
    transitions: Sequence[tuple[str, float]],
    *,
    target: Path,
    expected_duration: float,
    context: RuntimeContext,
    runner: CommandRunner,
) -> Any:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = part_path(target, context.run_id)
    temporary.unlink(missing_ok=True)
    command = [str(context.ffmpeg), "-hide_banner", "-v", "error", "-nostdin", "-y"]
    for shot in shots:
        command.extend(["-i", str(shot)])
    if len(shots) == 1:
        command.extend([
            "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-movflags", "+faststart", str(temporary),
        ])
        try:
            result = runner.run(command)
            if result.returncode != 0:
                raise RenderError("compose.failed", "compose", "最终单镜头封装失败", details={"stderr": result.stderr, "returncode": result.returncode})
            validated = validate_media(
                temporary, ffmpeg=context.ffmpeg, ffprobe=context.ffprobe, spec=SHOT_MEDIA_SPEC,
                expected_duration=expected_duration, duration_tolerance=0.20, runner=runner,
            )
            atomic_commit_file(temporary, target)
            return validated
        finally:
            temporary.unlink(missing_ok=True)
    # concat 输出使用 AVTB，而 MP4 输入常为 1/15360；若时间线出现
    # crossfade → cut → crossfade，未经归一化的下一路会令 xfade 拒绝
    # 两侧时基。先把每路起点和 timebase 固定，再串联任意合法组合。
    filters: list[str] = []
    for index in range(len(shots)):
        filters.append(f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[vin{index}]")
        filters.append(f"[{index}:a]asettb=1/48000,asetpts=PTS-STARTPTS[ain{index}]")
    video = "[vin0]"
    audio = "[ain0]"
    current_duration = float(durations[0])
    for index in range(1, len(shots)):
        kind, overlap = transitions[index - 1]
        next_video = f"[v{index}]"
        next_audio = f"[a{index}]"
        if kind == "crossfade":
            offset = current_duration - overlap
            filters.append(f"{video}[vin{index}]xfade=transition=fade:duration={overlap:.6f}:offset={offset:.6f}{next_video}")
            filters.append(f"{audio}[ain{index}]acrossfade=d={overlap:.6f}{next_audio}")
            current_duration += durations[index] - overlap
        else:
            filters.append(f"{video}[vin{index}]concat=n=2:v=1:a=0{next_video}")
            filters.append(f"{audio}[ain{index}]concat=n=2:v=0:a=1{next_audio}")
            current_duration += durations[index]
        video, audio = next_video, next_audio
    command.extend([
        "-filter_complex", ";".join(filters), "-map", video, "-map", audio,
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(temporary),
    ])
    try:
        result = runner.run(command)
        if result.returncode != 0:
            raise RenderError("compose.failed", "compose", "最终合成 FFmpeg 失败", details={"stderr": result.stderr, "returncode": result.returncode})
        validated = validate_media(
            temporary,
            ffmpeg=context.ffmpeg,
            ffprobe=context.ffprobe,
            spec=SHOT_MEDIA_SPEC,
            expected_duration=expected_duration,
            duration_tolerance=0.20,
            runner=runner,
        )
        atomic_commit_file(temporary, target)
        return validated
    finally:
        temporary.unlink(missing_ok=True)


def render_job(
    job_dir: str | Path,
    *,
    selected_shot_ids: Sequence[str] | None = None,
    force: bool = False,
    cancel_event: Any | None = None,
    on_event: Callable[[Mapping[str, Any]], None] | None = None,
    tts_provider: Any | None = None,
    runtime: RuntimeContext | None = None,
) -> RenderResult:
    """读取冻结 JobBundle，逐镜头渲染并原子提交 final。"""

    bundle = load_job_bundle(job_dir)
    context = runtime or RuntimeContext.resolve(bundle.root, cancel_event=cancel_event, on_event=on_event)
    runner = context.runner()
    root = bundle.root
    for directory in ("audio", "shots", "captions", "cache", "output"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    manifest_path = root / "cache" / "manifest.json"
    report_path = root / "output" / "render_report.json"
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    try:
        manifest = load_manifest(manifest_path, implementation_version=PIPELINE_VERSION)
    except Exception as exc:
        warnings.append({"code": "cache.invalid", "message": str(exc)})
        manifest = empty_manifest(implementation_version=PIPELINE_VERSION)

    requested = None if selected_shot_ids is None else tuple(selected_shot_ids)
    preflight_error: RenderError | None = None
    if requested is not None:
        if len(set(requested)) != len(requested):
            preflight_error = RenderError("pipeline.shot_duplicate", "preflight", "--shot 不得重复")
        known = {shot.id for shot in bundle.shots}
        unknown = [shot_id for shot_id in requested if shot_id not in known]
        if unknown and preflight_error is None:
            preflight_error = RenderError("pipeline.shot_unknown", "preflight", f"未知镜头：{', '.join(unknown)}")
    selected = None if requested is None else set(requested)
    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "shot_renderer_version": SHOT_RENDERER_VERSION,
        "composer_version": COMPOSER_VERSION,
        "tts_provider_version": getattr(tts_provider, "version", None),
        "caption_version": CAPTION_IMPLEMENTATION_VERSION,
        "motion_version": MOTION_IMPLEMENTATION_VERSION,
        "timeline_version": TIMELINE_IMPLEMENTATION_VERSION,
        "run_id": context.run_id,
        "status": "running",
        "started_at": _now(),
        "updated_at": _now(),
        "project_id": bundle.project.project_id,
        "schema_version": bundle.project.schema_version,
        "request": {"scope": "full" if selected is None else "selected", "shots": list(requested or ()), "force": bool(force)},
        "tools": {"ffmpeg": str(context.ffmpeg), "ffprobe": str(context.ffprobe)},
        "shots": [],
        "timeline": {},
        "final": {},
        "warnings": warnings,
        "errors": errors,
        "last_stage": "preflight",
    }

    def persist() -> None:
        report["updated_at"] = _now()
        atomic_write_json(report_path, report, run_id=context.run_id)

    def event(code: str, **extra: Any) -> None:
        payload = {"code": code, "stage": report.get("last_stage"), "run_id": context.run_id, **extra}
        context.emit(payload)

    if tts_provider is None:
        dots = dict(context.dots)
        tts_provider = DotsTtsProvider(
            python_path=dots.get("python"),
            synth_script=Path(__file__).resolve().parents[2] / "网站" / "dots_synth.py",
            prompts_dir=dots.get("prompts"),
            runner=runner,
            installed=bool(dots.get("installed")),
        )
    report["tts_provider_version"] = getattr(tts_provider, "version", None)
    persist()
    cache_counts = {"audio_hit": 0, "audio_rebuilt": 0, "shot_hit": 0, "shot_rebuilt": 0, "final_hit": 0, "final_rebuilt": 0}
    shot_paths: list[Path] = []
    shot_hashes: list[str] = []
    shot_durations: list[float] = []
    transitions = [(shot.transition_type, shot.transition_duration_sec) for shot in bundle.shots]

    try:
        if preflight_error is not None:
            raise preflight_error
        for shot in bundle.shots:
            if cancel_event is not None and cancel_event.is_set():
                raise PipelineCancelled(stage="pipeline")
            is_selected = selected is None or shot.id in selected
            report["last_stage"] = "tts"
            event("pipeline.tts", shot_id=shot.id)

            if not is_selected:
                expected_audio_key = audio_cache_key(
                    shot.speech_text,
                    shot.voice,
                    provider_name=getattr(tts_provider, "name", "dots-tts"),
                    provider_version=getattr(tts_provider, "version", "unknown"),
                    options_version=getattr(tts_provider, "options_version", "unknown"),
                )
                hit, audio_path, _reason = cache_entry_matches(
                    manifest.get("audio", {}).get(shot.id), expected_key=expected_audio_key, bundle_root=root,
                    validate=lambda path: _audio_validate(context, runner, path),
                )
                if not hit or audio_path is None:
                    raise RenderError("pipeline.dependency_missing", "tts", f"未选镜头 {shot.id} 缺少有效音频缓存", shot_id=shot.id)
                summary = _audio_validate(context, runner, audio_path)
                entry = manifest["audio"][shot.id]
                audio = type("Audio", (), {
                    "path": audio_path,
                    "sha256": entry["sha256"],
                    "duration_sec": summary.duration,
                    "cache_status": "hit",
                    "attempts": 0,
                    "relative_path": entry["path"],
                })()
            else:
                audio = ensure_shot_audio(
                    shot_id=shot.id,
                    text=shot.speech_text,
                    voice=shot.voice,
                    bundle_root=root,
                    run_id=context.run_id,
                    manifest=manifest,
                    provider=tts_provider,
                    probe_audio=lambda path: probe_media(path, ffprobe=context.ffprobe, runner=runner),
                    full_decode=lambda path: (decode_media(path, ffmpeg=context.ffmpeg, runner=runner) or True),
                    force=bool(force),
                    manifest_path=manifest_path,
                    created_at=_now(),
                    on_progress=lambda value, shot_id=shot.id: event("pipeline.tts_progress", shot_id=shot_id, progress=value),
                )
            cache_counts[f"audio_{'hit' if audio.cache_status == 'hit' else 'rebuilt'}"] += 1
            caption_text = select_caption_text(
                bundle.project.captions_enabled,
                shot.caption_mode,
                shot.speech_text,
                shot.caption_text,
            )
            key = _shot_key(bundle, shot, audio, caption_text)
            shot_target = root / "shots" / f"{shot.id}.mp4"
            caption_target = root / "captions" / f"{shot.id}.ass"
            expected_duration = audio.duration_sec + shot.head_pad_sec + shot.tail_pad_sec

            def validate_cached_shot(path: Path):
                return validate_media(
                    path, ffmpeg=context.ffmpeg, ffprobe=context.ffprobe, spec=SHOT_MEDIA_SPEC,
                    expected_duration=expected_duration, duration_tolerance=0.15, runner=runner,
                )

            hit, cached_shot, _reason = cache_entry_matches(
                manifest.get("shots", {}).get(shot.id), expected_key=key, bundle_root=root, validate=validate_cached_shot,
            )
            fallback = False
            actual_preset = shot.motion_preset
            if not is_selected and (not hit or cached_shot is None):
                raise RenderError("pipeline.dependency_missing", "shot_render", f"未选镜头 {shot.id} 缺少有效镜头缓存", shot_id=shot.id)
            if hit and cached_shot is not None and not (force and is_selected):
                validated = validate_cached_shot(cached_shot)
                shot_path = cached_shot
                cache_status = "hit"
            else:
                report["last_stage"] = "shot_render"
                event("pipeline.shot", shot_id=shot.id)
                validated, fallback, actual_preset = _render_shot(
                    bundle=bundle, shot=shot, audio=audio, caption_text=caption_text,
                    caption_path=caption_target, target=shot_target, context=context, runner=runner,
                )
                shot_path = shot_target
                cache_status = "rebuilt"
                update_cache_entry(
                    manifest, layer="shots", entry_id=shot.id, key=key, bundle_root=root,
                    artifact=shot_path, media_summary=_media_dict(validated.summary), duration_sec=validated.duration,
                    implementation_version=SHOT_RENDERER_VERSION, created_at=_now(),
                )
                save_manifest(manifest_path, manifest, run_id=context.run_id)
            cache_counts[f"shot_{cache_status}"] += 1
            shot_sha = sha256_file(shot_path)
            shot_duration = validated.duration
            shot_paths.append(shot_path)
            shot_hashes.append(shot_sha)
            shot_durations.append(shot_duration)
            report["shots"].append({
                "id": shot.id,
                "purpose": shot.purpose,
                "hero": shot.hero,
                "speech_kind": shot.speech_kind,
                "voice": shot.voice,
                "tts": {"cache": audio.cache_status, "attempts": audio.attempts, "path": audio.relative_path, "sha256": audio.sha256, "duration_sec": audio.duration_sec},
                "caption": {"mode": shot.caption_mode, "visible_text_sha256": _text_hash(caption_text), "path": _relative(root, caption_target) if caption_target.exists() else None},
                "motion": {"preset": shot.motion_preset, "strength": shot.motion_strength, "focus": [shot.focus_x, shot.focus_y], "actual_preset": actual_preset, "fallback_used": fallback, "intent": shot.motion_intent},
                "timing": {"head_pad_sec": shot.head_pad_sec, "tail_pad_sec": shot.tail_pad_sec, "target_duration_sec": expected_duration, "actual_duration_sec": shot_duration, "error_sec": shot_duration - expected_duration},
                "cache": cache_status,
                "output": {"path": _relative(root, shot_path), "sha256": shot_sha, "media": _media_dict(validated.summary)},
            })
            if fallback:
                warnings.append({"code": "render.motion_fallback", "shot_id": shot.id, "message": "运镜已回退 static"})
            persist()

        try:
            timeline = build_timeline(shot_durations, transitions)
        except TimelineError as exc:
            raise RenderError("timeline.invalid", "timeline", str(exc)) from exc
        for code in timeline.warnings:
            warnings.append({"code": code, "message": "最后镜头的非 cut 转场已忽略"})
        report["timeline"] = timeline.to_dict()
        report["last_stage"] = "compose"
        final_target = root / "output" / "final.mp4"
        normalized_transitions = [(item.transition_type, item.transition_duration_sec) for item in timeline.shots]
        final_key = _final_key(shot_hashes, normalized_transitions)

        def validate_cached_final(path: Path):
            return validate_media(
                path, ffmpeg=context.ffmpeg, ffprobe=context.ffprobe, spec=SHOT_MEDIA_SPEC,
                expected_duration=timeline.expected_duration, duration_tolerance=0.20, runner=runner,
            )

        final_hit, cached_final, _reason = cache_entry_matches(
            manifest.get("final", {}).get("final"), expected_key=final_key, bundle_root=root, validate=validate_cached_final,
        )
        force_final = bool(force)
        if final_hit and cached_final is not None and not force_final:
            final_validated = validate_cached_final(cached_final)
            final_path = cached_final
            final_status = "hit"
        else:
            event("pipeline.compose")
            final_validated = _compose_final(
                shot_paths, shot_durations, normalized_transitions,
                target=final_target, expected_duration=timeline.expected_duration, context=context, runner=runner,
            )
            final_path = final_target
            final_status = "rebuilt"
            update_cache_entry(
                manifest, layer="final", entry_id="final", key=final_key, bundle_root=root,
                artifact=final_path, media_summary=_media_dict(final_validated.summary),
                duration_sec=final_validated.duration, implementation_version=COMPOSER_VERSION, created_at=_now(),
            )
            save_manifest(manifest_path, manifest, run_id=context.run_id)
        cache_counts[f"final_{final_status}"] += 1
        final_sha = sha256_file(final_path)
        report["final"] = {
            "cache": final_status,
            "path": _relative(root, final_path),
            "sha256": final_sha,
            "duration_sec": final_validated.duration,
            "duration_error_sec": final_validated.duration - timeline.expected_duration,
            "media": _media_dict(final_validated.summary),
        }
        report["status"] = "success"
        report["last_stage"] = "complete"
        report["finished_at"] = _now()
        report["cache_summary"] = dict(cache_counts)
        persist()
        event("pipeline.complete", final_path=report["final"]["path"])
        return RenderResult(
            True, "success", context.run_id, bundle.project.project_id, len(bundle.shots),
            report["final"]["path"], final_sha, final_validated.duration,
            dict(cache_counts), tuple(warnings), tuple(errors),
        )
    except PipelineCancelled as exc:
        errors.append(exc.to_dict())
        report["status"] = "cancelled"
        report["finished_at"] = _now()
        report["last_stage"] = "cancelled"
        persist()
        event("pipeline.cancel_requested")
        raise
    except RenderError as exc:
        errors.append(exc.to_dict())
        report["status"] = "failed"
        report["finished_at"] = _now()
        persist()
        raise
    except Exception as exc:
        wrapped = RenderError("pipeline.internal_error", "pipeline", "核心管线发生未预期错误", details={"type": type(exc).__name__, "message": str(exc)})
        errors.append(wrapped.to_dict())
        report["status"] = "failed"
        report["finished_at"] = _now()
        persist()
        raise wrapped from exc


__all__ = ["COMPOSER_VERSION", "RenderResult", "SHOT_RENDERER_VERSION", "render_job"]
