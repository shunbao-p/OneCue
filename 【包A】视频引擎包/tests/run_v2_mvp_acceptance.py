#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""计划 05 的薄验收入口。

默认子命令均为只读；写 manifest、生成联系表或调用真实 render
必须由显式子命令触发。本文件只编排既有 video_v2 CLI 与 FFmpeg，
不复制核心渲染、缓存、字幕或时间线逻辑。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


MANIFEST_VERSION = 1
DEFAULT_TIMEOUT_SEC = 120.0
PROJECT_KEYS = ("story-mail-car", "explainer-sponge-city")
PROJECT_IDS = {
    "story-mail-car": "phase5-story-mail-car",
    "explainer-sponge-city": "phase5-explainer-sponge-city",
}
KNOWN_MOTION_BOUNDARY = (
    "FFmpeg 仅提供虚拟摄影机推拉、平移与轻漂移；雨落、流水、人物呼吸或摆动等"
    "自然语义动态尚未实现，正式高级 Provider 为零。"
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _finite_positive(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是有限正数")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是有限正数") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} 必须是有限正数")
    return result


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"保护目标不是安全常规文件：{source}")
    return {
        "path": str(source.resolve()),
        "size_bytes": source.stat().st_size,
        "sha256": sha256_file(source),
    }


def assert_file_unchanged(path: str | os.PathLike[str], snapshot: Mapping[str, Any]) -> None:
    current = snapshot_file(path)
    if current["sha256"] != snapshot.get("sha256") or current["size_bytes"] != snapshot.get("size_bytes"):
        raise AssertionError(f"受保护文件发生变化：{current['path']}")


def bundle_relative_path(root: str | os.PathLike[str], path: str | os.PathLike[str]) -> str:
    root_input = Path(root).absolute()
    root_path = root_input.resolve(strict=False)
    candidate = Path(path)
    current = candidate.absolute() if candidate.is_absolute() else root_input / candidate
    probe = root_input
    try:
        relative_parts = current.relative_to(root_input).parts
    except ValueError as exc:
        raise ValueError("路径越出验收根") from exc
    for part in relative_parts:
        if part in {"", ".", ".."}:
            raise ValueError("路径包含不安全段")
        probe = probe / part
        if probe.is_symlink():
            raise ValueError("路径不得包含符号链接")
    resolved = current.resolve(strict=False)
    try:
        relative = resolved.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("路径越出验收根") from exc
    value = relative.as_posix()
    if not value or any(part in {"", ".", ".."} for part in PurePosixPath(value).parts):
        raise ValueError("验收相对路径无效")
    return value


def _project_manifest(key: str) -> dict[str, Any]:
    return {
        "project_id": PROJECT_IDS[key],
        "job_dir": key,
        "inputs": {},
        "image_generation_ledger": None,
        "runs": {"first": None, "second": None, "internal_revision": None, "user_revision": None},
        "resources": {},
        "artifacts": {},
        "media_audit": {},
        "reliability": {},
        "codex_score": {},
        "internal_revisions_used": 0,
        "user_revisions_used": 0,
        "user_review": {"status": "not_started", "feedback": None, "verdict": None},
        "technical_verdict": None,
        "reliability_verdict": None,
        "quality_verdict": None,
    }


def new_acceptance_manifest() -> dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "in_progress",
        "overall_verdict": "CONDITIONAL",
        "projects": {key: _project_manifest(key) for key in PROJECT_KEYS},
        "reliability_scenarios": {},
        "protected_baseline": {},
        "known_motion_boundary": KNOWN_MOTION_BOUNDARY,
        "plan06_allowed": False,
    }


def _safe_relative_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise ValueError(f"{name} 必须是安全 POSIX 相对路径")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"{name} 必须是安全 POSIX 相对路径")
    return value


def validate_acceptance_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("验收 manifest 顶层必须是对象")
    required = {
        "manifest_version", "created_at", "updated_at", "status", "overall_verdict",
        "projects", "reliability_scenarios", "protected_baseline", "known_motion_boundary",
        "plan06_allowed",
    }
    if set(value) != required:
        raise ValueError("验收 manifest 字段集合不完整或含未知字段")
    if value["manifest_version"] != MANIFEST_VERSION:
        raise ValueError("验收 manifest 版本不受支持")
    if value["status"] not in {"in_progress", "awaiting_user_review", "complete", "failed"}:
        raise ValueError("验收状态不合法")
    if value["overall_verdict"] not in {"PASS", "CONDITIONAL", "FAIL"}:
        raise ValueError("总判定不合法")
    if not isinstance(value["known_motion_boundary"], str) or not value["known_motion_boundary"].strip():
        raise ValueError("必须记录自然语义动态边界")
    projects = value["projects"]
    if not isinstance(projects, dict) or set(projects) != set(PROJECT_KEYS):
        raise ValueError("必须恰好包含两个固定验收案例")
    accepted = True
    for key in PROJECT_KEYS:
        project = projects[key]
        if not isinstance(project, dict):
            raise ValueError(f"projects.{key} 必须是对象")
        expected_fields = set(_project_manifest(key))
        if set(project) != expected_fields:
            raise ValueError(f"projects.{key} 字段集合不完整或含未知字段")
        if project["project_id"] != PROJECT_IDS[key]:
            raise ValueError(f"projects.{key}.project_id 不合法")
        _safe_relative_string(project["job_dir"], f"projects.{key}.job_dir")
        for counter in ("internal_revisions_used", "user_revisions_used"):
            if not isinstance(project[counter], int) or isinstance(project[counter], bool) or not 0 <= project[counter] <= 1:
                raise ValueError(f"projects.{key}.{counter} 必须为 0 或 1")
        review = project["user_review"]
        if not isinstance(review, dict) or set(review) != {"status", "feedback", "verdict"}:
            raise ValueError(f"projects.{key}.user_review 结构无效")
        if review["status"] not in {"not_started", "awaiting", "received", "re_review_required"}:
            raise ValueError(f"projects.{key}.user_review.status 无效")
        if review["verdict"] not in {None, "accepted", "limited_revision", "unacceptable"}:
            raise ValueError(f"projects.{key}.user_review.verdict 无效")
        accepted = accepted and review["status"] == "received" and review["verdict"] == "accepted"
    if value["overall_verdict"] == "PASS" and not accepted:
        raise ValueError("用户尚未接受两片时不得判 PASS")
    if bool(value["plan06_allowed"]) != (value["overall_verdict"] == "PASS" and accepted):
        raise ValueError("plan06_allowed 与人工验收状态不一致")
    return deepcopy(value)


def write_manifest(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    target = Path(path)
    document = validate_acceptance_manifest(dict(value))
    document["updated_at"] = _now()
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(f"{target.stem}.part-plan05{target.suffix}")
    try:
        part.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        json.loads(part.read_text(encoding="utf-8"))
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)


def _rate(value: Any) -> float | None:
    if value in (None, "", "0/0"):
        return None
    try:
        rate = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None
    return rate if math.isfinite(rate) and rate > 0 else None


def normalize_ffprobe(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_format = payload.get("format") if isinstance(payload.get("format"), Mapping) else {}
    streams: list[dict[str, Any]] = []
    for raw in payload.get("streams", []):
        if not isinstance(raw, Mapping):
            continue
        duration = raw.get("duration")
        try:
            duration_value = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_value = None
        streams.append({
            "index": raw.get("index"),
            "codec_type": raw.get("codec_type"),
            "codec_name": raw.get("codec_name"),
            "width": raw.get("width"),
            "height": raw.get("height"),
            "pixel_format": raw.get("pix_fmt"),
            "frame_rate": _rate(raw.get("avg_frame_rate") or raw.get("r_frame_rate")),
            "sample_rate": int(raw["sample_rate"]) if raw.get("sample_rate") is not None else None,
            "channels": raw.get("channels"),
            "duration": duration_value,
        })
    try:
        duration = float(raw_format.get("duration"))
    except (TypeError, ValueError):
        duration = 0.0
    return {"duration": duration, "format_name": raw_format.get("format_name"), "streams": streams}


def evaluate_final_media(summary: Mapping[str, Any], *, report_expected_duration: float) -> dict[str, Any]:
    failures: list[str] = []
    streams = summary.get("streams") if isinstance(summary.get("streams"), list) else []
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1:
        failures.append("stream.video_count")
    if len(audios) != 1:
        failures.append("stream.audio_count")
    video = videos[0] if len(videos) == 1 else {}
    audio = audios[0] if len(audios) == 1 else {}
    checks = {
        "video.codec": (video.get("codec_name"), "h264"),
        "video.width": (video.get("width"), 1080),
        "video.height": (video.get("height"), 1920),
        "video.pixel_format": (video.get("pixel_format"), "yuv420p"),
        "audio.codec": (audio.get("codec_name"), "aac"),
        "audio.sample_rate": (audio.get("sample_rate"), 48000),
        "audio.channels": (audio.get("channels"), 2),
    }
    for name, (actual, expected) in checks.items():
        if actual != expected:
            failures.append(name)
    frame_rate = video.get("frame_rate")
    if frame_rate is None or abs(float(frame_rate) - 30.0) > 0.01:
        failures.append("video.frame_rate")
    duration = float(summary.get("duration") or 0.0)
    if not 30.0 <= duration <= 45.0:
        failures.append("format.duration_range")
    video_duration = video.get("duration")
    audio_duration = audio.get("duration")
    av_delta = None
    if video_duration is None or audio_duration is None:
        failures.append("av.duration_unavailable")
    else:
        av_delta = abs(float(video_duration) - float(audio_duration))
        if av_delta > 0.10 + 1e-9:
            failures.append("av.duration_delta")
    report_error = abs(duration - float(report_expected_duration))
    if report_error > 0.20 + 1e-9:
        failures.append("report.duration_error")
    return {
        "ok": not failures,
        "failures": failures,
        "duration_sec": duration,
        "video_duration_sec": video_duration,
        "audio_duration_sec": audio_duration,
        "av_duration_delta_sec": av_delta,
        "report_duration_error_sec": report_error,
        "stream_count": len(streams),
    }


def run_command(
    argv: Sequence[str],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    cwd: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) for item in argv):
        raise TypeError("argv 必须是非空 list[str]")
    timeout = _finite_positive(timeout_sec, "timeout_sec")
    return subprocess.run(
        list(argv),
        cwd=None if cwd is None else os.fspath(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=timeout,
        check=False,
    )


def build_video_v2_argv(
    *,
    python: str | os.PathLike[str],
    command: str,
    job_dir: str | os.PathLike[str],
    selected_shots: Sequence[str] = (),
    force: bool = False,
) -> list[str]:
    if command not in {"validate", "render"}:
        raise ValueError("command 只能是 validate 或 render")
    argv = [os.fspath(python), "-B", "-m", "video_v2", command, "--job-dir", os.fspath(job_dir)]
    if command == "validate" and (selected_shots or force):
        raise ValueError("validate 不接受渲染参数")
    for shot_id in selected_shots:
        if not isinstance(shot_id, str) or not shot_id.startswith("shot-"):
            raise ValueError("selected_shots 含非法镜头 ID")
        argv.extend(["--shot", shot_id])
    if force:
        argv.append("--force")
    argv.append("--json")
    return argv


def build_contact_sheet_argv(
    *,
    ffmpeg: str | os.PathLike[str],
    source: str | os.PathLike[str],
    output: str | os.PathLike[str],
    duration_sec: float,
    columns: int = 3,
    rows: int = 3,
    allowed_output_root: str | os.PathLike[str] | None = None,
) -> list[str]:
    duration = _finite_positive(duration_sec, "duration_sec")
    if not isinstance(columns, int) or isinstance(columns, bool) or columns <= 0:
        raise ValueError("columns 必须为正整数")
    if not isinstance(rows, int) or isinstance(rows, bool) or rows <= 0:
        raise ValueError("rows 必须为正整数")
    source_input = Path(source).absolute()
    output_input = Path(output).absolute()
    output_path = output_input.resolve(strict=False)
    if allowed_output_root is None:
        allowed_root = output_path.parent
    else:
        allowed_root = Path(allowed_output_root).resolve(strict=False)
        try:
            output_path.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError("联系表输出越出允许目录") from exc
    if output_path == allowed_root or output_path.suffix.lower() != ".png":
        raise ValueError("联系表输出必须是允许目录下的 PNG 文件")
    frames = columns * rows
    interval = max(duration / frames, 0.05)
    # 随包 FFmpeg 的最小发布构建没有 drawtext；时间点由固定间隔与
    # ffprobe 时长在旁证中重建，联系表本身只依赖稳定可用的基础滤镜。
    filtergraph = f"fps=1/{interval:.6f},scale=270:-2:flags=lanczos,tile={columns}x{rows}"
    return [
        os.fspath(ffmpeg), "-hide_banner", "-v", "error", "-nostdin", "-y",
        "-i", str(source_input), "-vf", filtergraph, "-frames:v", "1", str(output_input),
    ]


def classify_cache_summary(summary: Mapping[str, Any], *, shot_count: int, mode: str) -> dict[str, Any]:
    if not isinstance(shot_count, int) or isinstance(shot_count, bool) or shot_count <= 0:
        raise ValueError("shot_count 必须为正整数")
    values = {name: int(summary.get(name, 0)) for name in (
        "audio_hit", "audio_rebuilt", "shot_hit", "shot_rebuilt", "final_hit", "final_rebuilt"
    )}
    if mode == "full-hit":
        expected = {"audio_hit": shot_count, "audio_rebuilt": 0, "shot_hit": shot_count, "shot_rebuilt": 0, "final_hit": 1, "final_rebuilt": 0}
    elif mode == "selected-rerender":
        expected = {"audio_hit": shot_count, "audio_rebuilt": 0, "shot_hit": shot_count - 1, "shot_rebuilt": 1, "final_hit": 0, "final_rebuilt": 1}
    else:
        raise ValueError("未知缓存判断模式")
    mismatches = {key: {"expected": expected[key], "actual": values[key]} for key in expected if values[key] != expected[key]}
    return {"status": "pass" if not mismatches else "fail", "mode": mode, "actual": values, "expected": expected, "mismatches": mismatches}


def probe_raw(ffprobe: Path, media: Path, *, timeout_sec: float) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    command = [
        str(ffprobe), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(media),
    ]
    result = run_command(command, timeout_sec=timeout_sec)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败：{result.stderr}")
    return json.loads(result.stdout), result


def audit_final(
    *,
    ffmpeg: Path,
    ffprobe: Path,
    final: Path,
    report: Path,
    timeout_sec: float,
) -> dict[str, Any]:
    raw, probe_result = probe_raw(ffprobe, final, timeout_sec=timeout_sec)
    normalized = normalize_ffprobe(raw)
    report_data = json.loads(report.read_text(encoding="utf-8"))
    if report_data.get("status") != "success" or report_data.get("errors"):
        raise ValueError("render report 未成功或含错误")
    expected = report_data.get("timeline", {}).get("expected_duration")
    if expected is None:
        expected = report_data.get("final", {}).get("duration_sec")
    media_gate = evaluate_final_media(normalized, report_expected_duration=float(expected))
    decode = run_command(
        [str(ffmpeg), "-v", "error", "-nostdin", "-i", str(final), "-map", "0", "-f", "null", "-"],
        timeout_sec=timeout_sec,
    )
    report_hash = report_data.get("final", {}).get("sha256")
    actual_hash = sha256_file(final)
    failures = list(media_gate["failures"])
    if decode.returncode != 0:
        failures.append("media.decode")
    if report_hash != actual_hash:
        failures.append("report.final_sha256")
    return {
        "ok": not failures,
        "failures": failures,
        "final": str(final.resolve()),
        "final_sha256": actual_hash,
        "report": str(report.resolve()),
        "report_sha256": sha256_file(report),
        "probe_exit": probe_result.returncode,
        "decode_exit": decode.returncode,
        "media": normalized,
        "media_gate": media_gate,
    }


def _runtime_paths(package_root: Path) -> tuple[Path, Path, Path, Path]:
    python = package_root / "程序文件" / "runtime" / "bin" / "python3"
    engine = package_root / "程序文件" / "引擎"
    ffmpeg = package_root / "程序文件" / "bin" / "ffmpeg"
    ffprobe = package_root / "程序文件" / "bin" / "ffprobe"
    for path in (python, engine, ffmpeg, ffprobe):
        if not path.exists():
            raise FileNotFoundError(path)
    return python, engine, ffmpeg, ffprobe


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="短视频 V2 计划 05 验收 runner")
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parent.parent)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="创建目录协议与初始机器可读 manifest")
    initialize.add_argument("--acceptance-root", type=Path, required=True)
    validate = commands.add_parser("validate", help="只读调用既有 video_v2 validate")
    validate.add_argument("--job-dir", type=Path, required=True)
    render = commands.add_parser("render", help="显式调用既有 video_v2 render")
    render.add_argument("--job-dir", type=Path, required=True)
    render.add_argument("--shot", action="append", default=[])
    render.add_argument("--force", action="store_true")
    render.add_argument("--timeout", type=float, default=30 * 60.0)
    audit = commands.add_parser("audit-final", help="只读 probe/完整解码/report 交叉审计")
    audit.add_argument("--job-dir", type=Path, required=True)
    audit.add_argument("--timeout", type=float, default=300.0)
    sheet = commands.add_parser("contact-sheet", help="显式生成 final 联系表")
    sheet.add_argument("--job-dir", type=Path, required=True)
    sheet.add_argument("--output", type=Path, required=True)
    sheet.add_argument("--timeout", type=float, default=300.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    package_root = args.package_root.resolve()
    python, engine, ffmpeg, ffprobe = _runtime_paths(package_root)
    if args.command == "init":
        root = args.acceptance_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        for project in PROJECT_KEYS:
            for relative in (
                "references/style", "references/characters", "assets/keyframes", "audio", "shots",
                "captions", "cache", "output", "evidence/iterations", "evidence/probes",
            ):
                (root / project / relative).mkdir(parents=True, exist_ok=True)
        for relative in (
            "reliability-copies/selected-rerender", "reliability-copies/invalid-contract",
            "reliability-copies/corrupted-cache", "reliability-copies/tts-unavailable",
            "reliability-copies/motion-fallback", "reliability-copies/cancellation", "final-review",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        manifest_path = root / "final-review" / "manifest.json"
        if manifest_path.exists():
            validate_acceptance_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
        else:
            write_manifest(manifest_path, new_acceptance_manifest())
        print(json.dumps({"ok": True, "manifest": str(manifest_path)}, ensure_ascii=False))
        return 0
    if args.command in {"validate", "render"}:
        command = build_video_v2_argv(
            python=python,
            command=args.command,
            job_dir=args.job_dir.resolve(),
            selected_shots=tuple(getattr(args, "shot", ())),
            force=bool(getattr(args, "force", False)),
        )
        started = time.monotonic()
        result = run_command(command, timeout_sec=float(getattr(args, "timeout", DEFAULT_TIMEOUT_SEC)), cwd=engine)
        envelope = {
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "elapsed_sec": time.monotonic() - started,
            "argv": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        print(json.dumps(envelope, ensure_ascii=False))
        return result.returncode
    job_dir = args.job_dir.resolve()
    if args.command == "audit-final":
        result = audit_final(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            final=job_dir / "output" / "final.mp4",
            report=job_dir / "output" / "render_report.json",
            timeout_sec=args.timeout,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 3
    final = job_dir / "output" / "final.mp4"
    raw, _ = probe_raw(ffprobe, final, timeout_sec=args.timeout)
    duration = normalize_ffprobe(raw)["duration"]
    allowed = job_dir / "evidence"
    output = args.output.resolve()
    command = build_contact_sheet_argv(
        ffmpeg=ffmpeg,
        source=final,
        output=output,
        duration_sec=duration,
        allowed_output_root=allowed,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(command, timeout_sec=args.timeout)
    payload = {"ok": result.returncode == 0 and output.is_file(), "exit_code": result.returncode, "argv": command, "output": str(output)}
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
