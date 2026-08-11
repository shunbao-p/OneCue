# -*- coding: utf-8 -*-
"""macOS 包 B 控制边界：只调用包 B 自己的已验证启动器。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


EXPECTED_API_VERSION = "dots-tts.synthesize.v1"


class DotsControlError(RuntimeError):
    pass


def _run(info, command, *, timeout=15, runner=subprocess.run):
    if not info.get("installed"):
        raise DotsControlError("包 B 未安装或 macOS 布局无效")
    launcher = info.get("launcher")
    if not launcher or not Path(launcher).is_file():
        raise DotsControlError("包 B macOS 启动器缺失")
    try:
        result = runner(
            [info["python"], "-B", str(launcher), command],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DotsControlError(f"无法运行包 B 启动器：{exc}") from exc
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        detail = (result.stderr or result.stdout or "").strip()
        raise DotsControlError(f"包 B 启动器返回无效：{detail}") from exc
    if not isinstance(payload, dict):
        raise DotsControlError("包 B 启动器返回值不是 JSON 对象")
    return payload


def status(info, *, runner=subprocess.run):
    if not info.get("installed"):
        return {"state": "not_installed", "installed": False, "ready": False}
    payload = _run(info, "status", runner=runner)
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    version = state.get("api_version")
    running = bool(payload.get("running"))
    compatible = not running or version == EXPECTED_API_VERSION
    if running and not compatible:
        label = "incompatible"
    elif payload.get("ready"):
        label = "ready"
    elif running:
        label = "starting"
    else:
        label = "offline"
    return {
        "state": label,
        "installed": True,
        "running": running,
        "ready": bool(payload.get("ready")) and compatible,
        "compatible": compatible,
        "api_version": version or "",
        "expected_api_version": EXPECTED_API_VERSION,
        "pid": state.get("pid"),
        "progress": 100 if payload.get("ready") and compatible else 0,
        "reason": payload.get("reason", "") or (
            "API 版本不匹配" if running and not compatible else ""
        ),
        "raw": payload,
    }


def stop(info, *, runner=subprocess.run):
    current = status(info, runner=runner)
    if current["state"] == "not_installed":
        return {"ok": True, "state": "not_installed", "killed": []}
    if current.get("running") and not current.get("compatible"):
        return {"ok": False, "state": "incompatible", "reason": "API 版本不匹配，未发送信号"}
    result = _run(info, "stop", runner=runner)
    return {
        "ok": bool(result.get("stopped")) or result.get("reason") == "没有正在运行的包 B 服务",
        "state": "offline",
        "killed": [result.get("pid")] if result.get("stopped") and result.get("pid") else [],
        "reason": result.get("reason", ""),
        "raw": result,
    }


def probe_contract(info, synth_script, *, runner=subprocess.run):
    try:
        result = runner(
            [info["python"], str(synth_script), "--probe-contract"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DotsControlError(f"无法协商包 B API：{exc}") from exc
    if result.returncode != 0:
        detail = (result.stdout or result.stderr or "").strip()
        raise DotsControlError(detail or "包 B API 协商失败")
    line = next((item[9:] for item in result.stdout.splitlines() if item.startswith("CONTRACT ")), "")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise DotsControlError("包 B API 协商结果无效") from exc
    if payload.get("mode") not in ("v1", "legacy9"):
        raise DotsControlError("包 B API schema 不兼容")
    return payload
