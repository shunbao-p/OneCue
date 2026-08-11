from __future__ import annotations

from torch.utils.data import DataLoader

from dots_tts.config.data import DataConfig
from dots_tts.data.pipelines.base import BaseSamplePipeline
from dots_tts.data.pipelines.tts_pipeline import BasicTtsPipeline, InterleaveTtsPipeline
from dots_tts.data.source_adapters.jsonl_manifest_adapter import (
    JsonlManifestSourceAdapter,
)
from dots_tts.data.source_adapters.multi_source_adapter import (
    SequentialMultiSourceAdapter,
    SourceSpec,
    WeightedMultiSourceAdapter,
)
from dots_tts.data.streaming import (
    BatchedDataStream,
    StreamingSampleDataset,
    identity_collate,
)

_SOURCE_ADAPTER_CLASSES = {
    "JsonlManifestSourceAdapter": JsonlManifestSourceAdapter,
}


def _build_source_pipeline(
    tokenizer, data_cfg, pipeline_name: str, *, profiler=None
) -> BaseSamplePipeline:
    if pipeline_name == "basic":
        return BasicTtsPipeline(tokenizer, data_cfg, profiler=profiler)
    if pipeline_name == "interleave":
        return InterleaveTtsPipeline(tokenizer, data_cfg, profiler=profiler)
    raise ValueError(f"Unsupported data pipeline: {pipeline_name!r}")


def _build_source_specs(data_cfg, tokenizer, *, profiler=None) -> list[SourceSpec]:
    specs = []
    for source_cfg in data_cfg.sources:
        adapter_cls = _SOURCE_ADAPTER_CLASSES[source_cfg.adapter.class_name]
        adapter = adapter_cls(**source_cfg.adapter.params)
        specs.append(
            SourceSpec(
                name=source_cfg.name,
                weight=float(source_cfg.weight),
                adapter=adapter,
                pipeline=_build_source_pipeline(
                    tokenizer, data_cfg, source_cfg.pipeline, profiler=profiler
                ),
            )
        )
    return specs


def _resolve_rank_info(accelerator=None) -> tuple[int, int]:
    rank = (
        int(getattr(accelerator, "process_index", 0)) if accelerator is not None else 0
    )
    world_size = (
        int(getattr(accelerator, "num_processes", 1)) if accelerator is not None else 1
    )
    return rank, world_size


def _local_num_tokens_per_epoch(
    global_num_tokens_per_epoch: int, *, rank: int, world_size: int
) -> int:
    if world_size <= 0:
        raise ValueError(f"world_size must be positive, but got {world_size}.")
    if rank < 0 or rank >= world_size:
        raise ValueError(
            f"rank must be in [0, {world_size}), but got rank={rank}."
        )

    base, remainder = divmod(int(global_num_tokens_per_epoch), int(world_size))
    return base + int(rank < remainder)


def _build_dataset(
    data_cfg: DataConfig,
    *,
    tokenizer,
    seed: int,
    accelerator=None,
    sequential: bool,
    profiler=None,
):
    rank, world_size = _resolve_rank_info(accelerator)
    source_cls = SequentialMultiSourceAdapter if sequential else WeightedMultiSourceAdapter
    source = source_cls(
        sources=_build_source_specs(data_cfg, tokenizer, profiler=profiler)
    )
    return StreamingSampleDataset(
        source=source,
        rank=rank,
        world_size=world_size,
        seed=int(seed),
    )


def build_training_dataset(
    data_cfg: DataConfig,
    tokenizer,
    *,
    seed: int,
    accelerator=None,
    profiler=None,
):
    if data_cfg.num_tokens_per_epoch is None:
        raise ValueError("Training data requires num_tokens_per_epoch.")
    return _build_dataset(
        data_cfg,
        tokenizer=tokenizer,
        seed=seed,
        accelerator=accelerator,
        sequential=False,
        profiler=profiler,
    )


def build_validation_dataset(
    data_cfg: DataConfig,
    tokenizer,
    *,
    seed: int,
    accelerator=None,
    profiler=None,
):
    return _build_dataset(
        data_cfg,
        tokenizer=tokenizer,
        seed=seed,
        accelerator=accelerator,
        sequential=True,
        profiler=profiler,
    )


def _build_sample_loader(dataset, data_cfg: DataConfig) -> DataLoader:
    loader_kwargs = {
        "dataset": dataset,
        "batch_size": None,
        "collate_fn": identity_collate,
        "num_workers": data_cfg.num_workers,
        "pin_memory": data_cfg.pin_memory,
        "persistent_workers": data_cfg.num_workers > 0,
    }
    if data_cfg.num_workers > 0:
        loader_kwargs["prefetch_factor"] = int(data_cfg.prefetch_factor)
    sample_loader = DataLoader(**loader_kwargs)
    return sample_loader


def build_training_dataloader(
    dataset, data_cfg: DataConfig, tokenizer, *, profiler=None
):
    local_num_tokens_per_epoch = _local_num_tokens_per_epoch(
        int(data_cfg.num_tokens_per_epoch),
        rank=int(dataset.rank),
        world_size=int(dataset.world_size),
    )
    sample_loader = _build_sample_loader(dataset, data_cfg)
    batched_stream = BatchedDataStream(
        sample_dataset=dataset,
        data_cfg=data_cfg,
        tokenizer=tokenizer,
        num_tokens_per_epoch=local_num_tokens_per_epoch,
        profiler=profiler,
    )
    batched_stream.attach_loader(sample_loader)
    return batched_stream


def build_validation_dataloader(
    dataset, data_cfg: DataConfig, tokenizer, *, profiler=None
):
    sample_loader = _build_sample_loader(dataset, data_cfg)
    batched_stream = BatchedDataStream(
        sample_dataset=dataset,
        data_cfg=data_cfg,
        tokenizer=tokenizer,
        num_tokens_per_epoch=None,
        profiler=profiler,
    )
    batched_stream.attach_loader(sample_loader)
    return batched_stream


__all__ = [
    "build_training_dataloader",
    "build_training_dataset",
    "build_validation_dataloader",
    "build_validation_dataset",
]
