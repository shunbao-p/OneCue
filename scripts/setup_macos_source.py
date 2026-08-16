#!/usr/bin/env python3
"""Prepare a source checkout for Apple Silicon macOS development runs."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def find_python(runtime_root: Path) -> str:
    candidates = [
        os.environ.get("MACOS_PYTHON", ""),
        str(runtime_root / "bin" / "python3.12"),
        str(runtime_root / "bin" / "python"),
        shutil.which("python3.12") or "",
        "/opt/homebrew/bin/python3.12",
        "/usr/local/bin/python3.12",
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file() or not os.access(candidate, os.X_OK):
            continue
        probe = subprocess.run(
            [
                candidate,
                "-c",
                "import json, platform, sys; print(json.dumps({'version': list(sys.version_info[:2]), 'machine': platform.machine()}))",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0 and '"version": [3, 12]' in probe.stdout and any(
            marker in probe.stdout for marker in ('"machine": "arm64"', '"machine": "aarch64"')
        ):
            return candidate
    raise SystemExit(
        "未找到 arm64 Python 3.12。请先安装 Homebrew Python：brew install python@3.12"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("mf", "soar", "all", "none"), default="mf")
    parser.add_argument("--skip-deps", action="store_true", help="只建立运行时，不安装 pip 依赖。")
    args = parser.parse_args()

    if sys.platform != "darwin" or platform.machine() not in {"arm64", "aarch64"}:
        raise SystemExit("此脚本只支持 Apple Silicon macOS。")
    repo_root = Path(__file__).resolve().parents[1]
    package_b = repo_root / "【包B】语音引擎包"
    skill_root = repo_root / ".agents" / "skills" / "short-video-director"
    for required in (skill_root / "SKILL.md", skill_root / "VERSION"):
        if not required.is_file():
            raise SystemExit(f"仓库级 short-video-director Skill 不完整：{required}")
    runtime_root = package_b / "runtime" / "python"
    python312 = find_python(runtime_root)
    if not runtime_root.exists():
        run([python312, "-m", "venv", "--copies", str(runtime_root)])
    runtime_python = runtime_root / "bin" / "python3.12"
    if not runtime_python.is_file():
        runtime_python = runtime_root / "bin" / "python"
    if not runtime_python.is_file():
        raise SystemExit(f"运行时创建失败：{runtime_root}")

    if not args.skip_deps:
        lock = package_b / "constraints" / "macos-arm64-py312.lock"
        run([str(runtime_python), "-m", "pip", "install", "pip==25.0.1"])
        run([str(runtime_python), "-m", "pip", "install", "-r", str(lock)])
        run([str(runtime_python), "-m", "pip", "install", "--no-deps", "-e", str(package_b)])
        run(
            [
                str(runtime_python),
                "-c",
                "import gradio, huggingface_hub, torch, dots_tts; print('包 B Python 导入检查通过。')",
            ]
        )

        engine_root = repo_root / "【包A】视频引擎包" / "程序文件" / "引擎"
        run(
            [
                str(runtime_python),
                "-c",
                f"import sys; sys.path.insert(0, {str(engine_root)!r}); import video_v2; print('包 A video_v2 导入检查通过。')",
            ]
        )

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("未找到 ffmpeg/ffprobe。请先执行：brew install ffmpeg")
    if args.model != "none":
        run([str(runtime_python), str(repo_root / "scripts" / "download_macos_models.py"), "--model", args.model])
    (package_b / "pretrained_models").mkdir(parents=True, exist_ok=True)
    version = (skill_root / "VERSION").read_text(encoding="utf-8").strip()
    print(f"源码运行环境准备完成；仓库 Skill 版本：{version}。后续启动命令见根目录 README.md。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
