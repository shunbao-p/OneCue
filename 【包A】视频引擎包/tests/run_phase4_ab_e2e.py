# -*- coding: utf-8 -*-
"""Target-Mac Phase 4 proof: Package A calls Package B, then builds MP4."""

import argparse
import array
import base64
import hashlib
import http.client
import json
import subprocess
import time
import wave
from pathlib import Path


VOICE = "女播音.wav"
VOICE_TRANSCRIPT = "我相信很多听友听到这首歌应该是在96年90年代的那个夏天"
SYNTH_TEXT = "这是苹果芯片原生金属加速的联合验收语音。包A会把这段语音继续生成竖屏视频。"


def request(port, path, method="GET", payload=None, timeout=60):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    result = response.status, dict(response.getheaders()), raw
    connection.close()
    return result


def json_request(port, path, method="GET", payload=None, timeout=60):
    status, headers, raw = request(port, path, method, payload, timeout)
    parsed = json.loads(raw.decode("utf-8")) if raw else {}
    return status, headers, parsed


def wait_job(port, job_id, timeout=360):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _headers, payload = json_request(port, "/api/status/" + job_id)
        if status == 200 and payload.get("status") in ("done", "error", "stopped"):
            return payload
        time.sleep(0.2)
    raise TimeoutError("任务未在时限内结束：" + job_id)


def download(port, path, target, timeout=120):
    status, _headers, raw = request(port, path, timeout=timeout)
    if status != 200:
        raise AssertionError("下载失败 HTTP %s: %s" % (status, raw[:300]))
    target.write_bytes(raw)
    return target


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_pcm16_wav(path):
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        frames = stream.getnframes()
        raw = stream.readframes(frames)
    if sample_width != 2:
        raise AssertionError("验收脚本只接受 PCM16 WAV，实际 sample_width=%s" % sample_width)
    samples = array.array("h")
    samples.frombytes(raw)
    peak = max((abs(value) for value in samples), default=0)
    clipping = sum(abs(value) >= 32735 for value in samples) / max(1, len(samples))
    duration = frames / float(sample_rate)
    checks = {
        "sample_rate_48000": sample_rate == 48000,
        "mono": channels == 1,
        "duration_over_0_5": duration > 0.5,
        "non_silent": peak > 3,
        "clipping_below_0_1_percent": clipping < 0.001,
    }
    return {
        "path": str(Path(path).resolve()),
        "sha256": sha256(path),
        "bytes": Path(path).stat().st_size,
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "frames": frames,
        "duration_seconds": duration,
        "peak_pcm16": peak,
        "clipping_ratio": clipping,
        "checks": checks,
        "ok": all(checks.values()),
    }


def ffprobe(executable, path):
    command = [
        executable,
        "-v", "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--num-steps", type=int, default=None)
    args = parser.parse_args()

    evidence = args.evidence_dir.expanduser().resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    wav_path = evidence / "package-a-calls-b-mf.wav"
    mp4_path = evidence / "package-a-b-mf-1080x1920.mp4"
    report_path = evidence / "phase4-ab-e2e-report.json"
    report = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "port": args.port,
        "voice": {"name": VOICE, "prompt_text": VOICE_TRANSCRIPT},
        "synthesis_text": SYNTH_TEXT,
        "requested_num_steps": args.num_steps,
        "checks": {},
        "result": "FAIL",
    }

    try:
        health_status, _headers, health = json_request(args.port, "/api/health")
        unknown_status, _headers, unknown = json_request(args.port, "/api/not-a-real-route")
        dots_status, _headers, dots = json_request(args.port, "/api/dots_status")
        voices_status, _headers, voices = json_request(args.port, "/api/tts_voices")
        selected = [item for item in voices.get("voices", []) if item.get("name") == VOICE]
        require(health_status == 200 and health.get("status") == "ok", "包 A 健康检查失败")
        require(unknown_status == 404 and unknown.get("error") == "not found", "未知 API 未返回 404")
        require(dots_status == 200 and dots.get("state") == "ready", "包 B 未处于 ready")
        require(dots.get("compatible") is True and dots.get("api_version") == "dots-tts.synthesize.v1",
                "包 B v1 契约未就绪")
        require(voices_status == 200 and len(selected) == 1, "内置女播音音色不存在或重复")
        require(selected[0].get("prompt_text") == VOICE_TRANSCRIPT, "女播音转写不匹配")
        report["checks"]["services_and_contract"] = {
            "health": health,
            "unknown_http_status": unknown_status,
            "dots": dots,
            "selected_voice": selected[0],
        }

        empty_http, _headers, empty_reply = json_request(
            args.port, "/api/tts", "POST", {"text": "", "voice": VOICE}
        )
        require(empty_http == 200 and empty_reply.get("job_id"), "空文本未进入可追踪任务")
        empty_terminal = wait_job(args.port, empty_reply["job_id"], timeout=30)
        require(empty_terminal.get("status") == "error", "空文本未被拒绝")
        report["checks"]["empty_text_rejected"] = empty_terminal

        tts_started = time.monotonic()
        tts_payload = {"text": SYNTH_TEXT, "voice": VOICE, "seed": 42}
        if args.num_steps is not None:
            tts_payload["num_steps"] = args.num_steps
        tts_http, _headers, tts_reply = json_request(
            args.port,
            "/api/tts",
            "POST",
            tts_payload,
        )
        require(tts_http == 200 and tts_reply.get("job_id"), "包 A 未接受 TTS 任务")
        tts_terminal = wait_job(args.port, tts_reply["job_id"], timeout=360)
        require(tts_terminal.get("status") == "done", "包 A 调包 B 合成失败：%s" % tts_terminal)
        download(args.port, "/api/tts_file/" + tts_reply["job_id"], wav_path)
        wav = inspect_pcm16_wav(wav_path)
        require(wav["ok"], "A+B WAV 媒体门未通过：%s" % wav["checks"])
        report["checks"]["tts"] = {
            "http_status": tts_http,
            "job_id": tts_reply["job_id"],
            "terminal": tts_terminal,
            "wall_seconds": time.monotonic() - tts_started,
            "wav": wav,
        }

        video_started = time.monotonic()
        video_http, _headers, video_reply = json_request(
            args.port,
            "/api/generate",
            "POST",
            {
                "wav_b64": base64.b64encode(wav_path.read_bytes()).decode("ascii"),
                "wav_name": wav_path.name,
                "txt_name": "phase4-ab.txt",
                "txt_text": SYNTH_TEXT,
                "seed": 2,
                "full": True,
                "skip_header": False,
                "crf": "20",
            },
            timeout=120,
        )
        require(video_http == 200 and video_reply.get("job_id"), "包 A 未接受视频任务")
        video_terminal = wait_job(args.port, video_reply["job_id"], timeout=360)
        require(video_terminal.get("status") == "done", "真实 WAV→MP4 失败：%s" % video_terminal)
        download(args.port, "/api/download/" + video_reply["job_id"], mp4_path)
        media = ffprobe(args.ffprobe, mp4_path)
        streams = media.get("streams", [])
        videos = [item for item in streams if item.get("codec_type") == "video"]
        audios = [item for item in streams if item.get("codec_type") == "audio"]
        require(len(videos) == 1 and videos[0].get("codec_name") == "h264", "视频不是单路 H.264")
        require(videos[0].get("width") == 1080 and videos[0].get("height") == 1920,
                "视频不是 1080x1920")
        require(videos[0].get("r_frame_rate") == "25/1", "视频不是 25 fps")
        require(len(audios) == 1 and audios[0].get("codec_name") == "aac", "音频不是单路 AAC")
        require(audios[0].get("sample_rate") == "48000", "MP4 音频不是 48 kHz")
        report["checks"]["video"] = {
            "http_status": video_http,
            "job_id": video_reply["job_id"],
            "terminal": video_terminal,
            "wall_seconds": time.monotonic() - video_started,
            "path": str(mp4_path),
            "bytes": mp4_path.stat().st_size,
            "sha256": sha256(mp4_path),
            "ffprobe": media,
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
