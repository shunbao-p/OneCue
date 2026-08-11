# -*- coding: utf-8 -*-
"""Phase 3 Web 服务、任务生命周期与流式传输契约。"""

import base64
import hashlib
import http.client
import json
import queue
import socket
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock


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

import kt_video  # noqa: E402
import kt_web  # noqa: E402


def _missing_dots():
    return {
        "root": None,
        "python": "",
        "prompts": PROG_DIR / "_语音引擎未安装",
        "port": 7860,
        "url": "http://127.0.0.1:7860",
        "installed": False,
    }


def _request(port, path, method="GET", body=None, headers=None, timeout=10):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    result = response.status, dict(response.getheaders()), payload
    connection.close()
    return result


class RunningServerMixin:
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = self.root / "程序文件" / "临时文件"
        self.out = self.root / "成片"
        self.work.mkdir(parents=True)
        self.out.mkdir(parents=True)
        self.patches = [
            mock.patch.object(kt_web, "ROOT", self.root),
            mock.patch.object(kt_web, "WORK", self.work),
            mock.patch.object(kt_web, "OUTDIR", self.out),
        ]
        for patcher in self.patches:
            patcher.start()
        with kt_web.jobs_lock:
            kt_web.jobs.clear()
        self.server = kt_web.create_server("127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        with kt_web.jobs_lock:
            kt_web.jobs.clear()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()
        super().tearDown()


class TtsSubprocessPipeTests(unittest.TestCase):
    def test_stderr_is_drained_before_stdout_loop(self):
        source = Path(kt_web.__file__).read_text(encoding="utf-8")
        run_tts_source = source[source.index("def run_tts("):source.index("\nclass Handler", source.index("def run_tts("))]

        self.assertLess(
            run_tts_source.index("stderr_thread.start()"),
            run_tts_source.index("for line in proc.stdout:"),
            "stderr 必须在 stdout 循环前开始消费，避免双管道互相等待",
        )


class ServerFactoryTests(RunningServerMixin, unittest.TestCase):
    def test_loopback_port_zero_reports_kernel_selected_port_and_health(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertGreater(self.port, 0)
        status, _headers, body = _request(self.port, "/api/health")
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["port"], self.port)

    def test_second_start_on_same_port_falls_forward_without_disturbing_first(self):
        second = kt_web.create_server("127.0.0.1", self.port, max_tries=3)
        try:
            self.assertEqual(second.server_address[0], "127.0.0.1")
            self.assertNotEqual(second.server_address[1], self.port)
        finally:
            second.server_close()

    def test_running_sse_emits_heartbeat_within_contract_window(self):
        self.assertLessEqual(kt_web.SSE_HEARTBEAT_SECONDS, 15)
        job_id = kt_web.create_job("video")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        started = time.monotonic()
        with mock.patch.object(kt_web, "SSE_HEARTBEAT_SECONDS", 0.2):
            connection.request("GET", f"/api/events?job={job_id}")
            response = connection.getresponse()
            line = response.fp.readline()
        elapsed = time.monotonic() - started
        self.assertEqual(response.status, 200)
        self.assertEqual(line, b": ping\n")
        self.assertLess(elapsed, 15)
        connection.close()
        kt_web.finish_job(job_id, "stopped", {"type": "stopped"})

    def test_status_and_sse_are_repeatable_and_terminal_event_is_not_duplicated(self):
        job_id = kt_web.create_job("video")
        kt_web.push(job_id, {"type": "progress", "pct": 25})
        self.assertTrue(kt_web.finish_job(job_id, "done", {"type": "done", "url": "/x"}))
        self.assertFalse(kt_web.finish_job(job_id, "done", {"type": "done", "url": "/x"}))

        status, _headers, body = _request(self.port, f"/api/status/{job_id}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["status"], "done")

        started = time.monotonic()
        status, headers, body = _request(self.port, f"/api/events?job={job_id}")
        elapsed = time.monotonic() - started
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers["Content-Type"])
        self.assertLess(elapsed, 15)
        events = [
            json.loads(line[6:])
            for line in body.decode("utf-8").splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual([item["type"] for item in events], ["progress", "done"])

    def test_two_sse_clients_receive_the_same_replayed_history(self):
        job_id = kt_web.create_job("video")
        kt_web.push(job_id, {"type": "progress", "pct": 50})
        kt_web.finish_job(job_id, "done", {"type": "done"})
        bodies = []

        def read_events():
            bodies.append(_request(self.port, f"/api/events?job={job_id}")[2])

        readers = [threading.Thread(target=read_events) for _ in range(2)]
        for reader in readers:
            reader.start()
        for reader in readers:
            reader.join(timeout=5)
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[0], bodies[1])


class DownloadAndPathTests(RunningServerMixin, unittest.TestCase):
    def test_large_download_is_streamed_below_memory_target_and_matches_hash(self):
        source = self.out / "large-test.mp4"
        size = 80 * 1024 * 1024
        with source.open("wb") as stream:
            stream.seek(size - 1)
            stream.write(b"\0")
        job_id = kt_web.create_job("video")
        kt_web.set_job_output(job_id, source, status="done")

        expected = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                expected.update(chunk)

        actual = hashlib.sha256()
        tracemalloc.start()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        connection.request("GET", f"/api/download/{job_id}")
        response = connection.getresponse()
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            actual.update(chunk)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        connection.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(int(response.getheader("Content-Length")), size)
        self.assertEqual(actual.hexdigest(), expected.hexdigest())
        self.assertLess(peak, 64 * 1024 * 1024)

    def test_open_folder_uses_platform_boundary_and_rejects_escape(self):
        target = self.out / "中文 成片.mp4"
        target.write_bytes(b"video")
        opened = []
        with mock.patch.object(
            kt_web.platform_support,
            "open_in_file_manager",
            side_effect=lambda path, select=False: opened.append((Path(path), select)),
        ):
            query = urllib.parse.urlencode({"path": str(target)})
            status, _headers, body = _request(self.port, "/api/open_folder?" + query)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body.decode("utf-8")), {"ok": True})

            outside = self.root.parent / "outside.mp4"
            query = urllib.parse.urlencode({"path": str(outside)})
            status, _headers, _body = _request(self.port, "/api/open_folder?" + query)
        self.assertEqual(status, 403)
        self.assertEqual(opened, [(target.resolve(), True)])

    def test_download_rejects_job_output_outside_controlled_output_root(self):
        outside = self.root / "outside-output.mp4"
        outside.write_bytes(b"outside")
        job_id = kt_web.create_job("video")
        kt_web.set_job_output(job_id, outside, status="done")
        status, _headers, _body = _request(self.port, f"/api/download/{job_id}")
        self.assertEqual(status, 403)

    def test_oversized_request_is_rejected_before_body_read(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.putrequest("POST", "/api/generate")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(kt_web.MAX_REQUEST_BYTES + 1))
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual(response.status, 413)
        self.assertIn("MiB", json.loads(body.decode("utf-8"))["error"])


class RequestParsingTests(RunningServerMixin, unittest.TestCase):
    def test_generate_rejects_malformed_json_as_bad_request_and_stays_healthy(self):
        status, _headers, body = _request(
            self.port,
            "/api/generate",
            method="POST",
            body=b"{",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertIn("JSON", json.loads(body.decode("utf-8"))["error"])
        health, _headers, _body = _request(self.port, "/api/health")
        self.assertEqual(health, 200)

    def test_generate_rejects_invalid_base64_before_creating_job(self):
        payload = json.dumps({"wav_b64": "!!!", "txt_text": "测试"}).encode("utf-8")
        status, _headers, body = _request(
            self.port,
            "/api/generate",
            method="POST",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertIn("base64", json.loads(body.decode("utf-8"))["error"].lower())

    def test_tts_rejects_malformed_json_as_bad_request(self):
        status, _headers, body = _request(
            self.port,
            "/api/tts",
            method="POST",
            body=b"[",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertIn("JSON", json.loads(body.decode("utf-8"))["error"])


class JobLifecycleTests(RunningServerMixin, unittest.TestCase):
    class FakeProcess:
        def __init__(self):
            self.returncode = None
            self.terminated = False
            self.killed = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = 0

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    def test_stop_terminates_process_within_five_seconds_and_is_idempotent(self):
        job_id = kt_web.create_job("video")
        process = self.FakeProcess()
        kt_web.register_job_process(job_id, process)
        started = time.monotonic()
        status, _headers, body = _request(self.port, f"/api/stop/{job_id}")
        elapsed = time.monotonic() - started
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 5)
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertEqual(json.loads(body.decode("utf-8"))["status"], "stopped")
        self.assertEqual(kt_web.job_snapshot(job_id)["status"], "stopped")
        self.assertEqual(
            [event["type"] for event in kt_web.job_event_snapshot(job_id)],
            ["stopped"],
        )

        status, _headers, body = _request(self.port, f"/api/stop/{job_id}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["status"], "stopped")
        self.assertEqual(len(kt_web.job_event_snapshot(job_id)), 1)

    def test_cache_cleanup_skips_cross_instance_active_marker(self):
        active = self.work / "other-process-job"
        stale = self.work / "stale-job"
        active.mkdir()
        stale.mkdir()
        (active / kt_web.ACTIVE_MARKER).write_text("other process", encoding="utf-8")
        (stale / "old.tmp").write_text("old", encoding="utf-8")
        status, _headers, body = _request(self.port, "/api/clear_cache")
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(status, 200)
        self.assertTrue(active.is_dir())
        self.assertFalse(stale.exists())
        self.assertEqual(payload["cleared"], 1)

    def test_stop_and_completion_race_has_one_consistent_terminal_event(self):
        for _index in range(30):
            job_id = kt_web.create_job("video")
            barrier = threading.Barrier(2)

            def complete():
                barrier.wait(timeout=2)
                kt_web.finish_job(job_id, "done", {"type": "done"})

            def stop():
                barrier.wait(timeout=2)
                if kt_web.request_job_stop(job_id):
                    kt_web.finish_job(job_id, "stopped", {"type": "stopped"})

            actors = [threading.Thread(target=complete), threading.Thread(target=stop)]
            for actor in actors:
                actor.start()
            for actor in actors:
                actor.join(timeout=3)
            events = kt_web.job_event_snapshot(job_id)
            self.assertEqual(len(events), 1)
            self.assertEqual(kt_web.job_snapshot(job_id)["status"], events[0]["type"])

    def test_concurrent_video_jobs_use_distinct_work_directories(self):
        wav = (FIXTURES / "one_block.wav").read_bytes()
        payload = json.dumps({
            "wav_b64": base64.b64encode(wav).decode("ascii"),
            "txt_text": "你好，世界。",
            "dur": 0.2,
        }).encode("utf-8")
        barrier = threading.Barrier(2)
        work_dirs = []
        lock = threading.Lock()

        def fake_generate(*, out, work_dir, on_progress, on_log, **_kwargs):
            with lock:
                work_dirs.append(Path(work_dir))
            barrier.wait(timeout=5)
            on_progress(50, {"speed": 1})
            Path(out).write_bytes(b"\0" * 1200 + b"mdat")
            return str(out)

        with mock.patch.object(kt_web.kt_video, "generate", side_effect=fake_generate):
            responses = []

            def submit():
                responses.append(_request(
                    self.port,
                    "/api/generate",
                    method="POST",
                    body=payload,
                    headers={"Content-Type": "application/json"},
                ))

            threads = [threading.Thread(target=submit) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            job_ids = [json.loads(body.decode("utf-8"))["job_id"] for status, _h, body in responses]
            for job_id in job_ids:
                self.assertTrue(kt_web.wait_for_terminal(job_id, timeout=5))

        self.assertEqual(len(set(work_dirs)), 2)
        self.assertEqual({path.name for path in work_dirs}, set(job_ids))
        self.assertTrue(all(kt_web.job_snapshot(job_id)["status"] == "done" for job_id in job_ids))

    def test_failed_upload_does_not_break_health_or_later_video_api(self):
        payload = json.dumps({
            "wav_b64": base64.b64encode(b"not-wave").decode("ascii"),
            "txt_text": "测试",
        }).encode("utf-8")
        status, _headers, body = _request(
            self.port,
            "/api/generate",
            method="POST",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        job_id = json.loads(body.decode("utf-8"))["job_id"]
        self.assertTrue(kt_web.wait_for_terminal(job_id, timeout=5))
        self.assertEqual(kt_web.job_snapshot(job_id)["status"], "error")
        status, _headers, _body = _request(self.port, "/api/health")
        self.assertEqual(status, 200)

    def test_package_b_missing_status_and_tts_rejection_leave_video_service_healthy(self):
        with mock.patch.object(kt_web, "_dots", side_effect=_missing_dots):
            status, _headers, body = _request(self.port, "/api/dots_status")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body.decode("utf-8"))["state"], "not_installed")

            tts = json.dumps({"text": "测试", "voice": ""}).encode("utf-8")
            status, _headers, body = _request(
                self.port,
                "/api/tts",
                method="POST",
                body=tts,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 503)
            self.assertIn("未检测到语音引擎", json.loads(body.decode("utf-8"))["error"])

            status, _headers, _body = _request(self.port, "/api/health")
            self.assertEqual(status, 200)

    def test_darwin_incompatible_api_fails_before_tts_job_creation(self):
        installed = {
            "root": Path("/tmp/package-b"), "python": "/tmp/python",
            "prompts": Path("/tmp/prompts"), "port": 7860,
            "url": "http://127.0.0.1:7860", "installed": True,
        }
        before = set(kt_web.jobs)
        with mock.patch.object(kt_web, "_dots", return_value=installed), \
                mock.patch.object(kt_web.platform_support, "is_darwin", return_value=True), \
                mock.patch.object(
                    kt_web.dots_control, "probe_contract",
                    side_effect=kt_web.dots_control.DotsControlError("schema 不兼容"),
                ):
            tts = json.dumps({"text": "测试", "voice": "女播音.wav"}).encode("utf-8")
            status, _headers, body = _request(
                self.port, "/api/tts", method="POST", body=tts,
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(status, 503)
        self.assertIn("schema 不兼容", json.loads(body.decode("utf-8"))["error"])
        self.assertEqual(set(kt_web.jobs), before)


class RenderCancellationAndIsolationTests(unittest.TestCase):
    def test_generate_places_ass_in_explicit_job_work_dir_and_forwards_lifecycle_hooks(self):
        with tempfile.TemporaryDirectory() as temp:
            work_dir = Path(temp) / "job-a"
            cancel = threading.Event()
            on_process = mock.Mock()
            align = {
                "audio_sec": 1.0,
                "chunks": [{"start": 0.0, "end": 1.0, "text": "你好。"}],
            }
            with mock.patch.object(kt_video, "detect_pauses", return_value=[]), \
                    mock.patch.object(kt_video, "render_video") as render:
                kt_video.generate(
                    wav_path="input.wav",
                    txt_path="input.txt",
                    align=align,
                    out=Path(temp) / "out.mp4",
                    work_dir=work_dir,
                    cancel_event=cancel,
                    on_process=on_process,
                )
        ass_path = Path(render.call_args.args[0])
        self.assertEqual(ass_path.parent, work_dir)
        self.assertIs(render.call_args.kwargs["cancel_event"], cancel)
        self.assertIs(render.call_args.kwargs["on_process"], on_process)


class TtsDefaultsTests(unittest.TestCase):
    def test_package_a_defaults_to_the_mf_recommended_four_steps(self):
        synth_source = (WEB_DIR / "dots_synth.py").read_text(encoding="utf-8")
        web_source = (WEB_DIR / "kt_web.py").read_text(encoding="utf-8")
        html_source = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('ap.add_argument("--num_steps", type=int, default=4)', synth_source)
        self.assertIn('opts.get("num_steps") or 4', web_source)
        self.assertIn('id="ttsSteps" value="4"', html_source)
        self.assertIn("质量版 SOAR 推荐 10", html_source)


if __name__ == "__main__":
    unittest.main()
