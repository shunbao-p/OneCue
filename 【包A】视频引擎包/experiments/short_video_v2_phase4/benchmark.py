#!/usr/bin/env python3
"""计划 04 的隔离单镜头基准入口。"""

from __future__ import annotations

import argparse
import json
import math
import re
import resource
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = EXPERIMENT_DIR.parents[1]
ENGINE_DIR = PACKAGE_ROOT / "程序文件" / "引擎"
for candidate in (EXPERIMENT_DIR, ENGINE_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from normalize_clip import build_normalize_argv, normalize_clip  # noqa: E402
from providers.ffmpeg_baseline import (  # noqa: E402
    build_ffmpeg_baseline_argv,
    render_ffmpeg_baseline,
)
from video_v2.errors import MediaValidationError, PipelineCancelled  # noqa: E402
from video_v2.media import MediaSpec, ValidatedMedia, sha256_file, validate_media  # noqa: E402
from video_v2.runtime import CommandRunner, RuntimeContext  # noqa: E402
from video_v2.state import atomic_write_json  # noqa: E402


EXPERIMENT_VERSION = "phase4-feasibility-v1"
BENCHMARK_CASES = ("portrait", "architecture", "landscape")
PROVIDERS = ("ffmpeg",)
PHASE4_WORK_ROOT = PACKAGE_ROOT / "成片" / "短视频V2样片" / "phase4-image-motion"
VISUAL_SPEC = MediaSpec(
    require_video=True,
    video_codec="h264",
    width=1080,
    height=1920,
    pixel_format="yuv420p",
    frame_rate=30.0,
)
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class RunLayout:
    root: Path
    raw_output: Path
    normalized_output: Path
    manifest: Path


class ExperimentCommandRunner(CommandRunner):
    """为实验的每一次命令调用补上有限正超时。"""

    def __init__(self, *, default_timeout: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.default_timeout = validate_timeout(default_timeout)

    def run(self, argv, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.default_timeout
        return super().run(argv, **kwargs)


def validate_run_id(value: str) -> str:
    candidate = str(value)
    if not _SAFE_TOKEN.fullmatch(candidate):
        raise ValueError("run_id 只能包含 1–128 个安全 ASCII 字符")
    return candidate


def validate_case(value: str) -> str:
    candidate = str(value)
    if candidate not in BENCHMARK_CASES:
        raise ValueError(f"case 必须是：{', '.join(BENCHMARK_CASES)}")
    return candidate


def validate_provider(value: str) -> str:
    candidate = str(value)
    if candidate not in PROVIDERS:
        raise ValueError(f"provider 必须是：{', '.join(PROVIDERS)}")
    return candidate


def validate_timeout(value: float) -> float:
    candidate = float(value)
    if not math.isfinite(candidate) or candidate <= 0:
        raise ValueError("timeout 必须是有限正数")
    return candidate


def _has_existing_symlink(root: Path, candidate: Path) -> bool:
    if root.exists() and root.is_symlink():
        return True
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.exists() and current.is_symlink():
            return True
    return False


def validate_work_dir(value: Path) -> Path:
    candidate = Path(value).absolute()
    allowed = PHASE4_WORK_ROOT.absolute()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"work-dir 必须位于隔离根目录：{allowed}") from exc
    if _has_existing_symlink(allowed, candidate):
        raise ValueError("work-dir 及其现有祖先不得包含符号链接")
    resolved_allowed = allowed.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_allowed)
    except ValueError as exc:
        raise ValueError("work-dir 解析后越出隔离根目录") from exc
    return resolved_candidate


def create_run_layout(work_dir: Path, provider: str, case: str, run_id: str) -> RunLayout:
    safe_provider = validate_provider(provider)
    safe_case = validate_case(case)
    safe_run_id = validate_run_id(run_id)
    root = validate_work_dir(work_dir) / safe_provider / f"{safe_case}-{safe_run_id}"
    root.mkdir(parents=True, exist_ok=False)
    raw_dir = root / "raw"
    normalized_dir = root / "normalized"
    raw_dir.mkdir()
    normalized_dir.mkdir()
    return RunLayout(
        root=root,
        raw_output=raw_dir / f"{safe_case}.mp4",
        normalized_output=normalized_dir / f"{safe_case}.mp4",
        manifest=root / "manifest.json",
    )


def _resource_snapshot() -> dict[str, int]:
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "self_max_rss_bytes": int(self_usage.ru_maxrss),
        "children_max_rss_bytes": int(child_usage.ru_maxrss),
    }


def _tool_version(path: Path, runner: CommandRunner) -> str:
    result = runner.run([str(path), "-version"])
    return (result.stdout or result.stderr).splitlines()[0] if result.returncode == 0 else "unknown"


def _artifact_snapshot(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if path.is_file() and not path.is_symlink():
        payload.update({"sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    return payload


def ensure_visual_only(validated: ValidatedMedia) -> ValidatedMedia:
    if validated.summary.audio_stream is not None:
        raise MediaValidationError(
            "media.unexpected_audio",
            "计划 04 标准化视觉片不得含音轨",
            path=str(validated.summary.path),
        )
    return validated


def run_ffmpeg(args: argparse.Namespace) -> dict[str, Any]:
    source_input = Path(args.input)
    if source_input.is_symlink():
        raise ValueError("input 不得是符号链接")
    source = source_input.resolve(strict=False)
    if not source.is_file() or source.stat().st_size <= 0:
        raise ValueError("input 必须是现有、非空、非符号链接的图片")
    run_id = validate_run_id(args.run_id or f"run-{uuid.uuid4().hex}")
    timeout = validate_timeout(args.timeout)
    layout = create_run_layout(Path(args.work_dir), args.provider, args.case, run_id)
    started = time.monotonic()
    manifest = {
        "schema_version": 1,
        "experiment_version": EXPERIMENT_VERSION,
        "status": "running",
        "last_stage": "created",
        "run_id": run_id,
        "provider": args.provider,
        "provider_version": "ffmpeg-motion-v2.1",
        "case": args.case,
        "input": {
            "path": str(source),
            "sha256": sha256_file(source),
            "size_bytes": source.stat().st_size,
        },
        "parameters": {
            "duration_sec": args.duration,
            "preset": args.preset,
            "strength": args.strength,
            "focus_x": args.focus_x,
            "focus_y": args.focus_y,
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "timeout_sec": timeout,
        },
        "tools": {},
        "commands": {},
        "timing": {"wall_time_sec": 0.0},
        "resources": _resource_snapshot(),
        "outputs": {
            "raw": _artifact_snapshot(layout.raw_output),
            "normalized": _artifact_snapshot(layout.normalized_output),
        },
        "cancel_result": "not_exercised",
        "warnings": [],
        "errors": [],
    }

    def write_manifest(status: str, stage: str) -> None:
        manifest["status"] = status
        manifest["last_stage"] = stage
        manifest["timing"]["wall_time_sec"] = time.monotonic() - started
        manifest["resources"] = _resource_snapshot()
        manifest["outputs"]["raw"] = _artifact_snapshot(layout.raw_output)
        if status != "success":
            manifest["outputs"]["normalized"] = _artifact_snapshot(layout.normalized_output)
        atomic_write_json(layout.manifest, manifest, run_id=run_id)

    write_manifest("running", "created")
    stage = "preflight"
    try:
        context = RuntimeContext.resolve(layout.root, run_id=run_id)
        runner = ExperimentCommandRunner(default_timeout=timeout)
        manifest["tools"] = {
            "ffmpeg": {"path": str(context.ffmpeg), "version": _tool_version(context.ffmpeg, runner)},
            "ffprobe": {"path": str(context.ffprobe), "version": _tool_version(context.ffprobe, runner)},
        }
        manifest["commands"] = {
            "planned_raw": build_ffmpeg_baseline_argv(
                source,
                layout.raw_output,
                ffmpeg=context.ffmpeg,
                duration_sec=args.duration,
                preset=args.preset,
                strength=args.strength,
                focus_x=args.focus_x,
                focus_y=args.focus_y,
            ),
            "planned_normalize": build_normalize_argv(
                layout.raw_output,
                layout.normalized_output,
                ffmpeg=context.ffmpeg,
                duration_sec=args.duration,
            ),
        }
        write_manifest("running", stage)

        stage = "raw_render"
        raw_result = render_ffmpeg_baseline(
            source,
            layout.raw_output,
            ffmpeg=context.ffmpeg,
            runner=runner,
            duration_sec=args.duration,
            preset=args.preset,
            strength=args.strength,
            focus_x=args.focus_x,
            focus_y=args.focus_y,
            timeout_sec=timeout,
        )
        manifest["commands"]["raw"] = list(raw_result.argv)
        manifest["timing"]["raw_sec"] = raw_result.elapsed_sec
        write_manifest("running", stage)

        stage = "normalize"
        normalize_result = normalize_clip(
            layout.raw_output,
            layout.normalized_output,
            ffmpeg=context.ffmpeg,
            runner=runner,
            duration_sec=args.duration,
            timeout_sec=timeout,
        )
        manifest["commands"]["normalize"] = list(normalize_result.argv)
        manifest["timing"]["normalize_sec"] = normalize_result.elapsed_sec
        write_manifest("running", stage)

        stage = "validate"
        validated = ensure_visual_only(validate_media(
            layout.normalized_output,
            ffmpeg=context.ffmpeg,
            ffprobe=context.ffprobe,
            runner=runner,
            spec=VISUAL_SPEC,
            expected_duration=args.duration,
            duration_tolerance=0.15,
        ))
        manifest["outputs"]["normalized"] = validated.to_dict()
        write_manifest("success", "complete")
        return manifest
    except PipelineCancelled as exc:
        manifest["cancel_result"] = "cancelled_and_child_stopped"
        manifest["errors"] = [{
            "code": exc.code,
            "type": type(exc).__name__,
            "stage": stage,
            "message": str(exc),
        }]
        write_manifest("cancelled", stage)
        raise
    except Exception as exc:
        manifest["errors"] = [{
            "code": getattr(exc, "code", "experiment.failed"),
            "type": type(exc).__name__,
            "stage": stage,
            "message": str(exc),
        }]
        write_manifest("failed", stage)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--case", choices=BENCHMARK_CASES, required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--preset", default="slow_push_in")
    parser.add_argument("--strength", default="low")
    parser.add_argument("--focus-x", type=float, default=0.5)
    parser.add_argument("--focus-y", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not math.isfinite(args.duration) or args.duration <= 0 or args.duration > 30:
        raise ValueError("duration 必须在 (0, 30] 秒")
    validate_timeout(args.timeout)
    manifest = run_ffmpeg(args)
    print(json.dumps({
        "ok": True,
        "run_id": manifest["run_id"],
        "provider": manifest["provider"],
        "case": manifest["case"],
        "normalized": manifest["outputs"]["normalized"]["path"],
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
