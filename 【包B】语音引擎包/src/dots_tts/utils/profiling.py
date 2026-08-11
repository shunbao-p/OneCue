from __future__ import annotations

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from multiprocessing import Queue
from typing import Iterator

import torch
from loguru import logger

INFERENCE_STAGE_NAMES = (
    "FM",
    "latent_encoder",
    "patch_encoder",
    "LLM",
    "latent_decoder",
    "speaker_encoder",
    "vocoder",
)

_INFERENCE_STAGE_NAME_MAP = {
    name.lower(): name for name in INFERENCE_STAGE_NAMES
}
_CURRENT_INFERENCE_PROFILER: ContextVar[InferenceProfiler | None] = ContextVar(
    "current_inference_profiler",
    default=None,
)


def normalize_inference_stage_name(name: str) -> str:
    canonical = _INFERENCE_STAGE_NAME_MAP.get(name.strip().lower())
    if canonical is None:
        raise ValueError(
            f"Unsupported inference stage '{name}'. "
            f"Expected one of: {', '.join(INFERENCE_STAGE_NAMES)}."
        )
    return canonical


@dataclass(slots=True)
class InferenceStageStat:
    seconds: float = 0.0
    count: int = 0


@dataclass(frozen=True, slots=True)
class ProfileEvent:
    stage: str
    seconds: float
    count: int
    pid: int


class DataProfiler:
    def __init__(self, queue: Queue | None = None):
        self._queue = queue
        self._pid = os.getpid()

    @property
    def enabled(self) -> bool:
        return self._queue is not None

    @contextmanager
    def measure(self, stage: str, *, count: int = 1) -> Iterator[None]:
        if self._queue is None:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            self._queue.put(
                ProfileEvent(
                    stage=stage,
                    seconds=time.perf_counter() - start,
                    count=int(count),
                    pid=self._pid,
                )
            )

    def child(self) -> DataProfiler:
        return DataProfiler(self._queue)


def ensure_data_profiler(profiler: DataProfiler | None) -> DataProfiler:
    return DataProfiler() if profiler is None else profiler


class InferenceProfiler:
    def __init__(self, device: torch.device):
        self._device = device
        self._stats = {
            stage: InferenceStageStat() for stage in INFERENCE_STAGE_NAMES
        }

    def _sync(self) -> None:
        if self._device.type == "cuda":
            torch.cuda.synchronize(self._device)

    @contextmanager
    def measure(self, stage: str, *, count: int = 1) -> Iterator[None]:
        stage = normalize_inference_stage_name(stage)
        self._sync()
        start = time.perf_counter()
        try:
            yield
        finally:
            self._sync()
            stat = self._stats[stage]
            stat.seconds += time.perf_counter() - start
            stat.count += int(count)

    def summary(
        self,
        *,
        duration_seconds: float | None = None,
    ) -> dict[str, dict[str, float | int]]:
        summary: dict[str, dict[str, float | int]] = {}
        for stage in INFERENCE_STAGE_NAMES:
            stat = self._stats[stage]
            payload: dict[str, float | int] = {
                "seconds": stat.seconds,
                "count": stat.count,
            }
            if duration_seconds is not None:
                payload["rtf"] = (
                    stat.seconds / duration_seconds
                    if duration_seconds > 0
                    else float("inf")
                )
            summary[stage] = payload
        return summary


@contextmanager
def inference_profiling(
    *,
    enabled: bool,
    device: torch.device,
) -> Iterator[InferenceProfiler | None]:
    profiler = InferenceProfiler(device) if enabled else None
    with activate_inference_profiler(profiler):
        yield profiler


@contextmanager
def activate_inference_profiler(
    profiler: InferenceProfiler | None,
) -> Iterator[InferenceProfiler | None]:
    if profiler is None:
        yield None
        return
    token: Token[InferenceProfiler | None] = _CURRENT_INFERENCE_PROFILER.set(profiler)
    try:
        yield profiler
    finally:
        _CURRENT_INFERENCE_PROFILER.reset(token)


@contextmanager
def measure_inference(stage: str, *, count: int = 1) -> Iterator[None]:
    profiler = _CURRENT_INFERENCE_PROFILER.get()
    if profiler is None:
        yield
        return
    with profiler.measure(stage, count=count):
        yield


def log_inference_profile(
    *,
    request_id: str,
    profiling: dict[str, dict[str, float | int]],
    duration_seconds: float,
) -> None:
    active_stages = [
        stage
        for stage in INFERENCE_STAGE_NAMES
        if int(profiling[stage]["count"]) > 0
    ]
    if not active_stages:
        logger.info(
            "Inference profiling summary: request_id={} no_profiled_stages duration_seconds={:.3f}",
            request_id,
            duration_seconds,
        )
        return
    for stage in active_stages:
        stats = profiling[stage]
        logger.info(
            "Inference profiling: request_id={} stage={} seconds={:.4f} count={} rtf={:.4f}",
            request_id,
            stage,
            float(stats["seconds"]),
            int(stats["count"]),
            float(stats["rtf"]),
        )


__all__ = [
    "DataProfiler",
    "ProfileEvent",
    "INFERENCE_STAGE_NAMES",
    "activate_inference_profiler",
    "ensure_data_profiler",
    "InferenceProfiler",
    "InferenceStageStat",
    "inference_profiling",
    "log_inference_profile",
    "measure_inference",
    "normalize_inference_stage_name",
]
