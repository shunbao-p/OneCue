# -*- coding: utf-8 -*-
"""在真实 macOS 上编排 Phase 2 的 3/30/60 秒与代表性全量验证。"""

import argparse
import json
import os
import subprocess
import sys
import wave
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = TESTS_DIR.parent

sys.path.insert(0, str(TESTS_DIR))
from generate_phase2_wav import write_tone  # noqa: E402


def run(command, log_path=None, timeout=None):
    result = subprocess.run(
        [str(item) for item in command],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    if log_path is not None:
        Path(log_path).write_text(
            "COMMAND=" + json.dumps([str(item) for item in command], ensure_ascii=False)
            + "\nRETURN_CODE=" + str(result.returncode)
            + "\nSTDOUT\n" + result.stdout
            + "\nSTDERR\n" + result.stderr,
            encoding="utf-8",
        )
    if result.returncode != 0:
        raise RuntimeError(
            "命令失败（%d）: %s\n%s"
            % (result.returncode, command[0], result.stderr[-3000:])
        )
    return result


def wav_duration(path):
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / float(source.getframerate())


def render_case(case, suite_root, ffmpeg, ffprobe):
    output_dir = suite_root / case["directory"]
    render_command = [
        sys.executable,
        TESTS_DIR / "run_phase2_render_case.py",
        "--case-id", case["id"],
        "--wav", case["wav"],
        "--txt", case["txt"],
        "--output-dir", output_dir,
    ]
    if case["full"]:
        render_command.append("--full")
    else:
        render_command.extend(["--duration", str(case["expected_duration"])])
    run(render_command, suite_root / (case["id"] + "-render.log"), timeout=1800)

    media = output_dir / (case["id"] + ".mp4")
    report = output_dir / "ffprobe-report.json"
    run(
        [
            sys.executable,
            TESTS_DIR / "verify_phase2_media.py",
            "--ffprobe", ffprobe,
            "--media", media,
            "--expected-duration", str(case["expected_duration"]),
            "--tolerance", "0.25",
            "--report", report,
        ],
        suite_root / (case["id"] + "-ffprobe.log"),
        timeout=120,
    )

    frames_dir = output_dir / "frames"
    frames_dir.mkdir()
    frame_paths = []
    for fraction in (0.25, 0.50, 0.75):
        timestamp = max(0.04, case["expected_duration"] * fraction)
        frame_path = frames_dir / ("frame-%02d.png" % round(fraction * 100))
        run(
            [
                ffmpeg, "-v", "error", "-ss", "%.3f" % timestamp,
                "-i", media, "-frames:v", "1", "-y", frame_path,
            ],
            suite_root / (case["id"] + "-frame-%02d.log" % round(fraction * 100)),
            timeout=120,
        )
        frame_paths.append(str(frame_path))

    quicklook_dir = output_dir / "quicklook"
    quicklook_dir.mkdir()
    quicklook = run(
        ["/usr/bin/qlmanage", "-t", "-s", "900", "-o", quicklook_dir, media],
        suite_root / (case["id"] + "-quicklook.log"),
        timeout=120,
    )
    thumbnails = sorted(str(path) for path in quicklook_dir.iterdir())
    if not thumbnails:
        raise RuntimeError("Quick Look 未生成原生缩略图: " + str(media))
    return {
        "case_id": case["id"],
        "media": str(media),
        "render_report": str(output_dir / "render-report.json"),
        "ffprobe_report": str(report),
        "frames": frame_paths,
        "quicklook_returncode": quicklook.returncode,
        "quicklook_thumbnails": thumbnails,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-root", required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    args = parser.parse_args()

    suite_root = Path(args.suite_root).resolve()
    suite_root.mkdir(parents=True, exist_ok=False)
    ffmpeg = Path(args.ffmpeg).resolve()
    ffprobe = Path(args.ffprobe).resolve()
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise FileNotFoundError("ffmpeg/ffprobe 工具不存在")

    os.environ["PACKAGE_A_FFMPEG"] = str(ffmpeg)
    os.environ["PACKAGE_A_FFPROBE"] = str(ffprobe)

    inputs = suite_root / "inputs"
    inputs.mkdir()
    generated_text = TESTS_DIR / "fixtures" / "phase2_mixed_utf8.txt"
    representative_text = TESTS_DIR / "fixtures" / "representative_demo_text.txt"
    representative_wav = PACKAGE_ROOT / "示范素材" / "示范配音_梁文峰音色.wav"

    cases = []
    for duration in (3, 30, 60):
        wav_path = inputs / ("tone-%ds.wav" % duration)
        write_tone(wav_path, duration)
        cases.append({
            "id": "generated-%ds" % duration,
            "directory": (
                "case-3s 中文 空格 引号' 冒号: 反斜杠\\"
                if duration == 3 else "case-%ds" % duration
            ),
            "wav": wav_path,
            "txt": generated_text,
            "expected_duration": float(duration),
            "full": False,
        })

    cases.append({
        "id": "representative-full",
        "directory": "case-representative-full",
        "wav": representative_wav,
        "txt": representative_text,
        "expected_duration": wav_duration(representative_wav),
        "full": True,
    })

    results = [render_case(case, suite_root, ffmpeg, ffprobe) for case in cases]
    report = {
        "suite_root": str(suite_root),
        "python": sys.version,
        "ffmpeg": str(ffmpeg),
        "ffprobe": str(ffprobe),
        "cases": results,
    }
    report_path = suite_root / "suite-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PHASE2_SUITE=" + str(report_path))


if __name__ == "__main__":
    main()
