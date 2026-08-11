from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass

from dots_tts.data.pipelines.base import BaseSamplePipeline
from dots_tts.data.source_adapters.base_adapter import (
    BaseSourceAdapter,
    SourceContext,
)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    weight: float
    adapter: BaseSourceAdapter
    pipeline: BaseSamplePipeline


_UINT64_MASK = 0xFFFFFFFFFFFFFFFF


def _mix_uint64(value: int) -> int:
    value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9
    value &= _UINT64_MASK
    value = (value ^ (value >> 27)) * 0x94D049BB133111EB
    value &= _UINT64_MASK
    return (value ^ (value >> 31)) & _UINT64_MASK


def _stable_seed(*parts: int) -> int:
    value = 0x9E3779B97F4A7C15
    for part in parts:
        value = (value + int(part) + 0x9E3779B97F4A7C15) & _UINT64_MASK
        value = _mix_uint64(value)
    return value


class SequentialMultiSourceAdapter(BaseSourceAdapter):
    """Finite adapter that concatenates sources in the configured order."""

    def __init__(self, *, sources: list[SourceSpec]):
        if not sources:
            raise ValueError(
                "SequentialMultiSourceAdapter requires at least one source."
            )
        self.sources = list(sources)

    def initial_state(self) -> dict:
        return {
            "source_index": 0,
            "sources": {
                source.name: source.adapter.initial_state() for source in self.sources
            },
        }

    def is_cycle_start_state(self, state: dict | None) -> bool:
        normalized = self.normalize_state(state)
        if int(normalized["source_index"]) != 0:
            return False
        return all(
            source.adapter.is_cycle_start_state(normalized["sources"][source.name])
            for source in self.sources
        )

    def normalize_state(self, state: dict | None) -> dict:
        normalized = super().normalize_state(state)
        source_states = normalized.get("sources") or {}
        normalized["sources"] = {
            source.name: source.adapter.clone_state(source_states.get(source.name))
            for source in self.sources
        }
        normalized["source_index"] = int(normalized.get("source_index", 0))
        return normalized

    def clone_state(self, state: dict | None) -> dict:
        return deepcopy(self.normalize_state(state))

    def iter_samples(
        self,
        context: SourceContext,
        *,
        state: dict | None = None,
    ) -> Iterable[dict]:
        live_state = self.normalize_state(state)
        start_index = int(live_state["source_index"])
        for index in range(start_index, len(self.sources)):
            source = self.sources[index]
            child_state = live_state["sources"][source.name]
            raw_iter = source.adapter.iter_samples(context, state=child_state)
            for sample in source.pipeline(raw_iter):
                item = dict(sample)
                next_child_state = item.pop("_adapter_state", None)
                if next_child_state is None:
                    raise RuntimeError(
                        f"{source.adapter.__class__.__name__} must attach '_adapter_state' to samples."
                    )
                live_state["source_index"] = index
                live_state["sources"][source.name] = source.adapter.clone_state(
                    next_child_state
                )
                item["source_name"] = source.name
                item["_adapter_state"] = self.clone_state(live_state)
                yield item
            live_state["source_index"] = index + 1


class WeightedMultiSourceAdapter(BaseSourceAdapter):
    """Infinite weighted sampler that cycles each child source independently."""

    def __init__(self, *, sources: list[SourceSpec]):
        if not sources:
            raise ValueError("WeightedMultiSourceAdapter requires at least one source.")
        invalid = [source.name for source in sources if float(source.weight) <= 0.0]
        if invalid:
            raise ValueError(f"Source weights must be positive: {invalid}")
        self.sources = list(sources)
        self._cumulative_weights = []
        total = 0.0
        for source in self.sources:
            total += float(source.weight)
            self._cumulative_weights.append(total)
        self._total_weight = total

    def initial_state(self) -> dict:
        return {
            "draw_count": 0,
            "sources": {
                source.name: source.adapter.initial_state() for source in self.sources
            },
        }

    def is_cycle_start_state(self, state: dict | None) -> bool:
        normalized = self.normalize_state(state)
        if int(normalized["draw_count"]) != 0:
            return False
        return all(
            source.adapter.is_cycle_start_state(normalized["sources"][source.name])
            for source in self.sources
        )

    def normalize_state(self, state: dict | None) -> dict:
        normalized = super().normalize_state(state)
        source_states = normalized.get("sources") or {}
        normalized["sources"] = {
            source.name: source.adapter.clone_state(source_states.get(source.name))
            for source in self.sources
        }
        normalized["draw_count"] = int(normalized.get("draw_count", 0))
        return normalized

    def clone_state(self, state: dict | None) -> dict:
        return deepcopy(self.normalize_state(state))

    def _source_draw_value(self, context: SourceContext, draw_count: int) -> float:
        raw = _stable_seed(
            context.seed,
            context.epoch,
            context.rank,
            context.worker_id,
            draw_count,
        )
        return (raw / float(1 << 64)) * self._total_weight

    def _pick_source(self, context: SourceContext, draw_count: int) -> SourceSpec:
        draw_value = self._source_draw_value(context, draw_count)
        for source, upper in zip(self.sources, self._cumulative_weights, strict=True):
            if draw_value < upper:
                return source
        return self.sources[-1]

    def iter_samples(
        self,
        context: SourceContext,
        *,
        state: dict | None = None,
    ) -> Iterable[dict]:
        live_state = self.normalize_state(state)
        iterators: dict[str, object] = {}

        while True:
            draw_count = int(live_state["draw_count"])
            source = self._pick_source(context, draw_count)

            while True:
                child_state = live_state["sources"][source.name]
                child_iter = iterators.get(source.name)
                if child_iter is None:
                    raw_iter = source.adapter.iter_samples(context, state=child_state)
                    child_iter = iter(source.pipeline(raw_iter))
                    iterators[source.name] = child_iter

                try:
                    sample = dict(next(child_iter))
                except StopIteration:
                    if source.adapter.is_cycle_start_state(child_state):
                        raise RuntimeError(
                            "Weighted source yielded no samples for this worker. "
                            f"source={source.name!r}, worker={context.global_worker_id}, "
                            f"epoch={context.epoch}"
                        )
                    iterators.pop(source.name, None)
                    live_state["sources"][source.name] = source.adapter.advance_cycle(
                        child_state
                    )
                    continue

                next_child_state = sample.pop("_adapter_state", None)
                if next_child_state is None:
                    raise RuntimeError(
                        f"{source.adapter.__class__.__name__} must attach '_adapter_state' to samples."
                    )
                live_state["sources"][source.name] = source.adapter.clone_state(
                    next_child_state
                )
                live_state["draw_count"] = draw_count + 1
                sample["source_name"] = source.name
                sample["_adapter_state"] = self.clone_state(live_state)
                yield sample
                break
