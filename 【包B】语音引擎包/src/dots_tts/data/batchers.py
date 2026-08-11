from __future__ import annotations

import warnings
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from dots_tts.utils.profiling import ensure_data_profiler


@dataclass(slots=True)
class BatchDecision:
    dropped_samples: list[dict]
    batch_samples: list[dict]


@dataclass(slots=True)
class _PoolSample:
    sample: dict
    num_audio_tokens: int
    num_text_tokens: int
    arrival_step: int


class OnlineBatcher:
    def __init__(
        self,
        *,
        max_audio_tokens_in_batch: int,
        max_text_tokens_in_batch: int,
        max_batch_size: int | None,
        sample_pool_size: int,
        profiler=None,
    ):
        self.max_audio_tokens_in_batch = max(1, int(max_audio_tokens_in_batch))
        self.max_text_tokens_in_batch = max(1, int(max_text_tokens_in_batch))
        self.max_batch_size = max_batch_size
        self.sample_pool_size = max(1, int(sample_pool_size))
        self.profiler = ensure_data_profiler(profiler)

    @staticmethod
    def _sort_pool(pool: list[_PoolSample]) -> None:
        pool.sort(
            key=lambda item: (
                item.num_audio_tokens,
                item.num_text_tokens,
                -item.arrival_step,
            ),
            reverse=True,
        )

    def _choose_anchor_index(
        self,
        pool: list[_PoolSample],
        *,
        decision_step: int,
    ) -> int:
        oldest_waiting_index = -1
        oldest_waiting_step = decision_step

        for index, item in enumerate(pool):
            waited_steps = decision_step - item.arrival_step
            if waited_steps < self.sample_pool_size:
                continue
            if item.arrival_step <= oldest_waiting_step:
                oldest_waiting_index = index
                oldest_waiting_step = item.arrival_step

        return 0 if oldest_waiting_index < 0 else oldest_waiting_index

    def _build_next_decision(
        self,
        pool: list[_PoolSample],
        *,
        decision_step: int,
    ) -> BatchDecision:
        dropped_samples: list[dict] = []
        batch_samples: list[dict] = []
        selected_indices: list[int] = []
        anchor_index = self._choose_anchor_index(pool, decision_step=decision_step)
        anchor = pool[anchor_index]

        exceed_audio_budget = anchor.num_audio_tokens > self.max_audio_tokens_in_batch
        exceed_text_budget = anchor.num_text_tokens > self.max_text_tokens_in_batch
        exceed_batch_size = self.max_batch_size is not None and self.max_batch_size < 1
        if exceed_audio_budget or exceed_text_budget or exceed_batch_size:
            skipped = pool.pop(anchor_index).sample
            dropped_samples.append(skipped)
            warnings.warn(
                "Skipping sample that exceeds batching limits on its own: "
                f"fid={skipped.get('fid')!r}, "
                f"num_audio_tokens={anchor.num_audio_tokens}, "
                f"input_ids_length={anchor.num_text_tokens}, "
                f"max_audio_tokens_in_batch={self.max_audio_tokens_in_batch}, "
                f"max_text_tokens_in_batch={self.max_text_tokens_in_batch}, "
                f"max_batch_size={self.max_batch_size}",
                RuntimeWarning,
                stacklevel=2,
            )
            return BatchDecision(
                dropped_samples=dropped_samples,
                batch_samples=batch_samples,
            )

        longest_audio_tokens = anchor.num_audio_tokens
        longest_text_tokens = anchor.num_text_tokens
        batch_samples.append(anchor.sample)
        selected_indices.append(anchor_index)

        for index, item in enumerate(pool):
            if index == anchor_index:
                continue
            if (
                self.max_batch_size is not None
                and len(batch_samples) >= self.max_batch_size
            ):
                break

            proposed_batch_size = len(batch_samples) + 1
            proposed_longest_audio_tokens = max(
                longest_audio_tokens,
                item.num_audio_tokens,
            )
            proposed_longest_text_tokens = max(
                longest_text_tokens,
                item.num_text_tokens,
            )
            if (
                proposed_longest_audio_tokens * proposed_batch_size
                > self.max_audio_tokens_in_batch
            ):
                continue
            if (
                proposed_longest_text_tokens * proposed_batch_size
                > self.max_text_tokens_in_batch
            ):
                continue

            batch_samples.append(item.sample)
            selected_indices.append(index)
            longest_audio_tokens = proposed_longest_audio_tokens
            longest_text_tokens = proposed_longest_text_tokens

        for index in sorted(set(selected_indices), reverse=True):
            pool.pop(index)

        return BatchDecision(
            dropped_samples=dropped_samples,
            batch_samples=batch_samples,
        )

    def build_decisions(self, sample_iter: Iterable[dict]) -> Iterator[BatchDecision]:
        pool: list[_PoolSample] = []
        source_exhausted = False
        decision_step = 0
        iterator = iter(sample_iter)

        while not source_exhausted or pool:
            while not source_exhausted and len(pool) < self.sample_pool_size:
                try:
                    sample = next(iterator)
                except StopIteration:
                    source_exhausted = True
                    break
                pool.append(
                    _PoolSample(
                        sample=sample,
                        num_audio_tokens=int(sample.get("num_audio_tokens", 0)),
                        num_text_tokens=int(sample.get("input_ids_length", 0)),
                        arrival_step=decision_step,
                    )
                )

            if not pool:
                break

            profiler = self.profiler
            with profiler.measure("main.sort_pool", count=len(pool)):
                self._sort_pool(pool)
            with profiler.measure("main.build_batch_decision"):
                decision = self._build_next_decision(
                    pool,
                    decision_step=decision_step,
                )
            if decision.dropped_samples or decision.batch_samples:
                decision_step += 1
                yield decision
                continue
            raise RuntimeError("OnlineBatcher failed to make progress on a non-empty pool.")
