#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RELEASE_INFO = "发布信息"
EXCLUDED_DIR_NAMES = {
    ".runtime",
    "__pycache__",
    "bin",
    "build",
    "evidence",
    "logs",
    "outputs",
    "runtime",
    "tests",
    "tmp",
    "wzf",
}
EXCLUDED_SUFFIXES = {".bat", ".dll", ".exe", ".pyd", ".pyc"}
EXCLUDED_FILES = {".DS_Store", "DEVELOPMENT-SNAPSHOT-NOT-FINAL.txt"}


class BuildError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ignore_release_entry(path: Path) -> bool:
    if path.name in EXCLUDED_DIR_NAMES:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return path.name in EXCLUDED_FILES or path.name.startswith("._")


def copy_release(source: Path, destination: Path) -> None:
    if destination.exists():
        raise BuildError(f"发布目录已存在，拒绝覆盖：{destination}")

    def ignore(directory: str, names: list[str]) -> set[str]:
        base = Path(directory)
        return {name for name in names if ignore_release_entry(base / name)}

    shutil.copytree(source, destination, symlinks=True, ignore=ignore)
    for directory in (destination / "bin", destination / "logs", destination / "outputs", destination / "tmp"):
        directory.mkdir(parents=True, exist_ok=True)
    for launcher in destination.glob("*.command"):
        launcher.chmod(launcher.stat().st_mode | 0o111)


def command_json(argv: list[str], cwd: Path, timeout: float | None = None) -> dict[str, object]:
    result = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={key: value for key, value in os.environ.items() if key != "PYTORCH_ENABLE_MPS_FALLBACK"},
    )
    return {
        "command": argv,
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def require_success(name: str, result: dict[str, object]) -> None:
    if result["exit_code"] != 0:
        raise BuildError(f"{name} 失败：{result['stderr'] or result['stdout']}")


def safe_extract_tar(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as bundle:
        members = bundle.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise BuildError(f"Python 资产路径越界：{member.name}") from exc
            if member.issym() or member.islnk():
                link_target = (
                    target.parent / member.linkname
                    if member.issym()
                    else destination / member.linkname
                ).resolve()
                try:
                    link_target.relative_to(destination)
                except ValueError as exc:
                    raise BuildError(f"Python 资产链接越界：{member.name}") from exc
        bundle.extractall(destination, members=members)


def parse_wheel_hashes(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, filename = parts
        if len(digest) == 64:
            rows[Path(filename).name] = digest
    if not rows:
        raise BuildError(f"wheel 哈希表为空：{path}")
    return rows


def verify_wheelhouse(wheelhouse: Path, hash_file: Path) -> list[dict[str, object]]:
    expected = parse_wheel_hashes(hash_file)
    wheels = sorted(wheelhouse.glob("*.whl"))
    actual_names = {path.name for path in wheels}
    if actual_names != set(expected):
        missing = sorted(set(expected) - actual_names)
        extra = sorted(actual_names - set(expected))
        raise BuildError(f"wheelhouse 文件集合不匹配：missing={missing} extra={extra}")
    rows: list[dict[str, object]] = []
    for wheel in wheels:
        actual = sha256(wheel)
        if actual != expected[wheel.name]:
            raise BuildError(f"wheel 哈希不匹配：{wheel.name}")
        rows.append({"name": wheel.name, "size": wheel.stat().st_size, "sha256": actual})
    return rows


def build_clean_runtime(
    package: Path,
    python_asset: Path,
    python_sha256: str,
    wheelhouse: Path,
    wheel_hash_file: Path,
) -> tuple[Path, list[dict[str, object]], dict[str, object]]:
    if sha256(python_asset) != python_sha256:
        raise BuildError("CPython 原始资产哈希不匹配")
    wheels = verify_wheelhouse(wheelhouse, wheel_hash_file)
    runtime_root = package / "runtime"
    safe_extract_tar(python_asset, runtime_root)
    python = runtime_root / "python/bin/python3.12"
    if not python.is_file():
        raise BuildError("CPython 资产未生成 runtime/python/bin/python3.12")
    install = command_json(
        [
            str(python), "-m", "pip", "install",
            "--no-index", "--find-links", str(wheelhouse),
            "--no-deps", "--no-compile",
            "-r", str(package / "constraints/macos-arm64-py312.lock"),
        ],
        package,
        timeout=1800,
    )
    require_success("按锁安装 88 个 wheel", install)
    return python, wheels, install


def install_tools(package: Path, ffmpeg: Path, ffprobe: Path) -> dict[str, object]:
    destinations = {"ffmpeg": package / "bin/ffmpeg", "ffprobe": package / "bin/ffprobe"}
    for name, source in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        if not source.is_file():
            raise BuildError(f"缺少合规{name}：{source}")
        shutil.copy2(source, destinations[name])
        destinations[name].chmod(destinations[name].stat().st_mode | 0o111)
    ffmpeg_version = command_json([str(destinations["ffmpeg"]), "-hide_banner", "-version"], package)
    ffprobe_version = command_json([str(destinations["ffprobe"]), "-hide_banner", "-version"], package)
    require_success("ffmpeg -version", ffmpeg_version)
    require_success("ffprobe -version", ffprobe_version)
    configuration = str(ffmpeg_version["stdout"])
    if "--enable-nonfree" in configuration:
        raise BuildError("最终包拒绝 --enable-nonfree FFmpeg")
    for required in ("--enable-gpl", "--enable-libx264", "--enable-libass"):
        if required not in configuration:
            raise BuildError(f"最终 FFmpeg 缺少许可/能力配置：{required}")
    architectures = {
        name: command_json(["/usr/bin/file", str(path)], package)
        for name, path in destinations.items()
    }
    for name, result in architectures.items():
        require_success(f"{name} 架构检查", result)
        if "arm64" not in str(result["stdout"]):
            raise BuildError(f"{name} 不是 arm64")
    return {
        "ffmpeg": {
            "size": destinations["ffmpeg"].stat().st_size,
            "sha256": sha256(destinations["ffmpeg"]),
            "version": str(ffmpeg_version["stdout"]).splitlines()[0],
            "architecture": architectures["ffmpeg"]["stdout"],
        },
        "ffprobe": {
            "size": destinations["ffprobe"].stat().st_size,
            "sha256": sha256(destinations["ffprobe"]),
            "version": str(ffprobe_version["stdout"]).splitlines()[0],
            "architecture": architectures["ffprobe"]["stdout"],
        },
    }


def file_manifest(root: Path, excluded: set[Path] | None = None) -> list[dict[str, object]]:
    excluded = {path.resolve() for path in (excluded or set())}
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.resolve() in excluded:
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return rows


def required_hashes(package: Path) -> dict[str, dict[str, object]]:
    required = (
        "constraints/macos-arm64-py312.lock",
        "constraints/macos-arm64-runtime-lock.json",
        "manifests/macos-mf-model.json",
        "manifests/macos-soar-model.json",
        "pretrained_models/dots-tts-mf/config.json",
        "pretrained_models/dots-tts-mf/model.safetensors",
        "pretrained_models/dots-tts-soar/config.json",
        "pretrained_models/dots-tts-soar/model.safetensors",
        "pretrained_models/prompts/女播音.wav",
        "pretrained_models/prompts/prompt_text",
        "runtime/python/bin/python3.12",
        "bin/ffmpeg",
        "bin/ffprobe",
        "启动-快速版.command",
        "启动-质量版.command",
        "macOS使用说明.md",
    )
    rows: dict[str, dict[str, object]] = {}
    for relative in required:
        path = package / relative
        if not path.is_file():
            raise BuildError(f"最终包缺少必要文件：{relative}")
        rows[relative] = {"size": path.stat().st_size, "sha256": sha256(path)}
    return rows


def build(args: argparse.Namespace) -> dict[str, object]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise BuildError("最终包只能在 Apple Silicon macOS 上构建")
    source = args.source_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    python_asset = args.python_asset.expanduser().resolve()
    wheelhouse = args.wheelhouse.expanduser().resolve()
    wheel_hash_file = args.wheel_hash_file.expanduser().resolve()
    ffmpeg = args.ffmpeg.expanduser().resolve()
    ffprobe = args.ffprobe.expanduser().resolve()
    ffmpeg_build_report = args.ffmpeg_build_report.expanduser().resolve()
    ffmpeg_sources_archive = args.ffmpeg_sources_archive.expanduser().resolve()
    if not (source / "_internal/macos_launcher.py").is_file():
        raise BuildError(f"来源不是有效包 B：{source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    package = output_dir / "【包B】语音引擎包"
    copy_release(source, package)

    runtime_lock_source = json.loads(
        (source / "constraints/macos-arm64-runtime-lock.json").read_text(encoding="utf-8")
    )
    python_info = runtime_lock_source["python"]
    python, wheels, install = build_clean_runtime(
        package,
        python_asset,
        python_info["sha256"],
        wheelhouse,
        wheel_hash_file,
    )
    tools = install_tools(package, ffmpeg, ffprobe)

    release_runtime_lock = {
        "schema_version": 2,
        "status": "phase5-final-release",
        "target": "aarch64-apple-darwin",
        "python": {
            **python_info,
            "actual_sha256": sha256(python_asset),
        },
        "requirements": {
            "path": "constraints/macos-arm64-py312.lock",
            "sha256": sha256(package / "constraints/macos-arm64-py312.lock"),
            "install_mode": "pip --no-index --no-deps --no-compile",
            "wheel_count": len(wheels),
            "wheels": wheels,
        },
        "external_tools": tools,
    }
    runtime_lock_path = package / "constraints/macos-arm64-runtime-lock.json"
    runtime_lock_path.write_text(
        json.dumps(release_runtime_lock, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    info = package / RELEASE_INFO
    info.mkdir(parents=True, exist_ok=True)
    copied_ffmpeg_report = info / "package-a-ffmpeg-build-report.json"
    copied_ffmpeg_sources = info / ffmpeg_sources_archive.name
    shutil.copy2(ffmpeg_build_report, copied_ffmpeg_report)
    shutil.copy2(ffmpeg_sources_archive, copied_ffmpeg_sources)
    notices = info / "THIRD_PARTY_NOTICES.md"
    notices.write_text(
        "# 第三方组件与发布说明\n\n"
        "- Python 3.12 arm64 来自锁定的 python-build-standalone 原始资产。\n"
        f"- Python 依赖由 {len(wheels)} 个逐文件 SHA-256 校验的 wheel 离线安装；许可证随各 dist-info 保留在运行时中。\n"
        "- ffmpeg/ffprobe 来自包 A 同批离线源码构建，启用 GPL/libx264/libass，明确未启用 nonfree。\n"
        "- 精确工具构建报告和源码归档位于本目录。\n"
        "- 产品包未签名、未公证；公开分发前需要独立完成 Developer ID 与公证流程。\n",
        encoding="utf-8",
    )

    python_probe = command_json(
        [
            str(python), "-B", "-c",
            "import json,platform,torch,torchaudio,transformers,gradio,numpy,soundfile;print(json.dumps({'python':platform.python_version(),'machine':platform.machine(),'torch':torch.__version__,'torchaudio':torchaudio.__version__,'transformers':transformers.__version__,'gradio':gradio.__version__,'numpy':numpy.__version__,'soundfile':soundfile.__version__,'mps_built':torch.backends.mps.is_built(),'mps_available':torch.backends.mps.is_available()}))",
        ],
        package,
    )
    pip_check = command_json([str(python), "-m", "pip", "check"], package)
    launcher = package / "_internal/macos_launcher.py"
    preflight_mf = command_json(
        [str(python), "-B", str(launcher), "preflight", "--model", "dots-tts-mf", "--device", "auto", "--precision", "auto"],
        package,
        timeout=300,
    )
    preflight_soar = command_json(
        [str(python), "-B", str(launcher), "preflight", "--model", "dots-tts-soar", "--device", "auto", "--precision", "auto"],
        package,
        timeout=300,
    )
    for name, result in (
        ("python_probe", python_probe),
        ("pip_check", pip_check),
        ("preflight_mf", preflight_mf),
        ("preflight_soar", preflight_soar),
    ):
        require_success(name, result)

    lock_path = info / "release-lock.json"
    manifest_path = info / "file-manifest.json"
    lock = {
        "schema_version": 1,
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": "arm64-apple-darwin",
        "signature": "unsigned-unnotarized-local-validation",
        "notarization": "not-submitted-no-credentials",
        "default_production_model": "dots-tts-mf",
        "optional_quality_model": "dots-tts-soar",
        "quality_model_limit": "M1 Pro measured steady RTF approximately 9.4; non-real-time mode",
        "known_quality_limit": "Over-200-character chunked text may have a localized volume drop",
        "python_asset": {
            "name": python_asset.name,
            "size": python_asset.stat().st_size,
            "sha256": sha256(python_asset),
        },
        "wheel_hash_file_sha256": sha256(wheel_hash_file),
        "ffmpeg_build_report_sha256": sha256(copied_ffmpeg_report),
        "ffmpeg_sources_archive_sha256": sha256(copied_ffmpeg_sources),
        "required_files": required_hashes(package),
        "verification": {
            "runtime_install": install,
            "python_probe": python_probe,
            "pip_check": pip_check,
            "preflight_mf": preflight_mf,
            "preflight_soar": preflight_soar,
        },
    }
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "root": package.name,
        "release_lock_sha256": sha256(lock_path),
        "files": file_manifest(package, excluded={manifest_path}),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    archive = output_dir / "package-b-apple-silicon-macos-unsigned-unnotarized.zip"
    if archive.exists():
        raise BuildError(f"发布归档已存在，拒绝覆盖：{archive}")
    archive_result = command_json(
        ["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(package), str(archive)],
        output_dir,
        timeout=3600,
    )
    require_success("ditto 归档", archive_result)
    report = {
        "result": "PASS",
        "package": str(package),
        "archive": str(archive),
        "archive_size": archive.stat().st_size,
        "archive_sha256": sha256(archive),
        "release_lock": str(lock_path),
        "release_lock_sha256": sha256(lock_path),
        "file_manifest": str(manifest_path),
        "file_manifest_sha256": sha256(manifest_path),
        "manifest_file_count": len(manifest["files"]),
        "wheel_count": len(wheels),
        "signature": lock["signature"],
        "notarization": lock["notarization"],
    }
    report_path = output_dir / "package-b-build-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="构建包 B Apple Silicon macOS 最终本地验收包")
    parser.add_argument("--source-root", type=Path, default=PACKAGE_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python-asset", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--wheel-hash-file", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--ffmpeg-build-report", type=Path, required=True)
    parser.add_argument("--ffmpeg-sources-archive", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build(args)
    except Exception as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
