"""短视频 V2 Job Bundle Schema v1 的稳定公共入口。"""

from .contract import load_job_bundle, validate_job_bundle
from .models import (
    ContractIssue,
    JobBundle,
    JobBundleValidationError,
    ProjectSpec,
    ShotSpec,
    ValidationResult,
)

__all__ = [
    "ContractIssue",
    "JobBundle",
    "JobBundleValidationError",
    "ProjectSpec",
    "ShotSpec",
    "ValidationResult",
    "load_job_bundle",
    "validate_job_bundle",
]


def render_job(*args, **kwargs):
    """延迟导入核心渲染器，保持 `import video_v2` 无运行时副作用。"""
    from .pipeline import render_job as _render_job

    return _render_job(*args, **kwargs)


__all__.append("render_job")


def __getattr__(name):
    if name == "RenderResult":
        from .pipeline import RenderResult

        return RenderResult
    raise AttributeError(name)


__all__.append("RenderResult")
