# -*- coding: utf-8 -*-
"""FFmpeg 媒体探测、完整解码、规格验证与原子提交。"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .errors import MediaValidationError
from .runtime import CommandRunner


MEDIA_VERSION = "ffmpeg-media.1"


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _positive_duration(*values: Any) -> float:
    for value in values:
        parsed = _finite_float(value)
        if parsed > 0:
            return parsed
    return 0.0


def _rate(value: Any) -> float:
    try:
        parsed = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return 0.0
    return parsed if math.isfinite(parsed) and parsed >= 0 else 0.0


@dataclass(frozen=True)
class StreamSummary:
    index: int
    codec_type: str
    codec_name: str
    duration: float
    width: int | None = None
    height: int | None = None
    pixel_format: str | None = None
    frame_rate: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "codec_type": self.codec_type,
            "codec_name": self.codec_name,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "pixel_format": self.pixel_format,
            "frame_rate": self.frame_rate,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "channel_layout": self.channel_layout,
        }


@dataclass(frozen=True)
class MediaSummary:
    path: Path
    size_bytes: int
    duration: float
    format_name: str
    streams: tuple[StreamSummary, ...]

    @property
    def video_stream(self) -> StreamSummary | None:
        return next((stream for stream in self.streams if stream.codec_type == "video"), None)

    @property
    def audio_stream(self) -> StreamSummary | None:
        return next((stream for stream in self.streams if stream.codec_type == "audio"), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "duration": self.duration,
            "format_name": self.format_name,
            "streams": [stream.to_dict() for stream in self.streams],
        }


@dataclass(frozen=True)
class MediaSpec:
    require_video: bool = False
    require_audio: bool = False
    video_codec: str | None = None
    width: int | None = None
    height: int | None = None
    pixel_format: str | None = None
    frame_rate: float | None = None
    audio_codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None


@dataclass(frozen=True)
class ValidatedMedia:
    summary: MediaSummary
    sha256: str

    @property
    def duration(self) -> float:
        return self.summary.duration

    def to_dict(self) -> dict[str, Any]:
        payload = self.summary.to_dict()
        payload["sha256"] = self.sha256
        return payload


SHOT_MEDIA_SPEC = MediaSpec(
    require_video=True,
    require_audio=True,
    video_codec="h264",
    width=1080,
    height=1920,
    pixel_format="yuv420p",
    frame_rate=30.0,
    audio_codec="aac",
    sample_rate=48_000,
    channels=2,
)


def sha256_file(path: str | os.PathLike[str], *, chunk_size: int = 1024 * 1024) -> str:
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def probe_media(
    path: str | os.PathLike[str],
    *,
    ffprobe: str | os.PathLike[str],
    runner: CommandRunner | None = None,
) -> MediaSummary:
    source = Path(path)
    if not source.is_file():
        raise MediaValidationError("media.missing", "媒体文件不存在", path=str(source))
    if source.stat().st_size <= 0:
        raise MediaValidationError("media.empty", "媒体文件为空", path=str(source))
    command = [
        os.fspath(ffprobe), "-v", "error", "-show_format", "-show_streams",
        "-of", "json", os.fspath(source),
    ]
    result = (runner or CommandRunner()).run(command)
    if result.returncode != 0:
        raise MediaValidationError(
            "media.probe_failed", "ffprobe 无法解析媒体", path=str(source),
            details={"returncode": result.returncode, "stderr": result.stderr},
        )
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MediaValidationError(
            "media.probe_invalid_json", "ffprobe 返回了无效 JSON", path=str(source)
        ) from exc

    format_payload = payload.get("format") if isinstance(payload, dict) else None
    raw_streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(format_payload, dict) or not isinstance(raw_streams, list):
        raise MediaValidationError("media.probe_invalid", "ffprobe 摘要结构不完整", path=str(source))
    streams: list[StreamSummary] = []
    for raw in raw_streams:
        if not isinstance(raw, dict):
            continue
        stream_duration = _positive_duration(raw.get("duration"), format_payload.get("duration"))
        rate = _rate(raw.get("avg_frame_rate") or raw.get("r_frame_rate"))
        streams.append(StreamSummary(
            index=int(raw.get("index", len(streams))),
            codec_type=str(raw.get("codec_type", "")),
            codec_name=str(raw.get("codec_name", "")),
            duration=stream_duration,
            width=int(raw["width"]) if raw.get("width") is not None else None,
            height=int(raw["height"]) if raw.get("height") is not None else None,
            pixel_format=str(raw["pix_fmt"]) if raw.get("pix_fmt") is not None else None,
            frame_rate=rate if rate > 0 else None,
            sample_rate=int(raw["sample_rate"]) if raw.get("sample_rate") is not None else None,
            channels=int(raw["channels"]) if raw.get("channels") is not None else None,
            channel_layout=str(raw["channel_layout"]) if raw.get("channel_layout") is not None else None,
        ))
    duration = _positive_duration(format_payload.get("duration"), *(item.duration for item in streams))
    if duration <= 0:
        raise MediaValidationError("media.duration_invalid", "媒体时长不是有限正数", path=str(source))
    return MediaSummary(
        path=source.resolve(),
        size_bytes=source.stat().st_size,
        duration=duration,
        format_name=str(format_payload.get("format_name", "")),
        streams=tuple(streams),
    )


def decode_media(
    path: str | os.PathLike[str],
    *,
    ffmpeg: str | os.PathLike[str],
    runner: CommandRunner | None = None,
) -> None:
    source = Path(path)
    if not source.is_file():
        raise MediaValidationError("media.missing", "媒体文件不存在", path=str(source))
    result = (runner or CommandRunner()).run([
        os.fspath(ffmpeg), "-v", "error", "-nostdin", "-i", os.fspath(source),
        "-map", "0", "-f", "null", "-",
    ])
    if result.returncode != 0:
        raise MediaValidationError(
            "media.decode_failed", "媒体无法完整解码", path=str(source),
            details={"returncode": result.returncode, "stderr": result.stderr},
        )


def _mismatch(field: str, expected: Any, actual: Any, path: Path) -> MediaValidationError:
    return MediaValidationError(
        "media.spec_mismatch", f"媒体规格不符: {field}", path=str(path),
        details={"field": field, "expected": expected, "actual": actual},
    )


def check_media_spec(summary: MediaSummary, spec: MediaSpec) -> None:
    video = summary.video_stream
    audio = summary.audio_stream
    if spec.require_video and video is None:
        raise _mismatch("video_stream", "present", "missing", summary.path)
    if spec.require_audio and audio is None:
        raise _mismatch("audio_stream", "present", "missing", summary.path)
    if video is not None:
        checks = (
            ("video_codec", spec.video_codec, video.codec_name),
            ("width", spec.width, video.width),
            ("height", spec.height, video.height),
            ("pixel_format", spec.pixel_format, video.pixel_format),
        )
        for field, expected, actual in checks:
            if expected is not None and actual != expected:
                raise _mismatch(field, expected, actual, summary.path)
        if spec.frame_rate is not None and (
            video.frame_rate is None or abs(video.frame_rate - spec.frame_rate) > 0.01
        ):
            raise _mismatch("frame_rate", spec.frame_rate, video.frame_rate, summary.path)
    if audio is not None:
        checks = (
            ("audio_codec", spec.audio_codec, audio.codec_name),
            ("sample_rate", spec.sample_rate, audio.sample_rate),
            ("channels", spec.channels, audio.channels),
        )
        for field, expected, actual in checks:
            if expected is not None and actual != expected:
                raise _mismatch(field, expected, actual, summary.path)


def validate_media(
    path: str | os.PathLike[str],
    *,
    ffmpeg: str | os.PathLike[str],
    ffprobe: str | os.PathLike[str],
    spec: MediaSpec | None = None,
    expected_duration: float | None = None,
    duration_tolerance: float = 0.15,
    runner: CommandRunner | None = None,
) -> ValidatedMedia:
    active_runner = runner or CommandRunner()
    summary = probe_media(path, ffprobe=ffprobe, runner=active_runner)
    if spec is not None:
        check_media_spec(summary, spec)
    if expected_duration is not None and abs(summary.duration - expected_duration) > duration_tolerance:
        raise MediaValidationError(
            "media.duration_mismatch", "媒体时长超出容差", path=str(summary.path),
            details={
                "expected": expected_duration,
                "actual": summary.duration,
                "tolerance": duration_tolerance,
            },
        )
    decode_media(path, ffmpeg=ffmpeg, runner=active_runner)
    return ValidatedMedia(summary=summary, sha256=sha256_file(path))


def part_path(target: str | os.PathLike[str], run_id: str) -> Path:
    if not run_id or any(character in run_id for character in ("/", "\\", os.sep)):
        raise ValueError("run_id 必须是非空安全文件名片段")
    destination = Path(target)
    # 保留最终扩展名，使 FFmpeg 仍能从输出名推断容器。
    return destination.with_name(f"{destination.stem}.part-{run_id}{destination.suffix}")


def atomic_replace_validated(
    temporary: str | os.PathLike[str],
    target: str | os.PathLike[str],
    *,
    validate: Callable[[Path], Any],
) -> Any:
    source = Path(temporary)
    destination = Path(target)
    if source.parent.resolve() != destination.parent.resolve():
        raise ValueError("临时文件必须与目标文件位于同一目录")
    try:
        result = validate(source)
    except Exception:
        # source 是调用者显式传入的本 run 文件，不扫描、不触碰旧目标。
        source.unlink(missing_ok=True)
        raise
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    return result


def cleanup_run_parts(targets: Iterable[str | os.PathLike[str]], run_id: str) -> None:
    """只删除显式目标所对应的本 run 临时文件，不扫描目录。"""
    for target in targets:
        part_path(target, run_id).unlink(missing_ok=True)


# 向后兼容的清晰别名。
full_decode = decode_media
file_sha256 = sha256_file
