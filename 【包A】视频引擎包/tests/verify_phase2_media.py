# -*- coding: utf-8 -*-
"""使用 ffprobe 验证 Phase 2 媒体契约，并保存机器可读报告。"""

import argparse
import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(ffprobe, media):
    command = [
        str(ffprobe), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(media),
    ]
    result = subprocess.run(command, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise RuntimeError("ffprobe 失败: " + (result.stderr[-2000:] or "无 stderr"))
    return command, json.loads(result.stdout)


def verify(data, expected_duration, tolerance):
    videos = [item for item in data.get("streams", []) if item.get("codec_type") == "video"]
    audios = [item for item in data.get("streams", []) if item.get("codec_type") == "audio"]
    errors = []
    if len(videos) != 1:
        errors.append("视频流数应为 1")
    if len(audios) != 1:
        errors.append("音频流数应为 1")
    video = videos[0] if videos else {}
    audio = audios[0] if audios else {}
    if video.get("codec_name") != "h264":
        errors.append("视频编码不是 H.264")
    if (video.get("width"), video.get("height")) != (1080, 1920):
        errors.append("分辨率不是 1080x1920")
    try:
        rate = float(Fraction(video.get("avg_frame_rate", "0/1")))
    except (ValueError, ZeroDivisionError):
        rate = 0.0
    if abs(rate - 25.0) > 0.001:
        errors.append("帧率不是 25 fps")
    if audio.get("codec_name") != "aac":
        errors.append("音频编码不是 AAC")
    if str(audio.get("sample_rate")) != "48000":
        errors.append("音频采样率不是 48000 Hz")
    actual_duration = float(data.get("format", {}).get("duration", 0.0))
    duration_error = abs(actual_duration - float(expected_duration))
    if duration_error > float(tolerance):
        errors.append("时长误差超过 %.3f 秒" % float(tolerance))
    return {
        "passed": not errors,
        "errors": errors,
        "video": {
            "codec": video.get("codec_name"),
            "profile": video.get("profile"),
            "width": video.get("width"),
            "height": video.get("height"),
            "avg_frame_rate": video.get("avg_frame_rate"),
            "pix_fmt": video.get("pix_fmt"),
        },
        "audio": {
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
        },
        "expected_duration": float(expected_duration),
        "actual_duration": actual_duration,
        "duration_error": duration_error,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--media", required=True)
    parser.add_argument("--expected-duration", type=float, required=True)
    parser.add_argument("--tolerance", type=float, default=0.25)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    media = Path(args.media).resolve()
    command, raw = probe(args.ffprobe, media)
    summary = verify(raw, args.expected_duration, args.tolerance)
    report = {
        "command": command,
        "media": str(media),
        "media_bytes": media.stat().st_size,
        "media_sha256": sha256(media),
        "summary": summary,
        "raw": raw,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
