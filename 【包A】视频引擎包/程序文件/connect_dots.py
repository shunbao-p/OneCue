# -*- coding: utf-8 -*-
"""自动发现并连接语音引擎（包B / Dots.tts），写入 config.ini 的 [dots] root。"""
import sys
from pathlib import Path
import paths

manual = sys.argv[1] if len(sys.argv) > 1 else ""
cands = []
if manual:
    cands.append(Path(manual).resolve())
cands += paths.scan_for_dots()

if not cands:
    print("未自动找到语音引擎（Dots.tts）。")
    print("请确认：")
    print("  1) 您已经解压了【包B】语音引擎包；")
    print("  2) macOS 包含 runtime/python/bin/python3.12、启动器和 MF 模型。")
    print("找到后，可把该文件夹拖到“②连接语音引擎”入口上。")
    sys.exit(0)

root = cands[0]
paths.cfg_set("dots", "root", str(root))
info = paths.dots_info()
if not info["installed"]:
    print("找到的目录不是当前 macOS 可用的包 B：")
    print("  ", root)
    if info.get("diagnostic"):
        print("  ", info["diagnostic"])
    print("请重新解压语音引擎包。")
    sys.exit(0)

print("已连接语音引擎：", root)
print("配置已写入 config.ini。回到网页刷新即可看到配音功能。")
