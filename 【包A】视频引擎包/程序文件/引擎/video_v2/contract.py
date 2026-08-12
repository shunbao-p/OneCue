"""V2 Job Bundle Schema v1 的纯标准库、只读运行校验器。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .models import (
    ContractIssue,
    JobBundle,
    JobBundleValidationError,
    ProjectSpec,
    ShotSpec,
    ValidationResult,
)


SCHEMA_VERSION = 1
MAX_JSON_BYTES = 8 * 1024 * 1024
PROJECT_REQUIRED = frozenset(
    {"schema_version", "project_id", "title", "language", "canvas", "defaults", "captions"}
)
PROJECT_FIELDS = PROJECT_REQUIRED | {"target_duration_sec"}
STORYBOARD_REQUIRED = frozenset({"schema_version", "project_id", "shots"})
STORYBOARD_FIELDS = STORYBOARD_REQUIRED
SHOT_REQUIRED = frozenset(
    {"id", "purpose", "speech", "visual", "motion", "caption", "transition_out"}
)
SHOT_FIELDS = SHOT_REQUIRED | {"timing", "hero"}
TIMING_REQUIRED = frozenset({"head_pad_sec", "tail_pad_sec"})
SPEECH_REQUIRED = frozenset({"kind", "text"})
KEYFRAME_REQUIRED = frozenset({"path", "sha256"})
FOCUS_REQUIRED = frozenset({"x", "y"})
VISUAL_REQUIRED = frozenset({"keyframe", "focus"})
MOTION_REQUIRED = frozenset({"preset", "strength"})
CAPTION_REQUIRED = frozenset({"mode"})
TRANSITION_REQUIRED = frozenset({"type", "duration_sec"})
MOTION_PRESETS = frozenset(
    {"static", "slow_push_in", "slow_pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "gentle_drift"}
)
MOTION_STRENGTHS = frozenset({"low", "medium", "high"})
SPEECH_KINDS = frozenset({"narration", "dialogue"})
CAPTION_MODES = frozenset({"speech", "custom", "none"})
TRANSITION_TYPES = frozenset({"cut", "crossfade"})
ASSET_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
ERROR_CODES = frozenset(
    {
        "bundle.root_invalid",
        "bundle.file_missing",
        "json.invalid",
        "schema.version_unsupported",
        "schema.required",
        "schema.unknown_field",
        "schema.type_invalid",
        "schema.value_invalid",
        "schema.condition_failed",
        "project.id_mismatch",
        "shot.id_duplicate",
        "shot.order_invalid",
        "path.format_invalid",
        "path.outside_bundle",
        "path.symlink_forbidden",
        "asset.missing",
        "asset.type_unsupported",
        "asset.hash_mismatch",
    }
)

PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHOT_ID_RE = re.compile(r"^shot-[0-9]{3}$")
SPEAKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class _Issues:
    def __init__(self) -> None:
        self.items: list[ContractIssue] = []

    def add(self, code: str, document: str, location: str, message: str) -> None:
        self.items.append(ContractIssue(code, document, location, message))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(root: Path, name: str, issues: _Issues) -> dict[str, Any] | None:
    path = root / name
    if path.is_symlink():
        issues.add("path.symlink_forbidden", name, "$", f"{name} 不得为符号链接")
        return None
    if not path.exists() or not path.is_file():
        issues.add("bundle.file_missing", name, "$", f"缺少必需文件 {name}")
        return None
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            issues.add("schema.value_invalid", name, "$", "JSON 文件超过 8 MiB 运行安全上限")
            return None
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"非法数值 {token}")),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        issues.add("json.invalid", name, "$", f"{name} 不是有效 UTF-8 JSON：{exc}")
        return None
    if not isinstance(value, dict):
        issues.add("schema.type_invalid", name, "$", "JSON 顶层必须是对象")
        return None
    return value


def _object(
    value: Any,
    *,
    document: str,
    location: str,
    required: frozenset[str],
    allowed: frozenset[str],
    issues: _Issues,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        issues.add("schema.type_invalid", document, location, "字段必须是对象")
        return None
    for field in sorted(required - set(value)):
        issues.add("schema.required", document, f"{location}.{field}", f"缺少必填字段 {field}")
    for field in sorted(set(value) - allowed):
        issues.add("schema.unknown_field", document, f"{location}.{field}", f"未知字段 {field}")
    return value


def _string(
    value: Any,
    *,
    document: str,
    location: str,
    issues: _Issues,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
) -> str | None:
    if not isinstance(value, str):
        issues.add("schema.type_invalid", document, location, "字段必须是字符串")
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(value) > maximum
        or (pattern and (normalized != value or not pattern.fullmatch(value)))
    ):
        issues.add("schema.value_invalid", document, location, "字符串格式或长度不合法")
        return None
    return normalized


def _enum(value: Any, allowed: frozenset[str], document: str, location: str, issues: _Issues) -> str | None:
    if not isinstance(value, str):
        issues.add("schema.type_invalid", document, location, "字段必须是字符串")
        return None
    if value not in allowed:
        issues.add("schema.value_invalid", document, location, "字段值不在允许枚举中")
        return None
    return value


def _number(
    value: Any,
    *,
    document: str,
    location: str,
    issues: _Issues,
    minimum: float,
    maximum: float,
) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        issues.add("schema.type_invalid", document, location, "字段必须是数字")
        return None
    if not _is_number(value) or not minimum <= float(value) <= maximum:
        issues.add("schema.value_invalid", document, location, "数值超出允许范围或不是有限数")
        return None
    return float(value)


def _integer_const(value: Any, expected: int, document: str, location: str, issues: _Issues) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        issues.add("schema.type_invalid", document, location, "字段必须是整数")
        return None
    if value != expected:
        code = "schema.version_unsupported" if location.endswith("schema_version") else "schema.value_invalid"
        issues.add(code, document, location, f"仅支持值 {expected}")
        return None
    return value


def _voice(value: Any, document: str, location: str, issues: _Issues) -> str | None:
    voice = _string(value, document=document, location=location, issues=issues, maximum=255)
    if voice is None:
        return None
    basename = voice[:-4] if voice.endswith(".wav") else ""
    if len(voice) < 5 or voice != value or not basename or basename[-1].isspace() or "/" in voice or "\\" in voice or any(ord(c) < 32 or ord(c) == 127 for c in voice):
        issues.add("schema.value_invalid", document, location, "音色必须是安全的 .wav 文件名")
        return None
    return voice


def _timing(value: Any, document: str, location: str, issues: _Issues) -> tuple[float, float] | None:
    obj = _object(
        value,
        document=document,
        location=location,
        required=TIMING_REQUIRED,
        allowed=TIMING_REQUIRED,
        issues=issues,
    )
    if obj is None:
        return None
    head = _number(obj.get("head_pad_sec"), document=document, location=f"{location}.head_pad_sec", issues=issues, minimum=0, maximum=3)
    tail = _number(obj.get("tail_pad_sec"), document=document, location=f"{location}.tail_pad_sec", issues=issues, minimum=0, maximum=3)
    return (head, tail) if head is not None and tail is not None else None


def _validate_project(value: dict[str, Any], issues: _Issues) -> ProjectSpec | None:
    document = "project.json"
    before = len(issues.items)
    obj = _object(value, document=document, location="$", required=PROJECT_REQUIRED, allowed=PROJECT_FIELDS, issues=issues)
    if obj is None:
        return None
    version = _integer_const(obj.get("schema_version"), SCHEMA_VERSION, document, "$.schema_version", issues)
    project_id = _string(obj.get("project_id"), document=document, location="$.project_id", issues=issues, maximum=64, pattern=PROJECT_ID_RE)
    title = _string(obj.get("title"), document=document, location="$.title", issues=issues, maximum=120)
    language = _enum(obj.get("language"), frozenset({"zh-CN"}), document, "$.language", issues)
    target = None
    if "target_duration_sec" in obj:
        target = _number(obj["target_duration_sec"], document=document, location="$.target_duration_sec", issues=issues, minimum=1, maximum=600)

    canvas = _object(obj.get("canvas"), document=document, location="$.canvas", required=frozenset({"width", "height", "fps"}), allowed=frozenset({"width", "height", "fps"}), issues=issues)
    width = height = fps = None
    if canvas is not None:
        width = _integer_const(canvas.get("width"), 1080, document, "$.canvas.width", issues)
        height = _integer_const(canvas.get("height"), 1920, document, "$.canvas.height", issues)
        fps = _integer_const(canvas.get("fps"), 30, document, "$.canvas.fps", issues)

    defaults = _object(obj.get("defaults"), document=document, location="$.defaults", required=frozenset({"voice", "timing"}), allowed=frozenset({"voice", "timing"}), issues=issues)
    voice = None
    timing = None
    if defaults is not None:
        voice = _voice(defaults.get("voice"), document, "$.defaults.voice", issues)
        timing = _timing(defaults.get("timing"), document, "$.defaults.timing", issues)

    captions = _object(obj.get("captions"), document=document, location="$.captions", required=frozenset({"enabled", "style_preset"}), allowed=frozenset({"enabled", "style_preset"}), issues=issues)
    enabled = style = None
    if captions is not None:
        enabled = captions.get("enabled")
        if not isinstance(enabled, bool):
            issues.add("schema.type_invalid", document, "$.captions.enabled", "字段必须是布尔值")
            enabled = None
        style = _enum(captions.get("style_preset"), frozenset({"default_lower_third"}), document, "$.captions.style_preset", issues)

    if len(issues.items) != before or None in (version, project_id, title, width, height, fps, voice, timing, enabled, style) or language != "zh-CN":
        return None
    return ProjectSpec(version, project_id, title, language, target, width, height, fps, voice, timing[0], timing[1], enabled, style)


def _validate_asset(root: Path, raw: str, declared_hash: str, document: str, location: str, issues: _Issues) -> Path | None:
    if raw != raw.strip() or not raw or any(ord(c) < 32 or ord(c) == 127 for c in raw) or "\\" in raw or raw.startswith("~"):
        issues.add("path.format_invalid", document, location, "路径必须是无控制字符和反斜杠的 POSIX 相对路径")
        return None
    if raw.startswith("/") or PureWindowsPath(raw).is_absolute():
        issues.add("path.outside_bundle", document, location, "绝对路径不允许")
        return None
    if URI_RE.match(raw):
        issues.add("path.format_invalid", document, location, "URI 不允许作为本地素材路径")
        return None
    raw_parts = raw.split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        issues.add("path.outside_bundle", document, location, "路径不得包含 . 或 .. 段")
        return None
    try:
        parts = PurePosixPath(raw).parts
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                issues.add("path.symlink_forbidden", document, location, "路径祖先或目标不得为符号链接")
                return None
        resolved = current.resolve(strict=False)
        if not resolved.is_relative_to(root):
            issues.add("path.outside_bundle", document, location, "路径解析后越出任务目录")
            return None
        if not current.exists():
            issues.add("asset.missing", document, location, "引用素材不存在")
            return None
        if not current.is_file() or current.stat().st_size <= 0 or current.suffix.lower() not in ASSET_SUFFIXES:
            issues.add("asset.type_unsupported", document, location, "素材必须是受支持的非空常规图片文件")
            return None
        if _sha256_file(current) != declared_hash:
            issues.add("asset.hash_mismatch", document, location.replace(".path", ".sha256"), "素材 SHA-256 与声明不符")
            return None
    except OSError as exc:
        issues.add("path.format_invalid", document, location, f"路径无法由当前文件系统安全表示：{exc}")
        return None
    return resolved


def _validate_storyboard(value: dict[str, Any], root: Path, project: ProjectSpec | None, issues: _Issues) -> tuple[ShotSpec, ...] | None:
    document = "storyboard.json"
    start = len(issues.items)
    obj = _object(value, document=document, location="$", required=STORYBOARD_REQUIRED, allowed=STORYBOARD_FIELDS, issues=issues)
    if obj is None:
        return None
    _integer_const(obj.get("schema_version"), SCHEMA_VERSION, document, "$.schema_version", issues)
    project_id = _string(obj.get("project_id"), document=document, location="$.project_id", issues=issues, maximum=64, pattern=PROJECT_ID_RE)
    if project and project_id and project.project_id != project_id:
        issues.add("project.id_mismatch", document, "$.project_id", "project_id 与 project.json 不一致")
    raw_shots = obj.get("shots")
    if not isinstance(raw_shots, list):
        issues.add("schema.type_invalid", document, "$.shots", "shots 必须是数组")
        return None
    if not 1 <= len(raw_shots) <= 100:
        issues.add("schema.value_invalid", document, "$.shots", "shots 数量必须为 1–100")
        return None

    seen: set[str] = set()
    shots: list[ShotSpec] = []
    for index, raw_shot in enumerate(raw_shots):
        loc = f"$.shots[{index}]"
        shot_start = len(issues.items)
        shot = _object(raw_shot, document=document, location=loc, required=SHOT_REQUIRED, allowed=SHOT_FIELDS, issues=issues)
        if shot is None:
            continue
        shot_id = _string(shot.get("id"), document=document, location=f"{loc}.id", issues=issues, maximum=8, pattern=SHOT_ID_RE)
        if shot_id:
            if shot_id in seen:
                issues.add("shot.id_duplicate", document, f"{loc}.id", "镜头 ID 重复")
            else:
                seen.add(shot_id)
                expected = f"shot-{index + 1:03d}"
                if shot_id != expected:
                    issues.add("shot.order_invalid", document, f"{loc}.id", f"此位置应为 {expected}")
        purpose = _string(shot.get("purpose"), document=document, location=f"{loc}.purpose", issues=issues, maximum=300)

        speech = _object(shot.get("speech"), document=document, location=f"{loc}.speech", required=SPEECH_REQUIRED, allowed=SPEECH_REQUIRED | {"voice", "speaker_id"}, issues=issues)
        kind = text = voice = speaker = None
        if speech is not None:
            kind = _enum(speech.get("kind"), SPEECH_KINDS, document, f"{loc}.speech.kind", issues)
            text = _string(speech.get("text"), document=document, location=f"{loc}.speech.text", issues=issues, maximum=1000)
            voice = _voice(speech["voice"], document, f"{loc}.speech.voice", issues) if "voice" in speech else (project.default_voice if project else None)
            if "speaker_id" in speech:
                speaker = _string(speech["speaker_id"], document=document, location=f"{loc}.speech.speaker_id", issues=issues, maximum=64, pattern=SPEAKER_ID_RE)

        visual = _object(shot.get("visual"), document=document, location=f"{loc}.visual", required=VISUAL_REQUIRED, allowed=VISUAL_REQUIRED, issues=issues)
        key_path = key_hash = resolved = fx = fy = None
        if visual is not None:
            keyframe = _object(visual.get("keyframe"), document=document, location=f"{loc}.visual.keyframe", required=KEYFRAME_REQUIRED, allowed=KEYFRAME_REQUIRED, issues=issues)
            if keyframe is not None:
                raw_path = keyframe.get("path")
                if not isinstance(raw_path, str):
                    issues.add("schema.type_invalid", document, f"{loc}.visual.keyframe.path", "字段必须是字符串")
                elif not raw_path or len(raw_path) > 1024:
                    issues.add("schema.value_invalid", document, f"{loc}.visual.keyframe.path", "路径为空或过长")
                else:
                    key_path = raw_path
                key_hash = _string(keyframe.get("sha256"), document=document, location=f"{loc}.visual.keyframe.sha256", issues=issues, maximum=64, pattern=SHA256_RE)
                if key_path and key_hash:
                    resolved = _validate_asset(root, key_path, key_hash, document, f"{loc}.visual.keyframe.path", issues)
            focus = _object(visual.get("focus"), document=document, location=f"{loc}.visual.focus", required=FOCUS_REQUIRED, allowed=FOCUS_REQUIRED, issues=issues)
            if focus is not None:
                fx = _number(focus.get("x"), document=document, location=f"{loc}.visual.focus.x", issues=issues, minimum=0, maximum=1)
                fy = _number(focus.get("y"), document=document, location=f"{loc}.visual.focus.y", issues=issues, minimum=0, maximum=1)

        motion = _object(shot.get("motion"), document=document, location=f"{loc}.motion", required=MOTION_REQUIRED, allowed=MOTION_REQUIRED | {"intent"}, issues=issues)
        preset = strength = intent = None
        if motion is not None:
            preset = _enum(motion.get("preset"), MOTION_PRESETS, document, f"{loc}.motion.preset", issues)
            strength = _enum(motion.get("strength"), MOTION_STRENGTHS, document, f"{loc}.motion.strength", issues)
            if "intent" in motion:
                intent = _string(motion["intent"], document=document, location=f"{loc}.motion.intent", issues=issues, maximum=300)

        timing = _timing(shot["timing"], document, f"{loc}.timing", issues) if "timing" in shot else ((project.default_head_pad_sec, project.default_tail_pad_sec) if project else None)

        caption = _object(shot.get("caption"), document=document, location=f"{loc}.caption", required=CAPTION_REQUIRED, allowed=CAPTION_REQUIRED | {"text"}, issues=issues)
        caption_mode = caption_text = None
        if caption is not None:
            caption_mode = _enum(caption.get("mode"), CAPTION_MODES, document, f"{loc}.caption.mode", issues)
            has_text = "text" in caption
            if caption_mode == "custom" and not has_text:
                issues.add("schema.condition_failed", document, f"{loc}.caption.text", "custom 模式必须提供 text")
            elif caption_mode in {"speech", "none"} and has_text:
                issues.add("schema.condition_failed", document, f"{loc}.caption.text", "此字幕模式不得提供 text")
            elif caption_mode == "custom":
                caption_text = _string(caption.get("text"), document=document, location=f"{loc}.caption.text", issues=issues, maximum=1000)
            elif caption_mode == "speech":
                caption_text = text

        transition = _object(shot.get("transition_out"), document=document, location=f"{loc}.transition_out", required=TRANSITION_REQUIRED, allowed=TRANSITION_REQUIRED, issues=issues)
        transition_type = duration = None
        if transition is not None:
            transition_type = _enum(transition.get("type"), TRANSITION_TYPES, document, f"{loc}.transition_out.type", issues)
            duration = _number(transition.get("duration_sec"), document=document, location=f"{loc}.transition_out.duration_sec", issues=issues, minimum=0, maximum=1)
            if duration is not None and ((transition_type == "cut" and duration != 0) or (transition_type == "crossfade" and not 0.1 <= duration <= 1.0)):
                issues.add("schema.condition_failed", document, f"{loc}.transition_out.duration_sec", "转场类型与时长不匹配")

        hero = shot.get("hero", False)
        if not isinstance(hero, bool):
            issues.add("schema.type_invalid", document, f"{loc}.hero", "hero 必须是布尔值")

        required_values = (shot_id, purpose, kind, text, voice, key_path, key_hash, resolved, fx, fy, preset, strength, timing, caption_mode, transition_type, duration)
        if len(issues.items) == shot_start and all(value is not None for value in required_values):
            shots.append(ShotSpec(shot_id, purpose, kind, text, voice, speaker, key_path, resolved, key_hash, fx, fy, preset, strength, intent, timing[0], timing[1], caption_mode, caption_text, transition_type, duration, hero))

    return tuple(shots) if len(issues.items) == start and len(shots) == len(raw_shots) else None


def validate_job_bundle(job_dir: str | Path) -> ValidationResult:
    """只读验证 Job Bundle；可预期问题均进入稳定 issues。"""
    issues = _Issues()
    try:
        raw_root = Path(job_dir).expanduser()
        root_invalid = raw_root.is_symlink() or not raw_root.exists() or not raw_root.is_dir()
        root = raw_root.resolve() if not root_invalid else None
    except (OSError, RuntimeError):
        root_invalid = True
        root = None
    if root_invalid or root is None:
        issues.add("bundle.root_invalid", "bundle", "$", "任务根目录不存在、不是目录或为符号链接")
        return ValidationResult(tuple(issues.items))
    project_json = _load_json(root, "project.json", issues)
    storyboard_json = _load_json(root, "storyboard.json", issues)
    project = _validate_project(project_json, issues) if project_json is not None else None
    shots = _validate_storyboard(storyboard_json, root, project, issues) if storyboard_json is not None else None
    bundle = JobBundle(root, project, shots) if not issues.items and project is not None and shots is not None else None
    return ValidationResult(tuple(issues.items), bundle=bundle)


def load_job_bundle(job_dir: str | Path) -> JobBundle:
    """加载有效 Bundle；无效时抛出携带结构化 issues 的专用异常。"""
    result = validate_job_bundle(job_dir)
    if not result.ok or result.bundle is None:
        raise JobBundleValidationError(result.errors)
    return result.bundle
