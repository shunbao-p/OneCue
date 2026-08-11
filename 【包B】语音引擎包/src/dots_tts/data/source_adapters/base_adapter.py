from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeVar


@dataclass(frozen=True)
class SourceContext:
    """Execution context for a single adapter iterator."""

    epoch: int
    rank: int
    world_size: int
    worker_id: int
    num_workers: int
    seed: int

    @property
    def global_worker_count(self) -> int:
        return max(1, self.world_size * self.num_workers)

    @property
    def global_worker_id(self) -> int:
        return self.rank * self.num_workers + self.worker_id


class BaseSourceAdapter(ABC):
    """State-aware streaming source interface used by the training pipeline."""

    @abstractmethod
    def initial_state(self) -> dict[str, Any]:
        """Return the default iterator state for a new worker/epoch."""

    @abstractmethod
    def iter_samples(
        self,
        context: SourceContext,
        *,
        state: dict[str, Any] | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Yield raw samples and attach the next adapter state to each item."""

    @abstractmethod
    def is_cycle_start_state(self, state: dict[str, Any] | None) -> bool:
        """Return whether ``state`` points at the beginning of a source cycle."""

    def normalize_state(self, state: dict[str, Any] | None) -> dict[str, Any]:
        merged = self.initial_state()
        if state:
            merged.update(deepcopy(state))
        return merged

    def clone_state(self, state: dict[str, Any] | None) -> dict[str, Any]:
        return deepcopy(self.normalize_state(state))

    def advance_cycle(self, state: dict[str, Any] | None) -> dict[str, Any]:
        raise RuntimeError(
            f"{self.__class__.__name__} does not support repeated cycling."
        )


_T = TypeVar("_T")


class ShardableSourceAdapter(BaseSourceAdapter):
    """Helper mixin for deterministic rank/worker sharding."""

    @staticmethod
    def is_assigned_index(index: int, context: SourceContext) -> bool:
        return index % context.global_worker_count == context.global_worker_id

    @staticmethod
    def shard_items(
        items: Sequence[_T],
        context: SourceContext,
        *,
        shuffle: bool = False,
        seed_offset: int = 0,
    ) -> list[_T]:
        assigned = list(items)
        if shuffle:
            random.Random(context.seed + context.epoch + seed_offset).shuffle(assigned)
        return [
            item
            for index, item in enumerate(assigned)
            if ShardableSourceAdapter.is_assigned_index(index, context)
        ]
