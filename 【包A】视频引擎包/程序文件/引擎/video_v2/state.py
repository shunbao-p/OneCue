"""V2 管线的原子文件与内部缓存状态。

本模块只处理包 A 自有的可再生状态，不读取、解析或扩展
Job Bundle Schema v1。一个任务目录当前只允许单写者。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping


MANIFEST_VERSION = 1
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CACHE_LAYERS = ("audio", "shots", "final")


def sha256_file(path: str | Path) -> str:
    """计算文件 SHA-256，不相信 manifest 中的旧值。"""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """生成内部缓存键使用的稳定 JSON 字节。"""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_key(namespace: str, version: str, payload: Mapping[str, Any]) -> str:
    """为内部实现版本和影响产物的输入生成内容键。"""

    document = {
        "namespace": str(namespace),
        "version": str(version),
        "payload": dict(payload),
    }
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _validated_run_id(run_id: str) -> str:
    value = str(run_id)
    if not _RUN_ID_RE.fullmatch(value):
        raise ValueError("run_id 只能包含安全 ASCII 字符")
    return value


def part_path_for(target: str | Path, run_id: str) -> Path:
    """返回与目标同目录、归当前 run 独占的临时路径。"""

    target_path = Path(target)
    safe_run_id = _validated_run_id(run_id)
    # 将媒体扩展名保留在末尾，以便 FFmpeg 仍可按后缀选择 muxer。
    if target_path.suffix:
        name = f"{target_path.stem}.part-{safe_run_id}{target_path.suffix}"
    else:
        name = f"{target_path.name}.part-{safe_run_id}"
    return target_path.with_name(name)


def atomic_commit_file(
    part_path: str | Path,
    target_path: str | Path,
    *,
    validate: Callable[[Path], Any] | None = None,
) -> Path:
    """验证临时文件后原子替换目标。

    验证或替换失败时不会触碰旧目标。调用方仍拥有临时文件，
    可在 finally 中按精确路径清理。
    """

    part = Path(part_path)
    target = Path(target_path)
    if part.parent.resolve(strict=False) != target.parent.resolve(strict=False):
        raise ValueError("原子提交要求临时文件与目标同目录")
    if not part.exists() or not part.is_file() or part.is_symlink():
        raise FileNotFoundError(f"临时产物不存在或不安全: {part}")
    if validate is not None:
        validate(part)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(part, target)
    return target


def atomic_write_json(target: str | Path, value: Any, *, run_id: str) -> Path:
    """将可读 JSON 在同目录写完、重读验证后原子提交。"""

    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    part = part_path_for(target_path, run_id)
    try:
        data = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8") + b"\n"
        with part.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

        def validate_json(path: Path) -> None:
            json.loads(path.read_text(encoding="utf-8"))

        return atomic_commit_file(part, target_path, validate=validate_json)
    except Exception:
        part.unlink(missing_ok=True)
        raise


def read_json(path: str | Path) -> Any:
    """严格读取 UTF-8 JSON，拒绝 NaN/Infinity。"""

    def reject_constant(token: str) -> None:
        raise ValueError(f"非法 JSON 数值 {token}")

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=reject_constant,
    )


def empty_manifest(*, implementation_version: str = "core-pipeline-v1") -> dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "implementation_version": str(implementation_version),
        "audio": {},
        "shots": {},
        "final": {},
    }


def _validate_relative_artifact_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    pure = PurePosixPath(value)
    return (
        not pure.is_absolute()
        and all(part not in ("", ".", "..") for part in pure.parts)
    )


def validate_manifest(value: Any) -> dict[str, Any]:
    """验证内部 manifest 最小结构，防止损坏状态被误命中。"""

    if not isinstance(value, dict):
        raise ValueError("manifest 顶层必须是对象")
    if value.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError(f"manifest_version 必须为 {MANIFEST_VERSION}")
    for layer in _CACHE_LAYERS:
        entries = value.get(layer)
        if not isinstance(entries, dict):
            raise ValueError(f"manifest.{layer} 必须是对象")
        for entry_id, entry in entries.items():
            if not isinstance(entry_id, str) or not isinstance(entry, dict):
                raise ValueError(f"manifest.{layer} 条目结构无效")
            if "key" in entry and not isinstance(entry["key"], str):
                raise ValueError(f"manifest.{layer}.{entry_id}.key 无效")
            if "path" in entry and not _validate_relative_artifact_path(entry["path"]):
                raise ValueError(f"manifest.{layer}.{entry_id}.path 必须是 Bundle 相对路径")
            artifact_hash = entry.get("sha256")
            if artifact_hash is not None and (
                not isinstance(artifact_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", artifact_hash)
            ):
                raise ValueError(f"manifest.{layer}.{entry_id}.sha256 无效")
            duration = entry.get("duration_sec")
            if duration is not None and (
                not isinstance(duration, (int, float))
                or isinstance(duration, bool)
                or not math.isfinite(float(duration))
                or float(duration) <= 0
            ):
                raise ValueError(f"manifest.{layer}.{entry_id}.duration_sec 无效")
    return deepcopy(value)


def load_manifest(
    path: str | Path,
    *,
    implementation_version: str = "core-pipeline-v1",
) -> dict[str, Any]:
    """读取 manifest；缺失表示首次运行，损坏则明确报错。"""

    manifest_path = Path(path)
    if not manifest_path.exists():
        return empty_manifest(implementation_version=implementation_version)
    try:
        return validate_manifest(read_json(manifest_path))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        from .errors import RenderError

        raise RenderError(
            "cache.invalid",
            "cache.load",
            "缓存 manifest 损坏，不会将其作为命中",
            details={"path": str(manifest_path)},
        ) from exc


def save_manifest(path: str | Path, manifest: Mapping[str, Any], *, run_id: str) -> Path:
    validated = validate_manifest(dict(manifest))
    return atomic_write_json(path, validated, run_id=run_id)


def bundle_relative_path(bundle_root: str | Path, artifact: str | Path) -> str:
    """将产物转为 Bundle 相对 POSIX 路径，拒绝越界。"""

    root = Path(bundle_root).resolve(strict=False)
    path = Path(artifact).resolve(strict=False)
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError("缓存产物必须位于 Job Bundle 内") from exc
    value = relative.as_posix()
    if not _validate_relative_artifact_path(value):
        raise ValueError("缓存产物相对路径无效")
    return value


def cache_entry_matches(
    entry: Any,
    *,
    expected_key: str,
    bundle_root: str | Path,
    validate: Callable[[Path], Any] | None = None,
) -> tuple[bool, Path | None, str | None]:
    """以 key、Bundle 相对路径和实际产物哈希复核一条缓存。"""

    if not isinstance(entry, dict) or entry.get("key") != expected_key:
        return False, None, "key_mismatch"
    relative = entry.get("path")
    if not _validate_relative_artifact_path(relative):
        return False, None, "path_invalid"
    root = Path(bundle_root).resolve(strict=False)
    path = root.joinpath(*PurePosixPath(relative).parts).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        return False, None, "path_outside_bundle"
    if not path.exists() or not path.is_file() or path.is_symlink():
        return False, path, "artifact_missing"
    expected_hash = entry.get("sha256")
    if not isinstance(expected_hash, str) or sha256_file(path) != expected_hash:
        return False, path, "artifact_mismatch"
    if validate is not None:
        try:
            validate(path)
        except Exception:
            return False, path, "artifact_invalid"
    return True, path, None


def update_cache_entry(
    manifest: dict[str, Any],
    *,
    layer: str,
    entry_id: str,
    key: str,
    bundle_root: str | Path,
    artifact: str | Path,
    media_summary: Mapping[str, Any] | None = None,
    duration_sec: float | None = None,
    implementation_version: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """在内存 manifest 中更新已验证产物，并强制实际哈希。"""

    if layer not in _CACHE_LAYERS:
        raise ValueError(f"未知缓存层: {layer}")
    artifact_path = Path(artifact)
    if not artifact_path.exists() or not artifact_path.is_file():
        raise FileNotFoundError(artifact_path)
    entry: dict[str, Any] = {
        "key": str(key),
        "path": bundle_relative_path(bundle_root, artifact_path),
        "sha256": sha256_file(artifact_path),
    }
    if duration_sec is not None:
        if not math.isfinite(float(duration_sec)) or float(duration_sec) <= 0:
            raise ValueError("duration_sec 必须是有限正数")
        entry["duration_sec"] = float(duration_sec)
    if media_summary is not None:
        entry["media"] = dict(media_summary)
    if implementation_version is not None:
        entry["implementation_version"] = str(implementation_version)
    entry["created_at"] = str(
        created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    manifest.setdefault(layer, {})[str(entry_id)] = entry
    return entry


def cleanup_run_files(paths: list[str | Path], *, run_id: str) -> None:
    """只清理显式列出且名称归本 run 所有的文件。"""

    marker = f".part-{_validated_run_id(run_id)}"
    for raw_path in paths:
        path = Path(raw_path)
        if marker not in path.name:
            raise ValueError(f"拒绝清理非本 run 文件: {path}")
        path.unlink(missing_ok=True)


__all__ = [
    "MANIFEST_VERSION",
    "atomic_commit_file",
    "atomic_write_json",
    "bundle_relative_path",
    "cache_entry_matches",
    "canonical_json_bytes",
    "cleanup_run_files",
    "content_key",
    "empty_manifest",
    "load_manifest",
    "part_path_for",
    "read_json",
    "save_manifest",
    "sha256_file",
    "update_cache_entry",
    "validate_manifest",
]
