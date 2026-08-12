# -*- coding: utf-8 -*-
"""短视频 V2 运行期结构化错误。"""

from __future__ import annotations

from typing import Any, Mapping


class RenderError(Exception):
    """可稳定写入渲染报告的运行错误。"""

    def __init__(
        self,
        code: str,
        stage: str,
        message: str,
        *,
        shot_id: str | None = None,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.stage = str(stage)
        self.message = str(message)
        self.shot_id = shot_id
        self.retryable = bool(retryable)
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.shot_id is not None:
            payload["shot_id"] = self.shot_id
        if self.details:
            payload["details"] = dict(self.details)
        return payload


class PipelineCancelled(RenderError):
    def __init__(
        self,
        *args: str,
        message: str = "渲染已取消",
        stage: str = "runtime.command",
    ) -> None:
        # 允许通用错误工厂以 (code, stage, message) 形式构造取消对象。
        if len(args) == 3:
            code, selected_stage, selected_message = args
            super().__init__(code, selected_stage, selected_message, retryable=False)
            return
        if len(args) == 1:
            message = args[0]
        elif args:
            raise TypeError("PipelineCancelled 只接受 message 或 code/stage/message")
        super().__init__("pipeline.cancelled", stage, message, retryable=False)


class CommandFailed(RenderError):
    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        stderr: str = "",
        code: str = "runtime.command_failed",
    ) -> None:
        details: dict[str, Any] = {"stderr": stderr}
        if returncode is not None:
            details["returncode"] = returncode
        super().__init__(code, "runtime.command", message, details=details)


class MediaValidationError(RenderError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})
        if path is not None:
            merged["path"] = path
        super().__init__(code, "media.validate", message, details=merged)
