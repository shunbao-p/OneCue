# -*- coding: utf-8 -*-
"""
Kinetic Typography / 抖音爆款风格 竖屏短视频生成器
- 强制对齐：TTS 数字拼接缝(精确锚点) + 自然停顿(分段落细化) + 字符线性内插
- 字幕：ASS 卡拉OK 逐字高亮，超大黑体，纯黑底

可作为脚本运行：
  python kt_video.py --seg 01 --start-key "所以总体讲" --dur 10 --out 测试_10s.mp4
  python kt_video.py --seg 01 --full --skip-header --seed 2 --out 第01段_全片.mp4
也可被导入调用（网页后端用）：
  from kt_video import generate
  generate(wav_path=..., txt_path=..., out=..., on_progress=cb, on_log=cb)
"""
import re, os, sys, json, math, random, argparse, subprocess, threading, shutil, tempfile
from contextlib import contextmanager
from pathlib import Path

# 项目本地库 (jieba 等)
_local_lib = Path(__file__).parent / "pylibs"
if str(_local_lib) not in sys.path and _local_lib.exists():
    sys.path.insert(0, str(_local_lib))
import jieba
# 同目录的 kt_align（网页模式需要现场对齐）
sys.path.insert(0, str(Path(__file__).parent))
import kt_align

# 路径统一由 程序文件/paths.py 解析（可解压到任意位置）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paths as _paths

ROOT     = _paths.MATERIAL_DIR          # 命令行 --seg 模式下的素材目录
OUTDIR   = _paths.OUTPUT_DIR            # 成片输出目录
FFMPEG   = _paths.FFMPEG
FONTSDIR = _paths.FONTSDIR.replace("\\", "/")
FONTNAME = _paths.FONTNAME

W, H, FPS = 1080, 1920, 25

# 三色浅色（沿用需求文档）
LIGHT = ["&H0099EEFF", "&H00FFFFFF", "&H00B0D9FF"]   # ASS 是 &HAABBGGRR: 浅黄/白/浅橙
UNSUNG = "&H00333333"                                 # 未唱读：深灰，高对比

MAX_PER_LINE = 7      # 每行最多字符（决定字号能开多大）
MAX_LINES    = 2      # 每卡最多行数
FONTSIZE     = 128    # 远大于需求文档的 104px

CJK = r'\u4e00-\u9fff\u3400-\u4dbf'


# ---------------- 文本处理 ----------------
def clean_text(t):
    """去掉硬折行造成的伪空格，保留英文/数字之间的真空格"""
    t = t.replace('\u3000', ' ')
    for _ in range(3):
        t = re.sub(rf'(?<=[{CJK}])[ \t]+(?=[{CJK}])', '', t)
        t = re.sub(rf'(?<=[{CJK}])[ \t]+(?=[，。、；：？！“”（）])', '', t)
        t = re.sub(rf'(?<=[，。、；：？！“”（）])[ \t]+(?=[{CJK}])', '', t)
    return re.sub(r'[ \t]{2,}', ' ', t).strip()


def tokenize(t):
    """切成卡拉OK单元：单个汉字 / 连续英数串 / 标点。返回 [(text, weight, is_punct)]"""
    toks, i = [], 0
    while i < len(t):
        c = t[i]
        if re.match(rf'[{CJK}]', c):
            toks.append((c, 1.0, False)); i += 1
        elif re.match(r'[A-Za-z0-9]', c):
            j = i
            while j < len(t) and re.match(r'[A-Za-z0-9.]', t[j]):
                j += 1
            run = t[i:j]
            toks.append((run, max(1.0, len(run) * 0.55), False)); i = j
        elif c in ' \t':
            i += 1
        else:
            toks.append((c, 0.0, True)); i += 1   # 标点不占时长
    return toks


# ---------------- 静音检测 ----------------
def detect_pauses(wav, noise="-45dB", d=0.08):
    ffmpeg = _paths.resolve_ffmpeg(required=True)
    cmd = [ffmpeg, "-hide_banner", "-i", str(wav), "-af",
           f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    out = p.stderr + p.stdout
    if p.returncode != 0:
        raise RuntimeError("ffmpeg 静音检测失败: " + (out[-2000:] if out.strip() else "未知错误"))
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", out)]
    ends   = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", out)]
    return list(zip(starts, ends))[:min(len(starts), len(ends))]


# ---------------- 核心：构建逐字时间轴 ----------------
def build_timeline(align, pauses):
    timeline = []
    sent_id = 0
    for ck in align["chunks"]:
        c0, c1 = ck["start"], ck["end"]
        text = clean_text(ck["text"])

        parts = [s for s in re.split(r'(?<=[。！？])', text) if s.strip()]
        if not parts:
            continue
        toks_per = [tokenize(s) for s in parts]
        wts = [sum(w for _, w, _ in ts) for ts in toks_per]
        totw = sum(wts) or 1.0

        bounds, acc = [c0], 0.0
        for w in wts[:-1]:
            acc += w
            bounds.append(c0 + (c1 - c0) * acc / totw)
        bounds.append(c1)

        inner = [(a, b) for a, b in pauses if c0 + 0.35 < a and b < c1 - 0.35]
        used = set()
        for bi in range(1, len(bounds) - 1):
            pred = bounds[bi]
            best, bestd = None, 1.10
            for pi, (a, b) in enumerate(inner):
                if pi in used:
                    continue
                mid = (a + b) / 2
                if abs(mid - pred) < bestd:
                    best, bestd = pi, abs(mid - pred)
            if best is not None:
                a, b = inner[best]
                snap = (a + b) / 2
                if bounds[bi - 1] + 0.25 < snap < bounds[bi + 1] - 0.25:
                    bounds[bi] = snap
                    used.add(best)

        for si, ts in enumerate(toks_per):
            s0, s1 = bounds[si], bounds[si + 1]
            sw = sum(w for _, w, _ in ts) or 1.0
            acc = 0.0
            for txt, w, isp in ts:
                t0 = s0 + (s1 - s0) * acc / sw
                acc += w
                t1 = s0 + (s1 - s0) * acc / sw
                timeline.append([txt, t0, t1, isp, sent_id])
            sent_id += 1
    return timeline


# ---------------- 组卡片 ----------------
NO_START = '个们的了着过地得里上下中间时候样儿点些么吗呢啊吧和与或者'
NO_END   = '一这那每某很非不太最都也还就又更第各另所被把将对从向於于和与'


def vlen(tk):
    if tk[3]:
        return 0
    return 1 if len(tk[0]) == 1 else max(1, math.ceil(len(tk[0]) * 0.6))


def _char_offsets(toks):
    off = [0]
    for t in toks:
        off.append(off[-1] + len(t[0]))
    return off


def _jieba_full_boundaries(toks):
    s = "".join(t[0] for t in toks)
    good = {0, len(s)}
    pos = 0
    for w in jieba.cut(s):
        pos += len(w)
        good.add(pos)
    return good


def _token_at_off(off, target):
    for idx in range(1, len(off)):
        if off[idx] >= target:
            return idx
    return len(off) - 1


def _find_break(toks, i, j, full_good):
    off = _char_offsets(toks)
    target = off[j]
    best_off, best_k = -1, None
    for boundary in full_good:
        if i == 0 and boundary == 0:
            continue
        if boundary > target:
            continue
        k = _token_at_off(off, boundary)
        if k <= i or k > j:
            continue
        if k == j and boundary != target:
            continue
        prev_c = toks[k - 1][0][-1]
        next_c = toks[k][0][0]
        if prev_c in NO_END or next_c in NO_START:
            continue
        if boundary > best_off:
            best_off, best_k = boundary, k
    if best_k is not None:
        return best_k
    sub_good = _jieba_full_boundaries(toks[i:j])
    for k in range(j, i, -1):
        if _char_offsets(toks[i:j])[k - i] in sub_good:
            return k
    return j


def split_smart(toks, cap):
    if not toks:
        return []
    full_good = _jieba_full_boundaries(toks)
    out, i = [], 0
    while i < len(toks):
        n, j = 0, i
        while j < len(toks):
            v = vlen(toks[j])
            if n + v > cap:
                break
            n += v; j += 1
        if j >= len(toks):
            out.append(toks[i:]); break
        k = _find_break(toks, i, j, full_good)
        if k - i < cap * 0.55:
            k = j
        while k < len(toks) and toks[k][3]:
            k += 1
        if k <= i:
            k = i + 1
        out.append(toks[i:k]); i = k
    return out


def build_cards(timeline):
    cap = MAX_PER_LINE * MAX_LINES
    sents, cur, cur_sent = [], [], None
    for tk in timeline:
        if cur_sent is not None and tk[4] != cur_sent:
            sents.append(cur); cur = []
        cur_sent = tk[4]
        if tk[3] and not cur:
            continue
        cur.append(tk)
    if cur:
        sents.append(cur)

    cards = []
    for s in sents:
        cards.extend(split_smart(s, cap))
    return [c for c in cards if any(not t[3] for t in c)]


def layout_lines(toks):
    lines, cur, n = [], [], 0
    for tk in toks:
        txt, _, _, isp, _ = tk
        wlen = 0 if isp else (1 if len(txt) == 1 else max(1, math.ceil(len(txt) * 0.6)))
        if n + wlen > MAX_PER_LINE and cur:
            lines.append(cur); cur, n = [], 0
        cur.append(tk); n += wlen
    if cur:
        lines.append(cur)
    return lines


# ---------------- 重音词识别 ----------------
EMPH_WORDS = {'非常','最大','善意','人类','有用','金钱','世界','好事','真正',
              '核心','关键','重要','了不起','我们','价值','意义','未来','改变',
              '突破','力量','希望','梦想','相信','坚持','热爱','自由','美好',
              '大','对'}
EMPH_BOOST = 18
VERT_FRAC  = 0.32
# 旋转收紧：减小包围盒膨胀，降低出画概率（原 15 / 10）
ROT_H      = 10
ROT_V      = 7
# ---- 手机安全区（适配 iPhone 17 Pro Max / 抖音 / 视频号 9:16 全屏裁切）----
# iPhone 17 Pro Max 物理分辨率 1320x2868(≈19.5:9)，1080x1920 视频全屏会被上下裁切，
# 故安全区留足余量，保证字幕不被灵动岛/状态栏/底部手势条遮挡。
SAFE_TOP    = 230
SAFE_BOTTOM = 210
SAFE_SIDE   = 80
ROLL_IN     = 90   # 字幕从下方滚入的位移（竖版动态字幕轮动进入效果）


def compute_emphasis(joined):
    words = list(jieba.cut(joined))
    cand, pos = [], 0
    for w in words:
        if not w.strip():
            pos += len(w); continue
        is_cjk = re.match(rf'[{CJK}]', w)
        if len(w) >= 2 and is_cjk:
            score = len(w)
            if w in EMPH_WORDS:
                score += 3
            cand.append((score, pos, pos + len(w)))
        pos += len(w)
    cand.sort(reverse=True)
    return [(s, e) for _, s, e in cand[:2]]


# ---------------- ASS 生成 ----------------
def _rot_box(w, h, ang):
    """旋转 ang 度后的真实包围盒（用于安全区 clamp，避免出画）"""
    a = math.radians(ang)
    rw = abs(w * math.cos(a)) + abs(h * math.sin(a))
    rh = abs(w * math.sin(a)) + abs(h * math.cos(a))
    return rw, rh



def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc(s):
    return s.replace('\\', '').replace('{', '(').replace('}', ')')


DISPLAY_DROP = '，。、；：'


def make_ass(cards, offset=0.0, tmax=None, seed=7):
    rnd = random.Random(seed)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KT0,{FONTNAME},{FONTSIZE},{LIGHT[0]},{UNSUNG},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,8,5,60,60,60,1
Style: KT1,{FONTNAME},{FONTSIZE},{LIGHT[1]},{UNSUNG},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,8,5,60,60,60,1
Style: KT2,{FONTNAME},{FONTSIZE},{LIGHT[2]},{UNSUNG},&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,8,5,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines_out = []
    for ci, card in enumerate(cards):
        real = [t for t in card if not t[3]]
        if not real:
            continue
        t0 = real[0][1] - offset
        t1 = real[-1][2] - offset
        if tmax is not None and (t1 <= 0 or t0 >= tmax):
            continue
        t0 = max(0.0, t0)
        if tmax is not None:
            t1 = min(t1, tmax)
        if t1 - t0 < 0.08:
            continue

        joined = "".join(t[0] for t in real)
        emph_ranges = compute_emphasis(joined)
        emph = set()
        for s, e in emph_ranges:
            emph.update(range(s, e))

        orient = 'v' if rnd.random() < VERT_FRAC else 'h'
        if orient == 'v' and len(joined) > MAX_PER_LINE:
            orient = 'h'
        card_font = FONTSIZE + 2 - rnd.randint(0, 2)
        style_name = f"KT{rnd.randrange(len(LIGHT))}"

        # 方向 + 旋转（旋转已收紧，减小包围盒膨胀）
        if orient == 'v':
            an = 8
            rot = rnd.uniform(-ROT_V, ROT_V)
            n_units = len(real)
        else:
            an = 5
            rot = rnd.uniform(-ROT_H, ROT_H)
            lines = layout_lines(card)
            n_lines = len(lines)
            max_line_chars = max(sum(len(t[0]) for t in ln) for ln in lines)

        # 未旋转包围盒
        def _bw():
            if orient == 'v':
                return card_font * 1.25, n_units * card_font * 1.15
            return (max_line_chars * card_font * 1.05 + max(0, max_line_chars - 1) * 2,
                    n_lines * card_font * 1.15)
        box_w, box_h = _bw()
        rw, rh = _rot_box(box_w, box_h, rot)

        # 放不下则按比例缩小字号，确保旋转后仍完全落在手机安全区内
        avail_w = W - 2 * SAFE_SIDE
        avail_h = H - SAFE_TOP - SAFE_BOTTOM
        if rw > avail_w or rh > avail_h:
            sc = min(avail_w / rw, avail_h / rh) * 0.96
            card_font = int(max(48, card_font * sc))
            box_w, box_h = _bw()
            rw, rh = _rot_box(box_w, box_h, rot)

        # 落点 clamp：旋转后包围盒完全落在安全区内（不出画、不被刘海/手势条遮挡）
        half_rw, half_rh = rw / 2.0, rh / 2.0
        x_lo = SAFE_SIDE + half_rw
        x_hi = W - SAFE_SIDE - half_rw
        y_lo = SAFE_TOP + half_rh
        y_hi = H - SAFE_BOTTOM - half_rh
        if x_lo > x_hi: x_lo = x_hi = W / 2.0
        if y_lo > y_hi: y_lo = y_hi = H / 2.0
        x = int(rnd.uniform(x_lo, x_hi))
        y = int(rnd.uniform(y_lo, y_hi))

        emph_flag = [False] * len(joined)
        for c in emph:
            emph_flag[c] = True
        szmap, run_np = {}, 0
        for tk in card:
            if tk[3]:
                szmap[id(tk)] = card_font
            else:
                s = run_np; run_np += len(tk[0])
                szmap[id(tk)] = card_font + (EMPH_BOOST if any(emph_flag[s:s + len(tk[0])]) else 0)

        parts, prev_end = [], real[0][1]
        if orient == 'v':
            for tk in real:
                txt, a, b, isp, _ = tk
                sz = szmap[id(tk)]
                if isp:
                    if txt in DISPLAY_DROP:
                        continue
                    parts.append(r"{\fs%d}%s" % (sz, esc(txt)))
                else:
                    k = max(1, int(round((b - prev_end) * 100)))
                    prev_end = b
                    parts.append(r"{\k%d\fs%d}%s" % (k, sz, esc(txt)))
                parts.append(r"\N")
            if parts and parts[-1] == r"\N":
                parts.pop()
        else:
            for li, ln in enumerate(layout_lines(card)):
                if li:
                    parts.append(r"\N")
                for tk in ln:
                    txt, a, b, isp, _ = tk
                    sz = szmap[id(tk)]
                    if isp:
                        if txt in DISPLAY_DROP:
                            continue
                        parts.append(r"{\fs%d}%s" % (sz, esc(txt)))
                    else:
                        k = max(1, int(round((b - prev_end) * 100)))
                        prev_end = b
                        parts.append(r"{\k%d\fs%d}%s" % (k, sz, esc(txt)))

        body = "".join(parts)
        ov = (r"{\an%d\move(%d,%d,%d,%d,0,180)\frz%.1f\fad(70,160)"
              r"\t(0,110,\fscx104\fscy104)\t(110,220,\fscx100\fscy100)}"
              % (an, x, y + ROLL_IN, x, y, rot))
        lines_out.append(f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},{style_name},,0,0,0,,{ov}{body}")
    return head + "\n".join(lines_out) + "\n"


# ---------------- ffmpeg 渲染（带实时进度回调） ----------------
def _staged_filter_atom(value):
    """只接受暂存区内的安全相对名，避免 libavfilter 多层路径转义。"""
    value = os.fspath(value)
    parts = Path(value).parts
    if (not value or Path(value).is_absolute() or ".." in parts
            or not re.fullmatch(r"[A-Za-z0-9._/-]+", value)):
        raise ValueError("字幕过滤器路径必须先进入安全暂存目录")
    return "'" + value + "'"


@contextmanager
def stage_render_assets(ass_path, fonts_dir, font_file="simhei.ttf"):
    """把字幕和包内字体复制到安全短名暂存区，源路径可以含任意常见字符。"""
    ass_path = Path(ass_path).resolve()
    font_path = (Path(fonts_dir).resolve() / font_file)
    if not ass_path.is_file():
        raise FileNotFoundError("字幕文件不存在: " + str(ass_path))
    if not font_path.is_file():
        raise FileNotFoundError("字体文件不存在: " + str(font_path))
    with tempfile.TemporaryDirectory(prefix="package-a-render-") as directory:
        stage = Path(directory)
        staged_fonts = stage / "fonts"
        staged_fonts.mkdir()
        shutil.copy2(str(ass_path), str(stage / "subtitle.ass"))
        shutil.copy2(str(font_path), str(staged_fonts / font_path.name))
        yield stage, "subtitle.ass", "fonts"


def build_ffmpeg_environment(base_env=None, font_env=None):
    """从平台字体配置生成子进程环境，不让遗留 Windows Fontconfig 污染 Mac。"""
    env = dict(os.environ if base_env is None else base_env)
    env.pop("FONTCONFIG_PATH", None)
    env.update(_paths.FONT_ENV if font_env is None else font_env)
    return env


def build_ffmpeg_command(ffmpeg, ass_path, wav_path, out_path, fonts_dir,
                         start, dur, crf="20"):
    """构造可直接交给 ``subprocess`` 的 FFmpeg 参数列表。"""
    if not str(ffmpeg).strip():
        raise ValueError("ffmpeg 路径不能为空")
    start = float(start)
    dur = float(dur)
    if start < 0:
        raise ValueError("起始时间不能为负数")
    if dur <= 0:
        raise ValueError("渲染时长必须大于 0")
    try:
        crf_value = int(str(crf))
    except (TypeError, ValueError):
        raise ValueError("CRF 必须是 0..51 的整数")
    if not 0 <= crf_value <= 51:
        raise ValueError("CRF 必须是 0..51 的整数")

    vf = "subtitles=filename=%s:fontsdir=%s" % (
        _staged_filter_atom(ass_path),
        _staged_filter_atom(fonts_dir),
    )
    wav_path = Path(wav_path).resolve()
    out_path = Path(out_path).resolve()
    return [str(ffmpeg), "-y", "-progress", "pipe:1", "-nostats",
           "-hide_banner",
           "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}",
           "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(wav_path),
           "-filter_complex", f"[0:v]{vf}[v]",
           "-map", "[v]", "-map", "1:a",
           "-t", f"{dur:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(crf_value),
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", str(out_path)]


def _terminate_render_process(proc, timeout=3.0):
    """Best-effort cross-platform FFmpeg shutdown without shell commands."""
    try:
        if proc.poll() is not None:
            return
    except AttributeError:
        return
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
        return
    except (subprocess.TimeoutExpired, TypeError):
        pass
    except Exception:
        pass
    try:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=timeout)
    except Exception:
        pass


def render_video(ass_path, wav_path, out_path, start, dur, crf="20",
                 on_progress=None, on_log=None, cancel_event=None,
                 on_process=None):
    ffmpeg = _paths.resolve_ffmpeg(required=True)
    env = build_ffmpeg_environment(font_env=_paths.FONT_ENV)
    font_file = _paths.FONT_CONFIG.get("font_file", "simhei.ttf")
    with stage_render_assets(ass_path, _paths.FONTSDIR, font_file) as staged:
        stage, staged_ass, staged_fonts = staged
        cmd = build_ffmpeg_command(
            ffmpeg, staged_ass, wav_path, out_path, staged_fonts,
            start, dur, crf=crf,
        )

        if on_log:
            on_log("渲染中 ...")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=str(stage), text=True, errors="replace", bufsize=1,
        )

        if on_process:
            on_process(proc)

        err_buf = []
        def drain_stderr():
            for line in proc.stderr:
                err_buf.append(line)
        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stderr_thread.start()

        info = {"frame": 0, "fps": 0.0, "speed": 0.0}
        cur_ms = 0.0
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("__STOPPED__")
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("frame="):
                    try: info["frame"] = int(line.split("=")[1])
                    except: pass
                elif line.startswith("fps="):
                    try: info["fps"] = float(line.split("=")[1])
                    except: pass
                elif line.startswith("out_time_ms="):
                    try: cur_ms = int(line.split("=")[1])
                    except: pass
                elif line.startswith("speed="):
                    try: info["speed"] = float(line.split("=")[1].replace("x", ""))
                    except: pass
                elif line.startswith("progress="):
                    state = line.split("=")[1]
                    if state == "end":
                        if on_progress:
                            on_progress(100.0, {"frame": info["frame"], "fps": info["fps"],
                                               "speed": info["speed"], "eta": 0.0})
                    else:
                        out_sec = cur_ms / 1_000_000.0
                        pct = min(100.0, (out_sec / dur) * 100.0) if dur > 0 else 0.0
                        eta = (dur - out_sec) / info["speed"] if info["speed"] > 0 else None
                        if on_progress:
                            on_progress(pct, {"frame": info["frame"], "fps": info["fps"],
                                             "speed": info["speed"], "eta": eta})

            proc.wait()
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("__STOPPED__")
            if proc.returncode != 0:
                err = "".join(err_buf)
                raise RuntimeError("ffmpeg 失败: " + (err[-2000:] if err.strip() else "未知错误（无 stderr 输出）"))
        except BaseException:
            _terminate_render_process(proc)
            raise
        finally:
            stderr_thread.join(timeout=1)
            if on_process:
                on_process(None)
    if on_log:
        on_log(f"✅ 输出 {out_path}  ({Path(out_path).stat().st_size/1048576:.2f} MB)")
    return out_path


# ---------------- 统一入口（脚本 / 网页共用） ----------------
def generate(wav_path=None, txt_path=None, seg=None, align=None, out=None,
             start=None, start_key=None, dur=10.0, full=False, skip_header=False,
             seed=7, crf="20", on_progress=None, on_log=None,
             work_dir=None, cancel_event=None, on_process=None):
    def log(m):
        if on_log: on_log(m)
        else: print(m)

    # 解析输入
    if wav_path and txt_path:
        wav = Path(wav_path); txt = Path(txt_path)
    elif seg:
        wav = ROOT / f"{seg}.wav"
        txt = ROOT / f"{seg}.txt"
    else:
        raise ValueError("必须提供 wav_path+txt_path 或 seg")

    # 对齐
    if align is None:
        if seg:
            align = json.loads((_paths.WORK_DIR / f"align_{seg}.json").read_text(encoding="utf-8"))
            if not align.get("matched"):
                raise ValueError("对齐未匹配，先跑 kt_align.py")
        else:
            log("现场强制对齐 ...")
            align = kt_align.run_align(wav, txt)

    if align.get("matched") is False:
        raise ValueError(
            "音频与文本块数不匹配：检测到 %s 个音频块、%s 个文本块。"
            "请确认文稿分块与配音中的 0.25 秒拼接静音一致。"
            % (align.get("n_audio_spans", "?"), align.get("n_text_chunks", "?"))
        )

    log("检测自然停顿 ...")
    pauses = detect_pauses(wav)
    log(f"  停顿 {len(pauses)} 处")

    tl = build_timeline(align, pauses)
    cards = build_cards(tl)
    log(f"字幕卡 {len(cards)} 张")

    # 起点
    st = 0.0
    if start is not None:
        st = start
    elif start_key:
        key = clean_text(start_key)
        for c in cards:
            s = "".join(t[0] for t in c if not t[3])
            if key in s or s.startswith(key[:4]):
                st = c[0][1]; break
        else:
            raise SystemExit(f"找不到关键词 {start_key}")
    elif skip_header:
        st = align["chunks"][1]["start"]

    if dur is not None and dur <= 0:
        dur = None                      # 0/负数视为“整段全片”
    if full:
        dur = align["audio_sec"] - st
    elif dur is None:
        dur = align["audio_sec"] - st  # 时长留空 -> 整段
    st = max(0.0, st)

    out = Path(out) if out else (OUTDIR / f"第{seg or 'x'}段_{'全片' if full else f'测试{int(dur)}s'}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    ass_dir = Path(work_dir) if work_dir is not None else _paths.WORK_DIR
    ass_dir.mkdir(parents=True, exist_ok=True)
    ass = ass_dir / f"kt_{(seg or 'x')}.ass"
    ass.write_text(make_ass(cards, offset=st, tmax=dur, seed=seed), encoding="utf-8")
    n_ev = sum(1 for l in ass.read_text(encoding='utf-8').splitlines() if l.startswith("Dialogue"))
    log(f"ASS 事件 {n_ev} 条 -> {ass}")
    log(f"区间 {st:.2f}s ~ {st+dur:.2f}s")

    render_video(
        ass, wav, out, st, dur, crf=crf, on_progress=on_progress, on_log=log,
        cancel_event=cancel_event, on_process=on_process,
    )
    return str(out)


# ---------------- 命令行 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seg", default="01")
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--start-key", default=None)
    ap.add_argument("--dur", type=float, default=10.0)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--skip-header", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--crf", default="20")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    # 预览前几张卡，供人工核对
    out = generate(seg=a.seg, out=a.out, start=a.start, start_key=a.start_key,
                   dur=a.dur, full=a.full, skip_header=a.skip_header,
                   seed=a.seed, crf=a.crf)
    print(f"\n成品: {out}")


if __name__ == "__main__":
    main()
