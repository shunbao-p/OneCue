# -*- coding: utf-8 -*-
"""通用 Phase 2 渲染用例执行器：记录耗时、内存、哈希和输出路径。"""

import argparse
import hashlib
import json
import platform
import resource
import sys
import time
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

for directory in (PROG_DIR, ENGINE_DIR):
    value = str(directory)
    if value not in sys.path:
        sys.path.insert(0, value)

import kt_video  # noqa: E402


def _maxrss_bytes(usage):
    # macOS 以字节返回，Linux/Windows 常用 KiB；证据同时记录平台。
    return int(usage.ru_maxrss if platform.system() == "Darwin" else usage.ru_maxrss * 1024)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--wav", required=True)
    parser.add_argument("--txt", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--crf", default="20")
    args = parser.parse_args()
    if args.full == (args.duration is not None):
        parser.error("必须且只能选择 --full 或 --duration")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    work_dir = output_dir / "work"
    work_dir.mkdir()
    kt_video._paths.WORK_DIR = work_dir
    output = output_dir / (args.case_id + ".mp4")

    started = time.perf_counter()
    result = kt_video.generate(
        wav_path=Path(args.wav).resolve(),
        txt_path=Path(args.txt).resolve(),
        out=output,
        dur=args.duration,
        full=args.full,
        seed=args.seed,
        crf=args.crf,
    )
    elapsed = time.perf_counter() - started
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    report = {
        "case_id": args.case_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "wav": str(Path(args.wav).resolve()),
        "txt": str(Path(args.txt).resolve()),
        "output": str(Path(result).resolve()),
        "requested_duration": args.duration,
        "full": args.full,
        "elapsed_seconds": round(elapsed, 6),
        "self_maxrss_bytes": _maxrss_bytes(self_usage),
        "children_maxrss_bytes": _maxrss_bytes(child_usage),
        "conservative_peak_bytes": _maxrss_bytes(self_usage) + _maxrss_bytes(child_usage),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256(output),
    }
    report_path = output_dir / "render-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PHASE2_REPORT=" + json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
