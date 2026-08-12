"""计划 04 的 HyperFrames 外部隔离适配器。"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

from video_v2.runtime import CommandResult, CommandRunner


HYPERFRAMES_ROOT = Path("/Users/yuh/Library/Caches/text-video-plan04-feasibility/hyperframes")
HYPERFRAMES_VERSION = "0.7.106"
NODE_BIN = Path("/Users/yuh/.nvm/versions/node/v24.17.0/bin")
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _under(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"路径必须位于隔离根目录：{resolved_root}") from exc
    return resolved


def build_hyperframes_env(root: Path = HYPERFRAMES_ROOT) -> dict[str, str]:
    isolated = root.resolve(strict=False)
    browser = _under(
        isolated,
        isolated
        / "chrome"
        / "chrome-headless-shell"
        / "mac_arm-152.0.7928.2"
        / "chrome-headless-shell-mac-arm64"
        / "chrome-headless-shell",
    )
    env = dict(os.environ)
    package_ffmpeg = PACKAGE_ROOT / "程序文件" / "bin"
    env.update({
        "PATH": f"{package_ffmpeg}:{NODE_BIN}:/usr/bin:/bin:/usr/sbin:/sbin",
        "npm_config_cache": str(isolated / "npm-cache"),
        "XDG_CACHE_HOME": str(isolated / "chrome"),
        "HYPERFRAMES_BROWSER_PATH": str(browser),
        "HYPERFRAMES_NO_TELEMETRY": "1",
        "HYPERFRAMES_SKIP_SKILLS": "1",
    })
    return env


def build_hyperframes_render_argv(
    composition: str,
    output: Path,
    *,
    root: Path = HYPERFRAMES_ROOT,
    quality: str = "high",
) -> list[str]:
    if not _SAFE.fullmatch(composition) or not composition.endswith(".html"):
        raise ValueError("composition 必须是安全 HTML 文件名")
    if quality not in ("draft", "standard", "high"):
        raise ValueError("quality 必须是 draft、standard 或 high")
    isolated = root.resolve(strict=False)
    npx = NODE_BIN / "npx"
    if not npx.is_file():
        raise FileNotFoundError(npx)
    project = _under(isolated, isolated / "project" / "rainy-messenger-motion")
    source = _under(project / "compositions", project / "compositions" / composition)
    if source.is_symlink() or not source.is_file():
        raise ValueError("composition 必须是隔离项目内的常规文件")
    target = _under(isolated / "output", output)
    if target.suffix.lower() != ".mp4":
        raise ValueError("HyperFrames 输出必须是 MP4")
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    return [
        str(npx), "--yes", f"hyperframes@{HYPERFRAMES_VERSION}",
        "render", str(project),
        "--composition", f"compositions/{composition}",
        "--output", str(target),
        "--fps", "30",
        "--quality", quality,
        "--workers", "1",
        "--strict",
    ]


def run_hyperframes_render(
    composition: str,
    output: Path,
    *,
    runner: CommandRunner,
    root: Path = HYPERFRAMES_ROOT,
    quality: str = "high",
    timeout_sec: float = 300.0,
) -> CommandResult:
    timeout = float(timeout_sec)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 600:
        raise ValueError("timeout_sec 必须在 (0, 600]")
    return runner.run(
        build_hyperframes_render_argv(
            composition,
            output,
            root=root,
            quality=quality,
        ),
        env=build_hyperframes_env(root),
        check=True,
        timeout=timeout,
    )
