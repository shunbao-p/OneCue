# -*- coding: utf-8 -*-
"""包 B 的 Apple Silicon 启动、预检、状态恢复与安全停止入口。

Gradio 仍是唯一业务服务。本模块只管理 Finder 启动边界和进程生命周期，
不定义 Phase 3 的合成 API，也不复制推理实现。
"""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_PATH = Path(__file__).resolve()
RUNTIME_DIR = PACKAGE_ROOT / ".runtime"
STATE_FILE = RUNTIME_DIR / "state.json"
PID_FILE = RUNTIME_DIR / "dots.pid"
LOCK_FILE = RUNTIME_DIR / "launch.lock"
STALE_DIR = RUNTIME_DIR / "stale"
MODEL_MANIFEST = PACKAGE_ROOT / "manifests" / "macos-mf-model.json"
MODEL_MANIFEST_NAMES = {
    "dots-tts-mf": "macos-mf-model.json",
    "dots-tts-soar": "macos-soar-model.json",
}
API_VERSION = "dots-tts.synthesize.v1"
MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024
START_TIMEOUT_SECONDS = 180.0


class LaunchError(RuntimeError):
    """可向普通用户展示的启动失败。"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _run(argv, timeout=15):
    return subprocess.run(
        [str(item) for item in argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _first_line(text) -> str:
    lines = str(text or "").splitlines()
    return lines[0] if lines else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_probe(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".dots-write-", dir=directory, delete=False)
    probe = Path(handle.name)
    try:
        handle.write(b"ok")
        handle.close()
    finally:
        with contextlib.suppress(OSError):
            probe.unlink()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load_state(path: Path = STATE_FILE) -> tuple[dict, str | None]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"状态文件损坏：{exc}"
    if not isinstance(payload, dict):
        return {}, "状态文件不是 JSON 对象"
    return payload, None


def write_state(payload: dict, state_file: Path = STATE_FILE, pid_file: Path = PID_FILE) -> None:
    _atomic_json(Path(state_file), payload)
    pid_file = Path(pid_file)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = pid_file.with_name(f".{pid_file.name}.tmp-{os.getpid()}")
    temporary.write_text(f"{int(payload['pid'])}\n", encoding="ascii")
    os.replace(temporary, pid_file)


def _retire_state(reason: str, state_file: Path = STATE_FILE, pid_file: Path = PID_FILE) -> Path | None:
    state_file = Path(state_file)
    if not state_file.exists():
        with contextlib.suppress(OSError):
            Path(pid_file).unlink()
        return None
    state, parse_error = load_state(state_file)
    stale = dict(state)
    stale.update({"status": "stale", "stale_at": _now(), "stale_reason": parse_error or reason})
    stale_dir = state_file.parent / "stale"
    stale_dir.mkdir(parents=True, exist_ok=True)
    target = stale_dir / f"state-{time.time_ns()}.json"
    _atomic_json(target, stale)
    with contextlib.suppress(OSError):
        state_file.unlink()
    with contextlib.suppress(OSError):
        Path(pid_file).unlink()
    return target


@contextlib.contextmanager
def launch_lock(lock_file: Path = LOCK_FILE):
    lock_file = Path(lock_file)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_file.open("a+", encoding="utf-8")
    try:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        stream.truncate()
        stream.write(f"{os.getpid()}\n")
        stream.flush()
        yield
    finally:
        with contextlib.suppress(Exception):
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def _ps_field(pid: int, field: str) -> str | None:
    env = os.environ.copy()
    # Darwin's plain C locale escapes non-ASCII argv, which breaks identity
    # validation for packages placed below Chinese paths.  A fixed UTF-8
    # locale keeps both the English lstart format and the original argv.
    env.update({"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"})
    result = subprocess.run(
        ["/bin/ps", "-p", str(int(pid)), "-o", f"{field}="],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )
    if result.returncode:
        return None
    value = result.stdout.strip()
    return value or None


def _process_cwd(pid: int) -> str | None:
    proc_cwd = Path(f"/proc/{int(pid)}/cwd")
    if proc_cwd.exists():
        with contextlib.suppress(OSError):
            return str(proc_cwd.resolve())
    lsof = Path("/usr/sbin/lsof")
    if not lsof.exists():
        lsof = Path("/usr/bin/lsof")
    if lsof.exists():
        result = _run([lsof, "-a", "-p", str(int(pid)), "-d", "cwd", "-Fn"])
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("n"):
                    return str(Path(line[1:]).resolve())
    return None


def process_snapshot(pid: int) -> dict | None:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    start_time = _ps_field(pid, "lstart")
    command = _ps_field(pid, "command")
    if not start_time or not command:
        return None
    return {
        "pid": pid,
        "process_start_time": start_time,
        "command_text": command,
        "workdir": _process_cwd(pid),
    }


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def port_owner_pids(port: int) -> set[int]:
    for executable in (Path("/usr/sbin/lsof"), Path("/usr/bin/lsof")):
        if not executable.exists():
            continue
        result = _run([
            executable,
            "-nP",
            f"-iTCP:{int(port)}",
            "-sTCP:LISTEN",
            "-Fp",
        ])
        if result.returncode not in (0, 1):
            continue
        return {
            int(line[1:])
            for line in result.stdout.splitlines()
            if line.startswith("p") and line[1:].isdigit()
        }
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(0.2)
        if sock.connect_ex(("127.0.0.1", int(port))) == 0:
            return {-1}
    return set()


def validate_state_identity(state: dict, *, require_port: bool = False) -> tuple[bool, list[str], dict | None]:
    reasons = []
    required = (
        "pid",
        "process_start_time",
        "command",
        "workdir",
        "port",
        "api_version",
        "model",
        "device",
        "precision",
    )
    missing = [name for name in required if state.get(name) in (None, "", [])]
    if missing:
        return False, ["状态缺少字段：" + "、".join(missing)], None
    snapshot = process_snapshot(state["pid"])
    if snapshot is None:
        return False, ["记录的进程不存在"], None
    if snapshot["process_start_time"] != state["process_start_time"]:
        reasons.append("PID 已被复用或启动时间不一致")
    command = state.get("command")
    if not isinstance(command, list) or not command:
        reasons.append("状态中的命令格式无效")
    else:
        expected_launcher = str(LAUNCHER_PATH.resolve())
        if expected_launcher not in snapshot["command_text"] or "serve" not in snapshot["command_text"]:
            reasons.append("进程命令不是当前包 B 启动器")
        if expected_launcher not in {str(Path(item).resolve()) for item in command if str(item).endswith("macos_launcher.py")}:
            reasons.append("状态命令不属于当前包 B")
    expected_workdir = str(Path(state["workdir"]).resolve())
    if snapshot.get("workdir") != expected_workdir:
        reasons.append("进程工作目录不一致")
    owners = port_owner_pids(int(state["port"]))
    if owners and int(state["pid"]) not in owners:
        reasons.append("监听端口属于其他进程")
    if require_port and int(state["pid"]) not in owners:
        reasons.append("记录进程未监听目标端口")
    return not reasons, reasons, snapshot


def health(port: int, timeout: float = 1.0) -> bool:
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{int(port)}/")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= int(response.status) < 400
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _resolve_model(model: str, root: Path) -> Path:
    models_root = (root / "pretrained_models").resolve()
    candidate = Path(model)
    if not candidate.is_absolute():
        candidate = models_root / model
    candidate = candidate.resolve()
    try:
        candidate.relative_to(models_root)
    except ValueError as exc:
        raise LaunchError("模型必须位于包内 pretrained_models 目录。") from exc
    return candidate


def _load_model_manifest(path: Path = MODEL_MANIFEST) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LaunchError(f"模型清单缺失或损坏：{path}；请重新解压完整开发快照。") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("files"), list):
        raise LaunchError(f"模型清单格式无效：{path}")
    return payload


def model_manifest_path(model_path: Path, root: Path = PACKAGE_ROOT) -> Path:
    try:
        filename = MODEL_MANIFEST_NAMES[Path(model_path).name]
    except KeyError as exc:
        supported = "、".join(sorted(MODEL_MANIFEST_NAMES))
        raise LaunchError(f"模型没有 macOS 验证清单：{Path(model_path).name}；支持：{supported}。") from exc
    return Path(root).resolve() / "manifests" / filename


def verify_model(model_path: Path, manifest_path: Path = MODEL_MANIFEST) -> dict:
    manifest = _load_model_manifest(manifest_path)
    expected_model = manifest.get("model")
    if expected_model != model_path.name:
        raise LaunchError(f"模型清单只允许 {expected_model}，检测到 {model_path.name}。")
    checked = []
    for item in manifest["files"]:
        relative = Path(item["path"])
        path = model_path / relative
        if not path.is_file():
            raise LaunchError(f"模型文件缺失：{path}")
        size = path.stat().st_size
        if size != int(item["size"]):
            raise LaunchError(f"模型文件大小不一致：{path}")
        actual = _sha256(path)
        if actual != item["sha256"]:
            raise LaunchError(f"模型文件 SHA-256 不一致：{path}")
        checked.append(str(relative))
    return {"manifest": str(Path(manifest_path).resolve()), "checked_files": checked}


def collect_preflight(
    *,
    model: str,
    device: str,
    precision: str,
    port: int,
    root: Path = PACKAGE_ROOT,
    min_free_bytes: int = MIN_FREE_BYTES,
    require_bundled_python: bool = True,
    import_modules: tuple[str, ...] = (
        "torch",
        "torchaudio",
        "transformers",
        "gradio",
        "numpy",
        "soundfile",
        "librosa",
    ),
) -> dict:
    root = Path(root).resolve()
    report = {
        "schema_version": 1,
        "generated_at": _now(),
        "package_root": str(root),
        "system": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "requested": {"model": model, "device": device, "precision": precision, "port": int(port)},
        "checks": {},
        "failures": [],
    }
    failures = report["failures"]
    if report["system"] != "Darwin":
        failures.append(f"需要 macOS（Darwin），检测到 {report['system']}")
    if report["architecture"].lower() not in {"arm64", "aarch64"}:
        failures.append(f"需要 Apple Silicon arm64，检测到 {report['architecture']}")
    if sys.version_info[:2] != (3, 12):
        failures.append(f"需要包内 Python 3.12，检测到 {report['python']}")
    bundled_python_root = (root / "runtime" / "python").resolve()
    try:
        Path(sys.executable).resolve().relative_to(bundled_python_root)
        python_is_bundled = True
    except ValueError:
        python_is_bundled = False
    report["checks"]["bundled_python"] = {
        "ok": python_is_bundled,
        "executable": str(Path(sys.executable).resolve()),
        "expected_root": str(bundled_python_root),
    }
    if require_bundled_python and not python_is_bundled:
        failures.append("当前 Python 不在包内 runtime/python；请从 .command 启动完整开发快照。")

    imported = {}
    for name in import_modules:
        try:
            module = __import__(name)
            imported[name] = getattr(module, "__version__", "unknown")
        except Exception as exc:
            failures.append(f"依赖无法导入：{name}（{exc}）")
    report["checks"]["imports"] = imported

    if "torch" in imported:
        import torch

        mps = getattr(getattr(torch, "backends", None), "mps", None)
        built = bool(mps and mps.is_built())
        available = bool(mps and mps.is_available())
        report["checks"]["mps"] = {"built": built, "available": available}
        if device in {"auto", "mps"} and not (built and available):
            failures.append("PyTorch MPS 不可用；请确认在 Apple Silicon 原生终端中启动。")
        if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
            failures.append("检测到 PYTORCH_ENABLE_MPS_FALLBACK=1；正式启动拒绝 CPU fallback。")
        try:
            src_root = root / "src"
            if str(src_root) not in sys.path:
                sys.path.insert(0, str(src_root))
            from dots_tts.runtime_device import resolve_runtime_device_policy

            policy = resolve_runtime_device_policy(
                torch,
                requested_device=device,
                requested_precision=precision,
                optimize=False,
            )
            report["checks"]["runtime_policy"] = policy.as_dict()
            if device in {"auto", "mps"} and policy.actual_device != "mps":
                failures.append(f"设备策略未选择原生 MPS，实际为 {policy.actual_device}。")
        except Exception as exc:
            failures.append(f"设备/精度策略不受支持：{exc}")

    model_path = _resolve_model(model, root)
    report["model_path"] = str(model_path)
    try:
        report["checks"]["model_manifest"] = verify_model(
            model_path, model_manifest_path(model_path, root)
        )
    except Exception as exc:
        failures.append(str(exc))

    try:
        src_root = root / "src"
        if str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))
        from dots_tts.external_tools import resolve_external_tool

        ffmpeg = resolve_external_tool("ffmpeg", package_root=root, required=True)
        ffprobe = resolve_external_tool("ffprobe", package_root=root, required=True)
        report["checks"]["tools"] = {
            "ffmpeg": ffmpeg.as_dict(),
            "ffprobe": ffprobe.as_dict(),
        }
    except Exception as exc:
        failures.append(f"音频工具检查失败：{exc}")

    directory_results = {}
    for name in (".runtime", "logs", "outputs", "tmp"):
        directory = root / name
        try:
            _write_probe(directory)
            directory_results[name] = {"path": str(directory), "writable": True}
        except Exception as exc:
            directory_results[name] = {"path": str(directory), "writable": False, "error": str(exc)}
            failures.append(f"目录不可写：{directory}（{exc}）")
    report["checks"]["directories"] = directory_results

    try:
        free = shutil.disk_usage(root).free
        report["checks"]["disk"] = {"free_bytes": free, "minimum_bytes": int(min_free_bytes)}
        if free < int(min_free_bytes):
            failures.append(f"磁盘空间不足：可用 {free} 字节，至少需要 {int(min_free_bytes)} 字节。")
    except OSError as exc:
        failures.append(f"无法检查磁盘空间：{exc}")

    owners = port_owner_pids(int(port))
    report["checks"]["port"] = {"port": int(port), "owner_pids": sorted(owners)}
    if owners:
        failures.append(f"端口 {int(port)} 已被占用；请停止占用程序或指定其他端口。")
    report["ok"] = not failures
    return report


def _format_preflight_failure(report: dict) -> str:
    lines = ["启动前检查未通过，尚未加载模型："]
    lines.extend(f"- {item}" for item in report.get("failures", []))
    lines.append("恢复方法：按提示修复后重试；文件异常时重新解压完整 macOS 开发快照。")
    return "\n".join(lines)


def _service_command(args) -> list[str]:
    return [
        sys.executable,
        "-B",
        str(LAUNCHER_PATH),
        "serve",
        "--model",
        args.model,
        "--device",
        args.device,
        "--precision",
        args.precision,
        "--port",
        str(args.port),
        "--log-file",
        str(Path(args.log_file).resolve()),
    ]


def _open_browser(port: int) -> None:
    if platform.system() == "Darwin" and Path("/usr/bin/open").exists():
        subprocess.Popen(
            ["/usr/bin/open", f"http://127.0.0.1:{int(port)}/"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def query_service(*, reclaim: bool = True) -> dict:
    state, parse_error = load_state()
    if parse_error:
        stale_path = _retire_state(parse_error) if reclaim else None
        return {"running": False, "stale": True, "reason": parse_error, "stale_path": str(stale_path or "")}
    if not state:
        return {"running": False, "stale": False, "reason": "没有状态文件"}
    ok, reasons, _ = validate_state_identity(state, require_port=state.get("status") == "ready")
    if not ok:
        stale_path = _retire_state("；".join(reasons)) if reclaim else None
        return {
            "running": False,
            "stale": True,
            "reason": "；".join(reasons),
            "stale_path": str(stale_path or ""),
        }
    ready = health(int(state["port"]))
    return {"running": True, "ready": ready, "state": state}


def start_service(args) -> dict:
    with launch_lock():
        current = query_service(reclaim=True)
        if current.get("running"):
            state = current["state"]
            if args.open_browser and current.get("ready"):
                _open_browser(state["port"])
            return {"reused": True, "ready": current.get("ready", False), "state": state}

        report = collect_preflight(
            model=args.model,
            device=args.device,
            precision=args.precision,
            port=args.port,
        )
        if not report["ok"]:
            raise LaunchError(_format_preflight_failure(report))

        log_path = Path(args.log_file).resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        console_log_path = log_path.with_name(f"{log_path.stem}-console{log_path.suffix}")
        command = _service_command(args)
        env = os.environ.copy()
        env.update({
            "HF_HOME": str(PACKAGE_ROOT / "hf_download"),
            "TRANSFORMERS_CACHE": str(PACKAGE_ROOT / "tf_download"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "GRADIO_ANALYTICS_ENABLED": "False",
            "GRADIO_TEMP_DIR": str(PACKAGE_ROOT / "tmp"),
            "NO_PROXY": "localhost,127.0.0.1,::1",
            "no_proxy": "localhost,127.0.0.1,::1",
            "PYTHONUNBUFFERED": "1",
        })
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env.pop(key, None)
        stream = console_log_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(PACKAGE_ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            stream.close()

        snapshot = None
        for _ in range(40):
            snapshot = process_snapshot(process.pid)
            if snapshot:
                break
            if process.poll() is not None:
                break
            time.sleep(0.025)
        if snapshot is None:
            raise LaunchError(f"服务进程未能建立可验证身份；请查看 {log_path}")

        state = {
            "schema_version": 1,
            "status": "starting",
            "pid": process.pid,
            "process_start_time": snapshot["process_start_time"],
            "command": command,
            "workdir": str(PACKAGE_ROOT.resolve()),
            "port": int(args.port),
            "api_version": API_VERSION,
            "model": args.model,
            "device": args.device,
            "precision": args.precision,
            "log_file": str(log_path),
            "console_log_file": str(console_log_path),
            "started_at": _now(),
        }
        write_state(state)

    # Do not hold the single-instance lock while importing Gradio or loading a
    # model. A concurrent start will reuse the verified ``starting`` state,
    # while status/stop remain responsive.
    deadline = time.monotonic() + float(args.timeout)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _retire_state(f"服务提前退出，返回码 {process.returncode}")
            raise LaunchError(f"服务提前退出（返回码 {process.returncode}）；请查看 {log_path}")
        if health(args.port):
            state.update({"status": "ready", "ready_at": _now()})
            write_state(state)
            if args.open_browser:
                _open_browser(args.port)
            return {"reused": False, "ready": True, "state": state}
        time.sleep(0.25)

    ok, _, _ = validate_state_identity(state, require_port=False)
    if ok:
        with contextlib.suppress(OSError):
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        shutdown_deadline = time.monotonic() + 5.0
        while time.monotonic() < shutdown_deadline and _pid_alive(process.pid):
            time.sleep(0.1)
        if _pid_alive(process.pid):
            still_same, _, _ = validate_state_identity(state, require_port=False)
            if still_same:
                with contextlib.suppress(OSError):
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    _retire_state("服务启动超时")
    raise LaunchError(f"服务未在 {args.timeout:.0f} 秒内就绪；请查看 {log_path}")


def _cleanup_own_state() -> None:
    state, _ = load_state()
    if state.get("pid") != os.getpid():
        return
    snapshot = process_snapshot(os.getpid())
    if snapshot and snapshot["process_start_time"] == state.get("process_start_time"):
        with contextlib.suppress(OSError):
            STATE_FILE.unlink()
        with contextlib.suppress(OSError):
            PID_FILE.unlink()


def serve(args) -> int:
    def _exit_from_signal(signum, _frame):
        raise SystemExit(128 + int(signum))

    signal.signal(signal.SIGTERM, _exit_from_signal)
    signal.signal(signal.SIGINT, _exit_from_signal)
    model_path = _resolve_model(args.model, PACKAGE_ROOT)
    src_root = PACKAGE_ROOT / "src"
    for item in (PACKAGE_ROOT, src_root):
        if str(item) not in sys.path:
            sys.path.insert(0, str(item))
    from apps.gradio.service import recommended_num_steps_for_model

    default_num_steps = recommended_num_steps_for_model(
        str(model_path),
        repo_root=PACKAGE_ROOT,
    )
    sys.argv = [
        str(LAUNCHER_PATH),
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--execution-mode",
        "generate",
        "--device",
        args.device,
        "--precision",
        args.precision,
        "--model-name-or-path",
        str(model_path),
        "--output-dir",
        str(PACKAGE_ROOT / "outputs"),
        "--log-file",
        str(Path(args.log_file).resolve()),
        "--default-prompt-name",
        "女播音",
        "--default-num-steps",
        str(default_num_steps),
        "--skip-warmup",
        "--no-browser",
    ]
    try:
        from apps.gradio.app import main as gradio_main

        gradio_main()
        return 0
    finally:
        _cleanup_own_state()


def stop_service(timeout: float = 8.0) -> dict:
    with launch_lock():
        state, parse_error = load_state()
        if parse_error:
            stale = _retire_state(parse_error)
            return {"stopped": False, "stale": True, "reason": parse_error, "stale_path": str(stale or "")}
        if not state:
            return {"stopped": False, "reason": "没有正在运行的包 B 服务"}
        ok, reasons, _ = validate_state_identity(state, require_port=state.get("status") == "ready")
        if not ok:
            stale = _retire_state("；".join(reasons))
            return {
                "stopped": False,
                "stale": True,
                "reason": "身份校验失败，未发送信号：" + "；".join(reasons),
                "stale_path": str(stale or ""),
            }
        pid = int(state["pid"])
        group = os.getpgid(pid)
        os.killpg(group, signal.SIGTERM)

    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    else:
        state_now, _ = load_state()
        ok, _, _ = validate_state_identity(state_now, require_port=False)
        if ok and int(state_now["pid"]) == pid:
            with contextlib.suppress(OSError):
                os.killpg(group, signal.SIGKILL)
        second_deadline = time.monotonic() + 1.0
        while time.monotonic() < second_deadline and _pid_alive(pid):
            time.sleep(0.05)

    stopped = not _pid_alive(pid)
    if stopped:
        with contextlib.suppress(OSError):
            STATE_FILE.unlink()
        with contextlib.suppress(OSError):
            PID_FILE.unlink()
    return {"stopped": stopped, "pid": pid, "port": int(state["port"])}


def _add_runtime_arguments(parser, *, include_timeout: bool = False) -> None:
    parser.add_argument("--model", default="dots-tts-mf")
    parser.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    parser.add_argument(
        "--precision",
        choices=("auto", "float32", "float16", "bfloat16"),
        default="auto",
    )
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--log-file", default=str(PACKAGE_ROOT / "logs" / "gradio.log"))
    if include_timeout:
        parser.add_argument("--timeout", type=float, default=START_TIMEOUT_SECONDS)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="包 B Apple Silicon macOS 启动与状态管理")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    _add_runtime_arguments(start, include_timeout=True)
    start.add_argument("--no-browser", dest="open_browser", action="store_false")
    start.set_defaults(open_browser=True)
    serve_parser = commands.add_parser("serve")
    _add_runtime_arguments(serve_parser)
    preflight = commands.add_parser("preflight")
    _add_runtime_arguments(preflight)
    commands.add_parser("status")
    stop = commands.add_parser("stop")
    stop.add_argument("--timeout", type=float, default=8.0)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "start":
            result = start_service(args)
            state = result["state"]
            label = "复用" if result["reused"] else "启动"
            print(f"包 B 已{label}：http://127.0.0.1:{state['port']}/")
            return 0
        if args.command == "serve":
            return serve(args)
        if args.command == "status":
            result = query_service(reclaim=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("running") else 3
        if args.command == "stop":
            result = stop_service(args.timeout)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("stopped") or result.get("reason") == "没有正在运行的包 B 服务" else 4
        report = collect_preflight(
            model=args.model,
            device=args.device,
            precision=args.precision,
            port=args.port,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2
    except LaunchError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"启动失败：未预期错误（{type(exc).__name__}: {exc}）", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
