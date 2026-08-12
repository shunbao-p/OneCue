# -*- coding: utf-8 -*-
"""短视频 V2 的延迟运行时解析与安全命令执行器。"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .errors import CommandFailed, PipelineCancelled, RenderError


PIPELINE_VERSION = "package-a-v2-core.1"
RUNTIME_VERSION = "runtime.1"
TTS_PROVIDER_VERSION = "dots-synth.1"
MOTION_VERSION = "ffmpeg-motion.1"
CAPTION_VERSION = "ass-caption.1"
TIMELINE_VERSION = "ffmpeg-timeline.1"

@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_sec: float
    cancelled: bool = False


class _BoundedText:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self._parts: list[str] = []
        self._length = 0
        self._lock = threading.Lock()

    def append(self, value: str) -> None:
        with self._lock:
            self._parts.append(value)
            self._length += len(value)
            while self._length > self.limit and self._parts:
                overflow = self._length - self.limit
                first = self._parts[0]
                if len(first) <= overflow:
                    self._parts.pop(0)
                    self._length -= len(first)
                else:
                    self._parts[0] = first[overflow:]
                    self._length -= overflow

    def text(self) -> str:
        with self._lock:
            return "".join(self._parts)


class CommandRunner:
    """只接受 argv 列表的可取消进程执行器。"""

    def __init__(
        self,
        *,
        cancel_event: Any | None = None,
        popen_factory: Callable[..., Any] | None = None,
        poll_interval: float = 0.05,
        terminate_grace: float = 1.0,
        log_limit: int = 256_000,
    ) -> None:
        self.cancel_event = cancel_event
        self._popen = popen_factory or subprocess.Popen
        self.poll_interval = max(0.005, float(poll_interval))
        self.terminate_grace = max(0.0, float(terminate_grace))
        self.log_limit = max(1, int(log_limit))

    def _cancelled(self) -> bool:
        return bool(self.cancel_event is not None and self.cancel_event.is_set())

    @staticmethod
    def _check_argv(argv: Sequence[str]) -> list[str]:
        if not isinstance(argv, list):
            raise TypeError("argv 必须是 list[str]")
        if not argv or any(not isinstance(item, str) for item in argv):
            raise TypeError("argv 必须是非空 list[str]")
        return list(argv)

    @staticmethod
    def _drain(stream: Any, sink: _BoundedText) -> None:
        if stream is None:
            return
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    return
                sink.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace"))
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _stop(self, process: Any) -> bool:
        """先温和终止，限时未退出时强制终止；返回是否动用了后者。"""
        if process.poll() is not None:
            return False
        process.terminate()
        try:
            process.wait(timeout=self.terminate_grace)
            return False
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return True

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        check: bool = False,
    ) -> CommandResult:
        safe_argv = self._check_argv(argv)
        if self._cancelled():
            raise PipelineCancelled()

        started = time.monotonic()
        try:
            process = self._popen(
                safe_argv,
                cwd=None if cwd is None else os.fspath(cwd),
                env=None if env is None else dict(env),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        except OSError as exc:
            raise CommandFailed(f"无法启动外部命令: {exc}") from exc

        stdout = _BoundedText(self.log_limit)
        stderr = _BoundedText(self.log_limit)
        readers = [
            threading.Thread(target=self._drain, args=(process.stdout, stdout), daemon=True),
            threading.Thread(target=self._drain, args=(process.stderr, stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()

        cancelled = False
        timed_out = False
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if self._cancelled():
                    cancelled = True
                    self._stop(process)
                    break
                if timeout is not None and elapsed >= timeout:
                    timed_out = True
                    self._stop(process)
                    break
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            # 把 CLI Ctrl+C 转为统一取消语义，确保子进程先被收束，
            # 再由 pipeline 写 cancelled 报告并保护旧产物。
            cancelled = True
            self._stop(process)
        returncode = process.wait()
        for reader in readers:
            reader.join(timeout=2.0)

        result = CommandResult(
            argv=tuple(safe_argv),
            returncode=int(returncode),
            stdout=stdout.text(),
            stderr=stderr.text(),
            elapsed_sec=time.monotonic() - started,
            cancelled=cancelled,
        )
        if cancelled:
            raise PipelineCancelled()
        if timed_out:
            raise CommandFailed(
                f"外部命令超时（{timeout:.3f}s）",
                returncode=result.returncode,
                stderr=result.stderr,
                code="runtime.command_timeout",
            )
        if check and result.returncode != 0:
            raise CommandFailed(
                f"外部命令退出码为 {result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return result


@dataclass(frozen=True)
class RuntimeContext:
    job_dir: Path
    ffmpeg: Path
    ffprobe: Path
    font_path: Path
    font_name: str
    dots: Mapping[str, Any]
    run_id: str
    cancel_event: Any | None = field(default=None, compare=False, repr=False)
    on_event: Callable[[Mapping[str, Any]], None] | None = field(default=None, compare=False, repr=False)

    @classmethod
    def resolve(
        cls,
        job_dir: str | os.PathLike[str],
        *,
        run_id: str | None = None,
        cancel_event: Any | None = None,
        on_event: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> "RuntimeContext":
        # paths.py 创建部分 V1 目录，故只能在显式预检时延迟导入。
        program_dir = Path(__file__).resolve().parents[2]
        if str(program_dir) not in sys.path:
            sys.path.insert(0, str(program_dir))
        try:
            package_paths = importlib.import_module("paths")
            ffmpeg = Path(package_paths.resolve_ffmpeg(required=True)).resolve()
            ffprobe = Path(package_paths.resolve_ffprobe(required=True)).resolve()
            font_config = dict(package_paths.FONT_CONFIG)
        except RenderError:
            raise
        except Exception as exc:
            raise RenderError(
                "runtime.tools_unavailable",
                "preflight",
                "FFmpeg 或 ffprobe 不可用",
                details={"type": type(exc).__name__},
            ) from exc
        font_path = (Path(font_config["fonts_dir"]) / font_config["font_file"]).resolve()
        if not ffmpeg.is_file() or not ffprobe.is_file():
            raise RenderError("runtime.tools_unavailable", "preflight", "FFmpeg 或 ffprobe 不可用")
        if not font_path.is_file():
            raise RenderError(
                "runtime.font_unavailable",
                "preflight",
                "中文字体不可用",
                details={"path": str(font_path)},
            )
        return cls(
            job_dir=Path(job_dir).resolve(),
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            font_path=font_path,
            font_name=str(font_config["font_name"]),
            dots=dict(package_paths.dots_info()),
            run_id=run_id or uuid.uuid4().hex,
            cancel_event=cancel_event,
            on_event=on_event,
        )

    def runner(self, **kwargs: Any) -> CommandRunner:
        return CommandRunner(cancel_event=self.cancel_event, **kwargs)

    def emit(self, event: Mapping[str, Any]) -> None:
        if self.on_event is not None:
            try:
                self.on_event(dict(event))
            except Exception:
                # 进度观察者不得改变渲染结果或覆盖真正错误。
                return
