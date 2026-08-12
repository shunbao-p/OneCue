"""把实验视觉片统一为包 A 可继续处理的无声镜头规格。"""

from __future__ import annotations

import math
from pathlib import Path

from video_v2.runtime import CommandResult, CommandRunner


def build_normalize_argv(
    source: Path,
    output: Path,
    *,
    ffmpeg: Path,
    duration_sec: float = 4.0,
) -> list[str]:
    duration = float(duration_sec)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration_sec 必须是有限正数")
    filter_graph = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,fps=30,format=yuv420p,"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS"
    )
    return [
        str(ffmpeg), "-v", "error", "-nostdin", "-y",
        "-i", str(source), "-vf", filter_graph, "-an", "-t", f"{duration:.6f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-movflags", "+faststart", str(output),
    ]


def normalize_clip(
    source: Path,
    output: Path,
    *,
    ffmpeg: Path,
    runner: CommandRunner,
    duration_sec: float = 4.0,
    timeout_sec: float | None = 120.0,
) -> CommandResult:
    if not source.is_file() or source.is_symlink():
        raise ValueError("source 必须是常规媒体文件")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    return runner.run(
        build_normalize_argv(source, output, ffmpeg=ffmpeg, duration_sec=duration_sec),
        check=True,
        timeout=timeout_sec,
    )
