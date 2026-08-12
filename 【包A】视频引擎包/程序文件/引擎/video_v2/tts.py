"""包 B Dots.tts 直调 Provider 与镜头级音频缓存。"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .state import (
    atomic_commit_file,
    cache_entry_matches,
    content_key,
    part_path_for,
    save_manifest,
    sha256_file,
    update_cache_entry,
)


PROVIDER_NAME = "dots-tts"
PROVIDER_VERSION = "dots-synth-v1"
OPTIONS_VERSION = "steps4-guidance1.2-speed1-pause0.3-seed42-normalize0-v1"
DEFAULT_TIMEOUT_SEC = 30 * 60.0
_PROGRESS_RE = re.compile(r"^PROGRESS\s+(\d{1,3})/100$")
_DONE_RE = re.compile(r"^DONE\s+([0-9]+(?:\.[0-9]+)?)$")


class Runner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class ProviderRun:
    attempts: int
    elapsed_sec: float
    stdout: str
    stderr: str
    progress: tuple[int, ...]
    reported_duration_sec: float | None


@dataclass(frozen=True)
class AudioResult:
    shot_id: str
    path: Path
    relative_path: str
    cache_key: str
    cache_status: str
    sha256: str
    duration_sec: float
    attempts: int
    provider_name: str
    provider_version: str
    options_version: str
    media_summary: Mapping[str, Any]


def audio_cache_key(
    text: str,
    voice: str,
    *,
    provider_name: str = PROVIDER_NAME,
    provider_version: str = PROVIDER_VERSION,
    options_version: str = OPTIONS_VERSION,
) -> str:
    """只纳入实际改变声音的内容和实现版本。"""

    return content_key(
        "audio",
        "audio-cache-key-v1",
        {
            "text": text,
            "voice": voice,
            "provider_name": provider_name,
            "provider_version": provider_version,
            "options_version": options_version,
        },
    )


def _runtime_value(runtime: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(runtime, Mapping) and name in runtime:
            return runtime[name]
        if runtime is not None and hasattr(runtime, name):
            return getattr(runtime, name)
    return default


def _render_error(
    code: str,
    message: str,
    *,
    shot_id: str | None = None,
    retryable: bool = False,
    cause: BaseException | None = None,
) -> Exception:
    from .errors import RenderError

    error = RenderError(code, "tts", message, shot_id=shot_id, retryable=retryable)
    if cause is not None:
        error.__cause__ = cause
    return error


def _command_text(result: Any) -> tuple[str, str]:
    stdout = str(getattr(result, "stdout", "") or "")
    stderr = str(getattr(result, "stderr", "") or "")
    return stdout, stderr


def _classify_failure(result: Any, *, shot_id: str | None) -> Exception:
    stdout, stderr = _command_text(result)
    combined = f"{stdout}\n{stderr}".lower()
    returncode = int(getattr(result, "returncode", 1))
    timed_out = bool(getattr(result, "timed_out", False))
    if timed_out or "timed out" in combined or "timeout" in combined or "超时" in combined:
        return _render_error("tts.timeout", "包 B 语音生成超时", shot_id=shot_id, retryable=True)
    if returncode == 2 or "未知音色" in combined:
        return _render_error("tts.voice_unknown", "指定音色在包 B 中不存在", shot_id=shot_id)
    if returncode == 5 or "schema 不兼容" in combined or "契约协商失败" in combined:
        return _render_error("tts.contract_incompatible", "包 B API 契约与当前 Provider 不兼容", shot_id=shot_id)
    transient_markers = (
        "connection refused",
        "failed to connect",
        "connection reset",
        "temporarily unavailable",
        "service unavailable",
        "503",
        "连接失败",
        "无法连接",
        "服务未就绪",
        "模型未就绪",
    )
    if any(marker in combined for marker in transient_markers):
        return _render_error("tts.not_ready", "包 B 服务暂未就绪", shot_id=shot_id, retryable=True)
    return _render_error("tts.failed", "包 B 语音生成失败", shot_id=shot_id)


def _parse_protocol(stdout: str) -> tuple[tuple[int, ...], float | None]:
    progress: list[int] = []
    reported_duration: float | None = None
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        match = _PROGRESS_RE.fullmatch(line)
        if match:
            value = max(0, min(100, int(match.group(1))))
            if not progress or value > progress[-1]:
                progress.append(value)
            continue
        match = _DONE_RE.fullmatch(line)
        if match:
            candidate = float(match.group(1))
            if math.isfinite(candidate) and candidate > 0:
                reported_duration = candidate
    return tuple(progress), reported_duration


class DotsTtsProvider:
    """通过包 B Python argv 直接启动现有 ``dots_synth.py``。"""

    name = PROVIDER_NAME

    def __init__(
        self,
        runtime: Any = None,
        *,
        python_path: str | Path | None = None,
        synth_script: str | Path | None = None,
        prompts_dir: str | Path | None = None,
        runner: Runner | None = None,
        provider_version: str = PROVIDER_VERSION,
        options_version: str = OPTIONS_VERSION,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        installed: bool | None = None,
    ) -> None:
        dots_info = _runtime_value(runtime, "dots", default={})
        if not isinstance(dots_info, Mapping):
            dots_info = {}
        self.python_path = Path(
            python_path
            or _runtime_value(runtime, "dots_python", "package_b_python", "tts_python", default="")
            or dots_info.get("python", "")
        )
        self.synth_script = Path(
            synth_script
            or _runtime_value(runtime, "dots_synth", "dots_synth_script", "tts_script", default="")
            or Path(__file__).resolve().parents[2] / "网站" / "dots_synth.py"
        )
        self.prompts_dir = Path(
            prompts_dir
            or _runtime_value(runtime, "dots_prompts", "prompts_dir", "voice_dir", default="")
            or dots_info.get("prompts", "")
        )
        selected_runner = runner or _runtime_value(runtime, "runner")
        self.runner = selected_runner() if callable(selected_runner) and not hasattr(selected_runner, "run") else selected_runner
        self.version = str(provider_version)
        self.options_version = str(options_version)
        self.timeout_sec = float(timeout_sec)
        inferred_installed = bool(dots_info.get("installed", self.python_path and self.synth_script))
        self.installed = inferred_installed if installed is None else bool(installed)

    def _preflight(self, voice: str, *, shot_id: str | None) -> None:
        if (
            not self.installed
            or not self.python_path.is_file()
            or not self.synth_script.is_file()
            or self.runner is None
        ):
            raise _render_error("tts.not_installed", "未找到可用的包 B Python 或 dots_synth.py", shot_id=shot_id)
        voice_path = self.prompts_dir / voice
        if (
            not voice
            or Path(voice).name != voice
            or not voice_path.is_file()
            or voice_path.is_symlink()
        ):
            raise _render_error("tts.voice_unknown", f"包 B 中不存在音色 {voice}", shot_id=shot_id)

    def synthesize(
        self,
        text: str,
        voice: str,
        output_path: str | Path,
        *,
        shot_id: str | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> ProviderRun:
        self._preflight(voice, shot_id=shot_id)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.unlink(missing_ok=True)
        argv = [
            str(self.python_path),
            "-B",
            str(self.synth_script),
            "--text",
            text,
            "--voice",
            voice,
            "--out",
            str(output),
        ]
        started = time.monotonic()
        attempts = 0
        last_error: Exception | None = None
        for attempt in (1, 2):
            attempts = attempt
            output.unlink(missing_ok=True)
            try:
                result = self.runner.run(argv, timeout=self.timeout_sec)
            except Exception as exc:
                # 取消必须保留 runtime 层的 PipelineCancelled 语义。
                if exc.__class__.__name__ == "PipelineCancelled":
                    raise
                error_code = getattr(exc, "code", None)
                if error_code in {"pipeline.cancelled", "tts.timeout", "runtime.command_timeout"}:
                    if error_code == "pipeline.cancelled":
                        raise
                    last_error = _render_error(
                        "tts.timeout",
                        "包 B 语音生成超时",
                        shot_id=shot_id,
                        retryable=True,
                        cause=exc,
                    )
                else:
                    last_error = _render_error(
                        "tts.failed",
                        "包 B 语音进程无法启动",
                        shot_id=shot_id,
                        cause=exc,
                    )
            else:
                if bool(getattr(result, "cancelled", False)):
                    from .errors import PipelineCancelled

                    raise PipelineCancelled(stage="tts")
                if int(getattr(result, "returncode", 1)) == 0:
                    stdout, stderr = _command_text(result)
                    progress, duration = _parse_protocol(stdout)
                    if on_progress is not None:
                        for value in progress:
                            on_progress(value)
                    return ProviderRun(
                        attempts=attempts,
                        elapsed_sec=time.monotonic() - started,
                        stdout=stdout,
                        stderr=stderr,
                        progress=progress,
                        reported_duration_sec=duration,
                    )
                last_error = _classify_failure(result, shot_id=shot_id)
            retryable = bool(getattr(last_error, "retryable", False))
            if not retryable or attempt == 2:
                break
        output.unlink(missing_ok=True)
        assert last_error is not None
        raise last_error


def _duration_from_summary(summary: Any) -> float:
    if isinstance(summary, Mapping):
        candidates = (
            summary.get("duration_sec"),
            summary.get("duration"),
            (summary.get("format") or {}).get("duration")
            if isinstance(summary.get("format"), Mapping)
            else None,
        )
    else:
        candidates = (
            getattr(summary, "duration_sec", None),
            getattr(summary, "duration", None),
        )
    for candidate in candidates:
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            return value
    raise ValueError("音频时长不是有限正数")


def _summary_mapping(summary: Any) -> Mapping[str, Any]:
    if isinstance(summary, Mapping):
        return dict(summary)
    to_dict = getattr(summary, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, Mapping):
            return dict(value)
    return {"duration_sec": _duration_from_summary(summary)}


def ensure_shot_audio(
    *,
    shot_id: str,
    text: str,
    voice: str,
    bundle_root: str | Path,
    run_id: str,
    manifest: dict[str, Any],
    provider: DotsTtsProvider,
    probe_audio: Callable[[Path], Any],
    full_decode: Callable[[Path], Any],
    force: bool = False,
    manifest_path: str | Path | None = None,
    created_at: str | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> AudioResult:
    """复用或原子生成 ``audio/<shot-id>.wav``。

    ``probe_audio`` 与 ``full_decode`` 由媒体层注入，因而单元测试无需
    启动 FFmpeg 或包 B。
    """

    root = Path(bundle_root).resolve(strict=False)
    target = root / "audio" / f"{shot_id}.wav"
    key = audio_cache_key(
        text,
        voice,
        provider_name=provider.name,
        provider_version=provider.version,
        options_version=provider.options_version,
    )

    def validate_cached(path: Path) -> None:
        summary = probe_audio(path)
        _duration_from_summary(summary)
        result = full_decode(path)
        if result is False:
            raise ValueError("音频无法完整解码")

    entry = manifest.setdefault("audio", {}).get(shot_id)
    if not force:
        hit, cached_path, _reason = cache_entry_matches(
            entry,
            expected_key=key,
            bundle_root=root,
            validate=validate_cached,
        )
        if hit and cached_path is not None:
            summary = probe_audio(cached_path)
            return AudioResult(
                shot_id=shot_id,
                path=cached_path,
                relative_path=cached_path.relative_to(root).as_posix(),
                cache_key=key,
                cache_status="hit",
                sha256=sha256_file(cached_path),
                duration_sec=_duration_from_summary(summary),
                attempts=0,
                provider_name=provider.name,
                provider_version=provider.version,
                options_version=provider.options_version,
                media_summary=_summary_mapping(summary),
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    part = part_path_for(target, run_id)
    part.unlink(missing_ok=True)
    try:
        provider_run = provider.synthesize(
            text,
            voice,
            part,
            shot_id=shot_id,
            on_progress=on_progress,
        )

        def validate_new(path: Path) -> None:
            if path.stat().st_size <= 0:
                raise _render_error("tts.failed", "包 B 返回了空 WAV", shot_id=shot_id)
            try:
                summary_value = probe_audio(path)
                _duration_from_summary(summary_value)
            except Exception as exc:
                if getattr(exc, "code", None):
                    raise
                raise _render_error("media.probe_failed", "WAV 无法被 ffprobe 解析", shot_id=shot_id, cause=exc)
            try:
                decode_result = full_decode(path)
                if decode_result is False:
                    raise ValueError("完整解码返回 false")
            except Exception as exc:
                if getattr(exc, "code", None):
                    raise
                raise _render_error("media.decode_failed", "WAV 无法完整解码", shot_id=shot_id, cause=exc)

        atomic_commit_file(part, target, validate=validate_new)
        summary = probe_audio(target)
        duration = _duration_from_summary(summary)
        manifest_entry = update_cache_entry(
            manifest,
            layer="audio",
            entry_id=shot_id,
            key=key,
            bundle_root=root,
            artifact=target,
            media_summary=_summary_mapping(summary),
            duration_sec=duration,
            implementation_version=provider.version,
            created_at=created_at,
        )
        if manifest_path is not None:
            save_manifest(manifest_path, manifest, run_id=run_id)
        return AudioResult(
            shot_id=shot_id,
            path=target,
            relative_path=manifest_entry["path"],
            cache_key=key,
            cache_status="rebuilt",
            sha256=manifest_entry["sha256"],
            duration_sec=duration,
            attempts=provider_run.attempts,
            provider_name=provider.name,
            provider_version=provider.version,
            options_version=provider.options_version,
            media_summary=_summary_mapping(summary),
        )
    finally:
        part.unlink(missing_ok=True)


__all__ = [
    "AudioResult",
    "DEFAULT_TIMEOUT_SEC",
    "DotsTtsProvider",
    "OPTIONS_VERSION",
    "PROVIDER_NAME",
    "PROVIDER_VERSION",
    "ProviderRun",
    "audio_cache_key",
    "ensure_shot_audio",
]
