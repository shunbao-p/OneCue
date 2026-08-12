"""计划 04 的 DepthFlow 外部隔离适配器。"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from video_v2.runtime import CommandResult, CommandRunner


DEPTHFLOW_ROOT = Path("/Users/yuh/Library/Caches/text-video-plan04-feasibility/depthflow")
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class DepthFlowLayout:
    root: Path
    depth: Path
    raw: Path


def _under(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"路径必须位于隔离根目录：{resolved_root}") from exc
    return resolved


def _lexically_under(root: Path, candidate: Path) -> Path:
    """允许 venv 解释器本身是指向既有 Python 的链接。"""
    absolute_root = root.absolute()
    absolute = candidate.absolute()
    try:
        absolute.relative_to(absolute_root)
    except ValueError as exc:
        raise ValueError(f"路径必须位于隔离根目录：{absolute_root}") from exc
    return absolute


def create_layout(case: str, run_id: str, *, root: Path = DEPTHFLOW_ROOT) -> DepthFlowLayout:
    if case not in ("portrait", "architecture", "landscape"):
        raise ValueError("未知基准 case")
    if not _SAFE.fullmatch(str(run_id)):
        raise ValueError("run_id 不是安全 token")
    output_root = root.resolve(strict=False) / "output"
    target = _under(output_root, output_root / f"{case}-{run_id}")
    target.mkdir(parents=True, exist_ok=False)
    return DepthFlowLayout(target, target / "depth.png", target / "raw.mp4")


def build_depthflow_env(root: Path = DEPTHFLOW_ROOT) -> dict[str, str]:
    isolated = root.resolve(strict=False)
    env = dict(os.environ)
    package_ffmpeg = PACKAGE_ROOT / "程序文件" / "bin"
    env.update({
        "PATH": f"{package_ffmpeg}:/usr/bin:/bin:/usr/sbin:/sbin",
        "XDG_CACHE_HOME": str(isolated / "xdg"),
        "HF_HOME": str(isolated / "hf"),
        "HUGGINGFACE_HUB_CACHE": str(isolated / "hf" / "hub"),
        "HF_HUB_DISABLE_XET": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
    return env


def build_depthflow_argv(
    source: Path,
    layout: DepthFlowLayout,
    *,
    root: Path = DEPTHFLOW_ROOT,
    duration_sec: float = 4.0,
) -> list[str]:
    if source.is_symlink() or not source.is_file():
        raise ValueError("source 必须是常规图片")
    duration = float(duration_sec)
    if not math.isfinite(duration) or duration <= 0 or duration > 10:
        raise ValueError("duration_sec 必须在 (0, 10]")
    isolated = root.resolve(strict=False)
    executable = _lexically_under(isolated, isolated / "venv" / "bin" / "python")
    script = _under(isolated, isolated / "project" / "render_plan04.py")
    _under(isolated / "output", layout.root)
    return [
        str(executable), str(script),
        "--input", str(source.resolve()),
        "--depth", str(layout.depth),
        "--output", str(layout.raw),
        "--duration", f"{duration:.6f}",
        "--width", "1080",
        "--height", "1920",
        "--fps", "30",
    ]


def run_depthflow(
    source: Path,
    layout: DepthFlowLayout,
    *,
    runner: CommandRunner,
    root: Path = DEPTHFLOW_ROOT,
    duration_sec: float = 4.0,
    timeout_sec: float = 300.0,
) -> CommandResult:
    timeout = float(timeout_sec)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 600:
        raise ValueError("timeout_sec 必须在 (0, 600]")
    return runner.run(
        build_depthflow_argv(source, layout, root=root, duration_sec=duration_sec),
        env=build_depthflow_env(root),
        check=True,
        timeout=timeout,
    )
