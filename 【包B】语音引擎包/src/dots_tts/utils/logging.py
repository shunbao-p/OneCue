from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
    "{name}:{function}:{line} | {message}"
)

# 过滤器：静默 apps.gradio 的 INFO 废话，保留 dots_tts 的推理进度
def _terminal_filter(record: dict) -> bool:
    if record["level"].name == "INFO" and record["name"].startswith("apps.gradio"):
        return False
    return True


def configure_logging(
    *,
    level: str | None = None,
    log_file: str | os.PathLike[str] | None = None,
) -> None:
    resolved_level = (level or os.environ.get("DOTS_TTS_LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper()
    logger.remove()
    logger.add(
        sys.stderr,
        level=resolved_level,
        format=DEFAULT_LOG_FORMAT,
        filter=_terminal_filter,
        backtrace=True,
        diagnose=False,
        enqueue=False,
    )
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_path,
            level=resolved_level,
            format=DEFAULT_LOG_FORMAT,
            backtrace=True,
            diagnose=False,
            enqueue=False,
            encoding="utf-8",
        )
