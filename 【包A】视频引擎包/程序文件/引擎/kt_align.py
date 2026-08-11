# -*- coding: utf-8 -*-
"""
强制对齐分析器：复现 run_campaign.py 的 TTS 切块逻辑，
用「精确数字静音」定位块边界，得到文本块 <-> 音频时间的精确锚点。
输出 align_XX.json

可作为脚本运行：  python kt_align.py 01
也可被导入调用：  from kt_align import run_align
"""
import re, sys, json, wave
from pathlib import Path

# 路径统一由 程序文件/paths.py 解析（可解压到任意位置）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paths as _paths
ROOT = _paths.MATERIAL_DIR


# ---------- 1. 完全复刻 run_campaign.py 的文本处理 ----------
def build_chunks(raw, chunk=200):
    text = " ".join(l.strip() for l in raw.splitlines() if l.strip())
    sents = [s.strip() for s in re.split(r'(?<=[。！？；])', text) if s.strip()]
    chunks, cur = [], ""
    for s in sents:
        if cur and len(cur) + len(s) > chunk:
            chunks.append(cur); cur = s
        else:
            cur += s
    if cur:
        chunks.append(cur)
    return text, chunks


def run_align(wav_path, txt_path, out_path=None, chunk=200):
    """对单个 (wav, txt) 做强制对齐，返回 align dict；out_path 非空则写出 json。"""
    wav_path = Path(wav_path)
    txt_path = Path(txt_path)
    raw = txt_path.read_text(encoding="utf-8")
    full_text, chunks = build_chunks(raw, chunk)

    # ---------- 2. 读音频，找「精确零值静音」= 拼接缝 ----------
    w = wave.open(str(wav_path))
    fr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    data = w.readframes(n)
    w.close()
    total_sec = n / fr
    bps = sw * ch                      # bytes per sample-frame
    pad_frames = int(fr * 0.25)        # 拼接时插入的静音帧数
    pat = b"\x00" * (pad_frames * bps) # 0.25s 纯零

    # 用 bytes.find 以 C 速度扫描
    joins = []   # (run_start_frame, run_end_frame)
    pos = 0
    while True:
        idx = data.find(pat, pos)
        if idx < 0:
            break
        probe = idx + (-idx) % bps
        start_b = probe
        while start_b - bps >= 0 and data[start_b - bps:start_b] == b"\x00" * bps:
            start_b -= bps
        end_b = probe
        while end_b + bps <= len(data) and data[end_b:end_b + bps] == b"\x00" * bps:
            end_b += bps
        joins.append((start_b // bps, end_b // bps))
        pos = end_b if end_b > idx else idx + len(pat)

    # 去重合并
    merged = []
    for s, e in joins:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    joins = merged

    print(f"[段] 音频 {total_sec:.2f}s | 文本 {len(full_text)}字 | 预期块 {len(chunks)} | 检出数字静音 {len(joins)}")
    for i, (s, e) in enumerate(joins):
        print(f"   缝{i:02d}: {s/fr:8.3f}s -> {e/fr:8.3f}s  (时长 {(e-s)/fr:.3f}s)")

    # ---------- 3. 由缝切出块的音频区间 ----------
    spans = []
    prev_end = 0
    for s, e in joins:
        spans.append((prev_end / fr, s / fr))
        prev_end = e
    spans.append((prev_end / fr, n / fr))
    # 末尾那段 0.25s 静音是拼接循环给最后一块补的，会产生一个空 span，剔除
    spans = [(a, b) for a, b in spans if b - a > 0.05]

    ok = (len(spans) == len(chunks))
    print(f"\n切出音频块 {len(spans)} 个 (文本块 {len(chunks)} 个) -> {'✅ 匹配' if ok else '❌ 不匹配'}")

    result = {
        "seg": Path(txt_path).stem, "audio_sec": total_sec, "framerate": fr,
        "n_text_chunks": len(chunks), "n_audio_spans": len(spans),
        "matched": ok, "chunks": []
    }
    if ok:
        for i, (c, (a, b)) in enumerate(zip(chunks, spans)):
            dur = b - a
            cps = len(c) / dur if dur > 0 else 0
            result["chunks"].append({"i": i, "start": round(a, 3), "end": round(b, 3),
                                     "dur": round(dur, 3), "chars": len(c),
                                     "cps": round(cps, 2), "text": c})
            print(f"  块{i:02d} {a:7.2f}-{b:7.2f}s ({dur:6.2f}s) {len(c):4d}字 {cps:5.2f}字/秒 | {c[:34]}")

    if out_path:
        Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已写出 {out_path}")
    return result


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "01"
    wav = ROOT / f"{seg}.wav"
    txt = ROOT / f"{seg}.txt"
    out = _paths.WORK_DIR / f"align_{seg}.json"
    run_align(wav, txt, out)


if __name__ == "__main__":
    main()
