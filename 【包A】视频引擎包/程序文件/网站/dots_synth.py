# -*- coding: utf-8 -*-
"""
dots.tts TTS 合成助手（由视频生成 Web 后端以子进程调用）
- 复用 7860 上已加载的 DOTS 实例（不重复占显存）
- 按 200 字切块、块间插 0.25s 静音（与 DOTS配音_锣 成品一致，便于下游视频对齐）
- 自动适配 7860 的两种 DOTS 版本：
    * 新版：/gen_clone(text, ref_audio, ref_text)   —— 语音克隆
    * 旧版：/run_synthesis(...)                       —— 预设音色下拉
- 用 gradio_client.submit + 轮询 job.status().progress_data 获取大模型真实进度，
  实时推到 stdout（PROGRESS <pct>/100），让网页进度条与模型同步
- 支持自定义参考音色：传 --prompt_wav + --prompt_text 即可覆盖预设音色
- 行协议（stdout）：
    PROGRESS <pct>/100          # 0-100 的实时进度
    CHUNK <i>/<n> <字数>字        # 进入第 i 个文本块（日志用）
    STEP <描述>                  # 模型当前步骤描述（日志用）
    DONE <秒数>
    ERROR <信息>
"""
import sys, re, shutil, wave, os, json, argparse, time, threading
from pathlib import Path

# 强制 stdout/stderr 为 UTF-8：Windows 控制台默认 GBK，否则被 kt_web.py 按 UTF-8 读取时中文全乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 路径由 程序文件/paths.py 统一解析（本脚本由语音引擎自带的 python 执行，
# paths.py 只用标准库，任何 python3 都能导入）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import paths as _paths
    _di = _paths.dots_info()
    PROMPTS_DIR = _di["prompts"]
    DOTS_URL = _di["url"]
except Exception:
    PROMPTS_DIR = Path(__file__).resolve().parent / "_no_prompts"
    DOTS_URL = "http://127.0.0.1:7860"
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")
API_VERSION = "dots-tts.synthesize.v1"
V1_ENDPOINT = "/synthesize_v1"
LEGACY_ENDPOINT = "/run_synthesis"
V1_PARAMETERS = ("request",)
LEGACY9_PARAMETERS = (
    "text", "prompt_audio_path", "prompt_text", "num_steps",
    "guidance_scale", "normalize_text", "seed", "speed", "max_pause",
)


class ContractError(RuntimeError):
    pass


def load_voices():
    """扫描 prompts 目录下的全部音频，得到 {文件名: {prompt_wav, prompt_text}}。
    与原 7860 接口下拉一致：目录里有什么音频就显示什么音色。"""
    ref_map = {}
    f = PROMPTS_DIR / "prompt_text"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            name, txt = line.split("|", 1)
            ref_map[name.strip()] = txt.strip()
    voices = {}
    if PROMPTS_DIR.exists():
        for af in sorted(PROMPTS_DIR.iterdir()):
            if af.suffix.lower() in AUDIO_EXT:
                # 转写优先读 prompt_text；没有则用文件名（去扩展名）兜底——
                # DOTS 的 m4a 样本就是"文件名=实际朗读内容"的设计，空转写会导致服务器报
                # "已选择参考音频，请填写其实际朗读的中文转写" 而崩溃（returncode=1）
                txt = ref_map.get(af.stem, "") or af.stem
                voices[af.name] = {
                    "prompt_wav": str(af),
                    "prompt_text": txt,
                }
    return voices


def chunk_text(text, chunk=200):
    text = " ".join(l.strip() for l in text.splitlines() if l.strip())
    sents = [s.strip() for s in re.split(r"(?<=[。！？；])", text) if s.strip()]
    chunks, cur = [], ""
    for s in sents:
        if cur and len(cur) + len(s) > chunk:
            chunks.append(cur)
            cur = s
        else:
            cur += s
    if cur:
        chunks.append(cur)
    return chunks


def progress_fraction(pu):
    """从 ProgressUnit 提取 0..1 的进度；无法判断时返回 None。
    兼容多种语义：progress 可能是 0..1 或 0..100；也可能只有 index/length；
    最后从 desc（如"音频解码 FM 2/8 步"）解析数字兜底。"""
    if pu is None:
        return None
    p = getattr(pu, "progress", None)
    if p is not None:
        try:
            v = float(p)
            if v > 1.0:          # 兼容 0..100 的语义
                v = v / 100.0
            return max(0.0, min(1.0, v))
        except (TypeError, ValueError):
            pass
    length = getattr(pu, "length", None)
    if length:
        try:
            idx = getattr(pu, "index", 0) or 0
            return max(0.0, min(1.0, float(idx) / float(length)))
        except (TypeError, ValueError):
            pass
    # 兜底：从 desc 解析 "x/y 步"（gradio 多 worker 下 progress 字段常为空）
    desc = getattr(pu, "desc", None) or ""
    m = re.search(r"(\d+)\s*/\s*(\d+)", desc)
    if m:
        try:
            d1, d2 = int(m.group(1)), int(m.group(2))
            if d2 > 0:
                return max(0.0, min(1.0, d1 / d2))
        except (TypeError, ValueError):
            pass
    return None


def read_wav(p):
    w = wave.open(str(p))
    n = w.getnframes()
    fr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    data = w.readframes(n)
    w.close()
    return fr, ch, sw, data


def _parameter_names(endpoint):
    parameters = endpoint.get("parameters", []) if isinstance(endpoint, dict) else []
    return tuple(item.get("parameter_name") for item in parameters if isinstance(item, dict))


def negotiate_endpoint(c):
    """只接受版本化契约或已锁定的 9 参数 legacy schema。"""
    try:
        info = c.view_api(return_format="dict")
    except Exception as exc:
        raise ContractError(f"无法读取包 B API schema：{exc}") from exc
    eps = info.get("named_endpoints", {}) if isinstance(info, dict) else {}
    eps = eps if isinstance(eps, dict) else {}
    if V1_ENDPOINT in eps:
        actual = _parameter_names(eps[V1_ENDPOINT])
        if actual != V1_PARAMETERS:
            raise ContractError(
                f"{V1_ENDPOINT} schema 不兼容：期望 {V1_PARAMETERS}，实际 {actual}"
            )
        return {"mode": "v1", "api_name": V1_ENDPOINT, "api_version": API_VERSION}
    if LEGACY_ENDPOINT in eps:
        actual = _parameter_names(eps[LEGACY_ENDPOINT])
        if actual == LEGACY9_PARAMETERS:
            return {"mode": "legacy9", "api_name": LEGACY_ENDPOINT, "api_version": "legacy-ui-9"}
        raise ContractError(
            f"{LEGACY_ENDPOINT} legacy schema 不兼容：期望 {LEGACY9_PARAMETERS}，实际 {actual}"
        )
    raise ContractError("包 B 未暴露受支持的合成端点")


def detect_endpoint(c):
    """保留旧函数名，但返回经严格校验的契约。"""
    return negotiate_endpoint(c)


def _result_path(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("path"), str):
        return value["path"]
    path = getattr(value, "path", None)
    return path if isinstance(path, str) else None


def synth_chunk(c, text, prompt_wav, prompt_text, opts, on_within, endpoint):
    """提交单个文本块，轮询大模型真实进度，通过 on_within(frac) 实时回调 0..1。
    返回结果音频路径（str）。"""
    if endpoint["mode"] == "v1":
        request = {
            "text": text,
            "prompt_audio_path": prompt_wav,
            "prompt_text": prompt_text or "",
            "num_steps": opts["num_steps"],
            "guidance_scale": opts["guidance_scale"],
            "normalize_text": opts["normalize"],
            "seed": opts["seed"],
            "speed": opts["speed"],
            "max_pause": opts["max_pause"],
        }
        job = c.submit(
            request=request,
            api_name=V1_ENDPOINT,
        )
    else:  # 仅限精确匹配的 legacy 9 参数合同
        job = c.submit(
            api_name="/run_synthesis",
            text=text,
            prompt_audio_path=prompt_wav,
            prompt_text=prompt_text or "",
            num_steps=opts["num_steps"],
            guidance_scale=opts["guidance_scale"],
            normalize_text=opts["normalize"],
            seed=opts["seed"],
            speed=opts["speed"],
            max_pause=opts["max_pause"],
        )

    def poll():
        last_desc = [None]
        last_ts = [0.0]
        while not job.done():
            try:
                su = job.status()  # 直接返回 StatusUpdate（含 progress_data）
                pd = getattr(su, "progress_data", None)
                if pd:
                    pu = pd[-1]
                    f = progress_fraction(pu)
                    if f is not None:
                        on_within(f)
                    desc = getattr(pu, "desc", None)
                    # STEP 节流：desc 变化且距上次 ≥1s 才打印（gradio 多 worker 下 desc 乱序跳）
                    if desc and desc != last_desc[0] and time.time() - last_ts[0] >= 1.0:
                        last_desc[0] = desc
                        last_ts[0] = time.time()
                        print("STEP " + desc, flush=True)
            except Exception:
                pass
            time.sleep(0.15)

    pt = threading.Thread(target=poll, daemon=True)
    pt.start()
    try:
        result = job.result()
    except Exception as e:
        # gradio AppError 等（如"已选择参考音频，请填写转写"）转成 ERROR 行，避免裸崩 returncode=1
        msg = str(e)
        if "转写" in msg:
            msg = ("DOTS 要求所选参考音频必须有中文转写。该音色无转写文本，"
                   "请改选其它音色，或在页面「参考声音」区上传自己的参考音频并填写参考台词。")
        elif "max_generate_length" in msg or "patch count" in msg:
            msg = ("参考音频太长（DOTS 限制参考音频约 ≤60 秒，过长会报 max_generate_length 错误）。"
                   "请拖入更短的参考音频（建议 10~30 秒）再试。")
        print(f"ERROR 合成失败: {msg}", flush=True)
        return None
    finally:
        pt.join(timeout=1.0)
    if endpoint["mode"] == "v1":
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            print("ERROR 包 B v1 返回形状不兼容", flush=True)
            return None
        audio, response = result
        if not isinstance(response, dict) or response.get("api_version") != API_VERSION:
            print("ERROR 包 B v1 响应版本不兼容", flush=True)
            return None
        if response.get("ok") is not True:
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            print(f"ERROR 包 B 合成失败: {error.get('code', 'unknown')}: {error.get('message', '')}", flush=True)
            return None
        return _result_path(audio)
    if isinstance(result, (list, tuple)):
        return next((_result_path(item) for item in result if _result_path(item)), None)
    return _result_path(result)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-contract", action="store_true")
    ap.add_argument("--text")
    ap.add_argument("--voice", default="")          # 预设音色（prompts 目录里的文件名）
    ap.add_argument("--out")
    ap.add_argument("--prompt_wav", default="")     # 自定义参考音色（覆盖 --voice）
    ap.add_argument("--prompt_text", default="")
    ap.add_argument("--num_steps", type=int, default=4)
    ap.add_argument("--guidance_scale", type=float, default=1.2)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--max_pause", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--normalize", action="store_true")
    args = ap.parse_args()

    from gradio_client import Client

    print("CONNECT " + DOTS_URL, flush=True)
    try:
        c = Client(DOTS_URL)
        endpoint = negotiate_endpoint(c)
    except Exception as exc:
        print(f"ERROR 包 B API 契约协商失败：{exc}", flush=True)
        sys.exit(5)
    print("ENDPOINT " + endpoint["mode"], flush=True)
    if args.probe_contract:
        print("CONTRACT " + json.dumps(endpoint, ensure_ascii=False, sort_keys=True), flush=True)
        return
    if not args.text or not args.out:
        ap.error("合成模式必须提供 --text 和 --out")

    # 解析音色：优先自定义参考音频
    if args.prompt_wav:
        prompt_wav = args.prompt_wav
        prompt_text = args.prompt_text or ""
        if not prompt_text:
            print("ERROR 自定义参考音色需要提供参考台词(prompt_text)")
            sys.exit(4)
    else:
        voices = load_voices()
        if args.voice not in voices:
            names = "、".join(voices.keys()) or "（空）"
            print(f"ERROR 未知音色: {args.voice}；可用：{names}")
            sys.exit(2)
        v = voices[args.voice]
        prompt_wav = v["prompt_wav"]
        prompt_text = v["prompt_text"]

    chunks = chunk_text(args.text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not chunks:
        print("ERROR 文本为空")
        sys.exit(3)

    opts = {
        "num_steps": args.num_steps, "guidance_scale": args.guidance_scale,
        "normalize": args.normalize, "seed": args.seed,
        "speed": args.speed, "max_pause": args.max_pause,
    }

    tmp_paths = []
    for i, ch in enumerate(chunks):
        n = len(chunks)
        _last = {"pct": -1}

        def emit(frac, _i=i, _n=n):
            pct = int((_i + frac) / _n * 100)
            # 单调递增：gradio 多 worker 并行会让 progress_data 乱序波动，只推前进值
            if pct > _last["pct"]:
                _last["pct"] = pct
                print(f"PROGRESS {pct}/100", flush=True)

        print(f"CHUNK {i + 1}/{n} {len(ch)}字", flush=True)
        ap_path = synth_chunk(c, ch, prompt_wav, prompt_text, opts, emit, endpoint)
        if not ap_path:
            print(f"ERROR 合成失败（块 {i + 1}）")
            sys.exit(3)
        tp = str(out) + f".tmp{i}"
        shutil.copy(ap_path, tp)
        tmp_paths.append(tp)
        # 块完成：把整体进度推到该块结束位置
        print(f"PROGRESS {int((i + 1) / n * 100)}/100", flush=True)

    # 拼接 + 0.25s 静音缝
    fr0, ch0, sw0, _ = read_wav(tmp_paths[0])
    silence = b"\x00" * int(fr0 * 0.25) * sw0
    w = wave.open(str(out), "wb")
    w.setnchannels(ch0)
    w.setsampwidth(sw0)
    w.setframerate(fr0)
    for p in tmp_paths:
        _, _, _, data = read_wav(p)
        w.writeframes(data)
        w.writeframes(silence)
    w.close()
    for p in tmp_paths:
        try:
            os.remove(p)
        except Exception:
            pass

    w2 = wave.open(str(out))
    sec = w2.getnframes() / w2.getframerate()
    w2.close()
    print(f"DONE {sec:.2f}", flush=True)


if __name__ == "__main__":
    main()
