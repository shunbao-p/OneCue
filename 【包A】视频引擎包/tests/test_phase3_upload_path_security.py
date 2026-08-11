from __future__ import annotations

import base64
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"
WEB_DIR = PROG_DIR / "网站"
for item in (PROG_DIR, PROG_DIR / "引擎", WEB_DIR):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import kt_web


def request(port, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/api/generate", body=body, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    result = response.status, json.loads(data.decode("utf-8"))
    conn.close()
    return result


class UploadPathSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.out = self.root / "out"
        self.work.mkdir()
        self.out.mkdir()
        self.patches = [
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
        self.wav = (TESTS_DIR / "fixtures" / "one_block.wav").read_bytes()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def payload(self, **names):
        result = {
            "wav_b64": base64.b64encode(self.wav).decode("ascii"),
            "txt_text": "合法文本。",
            "wav_name": "audio.wav",
            "txt_name": "text.txt",
        }
        result.update(names)
        return result

    def test_client_names_reject_traversal_absolute_mixed_empty_and_controls_before_job(self):
        outside = self.root / "escaped.wav"
        attacks = [
            {"wav_name": "../escaped.wav"},
            {"wav_name": str(outside)},
            {"wav_name": "..\\escaped.wav"},
            {"wav_name": "folder/audio.wav"},
            {"wav_name": ""},
            {"wav_name": "bad\u0000name.wav"},
            {"txt_name": "../escaped.txt"},
            {"txt_name": "C:\\temp\\escaped.txt"},
        ]
        for fields in attacks:
            with self.subTest(fields=fields):
                before = set(kt_web.jobs)
                status, body = request(self.port, self.payload(**fields))
                self.assertEqual(status, 400)
                self.assertIn("文件名", body["error"])
                self.assertEqual(set(kt_web.jobs), before)
                self.assertFalse(outside.exists())

    def test_valid_chinese_names_are_preserved(self):
        captured = {}

        def fake_run(job_id, _wav, _text, opts):
            captured.update(opts)
            kt_web.finish_job(job_id, "stopped", {"type": "stopped"})

        with mock.patch.object(kt_web, "run_job", side_effect=fake_run):
            status, body = request(self.port, self.payload(
                wav_name="中文 音频（最终）.wav",
                txt_name="文稿-终稿.txt",
            ))
        self.assertEqual(status, 200)
        self.assertIn("job_id", body)
        self.assertEqual(captured["wav_name"], "中文 音频（最终）.wav")
        self.assertEqual(captured["txt_name"], "文稿-终稿.txt")

    def test_existing_symlink_target_is_rejected(self):
        task = self.work / "known-task"
        task.mkdir()
        outside = self.root / "outside.wav"
        outside.write_bytes(b"outside")
        link = task / "audio.wav"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("当前文件系统不支持符号链接")
        with self.assertRaises(ValueError):
            kt_web.resolve_upload_target(task, "audio.wav", ".wav")
        self.assertEqual(outside.read_bytes(), b"outside")


if __name__ == "__main__":
    unittest.main()
