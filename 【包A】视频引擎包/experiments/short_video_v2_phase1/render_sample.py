#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""计划 01 的隔离三镜头实验渲染器；不是正式 V2 入口。"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


SAMPLE_VERSION = "phase1-experimental-1"
RENDERER_VERSION = "phase1-renderer-2"
MOTION_PRESETS = frozenset(
    {"static", "slow_push_in", "gentle_drift", "slow_pull_out"}
)
TOP_LEVEL_FIELDS = frozenset(
    {
        "sample_version",
        "title",
        "resolution",
        "fps",
        "package_a_url",
        "voice",
        "shots",
    }
)
SHOT_FIELDS = frozenset(
    {
        "id",
        "narration",
        "image",
        "motion_preset",
        "focus",
        "head_pad_sec",
        "tail_pad_sec",
        "caption",
    }
)
EXPECTED_RESOLUTION = {"width": 1080, "height": 1920}
EXPECTED_FPS = 30
HTTP_TIMEOUT_SEC = 60
JOB_TIMEOUT_SEC = 600


class SampleError(RuntimeError):
    """计划内可报告错误。"""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [str(item) for item in command],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-3000:]
        raise SampleError(
            f"外部命令失败（code {result.returncode}）：{command[0]}\n{tail}"
        )
    return result


def _inside(root: Path, candidate: Path, label: str) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"{label}必须位于任务目录内：{candidate}")
    return candidate


def _finite_nonnegative(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是非负有限数") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label}必须是非负有限数")
    return number


def _focus(value, shot_id: str) -> dict[str, float]:
    if value is None:
        return {"x": 0.5, "y": 0.5}
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise ValueError(f"{shot_id} focus 必须只含 x/y")
    result = {}
    for axis in ("x", "y"):
        try:
            number = float(value[axis])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{shot_id} focus.{axis} 必须位于 0–1") from exc
        if not math.isfinite(number) or not 0 <= number <= 1:
            raise ValueError(f"{shot_id} focus.{axis} 必须位于 0–1")
        result[axis] = number
    return result


def load_storyboard(job_dir: Path, storyboard_path: Path) -> dict:
    job_dir = Path(job_dir).expanduser().resolve()
    storyboard_path = _inside(
        job_dir, Path(storyboard_path).expanduser(), "storyboard 路径"
    )
    if not storyboard_path.is_file():
        raise ValueError(f"storyboard 不存在：{storyboard_path}")
    try:
        document = json.loads(storyboard_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"storyboard 不是有效 JSON：{exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("storyboard 顶层必须是对象")
    unknown = set(document) - TOP_LEVEL_FIELDS
    if unknown:
        raise ValueError(f"未知顶层字段：{sorted(unknown)}")
    missing = TOP_LEVEL_FIELDS - set(document)
    if missing:
        raise ValueError(f"缺少顶层字段：{sorted(missing)}")
    if document["sample_version"] != SAMPLE_VERSION:
        raise ValueError(f"sample_version 必须是 {SAMPLE_VERSION}")
    if document["resolution"] != EXPECTED_RESOLUTION:
        raise ValueError("本实验只接受 1080x1920")
    if document["fps"] != EXPECTED_FPS:
        raise ValueError("本实验只接受 30 FPS")
    if not isinstance(document["title"], str) or not document["title"].strip():
        raise ValueError("title 不能为空")
    if not isinstance(document["voice"], str) or not document["voice"].strip():
        raise ValueError("voice 不能为空")
    if not isinstance(document["shots"], list) or len(document["shots"]) != 3:
        raise ValueError("本实验要求恰有 3 个镜头")

    normalized = dict(document)
    normalized_shots = []
    seen = set()
    for index, original in enumerate(document["shots"], start=1):
        if not isinstance(original, dict):
            raise ValueError(f"第 {index} 个镜头必须是对象")
        unknown = set(original) - SHOT_FIELDS
        if unknown:
            raise ValueError(f"未知镜头字段：{sorted(unknown)}")
        missing = SHOT_FIELDS - set(original)
        if missing:
            raise ValueError(f"镜头缺少字段：{sorted(missing)}")
        shot_id = original.get("id")
        expected_id = f"shot-{index:03d}"
        if shot_id != expected_id or shot_id in seen:
            raise ValueError(f"镜头 ID 必须唯一并按顺序为 shot-NNN：{shot_id}")
        seen.add(shot_id)
        narration = original.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise ValueError(f"{shot_id} 旁白不能为空")
        caption = original.get("caption")
        if not isinstance(caption, str) or not caption.strip():
            raise ValueError(f"{shot_id} caption 不能为空")
        preset = original.get("motion_preset")
        if preset not in MOTION_PRESETS:
            raise ValueError(f"{shot_id} 运镜预设不在白名单：{preset}")
        raw_image = original.get("image")
        if not isinstance(raw_image, str) or not raw_image.strip():
            raise ValueError(f"{shot_id} image 不能为空")
        if Path(raw_image).expanduser().is_absolute():
            raise ValueError(f"{shot_id} 图片必须位于任务目录内")
        image_path = _inside(job_dir, job_dir / raw_image, f"{shot_id} 图片")
        if not image_path.is_file():
            raise ValueError(f"{shot_id} 图片不存在：{image_path}")
        shot = dict(original)
        shot["narration"] = narration.strip()
        shot["caption"] = caption.strip()
        shot["focus"] = _focus(original.get("focus"), shot_id)
        shot["head_pad_sec"] = _finite_nonnegative(
            original.get("head_pad_sec"), f"{shot_id} head_pad_sec"
        )
        shot["tail_pad_sec"] = _finite_nonnegative(
            original.get("tail_pad_sec"), f"{shot_id} tail_pad_sec"
        )
        shot["image_path"] = image_path
        normalized_shots.append(shot)
    normalized["shots"] = normalized_shots
    normalized["storyboard_path"] = storyboard_path
    return normalized


def ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(float(seconds) * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def escape_ass(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", r"\N")
        .replace("\n", r"\N")
        .replace("\r", r"\N")
    )


def wrap_caption(text: str, max_chars: int = 16) -> str:
    """为 libass 不会自动分词的中文句子插入至多一个自然换行。"""
    compact = "".join(str(text).splitlines()).strip()
    if len(compact) <= max_chars:
        return compact
    punctuation = "，。！？：；、,!?;:"
    candidates = [
        index + 1
        for index, character in enumerate(compact[:-1])
        if character in punctuation
        and index + 1 <= max_chars
        and len(compact) - index - 1 <= max_chars
    ]
    if candidates:
        split_at = min(candidates, key=lambda value: abs(value - len(compact) / 2))
    else:
        split_at = min(max_chars, max(1, len(compact) // 2))
    return compact[:split_at] + "\n" + compact[split_at:]


def render_ass(events: list[tuple[float, float, str]], title: str) -> str:
    lines = [
        "[Script Info]",
        f"Title: {title}",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,SimHei,62,&H00FFFFFF,&H000000FF,&H00101010,&H64000000,-1,0,0,0,100,100,0,0,1,4,2,2,110,110,235,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for start, end, text in events:
        text = wrap_caption(text)
        lines.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{escape_ass(text)}"
        )
    return "\n".join(lines) + "\n"


def build_video_filter(
    *, preset: str, focus: dict, duration: float, fps: int, subtitle_name: str
) -> str:
    if preset not in MOTION_PRESETS:
        raise ValueError(f"未知运镜预设：{preset}")
    frames = max(2, int(math.ceil(duration * fps)))
    denominator = max(1, frames - 1)
    x = float(focus["x"])
    y = float(focus["y"])
    if preset == "slow_push_in":
        zoom = f"1.02+0.06*on/{denominator}"
        x_expr = f"(iw-iw/zoom)*{x:.6f}"
        y_expr = f"(ih-ih/zoom)*{y:.6f}"
    elif preset == "slow_pull_out":
        zoom = f"1.08-0.06*on/{denominator}"
        x_expr = f"(iw-iw/zoom)*{x:.6f}"
        y_expr = f"(ih-ih/zoom)*{y:.6f}"
    elif preset == "gentle_drift":
        zoom = "1.06"
        safe_x = 0.08 + 0.84 * x
        safe_y = 0.08 + 0.84 * y
        x_expr = f"(iw-iw/zoom)*({safe_x:.6f}+0.04*sin(PI*on/{denominator}))"
        y_expr = f"(ih-ih/zoom)*({safe_y:.6f}-0.02*sin(PI*on/{denominator}))"
    else:
        zoom = "1.03"
        x_expr = f"(iw-iw/zoom)*{x:.6f}"
        y_expr = f"(ih-ih/zoom)*{y:.6f}"
    return (
        "[0:v]scale=1220:2168:force_original_aspect_ratio=increase,"
        "crop=1220:2168,"
        f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:"
        f"s=1080x1920:fps={fps},"
        "format=yuv420p,"
        f"subtitles=filename='{subtitle_name}':fontsdir='fonts'[v]"
    )


def _url_parts(base_url: str):
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("package-a-url 必须是本机 HTTP 地址")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("package-a-url 不得携带路径、查询或片段")
    return parsed.hostname, parsed.port or 80


def http_request(base_url: str, path: str, *, method="GET", payload=None, timeout=HTTP_TIMEOUT_SEC):
    host, port = _url_parts(base_url)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, dict(response.getheaders()), raw
    finally:
        connection.close()


def json_request(base_url: str, path: str, *, method="GET", payload=None, timeout=HTTP_TIMEOUT_SEC):
    status, headers, raw = http_request(
        base_url, path, method=method, payload=payload, timeout=timeout
    )
    try:
        document = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SampleError(f"{path} 返回非 JSON 内容（HTTP {status}）") from exc
    return status, headers, document


def wait_job(base_url: str, job_id: str, timeout=JOB_TIMEOUT_SEC) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _headers, payload = json_request(base_url, f"/api/status/{job_id}")
        if status == 200 and payload.get("status") in {"done", "error", "stopped"}:
            return payload
        time.sleep(0.5)
    raise TimeoutError(f"任务超时：{job_id}")


def download_file(base_url: str, path: str, target: Path) -> None:
    status, _headers, raw = http_request(base_url, path, timeout=120)
    if status != 200:
        raise SampleError(f"下载失败 HTTP {status}: {path}")
    temporary = target.with_name(target.name + ".part")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(raw)
    temporary.replace(target)


def probe_media(ffprobe: str, path: Path) -> dict:
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(result.stdout)


def media_duration(probe: dict) -> float:
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SampleError("ffprobe 未返回有效时长") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise SampleError("媒体时长无效")
    return duration


def tool_info(executable: str) -> dict:
    result = run_command([executable, "-version"])
    first = (result.stdout or result.stderr).splitlines()[0]
    return {"path": str(Path(executable).expanduser().resolve()), "version": first}


def git_info(job_dir: Path) -> dict:
    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(job_dir), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    return {
        "head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "status": git("-c", "core.quotepath=false", "status", "--short").splitlines(),
    }


def base_report(*, job_dir: Path, storyboard_sha256: str, git_info: dict, tools: dict) -> dict:
    return {
        "sample_version": SAMPLE_VERSION,
        "renderer_version": RENDERER_VERSION,
        "status": "running",
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "job_dir": str(job_dir),
        "storyboard_sha256": storyboard_sha256,
        "git": git_info,
        "tools": tools,
        "services": {},
        "shots": [],
        "warnings": [],
        "errors": [],
        "output": {},
    }


def replace_shot(report: dict, record: dict) -> None:
    report["shots"] = [item for item in report["shots"] if item.get("id") != record["id"]]
    report["shots"].append(record)
    report["shots"].sort(key=lambda item: item["id"])
    report["updated_at"] = now_iso()


def prior_shot_usable(prior: dict | None, path: Path, requirements: dict) -> bool:
    if not prior or not path.is_file():
        return False
    for key, value in requirements.items():
        if prior.get(key) != value:
            return False
    expected_hash = prior.get("sha256")
    return bool(expected_hash and sha256_file(path) == expected_hash)


def synthesize_audio(
    *, base_url: str, shot: dict, target: Path, prior: dict | None, overwrite: bool
) -> dict:
    narration_hash = sha256_text(shot["narration"])
    if prior_shot_usable(
        prior,
        target,
        {"narration_sha256": narration_hash, "voice": shot["voice"]},
    ):
        return {**prior, "reused": True, "reuse_check_wall_seconds": 0.0}
    if target.exists() and not overwrite:
        raise SampleError(f"音频已存在且无法由报告证明可复用：{target}")

    attempts = []
    started = time.monotonic()
    for attempt in range(1, 3):
        try:
            http_status, _headers, reply = json_request(
                base_url,
                "/api/tts",
                method="POST",
                payload={
                    "text": shot["narration"],
                    "voice": shot["voice"],
                    "num_steps": 4,
                    "guidance_scale": 1.2,
                    "speed": 1.0,
                    "max_pause": 0.3,
                    "seed": 42,
                },
            )
            if http_status != 200 or not reply.get("job_id"):
                raise SampleError(f"包 A 未接受 TTS：HTTP {http_status} {reply}")
            terminal = wait_job(base_url, reply["job_id"])
            if terminal.get("status") != "done":
                raise SampleError(f"TTS 未完成：{terminal}")
            download_file(base_url, f"/api/tts_file/{reply['job_id']}", target)
            return {
                "path": str(target),
                "sha256": sha256_file(target),
                "narration_sha256": narration_hash,
                "voice": shot["voice"],
                "job_id": reply["job_id"],
                "attempts": attempts + [{"attempt": attempt, "status": "done"}],
                "wall_seconds": time.monotonic() - started,
                "reused": False,
            }
        except Exception as exc:
            attempts.append(
                {"attempt": attempt, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
            if attempt == 2:
                raise SampleError(f"{shot['id']} TTS 两次尝试均失败：{exc}") from exc
    raise AssertionError("unreachable")


def render_shot(
    *, ffmpeg: str, shot: dict, audio: Path, ass_path: Path, font: Path,
    target: Path, duration: float, fps: int
) -> float:
    started = time.monotonic()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v2-phase1-stage-") as temporary:
        stage = Path(temporary)
        shutil.copy2(shot["image_path"], stage / "image.png")
        shutil.copy2(audio, stage / "narration.wav")
        shutil.copy2(ass_path, stage / "caption.ass")
        fonts = stage / "fonts"
        fonts.mkdir()
        shutil.copy2(font, fonts / "simhei.ttf")
        video_filter = build_video_filter(
            preset=shot["motion_preset"],
            focus=shot["focus"],
            duration=duration,
            fps=fps,
            subtitle_name="caption.ass",
        )
        head_ms = int(round(shot["head_pad_sec"] * 1000))
        audio_filter = (
            f"[1:a]adelay={head_ms}:all=1,"
            f"apad=pad_dur={shot['tail_pad_sec']:.6f},"
            f"atrim=duration={duration:.6f},aresample=48000[a]"
        )
        temporary_output = stage / "shot.mp4"
        run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-y",
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-i",
                "image.png",
                "-i",
                "narration.wav",
                "-filter_complex",
                video_filter + ";" + audio_filter,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-t",
                f"{duration:.6f}",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(temporary_output),
            ],
            cwd=stage,
        )
        shutil.move(str(temporary_output), str(target))
    return time.monotonic() - started


def compose_final(ffmpeg: str, shots: list[Path], target: Path, fps: int) -> float:
    started = time.monotonic()
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-v", "error", "-y"]
    for shot in shots:
        command.extend(["-i", str(shot)])
    inputs = "".join(f"[{index}:v][{index}:a]" for index in range(len(shots)))
    command.extend(
        [
            "-filter_complex",
            f"{inputs}concat=n={len(shots)}:v=1:a=1[v][a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    run_command(command)
    return time.monotonic() - started


def generate_representative_frames(
    ffmpeg: str, shot_records: list[dict], evidence_dir: Path
) -> tuple[list[Path], Path]:
    frames_dir = evidence_dir / "representative-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for record in shot_records:
        target = frames_dir / f"{record['id']}-mid.png"
        run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-y",
                "-ss",
                f"{record['actual_duration_sec'] / 2:.6f}",
                "-i",
                record["output"]["path"],
                "-frames:v",
                "1",
                str(target),
            ]
        )
        frames.append(target)
    contact_sheet = evidence_dir / "contact-sheet.jpg"
    run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-v",
            "error",
            "-y",
            "-i",
            str(frames[0]),
            "-i",
            str(frames[1]),
            "-i",
            str(frames[2]),
            "-filter_complex",
            "[0:v]scale=360:640[a];[1:v]scale=360:640[b];[2:v]scale=360:640[c];[a][b][c]hstack=inputs=3[out]",
            "-map",
            "[out]",
            "-frames:v",
            "1",
            str(contact_sheet),
        ]
    )
    return frames, contact_sheet


def validate_shot_probe(probe: dict, target_duration: float) -> list[str]:
    warnings = []
    streams = probe.get("streams", [])
    videos = [item for item in streams if item.get("codec_type") == "video"]
    audios = [item for item in streams if item.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise SampleError("单镜头必须恰有一路视频和一路音频")
    video = videos[0]
    audio = audios[0]
    checks = {
        "codec": video.get("codec_name") == "h264",
        "resolution": (video.get("width"), video.get("height")) == (1080, 1920),
        "fps": video.get("avg_frame_rate") == "30/1",
        "pixel_format": video.get("pix_fmt") == "yuv420p",
        "audio_codec": audio.get("codec_name") == "aac",
        "sample_rate": audio.get("sample_rate") == "48000",
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SampleError(f"单镜头规格不合格：{failed}")
    actual = media_duration(probe)
    if abs(actual - target_duration) > 0.15:
        raise SampleError(
            f"单镜头时长误差 {abs(actual - target_duration):.3f}s 超过 0.15s"
        )
    if abs(actual - target_duration) > 0.05:
        warnings.append(f"单镜头时长存在 {abs(actual - target_duration):.3f}s 编码舍入")
    return warnings


def execute(args) -> dict:
    job_dir = Path(args.job_dir).expanduser().resolve()
    if not job_dir.is_dir():
        raise ValueError(f"job-dir 不存在：{job_dir}")
    storyboard_path = Path(args.storyboard).expanduser()
    if not storyboard_path.is_absolute():
        storyboard_path = (Path.cwd() / storyboard_path).resolve()
    document = load_storyboard(job_dir, storyboard_path)
    package_a_url = args.package_a_url or document["package_a_url"]
    _url_parts(package_a_url)
    ffmpeg = str(Path(args.ffmpeg).expanduser().resolve())
    ffprobe = str(Path(args.ffprobe).expanduser().resolve())
    for executable in (ffmpeg, ffprobe):
        if not Path(executable).is_file():
            raise ValueError(f"工具不存在：{executable}")

    output_dir = job_dir / "output"
    report_path = output_dir / "render_report.json"
    prior_report = None
    if report_path.is_file():
        try:
            prior_report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if not args.overwrite:
                raise SampleError("既有 render_report.json 无法读取；需显式 --overwrite")
        if prior_report and prior_report.get("sample_version") != SAMPLE_VERSION and not args.overwrite:
            raise SampleError("既有报告并非本实验产物；拒绝覆盖")
    prior_shots = {
        item.get("id"): item for item in (prior_report or {}).get("shots", []) if isinstance(item, dict)
    }

    tools = {
        "python": {"path": sys.executable, "version": sys.version.split()[0]},
        "ffmpeg": tool_info(ffmpeg),
        "ffprobe": tool_info(ffprobe),
    }
    report = base_report(
        job_dir=job_dir,
        storyboard_sha256=sha256_file(document["storyboard_path"]),
        git_info=git_info(job_dir),
        tools=tools,
    )
    report["shots"] = list(prior_shots.values())
    report["title"] = document["title"]
    report["package_a_url"] = package_a_url
    write_json(report_path, report)

    health_status, _headers, health = json_request(package_a_url, "/api/health")
    dots_status, _headers, dots = json_request(package_a_url, "/api/dots_status")
    if health_status != 200 or health.get("status") != "ok":
        raise SampleError(f"包 A 健康检查失败：{health}")
    if (
        dots_status != 200
        or dots.get("state") != "ready"
        or dots.get("compatible") is not True
    ):
        raise SampleError(f"包 B 未 ready 或 API 不兼容：{dots}")
    report["services"] = {"package_a": health, "package_b": dots}
    write_json(report_path, report)

    font = (
        Path(__file__).resolve().parents[2]
        / "程序文件"
        / "fonts"
        / "simhei.ttf"
    )
    if not font.is_file():
        raise SampleError(f"随包字幕字体不存在：{font}")
    audio_dir = job_dir / "audio"
    captions_dir = job_dir / "captions"
    shots_dir = job_dir / "shots"
    evidence_dir = job_dir / "evidence"
    for directory in (audio_dir, captions_dir, shots_dir, evidence_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    timeline = 0.0
    combined_events = []
    completed = []
    for shot in document["shots"]:
        shot = dict(shot)
        shot["voice"] = document["voice"]
        image_hash = sha256_file(shot["image_path"])
        narration_hash = sha256_text(shot["narration"])
        prior = prior_shots.get(shot["id"], {})
        audio_path = audio_dir / f"{shot['id']}.wav"
        audio_record = synthesize_audio(
            base_url=package_a_url,
            shot=shot,
            target=audio_path,
            prior=prior.get("tts"),
            overwrite=args.overwrite,
        )
        audio_probe = probe_media(ffprobe, audio_path)
        audio_duration = media_duration(audio_probe)
        audio_record["duration_sec"] = audio_duration
        audio_record["probe"] = audio_probe
        target_duration = audio_duration + shot["head_pad_sec"] + shot["tail_pad_sec"]

        ass_path = captions_dir / f"{shot['id']}.ass"
        ass_path.write_text(
            render_ass(
                [
                    (
                        shot["head_pad_sec"],
                        shot["head_pad_sec"] + audio_duration,
                        shot["caption"],
                    )
                ],
                title=shot["id"],
            ),
            encoding="utf-8",
        )
        ass_hash = sha256_file(ass_path)
        combined_events.append(
            (
                timeline + shot["head_pad_sec"],
                timeline + shot["head_pad_sec"] + audio_duration,
                shot["caption"],
            )
        )

        output_path = shots_dir / f"{shot['id']}.mp4"
        prior_output = prior.get("output") if isinstance(prior, dict) else None
        reuse_requirements = {
            "image_sha256": image_hash,
            "narration_sha256": narration_hash,
            "motion_preset": shot["motion_preset"],
            "target_duration_sec": round(target_duration, 6),
            "ass_sha256": ass_hash,
            "renderer_version": RENDERER_VERSION,
        }
        if prior_shot_usable(prior_output, output_path, reuse_requirements):
            render_seconds = 0.0
            reused = True
        else:
            if output_path.exists() and not args.overwrite:
                raise SampleError(f"镜头已存在且无法由报告证明可复用：{output_path}")
            render_seconds = render_shot(
                ffmpeg=ffmpeg,
                shot=shot,
                audio=audio_path,
                ass_path=ass_path,
                font=font,
                target=output_path,
                duration=target_duration,
                fps=document["fps"],
            )
            reused = False
        output_probe = probe_media(ffprobe, output_path)
        report["warnings"].extend(validate_shot_probe(output_probe, target_duration))
        actual_duration = media_duration(output_probe)
        output_record = {
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "bytes": output_path.stat().st_size,
            "image_sha256": image_hash,
            "narration_sha256": narration_hash,
            "motion_preset": shot["motion_preset"],
            "target_duration_sec": round(target_duration, 6),
            "ass_sha256": ass_hash,
            "renderer_version": RENDERER_VERSION,
            "render_wall_seconds": render_seconds,
            "reused": reused,
            "probe": output_probe,
        }
        record = {
            "id": shot["id"],
            "narration": shot["narration"],
            "narration_sha256": narration_hash,
            "image": {"path": str(shot["image_path"]), "sha256": image_hash},
            "tts": audio_record,
            "motion_preset": shot["motion_preset"],
            "focus": shot["focus"],
            "head_pad_sec": shot["head_pad_sec"],
            "tail_pad_sec": shot["tail_pad_sec"],
            "target_duration_sec": target_duration,
            "actual_duration_sec": actual_duration,
            "caption_path": str(ass_path),
            "output": output_record,
        }
        replace_shot(report, record)
        write_json(report_path, report)
        completed.append(record)
        timeline += actual_duration

    combined_ass = captions_dir / "captions.ass"
    combined_ass.write_text(
        render_ass(combined_events, title=document["title"]), encoding="utf-8"
    )
    final_path = output_dir / "final.mp4"
    expected_shot_hashes = [item["output"]["sha256"] for item in completed]
    prior_final = (prior_report or {}).get("output", {}).get("final", {})
    final_reused = prior_shot_usable(
        prior_final, final_path, {"shot_sha256": expected_shot_hashes}
    )
    if final_reused:
        final_render_seconds = 0.0
    else:
        if final_path.exists() and not args.overwrite:
            raise SampleError(f"最终视频已存在且无法由报告证明可复用：{final_path}")
        final_render_seconds = compose_final(
            ffmpeg,
            [Path(item["output"]["path"]) for item in completed],
            final_path,
            document["fps"],
        )
    final_probe = probe_media(ffprobe, final_path)
    frames, contact_sheet = generate_representative_frames(
        ffmpeg, completed, evidence_dir
    )
    ffprobe_report = {
        "shots": {item["id"]: item["output"]["probe"] for item in completed},
        "final": final_probe,
    }
    ffprobe_report_path = evidence_dir / "ffprobe-report.json"
    write_json(ffprobe_report_path, ffprobe_report)
    report["output"] = {
        "final": {
            "path": str(final_path),
            "sha256": sha256_file(final_path),
            "bytes": final_path.stat().st_size,
            "duration_sec": media_duration(final_probe),
            "shot_sha256": expected_shot_hashes,
            "render_wall_seconds": final_render_seconds,
            "reused": final_reused,
            "probe": final_probe,
        },
        "captions": str(combined_ass),
        "representative_frames": [str(path) for path in frames],
        "contact_sheet": str(contact_sheet),
        "ffprobe_report": str(ffprobe_report_path),
    }
    report["status"] = "PASS"
    report["finished_at"] = now_iso()
    report["updated_at"] = now_iso()
    write_json(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--package-a-url")
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    job_dir = Path(args.job_dir).expanduser().resolve()
    report_path = job_dir / "output" / "render_report.json"
    try:
        report = execute(args)
        print(json.dumps({"status": report["status"], "output": report["output"]}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        try:
            existing = {}
            if report_path.is_file():
                existing = json.loads(report_path.read_text(encoding="utf-8"))
            existing.setdefault("sample_version", SAMPLE_VERSION)
            existing.setdefault("shots", [])
            existing.setdefault("warnings", [])
            existing.setdefault("errors", [])
            existing.setdefault("output", {})
            existing["status"] = "FAIL"
            existing["updated_at"] = now_iso()
            existing["finished_at"] = now_iso()
            existing["errors"].append(
                {"type": type(exc).__name__, "message": str(exc)}
            )
            write_json(report_path, existing)
        except Exception:
            pass
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
