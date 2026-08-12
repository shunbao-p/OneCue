"""V2 cut/crossfade 权威时间线的纯数学实现。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


TIMELINE_IMPLEMENTATION_VERSION = "timeline-v2.1"
LAST_TRANSITION_WARNING = "timeline.last_transition_ignored"


class TimelineError(ValueError):
    code = "timeline.invalid"

    def __init__(self, message: str, *, shot_index: int | None = None):
        self.shot_index = shot_index
        super().__init__(message)

    def to_dict(self) -> dict[str, int | str | None]:
        return {"code": self.code, "message": str(self), "shot_index": self.shot_index}


@dataclass(frozen=True)
class TimelineShot:
    index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    transition_type: str
    transition_duration_sec: float
    overlap_sec: float
    cumulative_offset_sec: float

    @property
    def transition_out(self) -> str:
        return self.transition_type

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "index": self.index,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "duration_sec": self.duration_sec,
            "transition_type": self.transition_type,
            "transition_duration_sec": self.transition_duration_sec,
            "overlap_sec": self.overlap_sec,
            "cumulative_offset_sec": self.cumulative_offset_sec,
        }


@dataclass(frozen=True)
class Timeline:
    shots: tuple[TimelineShot, ...]
    expected_duration: float
    last_transition_ignored: bool
    warnings: tuple[str, ...] = ()

    @property
    def expected_final_duration(self) -> float:
        return self.expected_duration

    @property
    def overlaps(self) -> tuple[float, ...]:
        return tuple(shot.overlap_sec for shot in self.shots)

    def to_dict(self) -> dict[str, object]:
        return {
            "shots": [shot.to_dict() for shot in self.shots],
            "expected_duration": self.expected_duration,
            "last_transition_ignored": self.last_transition_ignored,
            "warnings": list(self.warnings),
        }


def _transition_pair(value: object, index: int) -> tuple[str, float]:
    if isinstance(value, (str, bytes)):
        raise TimelineError("转场必须是 (type, duration_sec) 对", shot_index=index)
    try:
        transition_type, duration = value  # type: ignore[misc]
    except (TypeError, ValueError) as exc:
        raise TimelineError("转场必须是 (type, duration_sec) 对", shot_index=index) from exc
    if transition_type not in {"cut", "crossfade"}:
        raise TimelineError(f"未知转场类型：{transition_type}", shot_index=index)
    try:
        numeric = float(duration)
    except (TypeError, ValueError) as exc:
        raise TimelineError("转场时长必须是数字", shot_index=index) from exc
    if not math.isfinite(numeric) or numeric < 0:
        raise TimelineError("转场时长必须是非负有限数", shot_index=index)
    if transition_type == "cut" and numeric != 0:
        raise TimelineError("cut 转场时长必须为 0", shot_index=index)
    if transition_type == "crossfade" and numeric <= 0:
        raise TimelineError("crossfade 转场时长必须大于 0", shot_index=index)
    return transition_type, numeric


def build_timeline(
    shot_durations: Sequence[float] | Iterable[float],
    transitions: Sequence[tuple[str, float]] | Iterable[tuple[str, float]],
) -> Timeline:
    """以已 probe 的镜头实际时长构建时间线。"""

    raw_durations = tuple(shot_durations)
    raw_transitions = tuple(transitions)
    if not raw_durations:
        raise TimelineError("时间线至少需要一个镜头")
    if len(raw_transitions) != len(raw_durations):
        raise TimelineError("每个镜头必须各有一个 transition_out")

    durations: list[float] = []
    for index, duration in enumerate(raw_durations):
        try:
            numeric = float(duration)
        except (TypeError, ValueError) as exc:
            raise TimelineError("镜头时长必须是数字", shot_index=index) from exc
        if not math.isfinite(numeric) or numeric <= 0:
            raise TimelineError("镜头时长必须是正的有限数", shot_index=index)
        durations.append(numeric)

    normalized = [_transition_pair(value, index) for index, value in enumerate(raw_transitions)]
    last_transition_ignored = normalized[-1][0] != "cut"
    if last_transition_ignored:
        normalized[-1] = ("cut", 0.0)

    for index, (transition_type, overlap) in enumerate(normalized[:-1]):
        if transition_type == "crossfade" and overlap >= min(durations[index], durations[index + 1]) - 1e-9:
            raise TimelineError(
                f"第 {index + 1} 个 crossfade 过长，相邻镜头无法承受 {overlap:.6f} 秒重叠",
                shot_index=index,
            )

    shots: list[TimelineShot] = []
    start = 0.0
    cumulative_overlap = 0.0
    for index, duration in enumerate(durations):
        transition_type, transition_duration = normalized[index]
        overlap = transition_duration if transition_type == "crossfade" and index < len(durations) - 1 else 0.0
        end = start + duration
        shots.append(
            TimelineShot(
                index=index,
                start_sec=start,
                end_sec=end,
                duration_sec=duration,
                transition_type=transition_type,
                transition_duration_sec=transition_duration,
                overlap_sec=overlap,
                cumulative_offset_sec=cumulative_overlap,
            )
        )
        cumulative_overlap += overlap
        start = end - overlap

    warnings = (LAST_TRANSITION_WARNING,) if last_transition_ignored else ()
    expected_duration = sum(durations) - cumulative_overlap
    return Timeline(tuple(shots), expected_duration, last_transition_ignored, warnings)

