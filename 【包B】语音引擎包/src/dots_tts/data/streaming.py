from __future__ import annotations

import math
import multiprocessing as mp
from collections.abc import Iterable
from copy import deepcopy

from torch.utils.data import DataLoader, IterableDataset, get_worker_info

from dots_tts.data.batchers import OnlineBatcher
from dots_tts.utils.profiling import ensure_data_profiler
from dots_tts.data.source_adapters.base_adapter import BaseSourceAdapter, SourceContext

_TRACKING_KEY = "__tracking_state__"
_RESUME_TOPOLOGY_KEY = "resume_topology"


def identity_collate(sample):
    return sample


class StreamingSampleDataset(IterableDataset):
    def __init__(
        self,
        *,
        source: BaseSourceAdapter,
        rank: int,
        world_size: int,
        seed: int,
    ):
        self.source = source
        self.rank = int(rank)
        self.world_size = int(world_size)
        self.seed = int(seed)
        self._epoch = mp.Value("q", 0)
        self._pending_resume_state: dict | None = None

    def load_state_dict(self, state: dict | None) -> None:
        self._pending_resume_state = deepcopy(state) if state else None

    def set_epoch(self, epoch: int) -> None:
        with self._epoch.get_lock():
            self._epoch.value = int(epoch)

    def _current_epoch(self) -> int:
        with self._epoch.get_lock():
            return int(self._epoch.value)

    def _take_resume_state(self, epoch: int) -> dict | None:
        if (
            self._pending_resume_state is None
            or int(self._pending_resume_state.get("epoch", -1)) != int(epoch)
        ):
            return None
        state = deepcopy(self._pending_resume_state)
        self._pending_resume_state = None
        return state

    @staticmethod
    def _validate_resume_topology(
        resume_state: dict,
        *,
        context: SourceContext,
        loader_num_workers: int,
    ) -> None:
        resume_topology = resume_state.get(_RESUME_TOPOLOGY_KEY)
        if not isinstance(resume_topology, dict):
            raise RuntimeError(
                "Resume state is missing required worker topology metadata."
            )
        expected_world_size = int(resume_topology["world_size"])
        expected_num_workers = int(resume_topology["loader_num_workers"])
        expected_global_worker_count = int(resume_topology["global_worker_count"])
        current_num_workers = int(loader_num_workers)
        current_global_worker_count = int(context.global_worker_count)
        if (
            expected_world_size != int(context.world_size)
            or expected_num_workers != current_num_workers
            or expected_global_worker_count != current_global_worker_count
        ):
            raise RuntimeError(
                "Resume requires the same data worker topology as the saved state. "
                f"saved(world_size={expected_world_size}, "
                f"num_workers_per_rank={expected_num_workers}, "
                f"global_worker_count={expected_global_worker_count}), "
                f"current(world_size={context.world_size}, "
                f"num_workers_per_rank={current_num_workers}, "
                f"global_worker_count={current_global_worker_count})."
            )

    def __iter__(self) -> Iterable[dict]:
        worker_info = get_worker_info()
        if worker_info is None:
            worker_id = 0
            loader_num_workers = 0
            effective_num_workers = 1
        else:
            worker_id = worker_info.id
            loader_num_workers = worker_info.num_workers
            effective_num_workers = worker_info.num_workers

        epoch = self._current_epoch()
        context = SourceContext(
            epoch=epoch,
            rank=self.rank,
            world_size=self.world_size,
            worker_id=worker_id,
            num_workers=effective_num_workers,
            seed=self.seed,
        )
        resume_state = self._take_resume_state(epoch)
        if resume_state is not None:
            self._validate_resume_topology(
                resume_state,
                context=context,
                loader_num_workers=loader_num_workers,
            )
        worker_state = (
            None
            if resume_state is None
            else (resume_state.get("workers") or {}).get(str(context.global_worker_id))
        )
        sample_iter = self.source.iter_samples(
            context,
            state=None if worker_state is None else worker_state.get("adapter_state"),
        )
        for sample in sample_iter:
            sample["data_worker_id"] = context.worker_id
            sample["data_global_worker_id"] = context.global_worker_id
            yield sample


class _DataStateTracker:
    def __init__(self, *, num_tokens_per_epoch: int | None):
        self.num_tokens_per_epoch = (
            None if num_tokens_per_epoch is None else int(num_tokens_per_epoch)
        )
        self._pending_state: dict | None = None
        self._reset_for_epoch(epoch=0)

    def _reset_for_epoch(self, *, epoch: int) -> None:
        self.epoch = int(epoch)
        self.samples_emitted = 0
        self.num_text_tokens = 0
        self.num_audio_tokens = 0
        self.num_total_tokens = 0
        self.workers: dict[str, dict] = {}
        self._next_sample_order_by_worker: dict[str, int] = {}

    def load_state_dict(self, state: dict | None) -> None:
        self._pending_state = deepcopy(state) if state else None

    def set_epoch(self, epoch: int) -> None:
        if self._pending_state is not None and int(
            self._pending_state.get("epoch", -1)
        ) == int(epoch):
            state = deepcopy(self._pending_state)
            self._pending_state = None
            self.epoch = int(state.get("epoch", epoch))
            self.samples_emitted = int(state.get("samples_emitted", 0))
            self.num_text_tokens = int(state.get("num_text_tokens", 0))
            self.num_audio_tokens = int(state.get("num_audio_tokens", 0))
            self.num_total_tokens = int(state.get("num_total_tokens", 0))
            self.workers = deepcopy(state.get("workers") or {})
            self._next_sample_order_by_worker = {
                worker_key: int((worker_state or {}).get("sample_order", -1)) + 1
                for worker_key, worker_state in self.workers.items()
            }
            return
        self._reset_for_epoch(epoch=int(epoch))

    def should_stop(self) -> bool:
        return (
            self.num_tokens_per_epoch is not None
            and self.num_total_tokens >= self.num_tokens_per_epoch
        )

    def stage_sample(self, sample: dict) -> dict:
        item = dict(sample)
        worker_key = str(item.pop("data_global_worker_id"))
        item.pop("data_worker_id", None)
        adapter_state = item.pop("_adapter_state", None)
        sample_order = int(self._next_sample_order_by_worker.get(worker_key, 0))
        self._next_sample_order_by_worker[worker_key] = sample_order + 1
        item[_TRACKING_KEY] = {
            "worker_key": worker_key,
            "adapter_state": deepcopy(adapter_state),
            "sample_order": sample_order,
            "num_text_tokens": int(item["num_text_tokens"]),
            "num_audio_tokens": int(item["num_audio_tokens"]),
            "num_total_tokens": int(
                item.get("num_total_tokens", item["input_ids_length"])
            ),
        }
        return item

    def _pop_tracking(self, sample: dict) -> tuple[dict, dict]:
        item = dict(sample)
        tracking = item.pop(_TRACKING_KEY, None)
        if not isinstance(tracking, dict):
            raise RuntimeError("Tracked sample is missing internal resume metadata.")
        return item, tracking

    def _advance_worker(self, tracking: dict) -> None:
        adapter_state = tracking.get("adapter_state")
        if adapter_state is None:
            return
        worker_key = str(tracking["worker_key"])
        sample_order = int(tracking.get("sample_order", -1))
        current_state = self.workers.get(worker_key)
        current_order = int((current_state or {}).get("sample_order", -1))
        if current_order >= sample_order:
            return
        self.workers[worker_key] = {
            "adapter_state": deepcopy(adapter_state),
            "sample_order": sample_order,
        }

    def mark_samples_dropped(self, samples: list[dict]) -> None:
        for sample in samples:
            _, tracking = self._pop_tracking(sample)
            self._advance_worker(tracking)

    def commit_batch(self, samples: list[dict]) -> list[dict]:
        committed: list[dict] = []
        for sample in samples:
            item, tracking = self._pop_tracking(sample)
            self._advance_worker(tracking)
            self.samples_emitted += 1
            self.num_text_tokens += int(tracking["num_text_tokens"])
            self.num_audio_tokens += int(tracking["num_audio_tokens"])
            self.num_total_tokens += int(tracking["num_total_tokens"])
            committed.append(item)
        return committed

    def state_dict(self) -> dict:
        return {
            "epoch": int(self.epoch),
            "samples_emitted": int(self.samples_emitted),
            "num_text_tokens": int(self.num_text_tokens),
            "num_audio_tokens": int(self.num_audio_tokens),
            "num_total_tokens": int(self.num_total_tokens),
            "workers": deepcopy(self.workers),
            "num_tokens_per_epoch": self.num_tokens_per_epoch,
        }


class BatchedDataStream:
    def __init__(
        self,
        *,
        sample_dataset: StreamingSampleDataset,
        data_cfg,
        tokenizer,
        num_tokens_per_epoch: int | None,
        profiler=None,
    ):
        from dots_tts.data.collator import PadCollator

        self.sample_dataset = sample_dataset
        self.profiler = ensure_data_profiler(profiler)
        llm_token_rate = (
            float(data_cfg.train_audio_sample_rate)
            / float(data_cfg.audio_samples_per_llm_token)
        )
        self.batcher = OnlineBatcher(
            max_audio_tokens_in_batch=max(
                1,
                math.ceil(float(data_cfg.max_audio_seconds_in_batch) * llm_token_rate),
            ),
            max_text_tokens_in_batch=data_cfg.max_text_tokens_in_batch,
            max_batch_size=data_cfg.max_samples_per_batch,
            sample_pool_size=data_cfg.bucketing_pool_size,
            profiler=self.profiler,
        )
        self.sample_loader = None
        self.collator = PadCollator(tokenizer)
        self.data_state = _DataStateTracker(
            num_tokens_per_epoch=num_tokens_per_epoch
        )
        self._decision_iterator = None
        self._sample_iterator = None
        self._pending_batch = None
        self._pending_samples = None

    def attach_loader(self, loader: DataLoader) -> None:
        self.sample_loader = loader

    def close(self) -> None:
        self._reset_iteration_state()
        self.sample_loader = None

    def load_state_dict(self, state: dict | None) -> None:
        self.data_state.load_state_dict(state)
        self.sample_dataset.load_state_dict(state)
        self._reset_iteration_state()

    def state_dict(self) -> dict:
        if self.sample_loader is None:
            raise RuntimeError("BatchedDataStream has no attached sample loader.")
        if self._pending_batch is not None or self._pending_samples is not None:
            raise RuntimeError(
                "Cannot serialize BatchedDataStream while a batch is pending commit."
            )
        loader_num_workers = int(getattr(self.sample_loader, "num_workers", 0))
        effective_num_workers = max(1, loader_num_workers)
        state = self.data_state.state_dict()
        state[_RESUME_TOPOLOGY_KEY] = {
            "world_size": int(self.sample_dataset.world_size),
            "loader_num_workers": loader_num_workers,
            "global_worker_count": int(self.sample_dataset.world_size)
            * effective_num_workers,
        }
        return state

    def set_epoch(self, epoch: int) -> None:
        self.sample_dataset.set_epoch(epoch)
        self.data_state.set_epoch(epoch)
        self._reset_iteration_state()

    def _reset_iteration_state(self) -> None:
        close_iterator = getattr(self._decision_iterator, "close", None)
        if callable(close_iterator):
            close_iterator()
        self._decision_iterator = None
        self._sample_iterator = None
        self._pending_batch = None
        self._pending_samples = None

    def _iter_staged_samples(self):
        if self.sample_loader is None:
            raise RuntimeError("BatchedDataStream has no attached sample loader.")
        self._sample_iterator = iter(self.sample_loader)
        profiler = self.profiler
        try:
            while True:
                if self.data_state.should_stop():
                    return
                try:
                    with profiler.measure("main.loader_wait_next_sample"):
                        sample = next(self._sample_iterator)
                except StopIteration:
                    return
                if sample is None:
                    continue
                with profiler.measure("main.stage_sample"):
                    staged = self.data_state.stage_sample(sample)
                yield staged
        finally:
            self._sample_iterator = None

    def _decision_stream(self):
        if self._decision_iterator is None:
            self._decision_iterator = iter(
                self.batcher.build_decisions(self._iter_staged_samples())
            )
        return self._decision_iterator

    def peek_batch(self) -> tuple[dict | None, bool]:
        if self._pending_batch is not None:
            return self._pending_batch, True

        for decision in self._decision_stream():
            if decision.dropped_samples:
                self.data_state.mark_samples_dropped(decision.dropped_samples)
            if not decision.batch_samples:
                continue
            self._pending_samples = decision.batch_samples
            with self.profiler.measure(
                "main.collate_batch",
                count=len(decision.batch_samples),
            ):
                self._pending_batch = self.collator(decision.batch_samples)
            return self._pending_batch, True
        return None, False

    def commit_batch(self) -> dict:
        if self._pending_batch is None or self._pending_samples is None:
            raise RuntimeError("BatchedDataStream has no pending batch to commit.")
        pending_batch = self._pending_batch
        self.data_state.commit_batch(self._pending_samples)
        self._pending_batch = None
        self._pending_samples = None
        return pending_batch

    def discard_batch(self) -> None:
        if self._pending_batch is None or self._pending_samples is None:
            raise RuntimeError("BatchedDataStream has no pending batch to discard.")
        self._pending_batch = None
        self._pending_samples = None

    def __iter__(self):
        while True:
            batch, has_batch = self.peek_batch()
            if not has_batch:
                return
            self.commit_batch()
            yield batch
            if self.data_state.should_stop():
                return
