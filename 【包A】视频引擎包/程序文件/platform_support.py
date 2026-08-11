# -*- coding: utf-8 -*-
"""包 A 的薄平台边界。

这里只处理系统识别、工具发现、字体环境和系统命令构造。视频、Web、TTS
状态与业务规则必须留在原模块中。所有外部命令均以参数数组表示，不拼接 shell。
"""

import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


WINDOWS_FONTCONFIG_PATH = "C:/Windows/Fonts"


class ToolResolutionError(RuntimeError):
    """工具配置无效或所有候选均不可用。"""

    def __init__(self, tool, checked, reason="未找到可执行文件"):
        self.tool = tool
        self.checked = [str(item) for item in checked]
        detail = "；已检查：" + "，".join(self.checked) if self.checked else ""
        super().__init__(f"{tool}：{reason}{detail}")


def current_system(system=None, release=None):
    """返回 ``windows``、``darwin`` 或其它小写系统名；WSL 视为 Windows 开发宿主。"""
    raw = str(platform.system() if system is None else system).strip().lower()
    if release is None:
        release = platform.release() if system is None else ""
    rel = str(release).lower()
    if raw == "linux" and "microsoft" in rel:
        return "windows"
    if raw.startswith("win"):
        return "windows"
    if raw == "darwin":
        return "darwin"
    return raw or "unknown"


def is_windows(system=None, release=None):
    return current_system(system, release) == "windows"


def is_darwin(system=None, release=None):
    return current_system(system, release) == "darwin"


def _configured_value(explicit, env, env_vars):
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip(), "显式配置"
    for key in env_vars:
        value = str(env.get(key, "")).strip()
        if value:
            return value, f"环境变量 {key}"
    return "", ""


def _usable_file(candidate, system):
    path = Path(candidate).expanduser()
    try:
        if not path.is_file():
            return False
        return is_windows(system) or os.access(str(path), os.X_OK)
    except OSError:
        return False


def _normal_path(candidate):
    return str(Path(candidate).expanduser().resolve())


def resolve_executable(
    tool,
    *,
    explicit=None,
    env_vars=(),
    bundled_paths=(),
    path_names=(),
    controlled_paths=(),
    env=None,
    system=None,
    which=None,
    required=False,
):
    """按“显式配置 → 随包工具 → PATH → 受控候选”解析工具。"""
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    configured, source = _configured_value(explicit, env, env_vars)
    checked = []

    if configured:
        checked.append(configured)
        is_path = "/" in configured or "\\" in configured
        found = None if is_path else which(configured)
        candidate = found or configured
        if _usable_file(candidate, system):
            return _normal_path(candidate)
        raise ToolResolutionError(tool, checked, f"{source}不可用")

    seen = set()
    for candidate in bundled_paths:
        value = str(candidate)
        if not value or value in seen:
            continue
        seen.add(value)
        checked.append(value)
        if _usable_file(value, system):
            return _normal_path(value)

    for name in path_names:
        checked.append(f"PATH:{name}")
        found = which(name)
        if found and _usable_file(found, system):
            return _normal_path(found)

    for candidate in controlled_paths:
        value = str(candidate)
        if not value or value in seen:
            continue
        seen.add(value)
        checked.append(value)
        if _usable_file(value, system):
            return _normal_path(value)

    if required:
        raise ToolResolutionError(tool, checked)
    return ""


def _darwin_tool_candidates(name):
    return [
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
        Path("/usr/bin") / name,
    ]


def resolve_ffmpeg(
    bin_dir,
    *,
    explicit=None,
    env=None,
    system=None,
    which=None,
    required=False,
):
    suffix = ".exe" if is_windows(system) else ""
    return resolve_executable(
        "ffmpeg",
        explicit=explicit,
        env_vars=("PACKAGE_A_FFMPEG", "KT_FFMPEG_PATH"),
        bundled_paths=(Path(bin_dir) / f"ffmpeg{suffix}",),
        path_names=(f"ffmpeg{suffix}", "ffmpeg"),
        controlled_paths=_darwin_tool_candidates("ffmpeg") if is_darwin(system) else (),
        env=env,
        system=system,
        which=which,
        required=required,
    )


def resolve_ffprobe(
    bin_dir,
    *,
    explicit=None,
    env=None,
    system=None,
    which=None,
    required=False,
):
    suffix = ".exe" if is_windows(system) else ""
    return resolve_executable(
        "ffprobe",
        explicit=explicit,
        env_vars=("PACKAGE_A_FFPROBE", "KT_FFPROBE_PATH"),
        bundled_paths=(Path(bin_dir) / f"ffprobe{suffix}",),
        path_names=(f"ffprobe{suffix}", "ffprobe"),
        controlled_paths=_darwin_tool_candidates("ffprobe") if is_darwin(system) else (),
        env=env,
        system=system,
        which=which,
        required=required,
    )


def resolve_python_runtime(
    runtime_dir,
    *,
    explicit=None,
    development=False,
    executable=None,
    env=None,
    system=None,
    which=None,
    required=False,
):
    executable = executable or sys.executable
    runtime_dir = Path(runtime_dir)
    if is_windows(system):
        bundled = [runtime_dir / "python.exe"]
    else:
        bundled = [runtime_dir / "bin" / "python3", runtime_dir / "python3"]
    if development and executable:
        bundled.insert(0, Path(executable))
    controlled = [Path("/usr/bin/python3")] if is_darwin(system) else []
    return resolve_executable(
        "python",
        explicit=explicit,
        env_vars=("PACKAGE_A_PYTHON", "KT_PYTHON_PATH"),
        bundled_paths=bundled,
        path_names=("python.exe", "python3", "python"),
        controlled_paths=controlled,
        env=env,
        system=system,
        which=which,
        required=required,
    )


def font_config(fonts_dir, *, explicit=None, env=None, system=None):
    """返回包内字体优先的候选、字体名和 FFmpeg 环境；Darwin 不注入 Windows 配置。"""
    env = os.environ if env is None else env
    configured, _source = _configured_value(
        explicit, env, ("PACKAGE_A_FONT_DIR", "KT_FONT_DIR")
    )
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path(fonts_dir))
    if is_windows(system):
        windows_dir = env.get("WINDIR") or env.get("SystemRoot")
        if windows_dir:
            candidates.append(Path(windows_dir) / "Fonts")
        candidates.append(Path(WINDOWS_FONTCONFIG_PATH))

    selected = Path(fonts_dir)
    for candidate in candidates:
        if (candidate / "simhei.ttf").is_file():
            selected = candidate
            break
    environment = {}
    if is_windows(system):
        environment["FONTCONFIG_PATH"] = WINDOWS_FONTCONFIG_PATH
    return {
        "fonts_dir": str(selected),
        "font_name": "SimHei",
        "font_file": "simhei.ttf",
        "candidates": [str(item) for item in candidates],
        "environment": environment,
    }


def build_open_command(target, select=False, system=None):
    """生成文件管理器参数数组；项目目录越界校验仍由 Web 层负责。"""
    target = str(Path(target))
    if is_windows(system):
        return ["explorer", f"/select,{target}"] if select else ["explorer", target]
    if is_darwin(system):
        return ["/usr/bin/open", "-R", target] if select else ["/usr/bin/open", target]
    return ["xdg-open", target]


def open_in_file_manager(target, select=False, system=None, popen=None):
    popen = subprocess.Popen if popen is None else popen
    return popen(build_open_command(target, select=select, system=system))


def open_browser(url, opener=None):
    opener = webbrowser.open if opener is None else opener
    return opener(str(url))


def iter_ports(base_port, max_tries=20):
    base_port = int(base_port)
    max_tries = int(max_tries)
    if not 1 <= base_port <= 65535 or max_tries < 1:
        raise ValueError("端口必须在 1..65535，尝试次数必须大于 0")
    for port in range(base_port, min(65536, base_port + max_tries)):
        yield port


def listener_diagnostic_command(port, system=None):
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1..65535")
    if is_windows(system):
        return ["netstat", "-ano"]
    if is_darwin(system):
        return ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"]
    return ["ss", "-ltnp", f"sport = :{port}"]


def process_termination_command(pid, force=False, system=None):
    pid = int(pid)
    if pid <= 0:
        raise ValueError("pid 必须大于 0")
    if is_windows(system):
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        return command
    return ["kill", "-KILL" if force else "-TERM", str(pid)]


def _tool_diagnostic(resolver, *args, **kwargs):
    try:
        path = resolver(*args, required=True, **kwargs)
        return {"available": True, "path": path, "error": ""}
    except ToolResolutionError as exc:
        return {"available": False, "path": "", "error": str(exc)}


def runtime_diagnostics(
    program_dir,
    fonts_dir,
    *,
    explicit_tools=None,
    env=None,
    system=None,
    which=None,
):
    """返回可序列化诊断数据，不执行外部工具或修改文件。"""
    program_dir = Path(program_dir)
    normalized = current_system(system)
    explicit_tools = explicit_tools or {}
    return {
        "system": normalized,
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "tools": {
            "python": _tool_diagnostic(
                resolve_python_runtime,
                program_dir / "runtime",
                explicit=explicit_tools.get("python"),
                env=env,
                system=normalized,
                which=which,
            ),
            "ffmpeg": _tool_diagnostic(
                resolve_ffmpeg,
                program_dir / "bin",
                explicit=explicit_tools.get("ffmpeg"),
                env=env,
                system=normalized,
                which=which,
            ),
            "ffprobe": _tool_diagnostic(
                resolve_ffprobe,
                program_dir / "bin",
                explicit=explicit_tools.get("ffprobe"),
                env=env,
                system=normalized,
                which=which,
            ),
        },
        "font": font_config(fonts_dir, env=env, system=normalized),
    }
