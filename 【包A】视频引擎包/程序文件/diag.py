# -*- coding: utf-8 -*-
"""收集环境与文件状态，生成诊断报告，帮助用户排错。"""

from datetime import datetime
import os
from pathlib import Path
import sys

import paths
import platform_support


def _display_path(value):
    """Keep diagnostics useful without exposing the absolute home directory."""
    text = str(value)
    home = str(Path.home())
    if home and (text == home or text.startswith(home + os.sep)):
        return "~" + text[len(home):]
    return text


def _actual_port():
    try:
        value = int((paths.WEB_DIR / ".port").read_text(encoding="utf-8").strip())
        return value if 1 <= value <= 65535 else None
    except (OSError, ValueError):
        return None


def build_report():
    diagnostics = platform_support.runtime_diagnostics(
        paths.PROG_DIR,
        paths.FONTS_DIR,
        explicit_tools={
            "python": paths.cfg_get("tools", "python", ""),
            "ffmpeg": paths.cfg_get("tools", "ffmpeg", ""),
            "ffprobe": paths.cfg_get("tools", "ffprobe", ""),
        },
    )
    out = [
        "===== 会议视频生成器 诊断报告 =====",
        "生成时间: " + datetime.now().astimezone().isoformat(timespec="seconds"),
        "系统: %s %s" % (diagnostics["system"], diagnostics["release"]),
        "架构: %s" % diagnostics["machine"],
        "本机 Python: %s" % diagnostics["python_version"],
        "",
    ]

    labels = {"python": "运行时 Python", "ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}
    for name in ("python", "ffmpeg", "ffprobe"):
        item = diagnostics["tools"][name]
        out.append(
            "[工具] %s: %s  (%s)" % (
                labels[name],
                "可用" if item["available"] else "不可用",
                item["path"] or item["error"],
            )
        )

    font = diagnostics["font"]
    font_file = paths.FONTS_DIR / font["font_file"]
    out.append("[字体] %s存在: %s  (%s)" % (font["font_file"], font_file.is_file(), font_file))
    out.append("[字体] FFmpeg 环境: %s" % (font["environment"] or "无需额外环境变量"))
    out.append("[配置] config.ini存在: %s" % paths.CONFIG_FILE.exists())
    out.append("[配置] Web 基础端口: %s  实际端口: %s" % (paths.web_port(), _actual_port() or "未运行"))

    info = paths.dots_info()
    out.append(
        "[语音引擎] 状态: %s  端口: %s"
        % ("installed" if info["installed"] else "not_installed", info["port"])
    )
    try:
        sys.path.insert(0, str(paths.ENGINE_DIR / "pylibs"))
        import jieba

        out.append("[依赖] jieba: 可用 (%s)" % getattr(jieba, "__version__", "?"))
    except Exception as exc:
        out.append("[依赖] jieba: 不可用 (%s)" % exc)

    out.extend(
        [
            "[目录] APP_ROOT = %s" % _display_path(paths.APP_ROOT),
            "[目录] PROG_DIR = %s" % _display_path(paths.PROG_DIR),
            "[目录] OUTPUT_DIR = %s  writable=%s" % (
                _display_path(paths.OUTPUT_DIR), os.access(paths.OUTPUT_DIR, os.W_OK)
            ),
            "",
            "===== 结束 =====",
        ]
    )
    return "\n".join(out)


def main():
    text = build_report()
    report = paths.PROG_DIR / "诊断报告.txt"
    report.write_text(text, encoding="utf-8")
    print("诊断报告已写入:", report)
    print(text)
    return report


if __name__ == "__main__":
    main()
