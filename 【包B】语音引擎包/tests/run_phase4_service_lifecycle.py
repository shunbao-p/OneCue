from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def run(command: list[str], cwd: Path, timeout: float = 240.0) -> dict[str, object]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={key: value for key, value in os.environ.items() if key != "PYTORCH_ENABLE_MPS_FALLBACK"},
    )
    return {
        "command": command,
        "exit_code": result.returncode,
        "wall_seconds": time.monotonic() - started,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.5)
        return client.connect_ex(("127.0.0.1", port)) == 0


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def http_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def wait_http_json(url: str, predicate, timeout: float = 60.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            payload = http_json(url)
            if predicate(payload):
                return payload
            last_error = "unexpected payload: %s" % payload
        except (OSError, urllib.error.URLError) as exc:
            last_error = "%s: %s" % (type(exc).__name__, exc)
        time.sleep(0.25)
    raise TimeoutError("HTTP readiness timed out for %s (%s)" % (url, last_error))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-a-root", type=Path, required=True)
    parser.add_argument("--package-b-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()

    a_root = args.package_a_root.expanduser().resolve()
    b_root = args.package_b_root.expanduser().resolve()
    evidence = args.evidence_dir.expanduser().resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    report_path = evidence / "phase4-service-lifecycle-report.json"
    b_python = b_root / "runtime/python/bin/python3"
    b_launcher = b_root / "_internal/macos_launcher.py"
    a_launcher = a_root / "程序文件/mac_launcher.py"
    a_python = a_root / "程序文件/runtime/bin/python3"
    a_ffmpeg = a_root / "程序文件/bin/ffmpeg"
    a_ffprobe = a_root / "程序文件/bin/ffprobe"
    a_state_path = a_root / "程序文件/网站/.package-a-server.json"
    b_state_path = b_root / ".runtime/state.json"

    b_start = [
        str(b_python), str(b_launcher), "start", "--model", "dots-tts-mf",
        "--device", "mps", "--precision", "float32", "--port", "7860",
        "--no-browser", "--timeout", "180",
    ]
    a_start = [
        "/usr/bin/python3", str(a_launcher), "start", "--mode", "development",
        "--python", str(a_python), "--ffmpeg", str(a_ffmpeg),
        "--ffprobe", str(a_ffprobe), "--no-browser",
    ]
    report: dict[str, object] = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "checks": {},
        "result": "FAIL",
    }

    try:
        a_initial = json.loads(a_state_path.read_text(encoding="utf-8"))
        b_initial = json.loads(b_state_path.read_text(encoding="utf-8"))
        reuse_b = run(b_start, b_root)
        reuse_a = run(a_start, a_root)
        require(reuse_b["exit_code"] == 0 and "复用" in reuse_b["stdout"], "包 B 重复启动未复用")
        require(reuse_a["exit_code"] == 0 and "复用" in reuse_a["stdout"], "包 A 重复启动未复用")
        report["checks"]["running_start_reuse"] = {"package_b": reuse_b, "package_a": reuse_a}

        stop_a = run(["/usr/bin/python3", str(a_launcher), "stop", "--timeout", "8"], a_root, 20)
        stop_b = run([str(b_python), str(b_launcher), "stop", "--timeout", "8"], b_root, 20)
        require(stop_a["exit_code"] == 0 and stop_a["wall_seconds"] <= 10.0, "包 A 停止失败或超过 10 秒")
        require(stop_b["exit_code"] == 0 and stop_b["wall_seconds"] <= 10.0, "包 B 停止失败或超过 10 秒")
        time.sleep(0.5)
        first_residue = {
            "package_a_pid_alive": pid_alive(int(a_initial["pid"])),
            "package_b_pid_alive": pid_alive(int(b_initial["pid"])),
            "port_8788_open": port_open(8788),
            "port_7860_open": port_open(7860),
        }
        require(not any(first_residue.values()), "首次停止后存在进程或端口残留")
        report["checks"]["first_stop"] = {
            "package_a": stop_a,
            "package_b": stop_b,
            "residue": first_residue,
        }

        restart_b = run(b_start, b_root)
        restart_a = run(a_start, a_root)
        require(restart_b["exit_code"] == 0 and "启动" in restart_b["stdout"], "包 B 重启失败")
        require(restart_a["exit_code"] == 0 and "启动" in restart_a["stdout"], "包 A 重启失败")
        a_restarted = json.loads(a_state_path.read_text(encoding="utf-8"))
        b_restarted = json.loads(b_state_path.read_text(encoding="utf-8"))
        health = wait_http_json(
            "http://127.0.0.1:8788/api/health",
            lambda payload: payload.get("status") == "ok",
        )
        dots = wait_http_json(
            "http://127.0.0.1:8788/api/dots_status",
            lambda payload: payload.get("state") == "ready",
            timeout=120.0,
        )
        require(health.get("status") == "ok" and dots.get("state") == "ready", "重启后 A+B 未就绪")
        report["checks"]["restart"] = {
            "package_b": restart_b,
            "package_a": restart_a,
            "health": health,
            "dots": dots,
        }

        final_stop_a = run(["/usr/bin/python3", str(a_launcher), "stop", "--timeout", "8"], a_root, 20)
        final_stop_b = run([str(b_python), str(b_launcher), "stop", "--timeout", "8"], b_root, 20)
        require(final_stop_a["exit_code"] == 0 and final_stop_a["wall_seconds"] <= 10.0,
                "包 A 最终停止失败或超过 10 秒")
        require(final_stop_b["exit_code"] == 0 and final_stop_b["wall_seconds"] <= 10.0,
                "包 B 最终停止失败或超过 10 秒")
        time.sleep(0.5)
        final_residue = {
            "package_a_pid_alive": pid_alive(int(a_restarted["pid"])),
            "package_b_pid_alive": pid_alive(int(b_restarted["pid"])),
            "port_8788_open": port_open(8788),
            "port_7860_open": port_open(7860),
            "package_a_state_exists": a_state_path.exists(),
            "package_b_state_exists": b_state_path.exists(),
        }
        require(not any(final_residue.values()), "最终停止后存在状态、进程或端口残留")
        report["checks"]["final_stop"] = {
            "package_a": final_stop_a,
            "package_b": final_stop_b,
            "residue": final_residue,
        }
        report["result"] = "PASS"
        return 0
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return 1
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
