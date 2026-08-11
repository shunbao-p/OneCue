# -*- coding: utf-8 -*-
"""包 A 的 macOS 启动、预检、诊断与停止编排。

业务服务仍由 ``网站/kt_web.py`` 提供；本模块只负责 Finder 启动边界、
受控运行时检查和单实例生命周期。所有外部命令都使用 argv 数组。
"""

import argparse
import contextlib
from datetime import datetime
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import paths
import platform_support


PROG_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = PROG_DIR.parent
WEB_SCRIPT = PROG_DIR / "网站" / "kt_web.py"
PORT_FILE = PROG_DIR / "网站" / ".port"
STATE_FILE = PROG_DIR / "网站" / ".package-a-server.json"
LOCK_FILE = PROG_DIR / "网站" / ".package-a-launch.lock"
LOG_FILE = PROG_DIR / "日志" / "mac-web.log"
DIAGNOSTIC_JSON = PROG_DIR / "日志" / "macOS诊断报告.json"
DIAGNOSTIC_TEXT = PROG_DIR / "日志" / "macOS诊断报告.txt"
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
START_TIMEOUT_SECONDS = 10.0


class LaunchError(RuntimeError):
    pass


def _run(argv, timeout=15):
    return subprocess.run(
        [str(item) for item in argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _first_line(text):
    return str(text or "").splitlines()[0] if str(text or "").splitlines() else ""


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


def tool_architectures(path):
    """Return architectures reported by the system ``file`` tool."""
    result = _run(["/usr/bin/file", "-b", str(Path(path).resolve())])
    if result.returncode:
        raise LaunchError("无法检测工具架构：%s" % (_first_line(result.stderr) or path))
    lowered = result.stdout.lower()
    found = []
    if "arm64" in lowered or "aarch64" in lowered:
        found.append("arm64")
    if "x86_64" in lowered:
        found.append("x86_64")
    if not found:
        raise LaunchError("检测到的文件不是可识别的 macOS Mach-O：%s" % result.stdout.strip())
    return found


def probe_ffmpeg(executable):
    version = _run([executable, "-hide_banner", "-version"])
    filters = _run([executable, "-hide_banner", "-filters"])
    encoders = _run([executable, "-hide_banner", "-encoders"])
    for label, result in (("版本", version), ("滤镜", filters), ("编码器", encoders)):
        if result.returncode:
            raise LaunchError("ffmpeg %s检查失败：%s" % (label, _first_line(result.stderr)))
    configuration = ""
    for line in version.stdout.splitlines():
        if line.startswith("configuration:"):
            configuration = line.split(":", 1)[1].strip()
            break
    filter_text = "\n" + filters.stdout + "\n"
    encoder_text = "\n" + encoders.stdout + "\n"
    return {
        "version": _first_line(version.stdout),
        "configuration": configuration,
        "subtitles": any(" subtitles " in (" " + line + " ") for line in filter_text.splitlines()),
        "libx264": "libx264" in encoder_text,
        "aac": any(line.rstrip().endswith(" aac") or " aac " in line for line in encoder_text.splitlines()),
        "png": any(line.rstrip().endswith(" png") or " png " in line for line in encoder_text.splitlines()),
    }


def probe_ffprobe(executable):
    result = _run([executable, "-hide_banner", "-version"])
    if result.returncode:
        raise LaunchError("ffprobe 版本检查失败：%s" % _first_line(result.stderr))
    return _first_line(result.stdout)


def _python_version(executable):
    result = _run([
        executable,
        "-B",
        "-c",
        "import platform,sys;print(platform.python_version());print(platform.machine());print(sys.executable)",
    ])
    if result.returncode:
        raise LaunchError("Python 运行时检查失败：%s" % _first_line(result.stderr))
    lines = result.stdout.splitlines()
    if len(lines) < 3:
        raise LaunchError("Python 运行时未返回完整版本与架构信息")
    return {"version": lines[0], "machine": lines[1], "executable": lines[2]}


def resolve_tools(root=PACKAGE_ROOT, mode="release", explicit_tools=None):
    root = Path(root).resolve()
    explicit_tools = explicit_tools or {}
    program = root / "程序文件"
    if mode == "release":
        candidates = {
            "python": program / "runtime" / "bin" / "python3",
            "ffmpeg": program / "bin" / "ffmpeg",
            "ffprobe": program / "bin" / "ffprobe",
        }
        missing = [name for name, path in candidates.items() if not path.is_file() or not os.access(path, os.X_OK)]
        if missing:
            detail = "、".join("%s=%s" % (name, candidates[name]) for name in missing)
            raise LaunchError("缺少发布运行时工具；检测到：%s；恢复：重新构建或重新解压完整 macOS 发布包" % detail)
        return {name: str(path.resolve()) for name, path in candidates.items()}

    python = explicit_tools.get("python") or os.environ.get("PACKAGE_A_PYTHON") or sys.executable
    ffmpeg = platform_support.resolve_ffmpeg(
        program / "bin", explicit=explicit_tools.get("ffmpeg"), required=True
    )
    ffprobe = platform_support.resolve_ffprobe(
        program / "bin", explicit=explicit_tools.get("ffprobe"), required=True
    )
    return {"python": str(Path(python).resolve()), "ffmpeg": ffmpeg, "ffprobe": ffprobe}


def _write_directory_probe(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".package-a-write-", dir=str(directory), delete=False)
    probe = Path(handle.name)
    try:
        handle.write(b"ok")
        handle.close()
    finally:
        with contextlib.suppress(OSError):
            probe.unlink()


def collect_preflight(root=PACKAGE_ROOT, mode="release", explicit_tools=None, min_free_bytes=MIN_FREE_BYTES):
    root = Path(root).resolve()
    report = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "system": platform.system(),
        "system_release": platform.release(),
        "macos_version": platform.mac_ver()[0],
        "architecture": platform.machine(),
        "package_root": str(root),
        "checks": {},
        "tools": {},
        "directories": {},
        "package_b": {"state": "not_installed"},
        "warnings": [],
        "failures": [],
    }
    failures = report["failures"]
    if report["system"].lower() != "darwin":
        failures.append("需要 macOS（Darwin）；检测到 %s" % report["system"])
    if report["architecture"].lower() != "arm64":
        failures.append("需要 Apple Silicon arm64；检测到 %s" % report["architecture"])

    try:
        tools = resolve_tools(root, mode=mode, explicit_tools=explicit_tools)
        report["tools"].update(tools)
        python_info = _python_version(tools["python"])
        report["tools"]["python_info"] = python_info
        if python_info["machine"].lower() != "arm64":
            failures.append("Python 必须为 arm64；检测到 %s" % python_info["machine"])
        if mode == "release" and not _inside(tools["python"], root / "程序文件" / "runtime"):
            failures.append("发布模式 Python 不在受控包内运行时中")

        ffmpeg_arch = tool_architectures(tools["ffmpeg"])
        ffprobe_arch = tool_architectures(tools["ffprobe"])
        report["tools"]["ffmpeg_architectures"] = ffmpeg_arch
        report["tools"]["ffprobe_architectures"] = ffprobe_arch
        if "arm64" not in ffmpeg_arch or "arm64" not in ffprobe_arch:
            failures.append("ffmpeg/ffprobe 必须包含 arm64；检测到 %s / %s" % (ffmpeg_arch, ffprobe_arch))

        capabilities = probe_ffmpeg(tools["ffmpeg"])
        report["tools"]["ffmpeg_info"] = capabilities
        report["tools"]["ffprobe_version"] = probe_ffprobe(tools["ffprobe"])
        required_capabilities = ("subtitles", "libx264", "aac", "png")
        capability_ok = all(capabilities.get(name) for name in required_capabilities)
        report["checks"]["ffmpeg_capabilities"] = {
            "ok": capability_ok,
            "required": list(required_capabilities),
        }
        if not capability_ok:
            missing = [name for name in required_capabilities if not capabilities.get(name)]
            failures.append("ffmpeg 缺少能力：%s；恢复：使用 Phase 4 锁定构建" % "、".join(missing))
        configuration = capabilities.get("configuration", "")
        if mode == "release" and "--enable-nonfree" in configuration:
            failures.append("发布 FFmpeg 检测到 --enable-nonfree，不能分发；恢复：按锁文件重新构建 GPL 版本")
        if mode == "release":
            for flag in ("--enable-gpl", "--enable-libx264", "--enable-libass", "--enable-zlib"):
                if flag not in configuration:
                    failures.append("发布 FFmpeg 配置缺少 %s" % flag)
        elif "--enable-nonfree" in configuration:
            report["warnings"].append("开发 FFmpeg 含 --enable-nonfree，仅限本机验证，禁止进入发布包")
    except Exception as exc:
        failures.append("缺少或无法使用运行时工具；检测到：%s；恢复：重新构建发布包，开发模式请显式传入工具路径" % exc)

    font = root / "程序文件" / "fonts" / "simhei.ttf"
    font_ok = font.is_file() and os.access(font, os.R_OK)
    report["checks"]["font"] = {"ok": font_ok, "path": str(font)}
    if not font_ok:
        failures.append("缺少可读字体 simhei.ttf；检测到 %s；恢复：重新解压完整包" % font)

    directory_map = {
        "work": root / "程序文件" / "临时文件",
        "logs": root / "程序文件" / "日志",
        "materials": root / "我的素材",
        "output": root / "成片",
    }
    directory_errors = []
    for name, directory in directory_map.items():
        try:
            _write_directory_probe(directory)
            report["directories"][name] = {"path": str(directory), "writable": True}
        except Exception as exc:
            report["directories"][name] = {"path": str(directory), "writable": False, "error": str(exc)}
            directory_errors.append("%s=%s" % (name, exc))
    report["checks"]["directories"] = {"ok": not directory_errors}
    if directory_errors:
        failures.append("目录不可写：%s；恢复：移动到当前用户可写目录并重新解压" % "；".join(directory_errors))

    try:
        usage = shutil.disk_usage(root)
        free_bytes = getattr(usage, "free", usage[2])
        report["disk"] = {"free_bytes": free_bytes, "minimum_bytes": int(min_free_bytes)}
        if free_bytes < int(min_free_bytes):
            failures.append("磁盘空间不足：检测到 %s 字节，至少需要 %s 字节；恢复：释放空间" % (free_bytes, min_free_bytes))
    except Exception as exc:
        failures.append("无法检测磁盘空间：%s" % exc)

    try:
        info = paths.dots_info()
        report["package_b"] = {
            "state": "installed" if info.get("installed") else "not_installed",
            "installed": bool(info.get("installed")),
        }
    except Exception as exc:
        report["package_b"] = {"state": "not_installed", "installed": False, "diagnostic": str(exc)}
    report["ok"] = not failures
    return report


def format_failures(report):
    if report.get("ok"):
        return "预检通过"
    lines = ["预检失败：缺少或不符合运行条件。"]
    lines.extend("- %s" % item for item in report.get("failures", []))
    lines.append("检测到的系统：%s / %s" % (report.get("system"), report.get("architecture")))
    lines.append("恢复：按上述提示修复，或重新解压由 Phase 4 构建脚本生成的完整 macOS 包。")
    return "\n".join(lines)


def read_port(port_file=PORT_FILE):
    try:
        value = int(Path(port_file).read_text(encoding="utf-8").strip())
        return value if 1 <= value <= 65535 else None
    except (OSError, ValueError):
        return None


def health(port, timeout=0.75):
    if not port:
        return None
    try:
        request = urllib.request.Request("http://127.0.0.1:%d/api/health" % int(port))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") == "ok" and payload.get("service") == "package-a-video":
            return payload
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return None
    return None


def load_state(state_file=STATE_FILE):
    try:
        data = json.loads(Path(state_file).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write_state(state, state_file=STATE_FILE):
    state_file = Path(state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_file.with_name(state_file.name + ".tmp-%d" % os.getpid())
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temporary), str(state_file))


def process_matches(pid, expected_script=WEB_SCRIPT):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        result = _run(["/bin/ps", "-p", str(pid), "-o", "command="])
        return result.returncode == 0 and str(Path(expected_script).resolve()) in result.stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def find_running_service():
    state = load_state()
    pid = state.get("pid")
    script = state.get("script")
    expected_script = str(WEB_SCRIPT.resolve())
    if not pid or script != expected_script or not process_matches(pid):
        return None
    port = state.get("port") or read_port()
    payload = health(port) if port else None
    if payload:
        return {
            "pid": int(pid),
            "port": int(port),
            "url": "http://127.0.0.1:%d/" % int(port),
            "health": payload,
        }
    return None


@contextlib.contextmanager
def _launch_lock(lock_file=LOCK_FILE):
    lock_file = Path(lock_file)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_file.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        stream.seek(0)
        stream.truncate()
        stream.write("%d\n" % os.getpid())
        stream.flush()
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
        stream.close()


def start_service(mode="release", explicit_tools=None, open_browser=True, timeout=START_TIMEOUT_SECONDS):
    running = find_running_service()
    if running:
        if open_browser:
            platform_support.open_browser(running["url"])
        return dict(running, reused=True)

    with _launch_lock():
        running = find_running_service()
        if running:
            if open_browser:
                platform_support.open_browser(running["url"])
            return dict(running, reused=True)

        report = collect_preflight(PACKAGE_ROOT, mode=mode, explicit_tools=explicit_tools)
        if not report["ok"]:
            write_diagnostics(report)
            raise LaunchError(format_failures(report))
        tools = report["tools"]
        with contextlib.suppress(OSError):
            PORT_FILE.unlink()
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log = LOG_FILE.open("a", encoding="utf-8")
        env = os.environ.copy()
        env.update({
            "PACKAGE_A_PYTHON": tools["python"],
            "PACKAGE_A_FFMPEG": tools["ffmpeg"],
            "PACKAGE_A_FFPROBE": tools["ffprobe"],
            "PYTHONUNBUFFERED": "1",
        })
        command = [tools["python"], "-B", str(WEB_SCRIPT)]
        try:
            process = subprocess.Popen(
                command,
                cwd=str(PACKAGE_ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log.close()
        _write_state({
            "schema_version": 1,
            "pid": process.pid,
            "port": None,
            "mode": mode,
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "script": str(WEB_SCRIPT.resolve()),
        })

        deadline = time.monotonic() + float(timeout)
        actual_port = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LaunchError("Web 服务提前退出（返回码 %s）；请查看 %s" % (process.returncode, LOG_FILE))
            actual_port = read_port()
            if actual_port and health(actual_port):
                break
            time.sleep(0.1)
        else:
            with contextlib.suppress(OSError):
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            raise LaunchError("Web 服务未在 %.1f 秒内就绪；请查看 %s" % (timeout, LOG_FILE))

        url = "http://127.0.0.1:%d/" % actual_port
        _write_state({
            "schema_version": 1,
            "pid": process.pid,
            "port": actual_port,
            "mode": mode,
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "script": str(WEB_SCRIPT.resolve()),
        })
        if open_browser:
            platform_support.open_browser(url)
        return {"pid": process.pid, "port": actual_port, "url": url, "reused": False}


def stop_service(timeout=5.0):
    state = load_state()
    pid = state.get("pid")
    if not pid or not process_matches(pid):
        return {"stopped": False, "reason": "没有可验证的包 A 服务进程"}
    try:
        group = os.getpgid(int(pid))
        os.killpg(group, signal.SIGTERM)
    except OSError as exc:
        return {"stopped": False, "reason": str(exc)}
    deadline = time.monotonic() + float(timeout)
    alive = True
    while time.monotonic() < deadline:
        alive = process_matches(pid)
        if not alive:
            break
        time.sleep(0.05)
    else:
        with contextlib.suppress(OSError):
            os.killpg(group, signal.SIGKILL)
        second_deadline = time.monotonic() + 1.0
        while time.monotonic() < second_deadline:
            alive = process_matches(pid)
            if not alive:
                break
            time.sleep(0.05)
    stopped = not alive
    if stopped:
        for path in (STATE_FILE, PORT_FILE):
            with contextlib.suppress(OSError):
                path.unlink()
    return {"stopped": stopped, "pid": int(pid)}


def sanitize_report(value, home=None):
    home = Path.home() if home is None else Path(home)
    home_text = str(home)
    if isinstance(value, dict):
        return {str(key): sanitize_report(item, home=home) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_report(item, home=home) for item in value]
    if isinstance(value, str) and home_text and home_text in value:
        return value.replace(home_text, "~")
    return value


def recent_log_lines(path=LOG_FILE, limit=40):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-int(limit):]
    except OSError:
        return []


def _diagnostic_text(report):
    lines = [
        "===== 包 A macOS 诊断报告 =====",
        "生成时间: %s" % report.get("generated_at", ""),
        "模式: %s" % report.get("mode", ""),
        "系统: %s %s" % (report.get("system", ""), report.get("macos_version") or report.get("system_release", "")),
        "架构: %s" % report.get("architecture", ""),
        "预检: %s" % ("通过" if report.get("ok") else "失败"),
        "实际端口: %s" % (report.get("port") or "未运行"),
        "包 B: %s" % report.get("package_b", {}).get("state", "not_installed"),
        "",
        "工具:",
    ]
    for name in ("python", "ffmpeg", "ffprobe"):
        lines.append("- %s: %s" % (name, report.get("tools", {}).get(name, "不可用")))
    lines.append("")
    lines.append("目录:")
    for name, item in report.get("directories", {}).items():
        lines.append("- %s: %s (writable=%s)" % (name, item.get("path"), item.get("writable")))
    if report.get("failures"):
        lines.append("")
        lines.append("失败与恢复:")
        lines.extend("- %s" % item for item in report["failures"])
    if report.get("warnings"):
        lines.append("")
        lines.append("警告:")
        lines.extend("- %s" % item for item in report["warnings"])
    if report.get("recent_service_log"):
        lines.append("")
        lines.append("最近服务日志:")
        lines.extend(report["recent_service_log"])
    lines.append("===== 结束 =====")
    return "\n".join(lines) + "\n"


def write_diagnostics(report, json_path=DIAGNOSTIC_JSON, text_path=DIAGNOSTIC_TEXT):
    sanitized = sanitize_report(report)
    json_path = Path(json_path)
    text_path = Path(text_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path.write_text(_diagnostic_text(sanitized), encoding="utf-8")
    return json_path, text_path


def diagnose(mode="release", explicit_tools=None):
    report = collect_preflight(PACKAGE_ROOT, mode=mode, explicit_tools=explicit_tools)
    running = find_running_service()
    report["port"] = running.get("port") if running else read_port()
    report["service"] = running or {"state": "not_running"}
    report["recent_service_log"] = sanitize_report(recent_log_lines())
    paths_out = write_diagnostics(report)
    return report, paths_out


def _parser():
    parser = argparse.ArgumentParser(description="包 A macOS 启动与诊断")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "preflight", "diagnose"):
        item = subparsers.add_parser(name)
        item.add_argument("--mode", choices=("release", "development"), default="release")
        item.add_argument("--python")
        item.add_argument("--ffmpeg")
        item.add_argument("--ffprobe")
        if name == "start":
            item.add_argument("--no-browser", action="store_true")
    stop = subparsers.add_parser("stop")
    stop.add_argument("--timeout", type=float, default=5.0)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    explicit = {
        name: getattr(args, name, None) for name in ("python", "ffmpeg", "ffprobe")
        if getattr(args, name, None)
    }
    try:
        if args.command == "start":
            result = start_service(args.mode, explicit, not args.no_browser)
            print("包 A 已%s：http://127.0.0.1:%s/" % ("复用" if result["reused"] else "启动", result["port"]))
            return 0
        if args.command == "stop":
            result = stop_service(args.timeout)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("stopped") or result.get("reason") == "没有可验证的包 A 服务进程" else 1
        report, output = diagnose(args.mode, explicit)
        if args.command == "preflight":
            print("预检通过" if report["ok"] else format_failures(report))
        else:
            print("诊断报告：%s\n%s" % output)
        return 0 if report["ok"] else 2
    except Exception as exc:
        print("启动失败：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
