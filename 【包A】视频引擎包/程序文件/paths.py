# -*- coding: utf-8 -*-
"""
统一路径解析模块 —— 让整个包可以解压到任意位置运行。

本文件位置固定为：  <包根>/程序文件/paths.py
所有路径都由此推导，不存在任何硬编码的绝对路径。

语音引擎（Dots.tts）的位置由 config.ini 记录，
用户双击【2】连接语音引擎.bat 时自动写入。
"""
import configparser
import json
import subprocess
import sys
from pathlib import Path
import platform_support

# ---------- 基础目录（全部相对包根推导）----------
PROG_DIR = Path(__file__).resolve().parent          # <包根>/程序文件
APP_ROOT = PROG_DIR.parent                          # <包根>

WEB_DIR      = PROG_DIR / "网站"
ENGINE_DIR   = PROG_DIR / "引擎"
BIN_DIR      = PROG_DIR / "bin"
FONTS_DIR    = PROG_DIR / "fonts"
RUNTIME_DIR  = PROG_DIR / "runtime"
WORK_DIR     = PROG_DIR / "临时文件"
LOG_DIR      = PROG_DIR / "日志"

MATERIAL_DIR = APP_ROOT / "我的素材"
OUTPUT_DIR   = APP_ROOT / "成片"
DEMO_DIR     = APP_ROOT / "示范素材"

CONFIG_FILE  = PROG_DIR / "config.ini"

for _d in (WORK_DIR, LOG_DIR, MATERIAL_DIR, OUTPUT_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


# ---------- config.ini 读写（编码容错：bat 写出的是 GBK）----------
def _read_config():
    c = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        for enc in ("utf-8-sig", "utf-8", "gbk", "mbcs"):
            try:
                c.read_string(CONFIG_FILE.read_text(encoding=enc))
                break
            except Exception:
                continue
    return c


def cfg_get(section, key, default=""):
    c = _read_config()
    try:
        v = c.get(section, key).strip()
        return v if v else default
    except Exception:
        return default


def cfg_set(section, key, value):
    """写回 config.ini（统一 UTF-8，保留其它键）"""
    c = _read_config()
    if not c.has_section(section):
        c.add_section(section)
    c.set(section, key, str(value))
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        c.write(f)


# ---------- 工具链（显式配置 → 随包工具 → PATH → 受控候选）----------
def resolve_python(required=True):
    return platform_support.resolve_python_runtime(
        RUNTIME_DIR,
        explicit=cfg_get("tools", "python", ""),
        required=required,
    )


def resolve_ffmpeg(required=True):
    return platform_support.resolve_ffmpeg(
        BIN_DIR,
        explicit=cfg_get("tools", "ffmpeg", ""),
        required=required,
    )


def resolve_ffprobe(required=True):
    return platform_support.resolve_ffprobe(
        BIN_DIR,
        explicit=cfg_get("tools", "ffprobe", ""),
        required=required,
    )


def _initial_tool(resolver):
    try:
        return resolver(required=True), ""
    except platform_support.ToolResolutionError as exc:
        return "", str(exc)


RUNTIME_PYTHON, RUNTIME_PYTHON_ERROR = _initial_tool(resolve_python)
FFMPEG, FFMPEG_ERROR = _initial_tool(resolve_ffmpeg)
FFPROBE, FFPROBE_ERROR = _initial_tool(resolve_ffprobe)
FONT_CONFIG = platform_support.font_config(FONTS_DIR)
FONTSDIR = FONT_CONFIG["fonts_dir"]
FONTNAME = FONT_CONFIG["font_name"]
FONT_ENV = FONT_CONFIG["environment"]


# ---------- 网页端口 ----------
def web_port(default=8787):
    try:
        return int(cfg_get("server", "port", str(default)))
    except Exception:
        return default


# ---------- 语音引擎（包B / Dots.tts）----------
DOTS_API_VERSION = "dots-tts.synthesize.v1"


def _macos_dots_layout(root):
    root = Path(root)
    python = root / "runtime" / "python" / "bin" / "python3.12"
    launcher = root / "_internal" / "macos_launcher.py"
    required = (
        python,
        launcher,
        root / "pretrained_models" / "dots-tts-mf",
        root / "pretrained_models" / "prompts",
        root / "manifests" / "macos-mf-model.json",
        root / "启动-快速版.command",
    )
    return python, launcher, all(item.exists() for item in required)


def _probe_macos_dots_python(python, runner=None):
    runner = subprocess.run if runner is None else runner
    probe = (
        "import json,platform,sys;"
        "print(json.dumps({'system':platform.system(),'machine':platform.machine(),"
        "'version':[sys.version_info.major,sys.version_info.minor,sys.version_info.micro]}))"
    )
    try:
        result = runner(
            [str(python), "-c", probe], capture_output=True, text=True,
            timeout=10, check=False,
        )
        payload = json.loads(result.stdout.strip()) if result.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        payload = {}
    ok = (
        payload.get("system") == "Darwin"
        and payload.get("machine") == "arm64"
        and payload.get("version", [])[:2] == [3, 12]
    )
    return ok, payload


def dots_info():
    """
    每次调用都重读 config.ini —— 这样用户运行【2】连接语音引擎.bat 之后，
    不需要重启网页服务就能立刻识别到语音引擎。

    返回 dict:
      root       语音引擎根目录 Path 或 None
      python     便携 python.exe 路径 str（未安装则空串）
      prompts    音色库目录 Path（未安装则指向一个不存在的占位路径）
      port       语音引擎网页端口 int
      url        http://127.0.0.1:<port>
      installed  bool  —— 是否检测到可用的语音引擎
    """
    port = 7860
    try:
        port = int(cfg_get("dots", "port", "7860"))
    except Exception:
        pass

    root_s = cfg_get("dots", "root", "")
    root = Path(root_s) if root_s else None

    py = ""
    prompts = PROG_DIR / "_语音引擎未安装"
    installed = False

    launcher = None
    layout = ""
    runtime_probe = {}
    diagnostic = ""
    if platform_support.is_windows() and root and root.exists():
        cand_py = root / "wzf" / "python.exe"
        cand_pr = root / "pretrained_models" / "prompts"
        if cand_py.exists():
            py = str(cand_py)
            installed = True
            layout = "windows-wzf"
        if cand_pr.exists():
            prompts = cand_pr
    elif platform_support.is_darwin() and root and root.exists():
        cand_py, cand_launcher, layout_ok = _macos_dots_layout(root)
        if layout_ok:
            runtime_ok, runtime_probe = _probe_macos_dots_python(cand_py)
            if runtime_ok:
                py = str(cand_py)
                prompts = root / "pretrained_models" / "prompts"
                launcher = cand_launcher
                installed = True
                layout = "macos-arm64-py312"
            else:
                diagnostic = "包 B Python 必须是 Darwin arm64 CPython 3.12"
        else:
            diagnostic = "包 B macOS 布局不完整"

    return {
        "root": root, "python": py, "prompts": prompts,
        "port": port, "url": f"http://127.0.0.1:{port}",
        "installed": installed, "layout": layout,
        "launcher": launcher, "state_file": root / ".runtime" / "state.json" if root else None,
        "api_version": DOTS_API_VERSION, "runtime_probe": runtime_probe,
        "diagnostic": diagnostic,
    }


def dots_installed():
    return dots_info()["installed"]


# ---------- 自动搜盘（供【2】连接语音引擎.bat 调用）----------
def scan_for_dots():
    """在常见位置搜索 Dots.tts 安装目录，返回找到的路径列表（按可信度排序）"""
    if not (platform_support.is_windows() or platform_support.is_darwin()):
        return []
    hits = []

    def _valid(p):
        p = Path(p)
        try:
            if platform_support.is_darwin():
                return _macos_dots_layout(p)[2]
            return (p / "wzf" / "python.exe").exists() and (p / "pretrained_models").exists()
        except OSError:
            return False

    # 1) 包根同级 / 上级目录
    near = [APP_ROOT.parent, APP_ROOT]
    for base in near:
        if _valid(base):
            hits.append(base)
        try:
            for d in base.iterdir():
                if d.is_dir() and _valid(d):
                    hits.append(d)
        except Exception:
            pass

    if platform_support.is_darwin():
        seen, out = set(), []
        for hit in hits:
            key = str(hit.resolve())
            if key not in seen:
                seen.add(key)
                out.append(hit)
        return out

    # 2) 各盘符常见位置
    names = ["DotsTTS", "Dots.tts", "语音引擎包", "语音引擎", "Dots", "dots.tts", "DOTS-TTS"]
    for drive in "DEFGCHIJ":
        try:
            root = Path(f"{drive}:\\")
            if not root.exists():
                continue
        except OSError:
            continue
        for n in names:
            for p in (root / n, root / "TTS" / n, root / "AI" / n):
                try:
                    if p.is_dir() and _valid(p):
                        hits.append(p)
                except Exception:
                    pass
        # 各盘根目录一层扫描
        try:
            for d in root.iterdir():
                if d.is_dir() and _valid(d):
                    hits.append(d)
        except Exception:
            pass

    # 去重保序
    seen, out = set(), []
    for h in hits:
        k = str(h).lower()
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


# ---------- 让 import 更方便 ----------
def enable_imports():
    """把 引擎目录 与 程序文件目录 加入 sys.path"""
    for p in (str(PROG_DIR), str(ENGINE_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


if __name__ == "__main__":
    # 直接运行时打印当前解析结果，供 bat 自检使用
    import json
    d = dots_info()
    print(json.dumps({
        "APP_ROOT": str(APP_ROOT),
        "RUNTIME_PYTHON": RUNTIME_PYTHON,
        "RUNTIME_PYTHON_ERROR": RUNTIME_PYTHON_ERROR,
        "FFMPEG": FFMPEG,
        "FFMPEG_EXISTS": bool(FFMPEG) and Path(FFMPEG).exists(),
        "FFMPEG_ERROR": FFMPEG_ERROR,
        "FFPROBE": FFPROBE,
        "FFPROBE_EXISTS": bool(FFPROBE) and Path(FFPROBE).exists(),
        "FFPROBE_ERROR": FFPROBE_ERROR,
        "FONT_EXISTS": (FONTS_DIR / "simhei.ttf").exists(),
        "WEB_PORT": web_port(),
        "DOTS_ROOT": str(d["root"]) if d["root"] else "",
        "DOTS_INSTALLED": d["installed"],
        "DOTS_PORT": d["port"],
    }, ensure_ascii=False, indent=2))
