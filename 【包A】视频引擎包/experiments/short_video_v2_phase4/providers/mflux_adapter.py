"""计划 04 的 MFLUX 静态图片隔离适配器。"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Mapping

from video_v2.runtime import CommandResult, CommandRunner


MFLUX_ROOT = Path("/Users/yuh/Library/Caches/text-video-plan04-feasibility/mflux")
MFLUX_MODEL = "mlx-community/flux2-klein-4b-4bit"
MFLUX_BASE_MODEL = "flux2-klein-4b"


def _under(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"路径必须位于隔离根目录：{resolved_root}") from exc
    return resolved


def build_mflux_env(root: Path = MFLUX_ROOT) -> dict[str, str]:
    isolated = root.resolve(strict=False)
    env = dict(os.environ)
    env.update({
        "HF_HOME": str(isolated / "hf"),
        "HUGGINGFACE_HUB_CACHE": str(isolated / "hf" / "hub"),
        "HF_HUB_DISABLE_XET": "1",
        "XDG_CACHE_HOME": str(isolated / "cache"),
        "TOKENIZERS_PARALLELISM": "false",
    })
    return env


def build_mflux_generate_argv(
    prompt: str,
    output: Path,
    *,
    executable: Path | None = None,
    root: Path = MFLUX_ROOT,
    seed: int,
    width: int,
    height: int,
    steps: int = 4,
    cache_limit_gb: int = 8,
) -> list[str]:
    isolated = root.resolve(strict=False)
    command = _under(
        isolated,
        executable or isolated / "venv" / "bin" / "mflux-generate-flux2",
    )
    target = _under(isolated / "output", output)
    if target.suffix.lower() != ".png":
        raise ValueError("MFLUX 输出必须是 PNG")
    if target.exists():
        raise FileExistsError(target)
    clean_prompt = str(prompt).strip()
    if not clean_prompt or len(clean_prompt) > 10_000:
        raise ValueError("prompt 必须是 1–10000 字符的非空文本")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed 必须是非负整数")
    if any(not isinstance(value, int) or value < 256 or value > 2048 or value % 16 for value in (width, height)):
        raise ValueError("width/height 必须是 256–2048 范围内的 16 倍数")
    if not isinstance(steps, int) or steps < 1 or steps > 50:
        raise ValueError("steps 必须在 1–50")
    if not isinstance(cache_limit_gb, int) or cache_limit_gb < 1 or cache_limit_gb > 8:
        raise ValueError("MLX cache 上限必须在 1–8 GiB")
    target.parent.mkdir(parents=True, exist_ok=True)
    return [
        str(command),
        "--model", MFLUX_MODEL,
        "--base-model", MFLUX_BASE_MODEL,
        "--prompt", clean_prompt,
        "--seed", str(seed),
        "--height", str(height),
        "--width", str(width),
        "--steps", str(steps),
        "--guidance", "1.0",
        "--low-ram",
        "--mlx-cache-limit-gb", str(cache_limit_gb),
        "--metadata",
        "--output", str(target),
    ]


def run_mflux_generate(
    prompt: str,
    output: Path,
    *,
    runner: CommandRunner,
    root: Path = MFLUX_ROOT,
    executable: Path | None = None,
    seed: int,
    width: int,
    height: int,
    steps: int = 4,
    timeout_sec: float = 900.0,
) -> CommandResult:
    timeout = float(timeout_sec)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 1800:
        raise ValueError("timeout_sec 必须是 (0, 1800] 的有限值")
    return runner.run(
        build_mflux_generate_argv(
            prompt,
            output,
            executable=executable,
            root=root,
            seed=seed,
            width=width,
            height=height,
            steps=steps,
        ),
        env=build_mflux_env(root),
        check=True,
        timeout=timeout,
    )
