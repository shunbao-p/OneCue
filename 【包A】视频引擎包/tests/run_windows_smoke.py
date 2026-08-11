# -*- coding: utf-8 -*-
"""用包 A 当前 Windows Python/FFmpeg 生成可重复的极短基线成片。"""

import sys
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent
PROG_DIR = PACKAGE_ROOT / "程序文件"
ENGINE_DIR = PROG_DIR / "引擎"
FIXTURES = TESTS_DIR / "fixtures"
EVIDENCE = TESTS_DIR / "evidence"

for path in (PROG_DIR, ENGINE_DIR):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

import kt_video  # noqa: E402


def main():
    evidence_work = EVIDENCE / "work"
    evidence_work.mkdir(parents=True, exist_ok=True)
    kt_video._paths.WORK_DIR = evidence_work
    output = EVIDENCE / "windows-smoke.mp4"
    result = kt_video.generate(
        wav_path=FIXTURES / "one_block.wav",
        txt_path=FIXTURES / "one_block.txt",
        out=output,
        full=True,
        seed=7,
        crf="20",
    )
    print(result)


if __name__ == "__main__":
    main()
