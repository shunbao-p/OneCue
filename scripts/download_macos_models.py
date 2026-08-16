#!/usr/bin/env python3
"""Download and verify the macOS model snapshots used by package B.

The repository intentionally does not contain multi-gigabyte model weights.
This script downloads the upstream snapshots into package B's local model
directories and verifies every file listed by the checked-in manifests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


MANIFESTS = {
    "mf": "macos-mf-model.json",
    "soar": "macos-soar-model.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(package_b: Path, manifest_name: str) -> dict[str, Any]:
    path = package_b / "manifests" / manifest_name
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 1
        or not isinstance(payload.get("files"), list)
        or not payload.get("repository")
        or not payload.get("revision")
    ):
        raise RuntimeError(f"模型清单格式无效：{path}")
    return payload


def verify_model(model_dir: Path, manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for item in manifest["files"]:
        relative = Path(str(item["path"]))
        path = model_dir / relative
        if not path.is_file():
            failures.append(f"缺少文件：{path}")
            continue
        expected_size = int(item["size"])
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            failures.append(f"大小不匹配：{path}（{actual_size} != {expected_size}）")
            continue
        actual_hash = sha256(path)
        if actual_hash != item["sha256"]:
            failures.append(f"SHA-256 不匹配：{path}（{actual_hash} != {item['sha256']}）")
    return failures


def download_one(package_b: Path, model_key: str) -> None:
    manifest_name = MANIFESTS[model_key]
    manifest = read_manifest(package_b, manifest_name)
    repo_id = str(manifest["repository"])
    revision = str(manifest["revision"])
    model_name = str(manifest["model"])
    target = package_b / "pretrained_models" / model_name
    failures = verify_model(target, manifest) if target.exists() else ["目标目录尚不存在"]
    if failures and failures != ["目标目录尚不存在"]:
        print(f"{model_name} 已存在但校验失败，将用上游快照补齐后重新校验。")

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "缺少 huggingface_hub，请先执行 README 中的依赖安装命令。"
        ) from exc

    patterns = [str(item["path"]) for item in manifest["files"]]
    print(f"下载 {repo_id}@{revision} -> {target}")
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(target),
        allow_patterns=patterns,
        max_workers=2,
    )
    failures = verify_model(target, manifest)
    if failures:
        detail = "\n".join(f"  - {item}" for item in failures)
        raise RuntimeError(
            f"{model_name} 下载完成但校验失败；不要启动服务：\n{detail}"
        )
    print(f"校验通过：{model_name}（{len(manifest['files'])} 个文件）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        choices=("mf", "soar", "all"),
        default="mf",
        help="mf 为默认快速版；soar 为质量版；all 下载两者。",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="只校验本地模型，不联网下载。",
    )
    args = parser.parse_args()
    if os.uname().sysname != "Darwin" or os.uname().machine not in {"arm64", "aarch64"}:
        raise SystemExit("此脚本只支持 Apple Silicon macOS。")

    repo_root = Path(__file__).resolve().parents[1]
    package_b = repo_root / "【包B】语音引擎包"
    selected = ("mf", "soar") if args.model == "all" else (args.model,)
    for model_key in selected:
        manifest_name = MANIFESTS[model_key]
        manifest = read_manifest(package_b, manifest_name)
        target = package_b / "pretrained_models" / str(manifest["model"])
        if args.verify_only:
            failures = verify_model(target, manifest)
            if failures:
                raise SystemExit("\n".join(failures))
            print(f"校验通过：{manifest['model']}")
        else:
            download_one(package_b, model_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
