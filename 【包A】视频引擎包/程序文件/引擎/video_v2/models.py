"""V2 Job Bundle Schema v1 的不可变公共数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ContractIssue:
    code: str
    document: str
    location: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "document": self.document,
            "location": self.location,
            "message": self.message,
        }


@dataclass(frozen=True)
class ProjectSpec:
    schema_version: int
    project_id: str
    title: str
    language: str
    target_duration_sec: float | None
    width: int
    height: int
    fps: int
    default_voice: str
    default_head_pad_sec: float
    default_tail_pad_sec: float
    captions_enabled: bool
    caption_style_preset: str


@dataclass(frozen=True)
class ShotSpec:
    id: str
    purpose: str
    speech_kind: str
    speech_text: str
    voice: str
    speaker_id: str | None
    keyframe_relative_path: str
    keyframe_path: Path
    keyframe_sha256: str
    focus_x: float
    focus_y: float
    motion_preset: str
    motion_strength: str
    motion_intent: str | None
    head_pad_sec: float
    tail_pad_sec: float
    caption_mode: str
    caption_text: str | None
    transition_type: str
    transition_duration_sec: float
    hero: bool


@dataclass(frozen=True)
class JobBundle:
    root: Path
    project: ProjectSpec
    shots: tuple[ShotSpec, ...]


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[ContractIssue, ...]
    warnings: tuple[ContractIssue, ...] = ()
    bundle: JobBundle | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def project_id(self) -> str | None:
        return self.bundle.project.project_id if self.bundle else None

    @property
    def shot_count(self) -> int:
        return len(self.bundle.shots) if self.bundle else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "contract": "short-video-v2-job-bundle",
            "schema_version": 1,
            "project_id": self.project_id,
            "shot_count": self.shot_count,
            "warnings": [issue.to_dict() for issue in self.warnings],
            "errors": [issue.to_dict() for issue in self.errors],
        }


class JobBundleValidationError(ValueError):
    """任务包不符合 v1 契约；`issues` 可供调用方稳定分支。"""

    def __init__(self, issues: tuple[ContractIssue, ...]):
        self.issues = issues
        summary = issues[0].message if issues else "任务包无效"
        super().__init__(summary)
