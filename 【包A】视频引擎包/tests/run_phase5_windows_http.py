# -*- coding: utf-8 -*-
"""Small real HTTP/download regression for Package A on Windows."""

import base64
import hashlib
import http.client
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
PROG = ROOT / "程序文件"
for path in (PROG, PROG / "引擎", PROG / "网站"):
    sys.path.insert(0, str(path))

import kt_web  # noqa: E402


def request(port, path, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    data = response.read()
    result = response.status, dict(response.getheaders()), data
    connection.close()
    return result


def json_request(port, path, method="GET", payload=None, raw=None):
    body = raw
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    status, response_headers, data = request(port, path, method, body, headers)
    return status, response_headers, json.loads(data.decode("utf-8")) if data else {}


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    evidence = TESTS / "evidence" / "phase5-windows-http"
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}}
    with tempfile.TemporaryDirectory(prefix="package-a-phase5-windows-") as temp:
        temp_root = Path(temp)
        kt_web.WORK = temp_root / "work"
        kt_web.OUTDIR = temp_root / "output"
        kt_web.WORK.mkdir()
        kt_web.OUTDIR.mkdir()
        with kt_web.jobs_lock:
            kt_web.jobs.clear()
        server = kt_web.create_server("127.0.0.1", 0)
        port = server.server_address[1]
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            malformed, _headers, malformed_body = json_request(
                port, "/api/generate", "POST", raw=b"{"
            )
            require(malformed == 400 and "JSON" in malformed_body.get("error", ""), "malformed JSON contract")
            dots_status, _headers, dots = json_request(port, "/api/dots_status")
            tts_status, _headers, tts = json_request(
                port, "/api/tts", "POST", payload={"text": "测试", "voice": ""}
            )
            require(dots_status == 200 and dots.get("state") == "not_installed", "Package B state")
            require(tts_status == 503 and "未检测到语音引擎" in tts.get("error", ""), "TTS rejection")
            report["checks"]["boundaries"] = {
                "malformed_status": malformed,
                "dots": dots,
                "tts_status": tts_status,
            }

            wav = (TESTS / "fixtures" / "one_block.wav").read_bytes()
            payload = {
                "wav_b64": base64.b64encode(wav).decode("ascii"),
                "txt_text": "Windows Web 下载验收。",
                "wav_name": "中文 空格.wav",
                "txt_name": "中文 空格.txt",
                "full": True,
                "seed": "2",
                "crf": "20",
            }
            status, _headers, reply = json_request(port, "/api/generate", "POST", payload=payload)
            require(status == 200 and reply.get("job_id"), "generate submit")
            job = reply["job_id"]
            deadline = time.monotonic() + 180
            terminal = None
            while time.monotonic() < deadline:
                _status, _headers, terminal = json_request(port, "/api/status/" + job)
                if terminal.get("status") in ("done", "error", "stopped"):
                    break
                time.sleep(0.05)
            require(terminal and terminal.get("status") == "done", "real Windows job: %r" % terminal)
            download_status, _headers, movie = request(port, "/api/download/" + job)
            require(download_status == 200 and movie, "download")
            movie_path = evidence / "windows-http-download.mp4"
            movie_path.write_bytes(movie)
            digest = hashlib.sha256(movie).hexdigest()
            ffmpeg = ROOT / "程序文件" / "bin" / "ffmpeg.exe"
            decoded = subprocess.run(
                [str(ffmpeg), "-hide_banner", "-i", str(movie_path), "-f", "null", "-"],
                capture_output=True, text=True, errors="replace", timeout=180,
            )
            media_text = decoded.stdout + decoded.stderr
            require(decoded.returncode == 0, "ffmpeg decode")
            for token in ("h264", "1080x1920", "25 fps", "aac", "48000 Hz"):
                require(token.lower() in media_text.lower(), "missing media token " + token)
            report["checks"]["real_http_video"] = {
                "job_id": job,
                "terminal": terminal,
                "bytes": len(movie),
                "sha256": digest,
                "ffmpeg_returncode": decoded.returncode,
                "required_tokens": ["h264", "1080x1920", "25 fps", "aac", "48000 Hz"],
            }
            report["result"] = "pass"
        except Exception as exc:
            report["result"] = "fail"
            report["error"] = "%s: %s" % (type(exc).__name__, exc)
            raise
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            (evidence / "phase5-windows-http.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
