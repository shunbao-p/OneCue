from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from dots_tts.config.base import StrictConfigBase

DEFAULT_SOURCE_ADAPTER_CLASS_NAME = "JsonlManifestSourceAdapter"


class SourceAdapterConfig(StrictConfigBase):
    class_name: Literal["JsonlManifestSourceAdapter"] = (
        DEFAULT_SOURCE_ADAPTER_CLASS_NAME
    )
    params: dict[str, Any] = Field(default_factory=dict)


class DataSourceConfig(StrictConfigBase):
    name: str
    weight: float = Field(default=1.0, gt=0.0)
    pipeline: Literal["basic", "interleave"] = "basic"
    adapter: SourceAdapterConfig = Field(default_factory=SourceAdapterConfig)


class DataConfig(StrictConfigBase):
    sources: list[DataSourceConfig]
    train_audio_sample_rate: int = Field(ge=1)
    audio_samples_per_llm_token: int = Field(ge=1)
    num_tokens_per_epoch: int | None = Field(
        default=None,
        ge=1,
        description="Global token budget across all ranks for one training epoch.",
    )
    num_workers: int = Field(default=0, ge=0)
    pin_memory: bool = False
    prefetch_factor: int = Field(
        default=2,
        ge=1,
        description="Samples prefetched by each DataLoader worker.",
    )
    max_audio_seconds_in_batch: float = Field(gt=0.0)
    max_text_tokens_in_batch: int = Field(ge=1)
    max_samples_per_batch: int | None = Field(default=None, ge=1)
    bucketing_pool_size: int = Field(default=64, ge=1)

    @model_validator(mode="after")
    def _validate_unique_source_names(self) -> "DataConfig":
        counts: dict[str, int] = {}
        for source in self.sources:
            counts[source.name] = counts.get(source.name, 0) + 1
        duplicated = [name for name, count in counts.items() if count > 1]
        if duplicated:
            raise ValueError(f"Source names must be unique: {duplicated}")
        return self


__all__ = [
    "DEFAULT_SOURCE_ADAPTER_CLASS_NAME",
    "DataConfig",
    "DataSourceConfig",
    "SourceAdapterConfig",
]
