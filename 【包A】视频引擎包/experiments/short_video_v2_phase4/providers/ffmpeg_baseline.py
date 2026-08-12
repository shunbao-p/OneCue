"""使用计划 03 固定预设生成无声 FFmpeg 视觉基线。"""

from __future__ import annotations

import math
from pathlib import Path

from video_v2.motion import build_motion_filter
from video_v2.runtime import CommandResult, CommandRunner


def build_ffmpeg_baseline_argv(
    source: Path,
    output: Path,
    *,
    ffmpeg: Path,
    duration_sec: float,
    preset: str,
    strength: str,
    focus_x: float,
    focus_y: float,
) -> list[str]:
    duration = float(duration_sec)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration_sec 必须是有限正数")
    if not source.is_file() or source.is_symlink():
        raise ValueError("source 必须是常规图片")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_graph = build_motion_filter(
        preset, strength, focus_x, focus_y, duration, 30, 1080, 1920,
    )
    return [
        str(ffmpeg), "-v", "error", "-nostdin", "-y",
        "-loop", "1", "-framerate", "30", "-i", str(source),
        "-vf", filter_graph, "-t", f"{duration:.6f}", "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]


def render_ffmpeg_baseline(
    source: Path,
    output: Path,
    *,
    ffmpeg: Path,
    runner: CommandRunner,
    duration_sec: float,
    preset: str,
    strength: str,
    focus_x: float,
    focus_y: float,
    timeout_sec: float | None = 120.0,
) -> CommandResult:
    return runner.run(
        build_ffmpeg_baseline_argv(
            source,
            output,
            ffmpeg=ffmpeg,
            duration_sec=duration_sec,
            preset=preset,
            strength=strength,
            focus_x=focus_x,
            focus_y=focus_y,
        ),
        check=True,
        timeout=timeout_sec,
    )
