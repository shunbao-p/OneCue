# -*- coding: utf-8 -*-
"""
本地视频生成 Web 服务（无第三方依赖，纯 stdlib）
- GET  /            -> index.html
- POST /api/generate -> 接收 wav(base64)+txt，启动生成任务，返回 job_id
- GET  /api/events?job=<id> -> SSE 实时进度（pct / 速度 / 剩余 / 日志）
- GET  /api/download/<job>  -> 下载成品 mp4

运行：  python kt_web.py   （默认端口 8787，占用则自动顺延）
"""
import sys, os, json, uuid, base64, binascii, threading, shutil, subprocess, time, urllib.request
from pathlib import Path, PureWindowsPath
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as _ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

# 强制 stdout/stderr 为 UTF-8，避免 Windows GBK 控制台下打印中文/emoji 报 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 路径统一由 程序文件/paths.py 解析：整个包可解压到任意位置，无任何硬编码绝对路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paths
paths.enable_imports()
import kt_video
import platform_support
import dots_control

ROOT = paths.APP_ROOT
PORT = paths.web_port()
PRODUCTION_HOST = "0.0.0.0"
SSE_HEARTBEAT_SECONDS = 10.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MAX_REQUEST_BYTES = 256 * 1024 * 1024
TERMINAL_STATUSES = frozenset(("done", "error", "stopped"))
ACTIVE_MARKER = ".package-a-active"


def parse_json_object(raw):
    """Decode one JSON request body and require an object payload."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("请求 JSON 格式无效") from exc
    if not isinstance(payload, dict):
        raise ValueError("请求 JSON 必须是对象")
    return payload


def safe_upload_name(value, default, suffix, field):
    """仅允许一个普通文件名，同时拒绝 POSIX/Windows 路径语义。"""
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ValueError(f"{field} 文件名必须是字符串")
    name = unicodedata.normalize("NFC", value)
    if not name or name != name.strip():
        raise ValueError(f"{field} 文件名不能为空或包含首尾空白")
    if len(name.encode("utf-8")) > 240:
        raise ValueError(f"{field} 文件名过长")
    if name in (".", "..") or "/" in name or "\\" in name or ":" in name:
        raise ValueError(f"{field} 文件名不得包含路径")
    if Path(name).is_absolute() or PureWindowsPath(name).is_absolute():
        raise ValueError(f"{field} 文件名不得是绝对路径")
    if Path(name).name != name or PureWindowsPath(name).name != name:
        raise ValueError(f"{field} 文件名必须是 basename")
    if any(unicodedata.category(char).startswith("C") for char in name):
        raise ValueError(f"{field} 文件名不得包含控制字符")
    if Path(name).suffix.lower() != suffix:
        raise ValueError(f"{field} 文件名必须以 {suffix} 结尾")
    return name


def validate_upload_names(opts):
    checked = dict(opts)
    checked["wav_name"] = safe_upload_name(
        checked.get("wav_name"), "audio.wav", ".wav", "wav_name"
    )
    checked["txt_name"] = safe_upload_name(
        checked.get("txt_name"), "text.txt", ".txt", "txt_name"
    )
    return checked


def resolve_upload_target(work_dir, name, suffix):
    """写入前确认最终目标仍是非链接任务目录的直接子文件。"""
    root = Path(work_dir)
    if root.is_symlink():
        raise ValueError("任务目录不得是符号链接")
    root = root.resolve(strict=True)
    checked = safe_upload_name(name, "", suffix, "上传")
    target = root / checked
    if target.is_symlink():
        raise ValueError("上传目标不得是符号链接")
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("上传目标越出当前任务目录") from exc
    if resolved.parent != root:
        raise ValueError("上传目标必须直接位于当前任务目录")
    return resolved


class ThreadingHTTPServer(_ThreadingHTTPServer):
    """Threaded server with exclusive binds so repeated starts reliably fall forward."""

    allow_reuse_address = False
    daemon_threads = True
WEB_DIR = Path(__file__).parent
WORK = paths.WORK_DIR
OUTDIR = paths.OUTPUT_DIR
WORK.mkdir(parents=True, exist_ok=True)
OUTDIR.mkdir(parents=True, exist_ok=True)

# ---- 启动时自动清理旧缓存（保留最近 5 个任务目录，删 24h 前的）----
def cleanup_old_jobs():
    import time as _t
    now = _t.time()
    dirs = sorted(WORK.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in dirs[5:]:  # 跳过最新 5 个
        try:
            if (d / ACTIVE_MARKER).exists():
                continue
            age = now - d.stat().st_mtime
            if age > 3600:  # 超过 1 小时的删掉
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass

# ---- 语音引擎（包B / Dots.tts）：位置由 config.ini 记录，每次调用重读 ----
DOTS_SYNTH = WEB_DIR / "dots_synth.py"

def _dots():
    """每次调用重读配置 —— 用户运行【2】连接语音引擎.bat 后无需重启网页即可生效"""
    return paths.dots_info()


def load_voices():
    """扫描 prompts 目录下的全部音频文件，得到 {文件名: {prompt_wav, prompt_text}}。
    与原 7860 接口下拉一致：目录里有什么音频就显示什么音色（含 .m4a 样本）。"""
    ref_map = {}
    DOTS_PROMPTS = _dots()["prompts"]
    f = DOTS_PROMPTS / "prompt_text"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            name, txt = line.split("|", 1)
            ref_map[name.strip()] = txt.strip()
    voices = {}
    if DOTS_PROMPTS.exists():
        for af in sorted(DOTS_PROMPTS.iterdir()):
            if af.suffix.lower() in (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"):
                # 转写优先读 prompt_text；没有则用文件名（去扩展名）兜底（DOTS m4a 样本设计）
                txt = ref_map.get(af.stem, "") or af.stem
                voices[af.name] = {
                    "prompt_wav": str(af),
                    "prompt_text": txt,
                }
    return voices

jobs = {}          # job_id -> 任务状态、事件历史、停止信号和当前子进程
jobs_lock = threading.Lock()


def create_job(kind="video"):
    """Create an isolated task record and return its opaque id."""
    job_id = uuid.uuid4().hex
    condition = threading.Condition(threading.RLock())
    now = time.time()
    with jobs_lock:
        jobs[job_id] = {
            "kind": str(kind),
            "condition": condition,
            "events": [],
            "next_seq": 1,
            "status": "running",
            "out": "",
            "proc": None,
            "worker": None,
            "stop_event": threading.Event(),
            "created_at": now,
            "updated_at": now,
        }
    return job_id


def _job(job_id):
    with jobs_lock:
        return jobs.get(job_id)


def _append_event_locked(job, obj):
    item = dict(obj)
    item.setdefault("seq", job.get("next_seq", 1))
    job["next_seq"] = int(item["seq"]) + 1
    job.setdefault("events", []).append(item)
    if len(job["events"]) > 512:
        del job["events"][:-512]
    job["updated_at"] = time.time()
    return item


def push(job_id, obj):
    """Publish one event to all current/future SSE readers."""
    job = _job(job_id)
    if not job:
        return False
    condition = job.get("condition")
    if condition is None:  # Phase 0 legacy contract records
        job["queue"].put(dict(obj))
        return True
    with condition:
        _append_event_locked(job, obj)
        condition.notify_all()
    return True


def finish_job(job_id, status, event, out=None):
    """Atomically publish exactly one terminal state/event."""
    if status not in TERMINAL_STATUSES:
        raise ValueError("终态必须是 done、error 或 stopped")
    job = _job(job_id)
    if not job:
        return False
    condition = job.get("condition")
    if condition is None:
        if job.get("status") in TERMINAL_STATUSES:
            return False
        job["status"] = status
        if out is not None:
            job["out"] = str(out)
        job["queue"].put(dict(event))
        return True
    with condition:
        if job.get("status") in TERMINAL_STATUSES:
            return False
        if job.get("status") == "stopping" and status != "stopped":
            return False
        job["status"] = status
        if out is not None:
            job["out"] = str(out)
        _append_event_locked(job, event)
        condition.notify_all()
    return True


def request_job_stop(job_id):
    """Atomically claim a running task for stop; completed work wins if already terminal."""
    job = _job(job_id)
    if not job:
        return False
    condition = job.get("condition")
    if condition is None:
        if job.get("status") in TERMINAL_STATUSES:
            return False
        job["stop_requested"] = True
        job["status"] = "stopping"
        return True
    with condition:
        if job.get("status") in TERMINAL_STATUSES or job.get("status") == "stopping":
            return False
        job["status"] = "stopping"
        job["stop_event"].set()
        job["updated_at"] = time.time()
        condition.notify_all()
    return True


def set_job_output(job_id, path, status=None):
    job = _job(job_id)
    if not job:
        return False
    condition = job.get("condition")
    lock = condition if condition is not None else jobs_lock
    with lock:
        job["out"] = str(path)
        if status is not None:
            job["status"] = status
        job["updated_at"] = time.time()
    return True


def register_job_process(job_id, proc):
    job = _job(job_id)
    if not job:
        return False
    condition = job.get("condition")
    lock = condition if condition is not None else jobs_lock
    with lock:
        job["proc"] = proc
        job["updated_at"] = time.time()
    return True


def register_job_worker(job_id, worker):
    job = _job(job_id)
    if not job:
        return False
    condition = job.get("condition")
    lock = condition if condition is not None else jobs_lock
    with lock:
        job["worker"] = worker
    return True


def job_stop_requested(job_id):
    job = _job(job_id)
    if not job:
        return True
    event = job.get("stop_event")
    return event.is_set() if event is not None else bool(job.get("stop_requested"))


def job_snapshot(job_id):
    job = _job(job_id)
    if not job:
        return None
    condition = job.get("condition")
    lock = condition if condition is not None else jobs_lock
    with lock:
        events = job.get("events", [])
        return {
            "job_id": job_id,
            "kind": job.get("kind", "video"),
            "status": job.get("status", "unknown"),
            "output_name": Path(job["out"]).name if job.get("out") else "",
            "last_event": dict(events[-1]) if events else None,
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }


def job_event_snapshot(job_id, after=0):
    job = _job(job_id)
    if not job:
        return []
    condition = job.get("condition")
    if condition is None:
        return []
    with condition:
        return [dict(item) for item in job.get("events", []) if item.get("seq", 0) > after]


def wait_for_terminal(job_id, timeout=10):
    job = _job(job_id)
    if not job:
        return False
    condition = job.get("condition")
    if condition is None:
        return job.get("status") in TERMINAL_STATUSES
    deadline = time.monotonic() + timeout
    with condition:
        while job.get("status") not in TERMINAL_STATUSES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            condition.wait(remaining)
        return True


def terminate_job_process(job_id, timeout=3.0):
    job = _job(job_id)
    proc = job.get("proc") if job else None
    if proc is None:
        return False
    try:
        if proc.poll() is not None:
            return False
    except Exception:
        return False
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    try:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=max(0.1, 4.5 - timeout))
        return True
    except Exception:
        return False


def valid_mp4(path):
    """成品有效性校验：必须有 mdat（真实视频帧数据），否则是 262 字节空片。
    小文件全扫，大文件扫前 512KB（mdat 通常在 moov 之后，可能超过 8KB）。"""
    try:
        sz = path.stat().st_size
        if sz < 1000:  # 小于 1KB 肯定是空片
            return False
        with open(path, "rb") as f:
            # 小文件全扫，大文件扫前 512KB
            read_size = min(sz, 524288)
            data = f.read(read_size)
        return b"mdat" in data
    except Exception:
        return False


def parse_multipart(body, boundary):
    """解析 multipart/form-data，返回 {field_name: value_bytes}。仅支持简单字段（无嵌套）。"""
    parts = {}
    delim = b"--" + boundary
    chunks = body.split(delim)
    for chunk in chunks:
        chunk = chunk.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        # 分离 header 和 content
        try:
            header_end = chunk.index(b"\r\n\r\n")
            header_block = chunk[:header_end].decode("utf-8", errors="replace")
            content = chunk[header_end + 4:]
            # 去掉尾部 \r\n
            if content.endswith(b"\r\n"):
                content = content[:-2]
        except ValueError:
            continue
        # 提取 name
        name = None
        for line in header_block.split("\r\n"):
            if "name=" in line:
                m = line.split('name="')[1]
                name = m.split('"')[0]
                break
        if name:
            parts[name] = content
    return parts


def run_job(job_id, wav_bytes, txt_text, opts):
    job = _job(job_id)
    out = None
    active_marker = None
    try:
        wdir = WORK / job_id
        wdir.mkdir(parents=True, exist_ok=True)
        opts = validate_upload_names(opts)
        wav_path = resolve_upload_target(wdir, opts["wav_name"], ".wav")
        txt_path = resolve_upload_target(wdir, opts["txt_name"], ".txt")
        active_marker = wdir / ACTIVE_MARKER
        active_marker.write_text(f"{os.getpid()}\n{time.time()}\n", encoding="utf-8")
        # 校验上传的录音确实是 WAV（防止把 txt/其它文件拖进录音框导致废片）
        if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
            raise ValueError("录音文件不是有效的 WAV（文件头前4字节应为 RIFF）。"
                             "请检查：是否把文本或其它文件放进了『录音文件』框？")

        wav_path.write_bytes(wav_bytes)
        txt_path.write_text(txt_text, encoding="utf-8")

        # 预检：wave.open 能否正常读取（提前暴露 truncated / 损坏文件）
        import wave as _wave
        try:
            _w = _wave.open(str(wav_path), "rb")
            _fr, _ch, _sw, _n = _w.getframerate(), _w.getnchannels(), _w.getsampwidth(), _w.getnframes()
            _w.close()
            push(job_id, {"type": "log", "msg": f"音频预检通过：{_ch}ch / {_fr}Hz / {_sw*8}bit / {_n}帧 / {_n/_fr:.1f}s / {len(wav_bytes)//1024}KB"})
        except Exception as we:
            raise RuntimeError(f"音频预检失败（wave.open 报错）：{type(we).__name__}: {we}。"
                             f"文件大小={len(wav_bytes)} 字节，前16字节={wav_bytes[:16].hex()}。"
                             f"可能是 base64 传输截断，请尝试缩短音频或重新上传。") from we

        out = OUTDIR / f"web_{job_id}.mp4"

        def on_progress(pct, info):
            if job_stop_requested(job_id):
                raise RuntimeError("__STOPPED__")
            push(job_id, {"type": "progress", "pct": pct, "info": info})

        def on_log(msg):
            if job_stop_requested(job_id):
                raise RuntimeError("__STOPPED__")
            push(job_id, {"type": "log", "msg": str(msg)})

        # 时长：前端留空 -> None -> 整段全片；0/负数/无法解析也视为整段
        raw_dur = opts.get("dur")
        dur = None
        if raw_dur not in (None, "", 0):
            try:
                dur = float(raw_dur)
            except (ValueError, TypeError):
                dur = None

        push(job_id, {"type": "log", "msg": f"对齐 + 生成字幕中（文件 {wav_path.name}）"})
        kt_video.generate(
            wav_path=str(wav_path), txt_path=str(txt_path),
            out=str(out),
            seed=int(opts.get("seed") or 2),
            full=bool(opts.get("full", False)),
            skip_header=bool(opts.get("skip_header", False)),
            dur=dur,
            crf=str(opts.get("crf") or "20"),
            on_progress=on_progress, on_log=on_log,
            work_dir=wdir,
            cancel_event=job.get("stop_event"),
            on_process=lambda proc: register_job_process(job_id, proc),
        )
        if job_stop_requested(job_id):
            raise RuntimeError("__STOPPED__")
        # 校验成品有效（有真实视频帧，非 262 字节空片）
        if not valid_mp4(out):
            try:
                out.unlink()
            except Exception:
                pass
            raise RuntimeError("生成的视频为空（无画面）。通常是音频与文本不匹配或文件放错框，请检查后重试。")
        finish_job(
            job_id,
            "done",
            {"type": "done", "out": out.name, "url": f"/api/download/{job_id}",
             "out_path": str(out)},
            out=out,
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        if str(e) == "__STOPPED__":
            try:
                if out and out.exists():
                    out.unlink()
            except Exception:
                pass
            finish_job(job_id, "stopped", {"type": "stopped", "msg": "任务已停止"})
            return
        try:
            if out and out.exists():
                out.unlink()          # 失败时清理 ffmpeg 已创建的空/废片
        except Exception:
            pass
        # 完整 traceback 写到服务日志（排查 wave.Error 等）
        try:
            print(f"[ERROR job={job_id}] {tb}", flush=True)
        except Exception:
            pass
        finish_job(job_id, "error", {"type": "error", "msg": f"{type(e).__name__}: {e}"})
    finally:
        register_job_process(job_id, None)
        try:
            if active_marker:
                active_marker.unlink(missing_ok=True)
        except Exception:
            pass


def run_tts(job_id, text, voice, opts, ref_audio_b64=None, ref_text=None, ref_name=""):
    """文字生音频：调用 7860 上的 TTS 实例（wzf python + gradio_client）"""
    job = _job(job_id)
    out_wav = None
    active_marker = None
    try:
        wdir = WORK / job_id
        wdir.mkdir(parents=True, exist_ok=True)
        active_marker = wdir / ACTIVE_MARKER
        active_marker.write_text(f"{os.getpid()}\n{time.time()}\n", encoding="utf-8")
        out_wav = wdir / "tts.wav"
        if not text or not text.strip():
            raise ValueError("合成文本不能为空")

        # ---- 未安装语音引擎 -> 友好提示，绝不抛堆栈 ----
        _d = _dots()
        if not _d["installed"]:
            raise RuntimeError(
                "未检测到语音引擎（语音引擎包）。\n"
                "你可以：1) 去网盘下载【语音引擎包】，解压后双击本包的"
                "【2】连接语音引擎.bat；\n"
                "或 2) 直接在上方上传已有的音频文件，跳过这一步。")
        DOTS_PYTHON = _d["python"]

        # 这些参数前端可能留空（或缺失），用 `or 默认值` 兜底，避免 float(None)/int(None) 崩溃
        num_steps = opts.get("num_steps") or 4
        guidance_scale = opts.get("guidance_scale") or 1.2
        speed = opts.get("speed") or 1.0
        max_pause = opts.get("max_pause") or 0.3
        seed = opts.get("seed") or 42
        cmd = [
            DOTS_PYTHON, str(DOTS_SYNTH),
            "--text", text, "--voice", voice, "--out", str(out_wav),
            "--num_steps", str(int(num_steps)),
            "--guidance_scale", str(float(guidance_scale)),
            "--speed", str(float(speed)),
            "--max_pause", str(float(max_pause)),
            "--seed", str(int(seed)),
        ]
        if opts.get("normalize"):
            cmd.append("--normalize")

        # 自定义参考音色：把上传的参考音频写入临时文件，覆盖预设音色
        if ref_audio_b64:
            try:
                raw = base64.b64decode(ref_audio_b64)
            except Exception:
                raise ValueError("参考音频 base64 解码失败")
            if len(raw) < 1024:
                raise ValueError("参考音频文件过小或为空")
            # 按原文件扩展名保存（DOTS 按扩展名/文件头识别格式）
            ref_ext = os.path.splitext(ref_name or "")[1].lower()
            if ref_ext not in (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"):
                ref_ext = ".wav"
            ref_path = wdir / f"ref_audio{ref_ext}"
            ref_path.write_bytes(raw)
            cmd += ["--prompt_wav", str(ref_path), "--prompt_text", ref_text or ""]

        push(job_id, {"type": "log", "msg": f"TTS 合成中（音色：{voice or '自定义参考音色'}）…"})
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1, encoding="utf-8", errors="replace")
        register_job_process(job_id, proc)
        err_buf = []
        # 必须在消费 stdout 前并发排空 stderr。否则子进程若先写满 stderr
        # 管道，父进程会等待 stdout EOF，而子进程会等待 stderr 可写，形成死锁。
        stderr_thread = threading.Thread(
            target=lambda: err_buf.append(proc.stderr.read()),
            daemon=True,
        )
        stderr_thread.start()
        dur = None
        for line in proc.stdout:
            if job_stop_requested(job_id):
                break
            line = line.strip()
            if line.startswith("PROGRESS "):
                try:
                    pct = int(line.split()[1].split("/")[0])
                except Exception:
                    pct = None
                if pct is not None:
                    push(job_id, {"type": "progress", "pct": pct})
            elif line.startswith("STEP "):
                pass   # 只更新进度条，不推送 STEP 内部日志（避免刷屏干扰）
            elif line.startswith("CHUNK "):
                push(job_id, {"type": "log", "msg": line})
            elif line.startswith("ENDPOINT "):
                push(job_id, {"type": "log", "msg": "接口：" + line[9:]})
            elif line.startswith("DONE "):
                try:
                    dur = float(line.split()[1])
                except Exception:
                    dur = None
                dur_str = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "?"
                push(job_id, {"type": "log", "msg": f"✅ 音频合成完成，时长 {dur_str}"})
            elif line.startswith("ERROR "):
                raise RuntimeError(line[6:].strip())
        proc.wait()
        stderr_thread.join(timeout=5)
        if job_stop_requested(job_id):
            finish_job(job_id, "stopped", {"type": "stopped", "msg": "任务已停止"})
            return
        if proc.returncode != 0:
            raw_stderr = (err_buf[0] if err_buf else "") or ""
            # stderr 可能是 GBK 或 UTF-8，尝试 UTF-8 失败则回退 GBK，避免乱码
            if isinstance(raw_stderr, bytes):
                try:
                    stderr_tail = raw_stderr.decode("utf-8", "strict")
                except UnicodeDecodeError:
                    stderr_tail = raw_stderr.decode("gbk", "replace")
            else:
                stderr_tail = raw_stderr
            stderr_tail = stderr_tail[-1500:]
            raise RuntimeError(f"TTS 进程异常退出（code {proc.returncode}）{('，' + stderr_tail) if stderr_tail else ''}")
        if not out_wav.exists():
            raise RuntimeError("未生成音频文件（TTS 后端不可用或未返回有效音频）")

        # 复制到稳定的「视频/配音」目录（web_jobs 是缓存目录，会被定期清理导致"打开文件夹找不到"）
        voice_out_dir = OUTDIR / "配音"
        voice_out_dir.mkdir(parents=True, exist_ok=True)
        final_wav = voice_out_dir / f"tts_{job_id[:8]}_{int(time.time())}.wav"
        shutil.copy(out_wav, final_wav)

        finish_job(job_id, "done", {
            "type": "done", "kind": "tts",
            "wav_name": final_wav.name, "duration": dur,
            "voice": voice, "text": text, "url": f"/api/tts_file/{job_id}",
            "out_path": str(final_wav),
        }, out=final_wav)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        if job_stop_requested(job_id) or str(e) == "__STOPPED__":
            try:
                if out_wav and out_wav.exists():
                    out_wav.unlink()
            except Exception:
                pass
            finish_job(job_id, "stopped", {"type": "stopped", "msg": "任务已停止"})
            return
        try:
            if out_wav and out_wav.exists():
                out_wav.unlink()
        except Exception:
            pass
        try:
            print(f"[ERROR tts job={job_id}] {tb}", flush=True)
        except Exception:
            pass
        finish_job(job_id, "error", {"type": "error", "msg": f"{type(e).__name__}: {e}"})
    finally:
        register_job_process(job_id, None)
        try:
            if active_marker:
                active_marker.unlink(missing_ok=True)
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_request_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send(400, b'{"error":"invalid content length"}')
            return None
        if length < 0:
            self._send(400, b'{"error":"invalid content length"}')
            return None
        if length > MAX_REQUEST_BYTES:
            self._send(413, json.dumps({
                "error": f"请求体超过 {MAX_REQUEST_BYTES // 1024 // 1024} MiB 上限"
            }, ensure_ascii=False).encode("utf-8"))
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self._send(400, b'{"error":"incomplete request body"}')
            return None
        return body

    def _send_file(self, path, ctype, download_name=None):
        """Send a file in bounded chunks; never materialize the whole file in RAM."""
        path = Path(path)
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(size))
        if download_name:
            encoded = quote(str(download_name), safe="")
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=download; filename*=UTF-8''{encoded}",
            )
        self.end_headers()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return

    def do_GET(self):
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            data = (WEB_DIR / "index.html").read_bytes()
            self._send(200, data, "text/html; charset=utf-8", extra={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            })
        elif route == "/api/health":
            self.handle_health()
        elif route.startswith("/api/status/"):
            self.handle_status()
        elif route == "/api/tts_voices":
            self.handle_tts_voices()
        elif route == "/api/output_dirs":
            self.handle_output_dirs()
        elif route == "/api/events":
            self.handle_events()
        elif route.startswith("/api/stop/"):
            self.handle_stop()
        elif route.startswith("/api/download/"):
            self.handle_download()
        elif route.startswith("/api/tts_file/"):
            self.handle_tts_file()
        elif route == "/api/voice_audio":
            self.handle_voice_audio()
        elif route == "/api/cache_info":
            self.handle_cache_info()
        elif route == "/api/clear_cache":
            self.handle_clear_cache()
        elif route == "/api/dots_status":
            self.handle_dots_status()
        elif route == "/api/dots_stop":
            self.handle_dots_stop()
        elif route == "/api/open_folder":
            self.handle_open_folder()
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        route = urlparse(self.path).path
        if route == "/api/generate":
            self.handle_generate()
        elif route == "/api/tts":
            self.handle_tts()
        else:
            self._send(404, b'{"error":"not found"}')

    def handle_health(self):
        host, port = self.server.server_address[:2]
        body = json.dumps({
            "status": "ok",
            "host": host,
            "port": int(port),
            "service": "package-a-video",
        }, ensure_ascii=False).encode("utf-8")
        self._send(200, body, extra={"Cache-Control": "no-store"})

    def handle_status(self):
        job_id = urlparse(self.path).path.rsplit("/", 1)[-1]
        snapshot = job_snapshot(job_id)
        if snapshot is None:
            self._send(404, b'{"error":"no job"}')
            return
        self._send(200, json.dumps(snapshot, ensure_ascii=False).encode("utf-8"),
                   extra={"Cache-Control": "no-store"})

    # ---- TTS 音色列表 ----
    def handle_tts_voices(self):
        try:
            voices = load_voices()
            data = [{"name": k, "prompt_text": v["prompt_text"]} for k, v in voices.items()]
            self._send(200, json.dumps({"voices": data}, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

    # ---- 默认输出目录 ----
    def handle_output_dirs(self):
        try:
            body = json.dumps({
                "video_dir": str(OUTDIR.resolve()),
                "tts_dir": str(WORK.resolve()),
            }, ensure_ascii=False).encode("utf-8")
            self._send(200, body)
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

    # ---- TTS 合成任务 ----
    def handle_tts(self):
        try:
            raw = self._read_request_body()
            if raw is None:
                return
            try:
                payload = parse_json_object(raw)
            except ValueError as exc:
                self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))
                return
            text = payload.get("text", "")
            voice = payload.get("voice", "")
            opts = {k: payload.get(k) for k in
                    ("num_steps", "guidance_scale", "speed", "max_pause", "seed", "normalize")}
            ref_audio_b64 = payload.get("ref_audio_b64")
            ref_text = payload.get("ref_text", "")
            ref_name = payload.get("ref_name", "")
            dots = _dots()
            if not dots["installed"]:
                self._send(503, json.dumps({
                    "error": "未检测到语音引擎（包 B 未安装）；可直接上传已有 WAV 继续生成视频。"
                }, ensure_ascii=False).encode("utf-8"))
                return
            if platform_support.is_darwin():
                try:
                    contract = dots_control.probe_contract(dots, DOTS_SYNTH)
                except dots_control.DotsControlError as exc:
                    self._send(503, json.dumps({
                        "error": f"语音引擎 API 不可用：{exc}"
                    }, ensure_ascii=False).encode("utf-8"))
                    return
                if contract.get("mode") not in ("v1", "legacy9"):
                    self._send(503, json.dumps({"error": "语音引擎 API schema 不兼容"}, ensure_ascii=False).encode("utf-8"))
                    return
            job_id = create_job("tts")
            t = threading.Thread(target=run_tts,
                                args=(job_id, text, voice, opts, ref_audio_b64, ref_text, ref_name),
                                daemon=True)
            register_job_worker(job_id, t)
            t.start()
            self._send(200, json.dumps({"job_id": job_id}).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

    # ---- TTS 成品下载 ----
    def handle_tts_file(self):
        job_id = urlparse(self.path).path.rsplit("/", 1)[-1]
        job = _job(job_id)
        if not job or job.get("status") != "done" or not job.get("out"):
            self._send(404, b'{"error":"no file"}')
            return
        p = Path(job["out"]).resolve()
        try:
            p.relative_to(Path(OUTDIR).resolve())
        except ValueError:
            self._send(403, b'{"error":"output outside project"}')
            return
        if not p.exists():
            self._send(404, b'{"error":"missing"}')
            return
        self._send_file(p, "audio/wav", p.name)

    # ---- 缓存信息 ----
    def handle_cache_info(self):
        try:
            total = 0
            count = 0
            for d in WORK.iterdir():
                if d.is_dir():
                    count += 1
                    for f in d.rglob("*"):
                        if f.is_file():
                            total += f.stat().st_size
            self._send(200, json.dumps({
                "dir": str(WORK.resolve()),
                "count": count,
                "size_mb": round(total / 1024 / 1024, 1),
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

    # ---- 清理缓存 ----
    def handle_clear_cache(self):
        try:
            cleared = 0
            with jobs_lock:
                active = {
                    job_id for job_id, job in jobs.items()
                    if job.get("status") not in TERMINAL_STATUSES
                }
            for d in WORK.iterdir():
                if (d.is_dir() and d.name not in active
                        and not (d / ACTIVE_MARKER).exists()):
                    shutil.rmtree(d, ignore_errors=True)
                    cleared += 1
            self._send(200, json.dumps({
                "ok": True, "cleared": cleared, "skipped_running": len(active)
            }).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

    # ---- Dots.tts 大模型状态（联动：加载进度 / 关网页关模型）----
    def dots_pid(self):
        try:
            pf = WEB_DIR / "dots.pid"
            if pf.exists():
                return int(pf.read_text(encoding="utf-8").strip())
        except Exception:
            pass
        return None

    def dots_ready(self):
        try:
            with urllib.request.urlopen(_dots()["url"] + "/", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def handle_dots_status(self):
        try:
            _d = _dots()
            if platform_support.is_darwin():
                payload = dots_control.status(_d)
                payload["root"] = str(_d["root"]) if _d.get("root") else ""
                payload.setdefault("log_tail", "")
                payload.setdefault("progress_desc", payload.get("reason", ""))
                self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                return
            pid = self.dots_pid()
            ready = self.dots_ready() if _d["installed"] else False
            if not _d["installed"]:
                state = "not_installed"
            else:
                state = "ready" if ready else ("starting" if pid else "offline")
            log_tail = ""
            try:
                lf = WEB_DIR / "dots_server.log"
                if lf.exists():
                    lines = lf.read_text(encoding="utf-8", errors="replace").splitlines()
                    log_tail = "\n".join(lines[-6:])
            except Exception:
                pass
            # 加载进度：读 launcher 写的 dots_progress.txt（7860 就绪则强制 100）
            progress = 0
            progress_desc = ""
            try:
                pf = WEB_DIR / "dots_progress.txt"
                if pf.exists():
                    parts = pf.read_text(encoding="utf-8", errors="replace").strip().split("|", 1)
                    progress = int(parts[0])
                    if len(parts) > 1:
                        progress_desc = parts[1]
            except Exception:
                pass
            if ready:
                progress = 100
            self._send(200, json.dumps({
                "state": state, "pid": pid, "log_tail": log_tail,
                "progress": progress, "progress_desc": progress_desc,
                "installed": _d["installed"],
                "root": str(_d["root"]) if _d["root"] else "",
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_dots_stop(self):
        """关掉 Dots.tts：杀由启动器拉起的进程（读 dots.pid），并尝试杀 7860 监听进程。"""
        dots = _dots()
        if platform_support.is_darwin():
            try:
                result = dots_control.stop(dots)
                self._send(200 if result.get("ok") else 409,
                           json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except dots_control.DotsControlError as exc:
                self._send(409, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"))
            return
        if not dots["installed"]:
            self._send(200, json.dumps({
                "ok": True, "state": "not_installed", "killed": []
            }).encode("utf-8"))
            return
        killed = []
        # 1. 按 pid 文件杀
        pid = self.dots_pid()
        if pid:
            try:
                os.kill(pid, 9)
                killed.append(pid)
            except Exception:
                pass
        # 2. 兜底：杀监听 7860 的进程
        try:
            out = subprocess.run("netstat -ano", capture_output=True, text=True,
                                 shell=True, encoding="gbk", errors="replace").stdout
            import re
            seen = set()
            for line in out.splitlines():
                if f":{_dots()['port']}" in line and "LISTENING" in line:
                    m = re.search(r"(\d+)\s*$", line)
                    if m:
                        p2 = int(m.group(1))
                        if p2 not in seen and p2 not in killed:
                            seen.add(p2)
                            try:
                                os.kill(p2, 9)
                                killed.append(p2)
                            except Exception:
                                pass
        except Exception:
            pass
        # 3. 清 pid 文件
        try:
            (WEB_DIR / "dots.pid").unlink()
        except Exception:
            pass
        self._send(200, json.dumps({"ok": True, "killed": killed}).encode("utf-8"))

    # ---- 音色库试听（返回 prompts 目录下的音频文件）----
    def handle_voice_audio(self):
        from urllib.parse import urlparse, parse_qs, unquote
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("name") or [None])[0]
        if not name:
            self._send(400, b'{"error":"no name"}')
            return
        # 安全校验：只允许 prompts 目录下的文件名
        DOTS_PROMPTS = _dots()["prompts"]
        p = (DOTS_PROMPTS / name).resolve()
        try:
            p.relative_to(DOTS_PROMPTS.resolve())
        except ValueError:
            self._send(403, b'{"error":"outside prompts dir"}')
            return
        if not p.exists():
            self._send(404, b'{"error":"file not found"}')
            return
        ct = "audio/wav" if p.suffix.lower() == ".wav" else "audio/mp4"
        self._send_file(p, ct)

    # ---- 打开输出文件夹（限项目目录内，委托平台层 Finder / Explorer）----
    def handle_open_folder(self):
        q = parse_qs(urlparse(self.path).query)
        raw_path = (q.get("path") or [None])[0]
        if not raw_path:
            self._send(400, b'{"error":"no path"}')
            return
        root = Path(ROOT).resolve()
        target = Path(raw_path).expanduser().resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._send(403, b'{"error":"path not in project"}')
            return
        try:
            if target.is_file():
                platform_support.open_in_file_manager(target, select=True)
            elif target.is_dir():
                platform_support.open_in_file_manager(target)
            else:
                # 路径不存在 -> 回退到最近的存在的父目录
                parent = target
                while parent != root and not parent.exists():
                    parent = parent.parent
                platform_support.open_in_file_manager(parent if parent.is_dir() else root)
            self._send(200, json.dumps({"ok": True}).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({
                "error": f"无法打开文件管理器：{type(e).__name__}: {e}"
            }, ensure_ascii=False).encode("utf-8"))

    # ---- 生成任务 ----
    def handle_generate(self):
        try:
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" in ctype:
                # multipart 上传：wav 文件直接走二进制，不走 base64（解决大文件损坏）
                boundary = self.headers.get("Content-Type", "").split("boundary=")[-1].strip()
                if not boundary:
                    self._send(400, json.dumps({"error": "缺少 boundary"}).encode("utf-8"))
                    return
                body = self._read_request_body()
                if body is None:
                    return
                parts = parse_multipart(body, boundary.encode())
                wav_bytes = parts.get("wav", b"")
                txt_text = parts.get("txt", b"").decode("utf-8", errors="replace")
                wav_name = parts.get("wav_name", b"audio.wav").decode("utf-8", errors="replace")
                txt_name = parts.get("txt_name", b"text.txt").decode("utf-8", errors="replace")
                tts_job = parts.get("tts_job", b"").decode("utf-8", errors="replace").strip()
                opts = {
                    "wav_name": wav_name, "txt_name": txt_name,
                    "seed": parts.get("seed", b"2").decode("utf-8", errors="replace").strip(),
                    "full": parts.get("full", b"").decode("utf-8", errors="replace").strip() == "true",
                    "skip_header": parts.get("skip_header", b"").decode("utf-8", errors="replace").strip() == "true",
                    "dur": parts.get("dur", b"").decode("utf-8", errors="replace").strip() or None,
                    "crf": parts.get("crf", b"20").decode("utf-8", errors="replace").strip(),
                }
                if tts_job:
                    src = jobs.get(tts_job, {}).get("out")
                    if not src or not os.path.exists(src):
                        self._send(400, json.dumps({"error": "tts_job 无效或音频已过期"}).encode("utf-8"))
                        return
                    wav_bytes = open(src, "rb").read()
                    opts["wav_name"] = os.path.basename(src)
                if not wav_bytes:
                    self._send(400, json.dumps({"error": "缺少 wav 文件"}).encode("utf-8"))
                    return
                if not txt_text:
                    self._send(400, json.dumps({"error": "缺少 txt 文本"}).encode("utf-8"))
                    return
            else:
                # 兼容旧 JSON+base64 方式
                raw = self._read_request_body()
                if raw is None:
                    return
                try:
                    payload = parse_json_object(raw)
                except ValueError as exc:
                    self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))
                    return
                txt_text = payload.get("txt_text", "")
                wav_bytes = None
                if payload.get("tts_job"):
                    src = jobs.get(payload["tts_job"], {}).get("out")
                    if not src or not os.path.exists(src):
                        self._send(400, json.dumps({"error": "tts_job 无效或音频已过期"}).encode("utf-8"))
                        return
                    wav_bytes = open(src, "rb").read()
                    payload.setdefault("wav_name", os.path.basename(src))
                else:
                    wav_b64 = payload.get("wav_b64", "")
                    if not wav_b64:
                        self._send(400, json.dumps({"error": "缺少 wav 或 tts_job"}).encode("utf-8"))
                        return
                    try:
                        wav_bytes = base64.b64decode(wav_b64, validate=True)
                    except (ValueError, binascii.Error):
                        self._send(400, json.dumps({"error": "wav_b64 不是有效 base64"}).encode("utf-8"))
                        return
                if not txt_text:
                    self._send(400, json.dumps({"error": "缺少 txt"}).encode("utf-8"))
                    return
                opts = {k: payload.get(k) for k in
                        ("wav_name", "txt_name", "seed", "full", "skip_header", "dur", "crf")}
            try:
                opts = validate_upload_names(opts)
            except ValueError as exc:
                self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))
                return
            job_id = create_job("video")
            t = threading.Thread(target=run_job, args=(job_id, wav_bytes, txt_text, opts), daemon=True)
            register_job_worker(job_id, t)
            t.start()
            self._send(200, json.dumps({"job_id": job_id}).encode("utf-8"))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}).encode("utf-8"))

    # ---- 停止任务 ----
    def handle_stop(self):
        job_id = urlparse(self.path).path.rsplit("/", 1)[-1]
        job = _job(job_id)
        if not job:
            self._send(404, b'{"error":"no job"}')
            return
        if request_job_stop(job_id):
            terminate_job_process(job_id)
            finish_job(job_id, "stopped", {"type": "stopped", "msg": "任务已停止"})
        self._send(200, json.dumps({
            "ok": True, "status": job_snapshot(job_id)["status"]
        }).encode("utf-8"))

    # ---- SSE 实时进度 ----
    def handle_events(self):
        q = parse_qs(urlparse(self.path).query)
        job_id = (q.get("job") or [None])[0]
        job = _job(job_id) if job_id else None
        if not job:
            self._send(404, b'{"error":"no job"}')
            return
        condition = job.get("condition")
        if condition is None:
            self._send(409, b'{"error":"legacy job has no replayable events"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            after = int((q.get("after") or [self.headers.get("Last-Event-ID", "0")])[0] or 0)
        except ValueError:
            after = 0
        try:
            while True:
                with condition:
                    available = [
                        dict(item) for item in job.get("events", [])
                        if item.get("seq", 0) > after
                    ]
                    if not available and job.get("status") not in TERMINAL_STATUSES:
                        condition.wait(SSE_HEARTBEAT_SECONDS)
                        available = [
                            dict(item) for item in job.get("events", [])
                            if item.get("seq", 0) > after
                        ]
                    terminal = job.get("status") in TERMINAL_STATUSES
                if not available:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    if terminal:
                        break
                    continue
                for item in available:
                    after = max(after, int(item.get("seq", 0)))
                    block = (
                        f"id: {after}\n"
                        + "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
                    )
                    self.wfile.write(block.encode("utf-8"))
                    self.wfile.flush()
                    if item.get("type") in TERMINAL_STATUSES:
                        self.close_connection = True
                        return
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    # ---- 下载成品 ----
    def handle_download(self):
        job_id = urlparse(self.path).path.rsplit("/", 1)[-1]
        job = _job(job_id)
        if not job or job.get("status") != "done" or not job.get("out"):
            self._send(404, b'{"error":"no file"}')
            return
        p = Path(job["out"]).resolve()
        try:
            p.relative_to(Path(OUTDIR).resolve())
        except ValueError:
            self._send(403, b'{"error":"output outside project"}')
            return
        if not p.exists():
            self._send(404, b'{"error":"missing"}')
            return
        self._send_file(p, "video/mp4", p.name)

    def log_message(self, fmt, *args):
        pass   # 静默


def create_server(host, port, handler_class=Handler, max_tries=20,
                  server_class=None):
    """Bind a testable server; port 0 is passed through for kernel allocation."""
    server_class = ThreadingHTTPServer if server_class is None else server_class
    port = int(port)
    candidates = (0,) if port == 0 else platform_support.iter_ports(port, max_tries)
    last_error = None
    for candidate in candidates:
        try:
            server = server_class((str(host), candidate), handler_class)
            server.package_a_bind_port = candidate
            return server
        except OSError as exc:
            last_error = exc
    detail = f"：{last_error}" if last_error else ""
    raise OSError(f"无法绑定 Web 服务端口{detail}")


def main(host=PRODUCTION_HOST, port=None):
    global PORT
    requested_port = PORT if port is None else int(port)
    try:
        # 生产默认 0.0.0.0，测试显式传 127.0.0.1 与端口 0。
        httpd = create_server(host, requested_port)
    except OSError as exc:
        print(f"❌ 无法绑定端口：{exc}")
        return
    actual_port = int(getattr(httpd, "server_address", (host, httpd.package_a_bind_port))[1])
    PORT = actual_port
    cleanup_old_jobs()
    # 把实际监听端口写入 .port，便于启动器/用户定位访问地址（端口顺延时也能找对）
    try:
        Path(__file__).resolve().parent.joinpath(".port").write_text(str(PORT), encoding="utf-8")
    except Exception:
        pass
    # 打印本机局域网 IP（供手机访问）
    lan = None
    try:
        import socket as _s
        s = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    print(f"✅ 视频生成 Web 已启动:  http://127.0.0.1:{PORT}/")
    if lan:
        print(f"   📱 局域网访问: http://{lan}:{PORT}/  （需防火墙放行 {PORT} 端口）")
    print("   按 Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        close = getattr(httpd, "server_close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
