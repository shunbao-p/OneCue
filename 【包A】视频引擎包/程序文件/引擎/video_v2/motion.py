"""V2 的 FFmpeg 固定运镜预设。"""

from __future__ import annotations

import math
from dataclasses import dataclass


MOTION_IMPLEMENTATION_VERSION = "ffmpeg-motion-v2.1"
MOTION_PRESETS = (
    "static",
    "slow_push_in",
    "slow_pull_out",
    "pan_left",
    "pan_right",
    "tilt_up",
    "tilt_down",
    "gentle_drift",
)
MOTION_STRENGTHS = ("low", "medium", "high")


@dataclass(frozen=True)
class MotionParameters:
    overscan: float
    zoom_delta: float
    travel_fraction: float


_STRENGTH_PARAMETERS = {
    "low": MotionParameters(overscan=1.06, zoom_delta=0.025, travel_fraction=0.30),
    "medium": MotionParameters(overscan=1.10, zoom_delta=0.050, travel_fraction=0.55),
    "high": MotionParameters(overscan=1.16, zoom_delta=0.080, travel_fraction=0.80),
}


def clamp_focus(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("focus 必须为有限数")
    return min(1.0, max(0.0, numeric))


def motion_parameters(preset: str, strength: str) -> MotionParameters:
    if preset not in MOTION_PRESETS:
        raise ValueError(f"未知运镜预设：{preset}")
    try:
        parameters = _STRENGTH_PARAMETERS[strength]
    except KeyError as exc:
        raise ValueError(f"未知运镜强度：{strength}") from exc
    if preset == "static":
        return MotionParameters(overscan=1.0, zoom_delta=0.0, travel_fraction=0.0)
    return parameters


def _even_ceiling(value: float) -> int:
    return int(math.ceil(value / 2.0) * 2)


def _fmt(value: float) -> str:
    return f"{value:.6f}"


def build_motion_filter(
    preset: str,
    strength: str,
    focus_x: float,
    focus_y: float,
    duration_sec: float,
    fps: int,
    width: int,
    height: int,
) -> str:
    """返回确定性的视频滤镜链；它不接受任务传入的任意表达式。"""

    duration = float(duration_sec)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("运镜时长必须为正的有限数")
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps 必须为正整数")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (width, height)):
        raise ValueError("输出尺寸必须为正整数")

    parameters = motion_parameters(preset, strength)
    x_focus = clamp_focus(focus_x)
    y_focus = clamp_focus(focus_y)
    frames = max(2, int(math.ceil(duration * fps)))
    denominator = frames - 1
    progress = f"on/{denominator}"
    scaled_width = _even_ceiling(width * parameters.overscan)
    scaled_height = _even_ceiling(height * parameters.overscan)
    actual_overscan = max(scaled_width / width, scaled_height / height)
    base_zoom = actual_overscan
    amplitude = parameters.travel_fraction / 2.0

    if preset == "slow_push_in":
        zoom = f"{_fmt(base_zoom)}+{_fmt(parameters.zoom_delta)}*{progress}"
        x_position = _fmt(x_focus)
        y_position = _fmt(y_focus)
    elif preset == "slow_pull_out":
        zoom = f"{_fmt(base_zoom + parameters.zoom_delta)}-{_fmt(parameters.zoom_delta)}*{progress}"
        x_position = _fmt(x_focus)
        y_position = _fmt(y_focus)
    else:
        zoom = _fmt(base_zoom)
        x_position = _fmt(x_focus)
        y_position = _fmt(y_focus)
        if preset == "pan_left":
            x_position = f"{_fmt(x_focus)}+{_fmt(amplitude)}*(1-2*{progress})"
        elif preset == "pan_right":
            x_position = f"{_fmt(x_focus)}+{_fmt(amplitude)}*(2*{progress}-1)"
        elif preset == "tilt_up":
            y_position = f"{_fmt(y_focus)}+{_fmt(amplitude)}*(1-2*{progress})"
        elif preset == "tilt_down":
            y_position = f"{_fmt(y_focus)}+{_fmt(amplitude)}*(2*{progress}-1)"
        elif preset == "gentle_drift":
            drift = amplitude * 0.65
            x_position = f"{_fmt(x_focus)}+{_fmt(drift)}*(2*{progress}-1)"
            y_position = f"{_fmt(y_focus)}+{_fmt(drift / 2)}*(1-2*{progress})"

    # zoompan 的 x/y 以输入像素为单位；以 min/max 夹在可裁切区间内。
    x_expr = f"min(max((iw-iw/zoom)*({x_position}),0),iw-iw/zoom)"
    y_expr = f"min(max((ih-ih/zoom)*({y_position}),0),ih-ih/zoom)"
    pre_crop_x = f"min(max((iw-ow)*{_fmt(x_focus)},0),iw-ow)"
    pre_crop_y = f"min(max((ih-oh)*{_fmt(y_focus)},0),ih-oh)"
    return (
        f"scale={scaled_width}:{scaled_height}:force_original_aspect_ratio=increase,"
        f"crop={scaled_width}:{scaled_height}:x='{pre_crop_x}':y='{pre_crop_y}',"
        f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps},"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
    )


# 语义别名，便于后续 FFmpeg Provider 按职责调用。
build_video_filter = build_motion_filter

