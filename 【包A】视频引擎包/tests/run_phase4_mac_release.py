# -*- coding: utf-8 -*-
"""Validate an extracted Phase 4 release through its real HTTP service."""

import argparse
import hashlib
import http.client
import json
import time
import uuid
from pathlib import Path
import subprocess


def request(port, path, method="GET", body=None, headers=None, timeout=60):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    result = response.status, dict(response.getheaders()), payload
    connection.close()
    return result


def json_request(port, path, method="GET", payload=None):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    status, response_headers, raw = request(port, path, method, body, headers)
    return status, response_headers, json.loads(raw.decode("utf-8")) if raw else {}


def multipart(wav_bytes, text):
    boundary = "package-a-phase4-" + uuid.uuid4().hex
    marker = ("--" + boundary).encode("ascii")
    fields = {
        "txt": text.encode("utf-8"), "wav_name": b"one_block.wav",
        "txt_name": b"one_block.txt", "seed": b"2", "full": b"true",
        "skip_header": b"false", "dur": b"", "crf": b"20",
    }
    chunks = []
    for name, value in fields.items():
        chunks.extend([marker, ('Content-Disposition: form-data; name="%s"' % name).encode("ascii"), b"", value])
    chunks.extend([
        marker, b'Content-Disposition: form-data; name="wav"; filename="one_block.wav"',
        b"Content-Type: audio/wav", b"", wav_bytes, marker + b"--", b"",
    ])
    return b"\r\n".join(chunks), boundary


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--wav", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args()
    root = Path(args.package_root).resolve()
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    port = int((root / "程序文件/网站/.port").read_text(encoding="utf-8").strip())
    ffprobe = root / "程序文件/bin/ffprobe"
    report = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "port": port, "checks": {}}
    try:
        health_status, _headers, health = json_request(port, "/api/health")
        require(health_status == 200 and health.get("port") == port, "health/port mismatch")
        dots_status, _headers, dots = json_request(port, "/api/dots_status")
        tts_status, _headers, tts = json_request(port, "/api/tts", "POST", {"text": "测试", "voice": ""})
        require(dots_status == 200 and dots.get("state") == "not_installed", "Package B state changed")
        require(tts_status == 503 and "未检测到语音引擎" in tts.get("error", ""), "TTS rejection unclear")
        report["checks"]["health_and_package_b"] = {"health": health, "dots": dots, "tts_status": tts_status}

        body, boundary = multipart(Path(args.wav).read_bytes(), "你好，世界。")
        status, _headers, raw = request(
            port, "/api/generate", "POST", body,
            {"Content-Type": "multipart/form-data; boundary=" + boundary},
        )
        require(status == 200, "generate HTTP %s" % status)
        job = json.loads(raw.decode("utf-8"))["job_id"]
        deadline = time.monotonic() + 180
        terminal = None
        while time.monotonic() < deadline:
            job_status, _headers, payload = json_request(port, "/api/status/" + job)
            if job_status == 200 and payload.get("status") in ("done", "error", "stopped"):
                terminal = payload
                break
            time.sleep(0.1)
        require(terminal and terminal.get("status") == "done", "video job failed: %r" % terminal)
        download_status, _headers, movie = request(port, "/api/download/" + job, timeout=90)
        require(download_status == 200 and movie, "download failed")
        movie_path = evidence / "phase4-release-output.mp4"
        movie_path.write_bytes(movie)
        probe = subprocess.run([
            str(ffprobe), "-v", "error", "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
            "-of", "json", str(movie_path),
        ], check=True, capture_output=True, text=True)
        media = json.loads(probe.stdout)
        streams = media["streams"]
        video = next(item for item in streams if item["codec_type"] == "video")
        audio = next(item for item in streams if item["codec_type"] == "audio")
        require(video["codec_name"] == "h264", "video codec is not H.264")
        require((video["width"], video["height"]) == (1080, 1920), "video geometry changed")
        require(video["r_frame_rate"] == "25/1", "frame rate changed")
        require(audio["codec_name"] == "aac" and audio["sample_rate"] == "48000", "audio contract changed")
        report["checks"]["real_video"] = {
            "job_id": job, "terminal": terminal, "bytes": len(movie),
            "sha256": sha256(movie_path), "ffprobe": media,
        }
        report["result"] = "pass"
    except Exception as exc:
        report["result"] = "fail"
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        output = evidence / "phase4-release-http-report.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
