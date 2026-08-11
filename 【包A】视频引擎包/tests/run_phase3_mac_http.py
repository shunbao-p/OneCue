# -*- coding: utf-8 -*-
"""Run the Phase 3 real-HTTP acceptance suite on the target Mac (stdlib only)."""

import argparse
import base64
import hashlib
import http.client
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import wave
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"
ENGINE_DIR = PROG_DIR / "引擎"
WEB_DIR = PROG_DIR / "网站"
FIXTURES = TESTS_DIR / "fixtures"

for directory in (PROG_DIR, ENGINE_DIR, WEB_DIR):
    value = str(directory)
    if value not in sys.path:
        sys.path.insert(0, value)


def request(port, path, method="GET", body=None, headers=None, timeout=30):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    result = response.status, dict(response.getheaders()), payload
    connection.close()
    return result


def json_request(port, path, method="GET", payload=None, timeout=30):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    status, response_headers, raw = request(
        port, path, method=method, body=body, headers=headers, timeout=timeout
    )
    parsed = json.loads(raw.decode("utf-8")) if raw else {}
    return status, response_headers, parsed


def multipart_body(wav_bytes, text):
    boundary = "package-a-phase3-" + uuid.uuid4().hex
    fields = {
        "txt": text.encode("utf-8"),
        "wav_name": "one_block.wav".encode("utf-8"),
        "txt_name": "one_block.txt".encode("utf-8"),
        "seed": b"2",
        "full": b"true",
        "skip_header": b"false",
        "dur": b"",
        "crf": b"20",
    }
    chunks = []
    marker = ("--" + boundary).encode("ascii")
    for name, value in fields.items():
        chunks.extend([
            marker,
            ('Content-Disposition: form-data; name="%s"' % name).encode("ascii"),
            b"",
            value,
        ])
    chunks.extend([
        marker,
        b'Content-Disposition: form-data; name="wav"; filename="one_block.wav"',
        b"Content-Type: audio/wav",
        b"",
        wav_bytes,
        marker + b"--",
        b"",
    ])
    return b"\r\n".join(chunks), boundary


def submit_multipart(port, wav_bytes, text):
    body, boundary = multipart_body(wav_bytes, text)
    status, _headers, raw = request(
        port,
        "/api/generate",
        method="POST",
        body=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    if status != 200:
        raise RuntimeError("generate HTTP %s: %s" % (status, raw.decode("utf-8", "replace")))
    return json.loads(raw.decode("utf-8"))["job_id"]


def read_sse(port, job_id, timeout=180):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    started = time.monotonic()
    connection.request("GET", "/api/events?" + urllib.parse.urlencode({"job": job_id}))
    response = connection.getresponse()
    if response.status != 200:
        raise RuntimeError("SSE HTTP %s" % response.status)
    events = []
    first_data_seconds = None
    while True:
        line = response.fp.readline()
        if not line:
            break
        if line.startswith(b"data: "):
            if first_data_seconds is None:
                first_data_seconds = time.monotonic() - started
            event = json.loads(line[6:].decode("utf-8"))
            event["received_monotonic"] = time.monotonic()
            events.append(event)
            if event.get("type") in ("done", "error", "stopped"):
                break
    connection.close()
    return {
        "http_status": response.status,
        "first_data_seconds": first_data_seconds,
        "events": events,
    }


def wait_status(port, job_id, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _headers, payload = json_request(port, "/api/status/" + job_id)
        if status == 200 and payload.get("status") in ("done", "error", "stopped"):
            return payload
        time.sleep(0.05)
    raise TimeoutError("job did not reach terminal state: " + job_id)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_rss_bytes(pid):
    result = subprocess.run(
        ["/bin/ps", "-o", "rss=", "-p", str(pid)],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip()) * 1024


def write_tone_wav(path, seconds=120, rate=48000):
    path = Path(path)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        for start in range(0, rate * seconds, rate):
            count = min(rate, rate * seconds - start)
            frame = bytearray(count * 2)
            for index in range(count):
                sample = int(9000 * math.sin(2 * math.pi * 220 * (start + index) / rate))
                frame[index * 2:index * 2 + 2] = int(sample).to_bytes(2, "little", signed=True)
            output.writeframesraw(frame)
    return path


def probe_media(ffprobe, path):
    command = [
        ffprobe, "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PACKAGE_A_FFMPEG"] = str(Path(args.ffmpeg).expanduser().resolve())
    os.environ["PACKAGE_A_FFPROBE"] = str(Path(args.ffprobe).expanduser().resolve())

    import kt_web

    report = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "system": subprocess.run(["uname", "-srm"], check=True, capture_output=True, text=True).stdout.strip(),
        "python": sys.version,
        "package_root": str(PACKAGE_ROOT),
        "checks": {},
    }
    generated_large = None
    long_wav = evidence_dir / "stop-input-120s.wav"
    server = kt_web.create_server("127.0.0.1", 0)
    port = int(server.server_address[1])
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    report["server"] = {"host": server.server_address[0], "port": port}

    try:
        # Browser/static page + health + actual random port.
        status, headers, index = request(port, "/")
        h_status, _h, health = json_request(port, "/api/health")
        assert_true(status == 200 and b"<!DOCTYPE html" in index, "index not browser-accessible")
        assert_true(h_status == 200 and health.get("port") == port, "health/actual port mismatch")
        report["checks"]["browser_health"] = {
            "index_status": status,
            "index_bytes": len(index),
            "content_type": headers.get("Content-Type"),
            "health": health,
        }

        # Repeated startup must bind a different port.
        second = kt_web.create_server("127.0.0.1", port, max_tries=5)
        report["checks"]["repeated_start"] = {
            "first_port": port,
            "second_port": int(second.server_address[1]),
        }
        assert_true(second.server_address[1] != port, "second server reused occupied port")
        second.server_close()

        # Real configured heartbeat duration.
        heartbeat_job = kt_web.create_job("video")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        heartbeat_started = time.monotonic()
        connection.request("GET", "/api/events?job=" + heartbeat_job)
        heartbeat_response = connection.getresponse()
        heartbeat_line = heartbeat_response.fp.readline()
        heartbeat_seconds = time.monotonic() - heartbeat_started
        connection.close()
        kt_web.finish_job(heartbeat_job, "stopped", {"type": "stopped"})
        assert_true(heartbeat_line == b": ping\n", "SSE heartbeat missing")
        assert_true(heartbeat_seconds <= 15, "SSE heartbeat exceeded 15 seconds")
        report["checks"]["sse_heartbeat"] = {
            "seconds": heartbeat_seconds,
            "line": heartbeat_line.decode("ascii").strip(),
        }

        # Package B remains unavailable and TTS rejection does not poison health.
        dots_status, _h, dots = json_request(port, "/api/dots_status")
        tts_status, _h, tts = json_request(
            port, "/api/tts", method="POST", payload={"text": "测试", "voice": ""}
        )
        health_after_tts, _h, _body = json_request(port, "/api/health")
        assert_true(dots_status == 200 and dots.get("state") == "not_installed", "dots status changed")
        assert_true(tts_status == 503 and "未检测到语音引擎" in tts.get("error", ""), "TTS was not friendly-rejected")
        assert_true(health_after_tts == 200, "video health failed after TTS rejection")
        report["checks"]["package_b_excluded"] = {
            "dots": dots,
            "tts_http_status": tts_status,
            "tts_error": tts.get("error"),
            "health_after_tts": health_after_tts,
        }

        # One complete real multipart video job, SSE, status, download and ffprobe.
        wav_bytes = (FIXTURES / "one_block.wav").read_bytes()
        completed_job = submit_multipart(port, wav_bytes, "你好，世界。")
        completed_sse = read_sse(port, completed_job)
        completed_status = wait_status(port, completed_job)
        assert_true(completed_status["status"] == "done", "real video job failed")
        assert_true(completed_sse["first_data_seconds"] is not None and completed_sse["first_data_seconds"] <= 15,
                    "SSE first event exceeded 15 seconds")
        events = completed_sse["events"]
        assert_true(any(item.get("type") == "progress" for item in events), "no progress event observed")
        assert_true(events[-1].get("type") == "done", "SSE did not end in done")
        source_path = Path(kt_web._job(completed_job)["out"])
        downloaded = evidence_dir / "completed-download.mp4"
        download_connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        download_connection.request("GET", "/api/download/" + completed_job)
        download_response = download_connection.getresponse()
        with downloaded.open("wb") as output:
            while True:
                chunk = download_response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        download_connection.close()
        source_hash = sha256_file(source_path)
        download_hash = sha256_file(downloaded)
        assert_true(download_response.status == 200, "download HTTP failed")
        assert_true(source_hash == download_hash and source_path.stat().st_size == downloaded.stat().st_size,
                    "download content mismatch")
        media = probe_media(args.ffprobe, downloaded)
        report["checks"]["completed_video"] = {
            "job_id": completed_job,
            "status": completed_status,
            "sse_first_data_seconds": completed_sse["first_data_seconds"],
            "sse_types": [item.get("type") for item in events],
            "progress_values": [item.get("pct") for item in events if item.get("type") == "progress"],
            "source_size": source_path.stat().st_size,
            "download_size": downloaded.stat().st_size,
            "source_sha256": source_hash,
            "download_sha256": download_hash,
            "ffprobe": media,
        }

        # Finder via the actual HTTP endpoint; open -R is selected by the platform layer.
        finder_query = urllib.parse.urlencode({"path": str(source_path)})
        finder_status, _h, finder_body = json_request(port, "/api/open_folder?" + finder_query)
        time.sleep(0.5)
        finder_process = subprocess.run(
            ["/usr/bin/pgrep", "-x", "Finder"], capture_output=True, text=True
        )
        assert_true(finder_status == 200 and finder_body.get("ok") is True, "Finder endpoint failed")
        report["checks"]["finder"] = {
            "http_status": finder_status,
            "response": finder_body,
            "target": str(source_path),
            "finder_process_present": finder_process.returncode == 0,
            "finder_pids": finder_process.stdout.split(),
        }

        # Failure recovery through the real API.
        bad_status, _h, bad_reply = json_request(
            port,
            "/api/generate",
            method="POST",
            payload={"wav_b64": base64.b64encode(b"not-wave").decode("ascii"), "txt_text": "测试"},
        )
        assert_true(bad_status == 200, "bad upload was not accepted as async job")
        bad_terminal = wait_status(port, bad_reply["job_id"], timeout=10)
        recovery_status, _h, _health = json_request(port, "/api/health")
        assert_true(bad_terminal["status"] == "error" and recovery_status == 200, "failure recovery failed")
        report["checks"]["failure_recovery"] = {
            "job_id": bad_reply["job_id"],
            "terminal": bad_terminal,
            "health_status": recovery_status,
        }

        # Two real encoders at once; their ASS work directories must stay isolated.
        concurrent_jobs = [submit_multipart(port, wav_bytes, "你好，世界。") for _ in range(2)]
        concurrent_status = [wait_status(port, item, timeout=180) for item in concurrent_jobs]
        assert_true(all(item["status"] == "done" for item in concurrent_status), "concurrent job failed")
        ass_paths = [str((kt_web.WORK / item / "kt_x.ass").resolve()) for item in concurrent_jobs]
        assert_true(len(set(ass_paths)) == 2 and all(Path(item).is_file() for item in ass_paths),
                    "concurrent ASS isolation failed")
        report["checks"]["concurrency"] = {
            "job_ids": concurrent_jobs,
            "terminal": concurrent_status,
            "ass_paths": ass_paths,
        }

        # Stop a real FFmpeg process through HTTP and verify it has exited.
        write_tone_wav(long_wav)
        long_bytes = long_wav.read_bytes()
        stop_job = submit_multipart(port, long_bytes, "这是用于停止验证的长音频。")
        deadline = time.monotonic() + 30
        process = None
        while time.monotonic() < deadline:
            process = kt_web._job(stop_job).get("proc")
            if process is not None and process.poll() is None:
                break
            if kt_web.job_snapshot(stop_job)["status"] in ("done", "error", "stopped"):
                break
            time.sleep(0.02)
        assert_true(process is not None and process.poll() is None, "real FFmpeg process was not observed")
        process_pid = process.pid
        stop_started = time.monotonic()
        stop_http, _h, stop_reply = json_request(port, "/api/stop/" + stop_job)
        stop_seconds = time.monotonic() - stop_started
        stop_terminal = wait_status(port, stop_job, timeout=10)
        process_state = subprocess.run(
            ["/bin/ps", "-p", str(process_pid), "-o", "stat="], capture_output=True, text=True
        )
        assert_true(stop_http == 200 and stop_terminal["status"] == "stopped", "stop endpoint failed")
        assert_true(stop_seconds <= 5, "stop exceeded five seconds")
        assert_true(process.poll() is not None and not process_state.stdout.strip(), "FFmpeg process remained")
        report["checks"]["stop"] = {
            "job_id": stop_job,
            "ffmpeg_pid": process_pid,
            "http_status": stop_http,
            "response": stop_reply,
            "seconds": stop_seconds,
            "terminal": stop_terminal,
            "process_returncode": process.poll(),
            "ps_state_after": process_state.stdout.strip(),
        }

        # 96 MiB stream probe; sample the Python service process RSS while discarding client bytes.
        generated_large = Path(kt_web.OUTDIR) / ("phase3-stream-" + uuid.uuid4().hex + ".mp4")
        with generated_large.open("wb") as output:
            output.seek(96 * 1024 * 1024 - 1)
            output.write(b"\0")
        expected_large_hash = sha256_file(generated_large)
        large_job = kt_web.create_job("video")
        kt_web.set_job_output(large_job, generated_large, status="done")
        baseline_rss = current_rss_bytes(os.getpid())
        samples = [baseline_rss]
        sampling = threading.Event()
        sampling.set()

        def sample_rss():
            while sampling.is_set():
                try:
                    samples.append(current_rss_bytes(os.getpid()))
                except Exception:
                    pass
                time.sleep(0.01)

        sampler = threading.Thread(target=sample_rss, daemon=True)
        sampler.start()
        large_hash = hashlib.sha256()
        large_size = 0
        stream_started = time.monotonic()
        stream_connection = http.client.HTTPConnection("127.0.0.1", port, timeout=90)
        stream_connection.request("GET", "/api/download/" + large_job)
        stream_response = stream_connection.getresponse()
        while True:
            chunk = stream_response.read(1024 * 1024)
            if not chunk:
                break
            large_size += len(chunk)
            large_hash.update(chunk)
        stream_seconds = time.monotonic() - stream_started
        stream_connection.close()
        sampling.clear()
        sampler.join(timeout=2)
        peak_rss = max(samples)
        rss_delta = max(0, peak_rss - baseline_rss)
        assert_true(stream_response.status == 200 and large_size == generated_large.stat().st_size,
                    "large stream size mismatch")
        assert_true(large_hash.hexdigest() == expected_large_hash, "large stream hash mismatch")
        assert_true(rss_delta < 64 * 1024 * 1024, "large stream RSS delta exceeded 64 MiB")
        report["checks"]["streaming_download"] = {
            "http_status": stream_response.status,
            "bytes": large_size,
            "seconds": stream_seconds,
            "sha256": large_hash.hexdigest(),
            "baseline_rss_bytes": baseline_rss,
            "peak_rss_bytes": peak_rss,
            "rss_delta_bytes": rss_delta,
            "rss_sample_count": len(samples),
        }

        report["result"] = "pass"
    except Exception as exc:
        report["result"] = "fail"
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        if generated_large is not None:
            try:
                generated_large.unlink()
            except FileNotFoundError:
                pass
        try:
            long_wav.unlink()
        except FileNotFoundError:
            pass
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        (evidence_dir / "phase3-http-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
