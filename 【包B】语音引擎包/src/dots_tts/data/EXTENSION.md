# Data Source Extension Guide

This document answers exactly one question: how to plug a new training data source into the current `dots_tts` data pipeline.

If you only need to swap in a different JSONL manifest, no code changes are required. To support a new raw data format, you usually only need to add:

- one **source adapter**
- optionally one **sample pipeline**

## Data flow

1. An **adapter** reads from the raw data source and yields raw samples.
2. A **pipeline** turns each raw sample into a training sample (1:1).
3. A **multi-source wrapper** handles mixing across sources and resume state.
4. `StreamingSampleDataset` / `DataLoader` pulls samples.
5. `OnlineBatcher` assembles batches and `PadCollator` performs padding.

## What an adapter must implement

Subclass `BaseSourceAdapter`:

```python
class BaseSourceAdapter(ABC):
    @abstractmethod
    def initial_state(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def iter_samples(
        self,
        context: SourceContext,
        *,
        state: dict[str, Any] | None = None,
    ) -> Iterable[dict[str, Any]]:
        ...

    @abstractmethod
    def is_cycle_start_state(self, state: dict[str, Any] | None) -> bool:
        ...

    # Optional — only required when used under WeightedMultiSourceAdapter,
    # which cycles each finite child source independently. The default
    # implementation raises if your adapter never gets re-cycled.
    def advance_cycle(self, state: dict[str, Any] | None) -> dict[str, Any]:
        ...
```

Each emitted sample **must** carry these fields:

- `fid`
- `text`
- `audio`
- `_adapter_state`

Key constraints:

- `_adapter_state` must describe **where to resume next**, not the position of the current item.
- The state must be plain Python data — serializable and recoverable after a restart.
- If your source needs to be split across workers, use `context.global_worker_id` and `context.global_worker_count` (or subclass `ShardableSourceAdapter` and use its `is_assigned_index` / `shard_items` helpers).
- If the source will participate in weighted cyclic sampling, you must implement `advance_cycle` and make `is_cycle_start_state` correct — otherwise `WeightedMultiSourceAdapter` cannot detect an empty cycle and will raise.

After implementing the adapter, register the class in `dots_tts/data/builders.py::_SOURCE_ADAPTER_CLASSES` so that the YAML config can resolve it by `class_name`.

## What a pipeline must implement

Pipelines must subclass `BaseSamplePipeline` and perform a strict **1:1** sample transform.

Minimum implementation:

```python
class MyPipeline(BaseSamplePipeline):
    def process_sample(self, sample: dict) -> dict:
        sample["text"] = str(sample["text"]).strip()
        return sample
```

Do **not**:

- filter samples out
- expand a single sample into multiple samples
- assemble batches inside the pipeline

`BaseSamplePipeline.__call__` automatically merges the original raw sample (including `_adapter_state` and any extra fields the adapter attached) with whatever your `process_sample` returns. You do not need to copy these fields manually — just return the fields you produced or want to overwrite.

To wire a new pipeline into config, also extend `dots_tts/data/builders.py::_build_source_pipeline` so it can be selected by name in YAML.

## How multi-source wrappers affect you

There are two wrappers in the current codebase:

- `SequentialMultiSourceAdapter` — used for validation. Reads sources in the configured order, exhaustively, once.
- `WeightedMultiSourceAdapter` — used for training. Draws sources by weight, cycles each child source independently when exhausted.

Both wrappers **replace** the `_adapter_state` produced by your child adapter with their own resume state before yielding to the dataset. Even so, the child adapter must still emit its own `_adapter_state` — the wrapper reads it to track where each sub-source has read to.

## Config

Each source is configured independently:

```yaml
train_data:
  sources:
    - name: train_a
      weight: 1.0
      pipeline: basic
      adapter:
        class_name: JsonlManifestSourceAdapter
        params:
          manifest_path: train_a.jsonl
    - name: train_b
      weight: 2.0
      pipeline: interleave
      adapter:
        class_name: JsonlManifestSourceAdapter
        params:
          manifest_path: train_b.jsonl
```

Constraints:

- `sources[].name` must be unique within the same `train_data` / `val_data` block (it is used as a dict key for resume state).
- `sources[].pipeline` is a per-source setting, not shared across the dataset.
- All sources must ultimately produce the same training-sample structure, since they feed into the same batcher and collator.
- `class_name` must match a key registered in `_SOURCE_ADAPTER_CLASSES`; `params` is forwarded verbatim as kwargs to the adapter constructor.
