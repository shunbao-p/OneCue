from __future__ import annotations

import json
import random
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from dots_tts.data.source_adapters.base_adapter import (
    BaseSourceAdapter,
    ShardableSourceAdapter,
    SourceContext,
)


class JsonlManifestSourceAdapter(ShardableSourceAdapter, BaseSourceAdapter):
    """Finite adapter for line-delimited JSON manifests."""

    def __init__(
        self,
        *,
        manifest_path: str,
        fid_key: str = "fid",
        text_key: str = "text",
        audio_key: str = "audio",
        shuffle: bool = False,
        encoding: str = "utf-8",
    ):
        self.manifest_path = Path(manifest_path)
        self.fid_key = fid_key
        self.text_key = text_key
        self.audio_key = audio_key
        self.shuffle = shuffle
        self.encoding = encoding
        self._records: list[dict[str, Any]] | None = None

    def initial_state(self) -> dict[str, Any]:
        return {"cycle": 0, "cursor": 0}

    def is_cycle_start_state(self, state: dict[str, Any] | None) -> bool:
        normalized = self.normalize_state(state)
        return int(normalized["cursor"]) == 0

    def advance_cycle(self, state: dict[str, Any] | None) -> dict[str, Any]:
        normalized = self.normalize_state(state)
        return {"cycle": int(normalized["cycle"]) + 1, "cursor": 0}

    def _iter_records(self) -> Iterator[dict[str, Any]]:
        if not self.manifest_path.is_file():
            raise FileNotFoundError(f"Manifest file not found: {self.manifest_path!s}")
        with self.manifest_path.open("r", encoding=self.encoding) as fin:
            for line_no, raw_line in enumerate(fin, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON at {self.manifest_path}:{line_no}"
                    ) from exc

    def _base_records(self) -> list[dict[str, Any]]:
        if self._records is None:
            self._records = list(self._iter_records())
        return self._records

    def _build_sample(self, record: dict[str, Any]) -> dict[str, Any]:
        missing = [
            key
            for key in (self.fid_key, self.text_key, self.audio_key)
            if key not in record
        ]
        if missing:
            raise KeyError(
                f"Manifest record is missing required keys {missing}: {record}"
            )

        sample = {
            "fid": str(record[self.fid_key]),
            "text": record[self.text_key],
            "audio": record[self.audio_key],
        }
        for key, value in record.items():
            if key in {self.fid_key, self.text_key, self.audio_key}:
                continue
            sample[key] = value
        return sample

    def _indices_for_cycle(
        self,
        context: SourceContext,
        *,
        cycle: int,
    ) -> list[int]:
        indices = list(range(len(self._base_records())))
        if self.shuffle:
            random.Random(context.seed + context.epoch + 1009 * int(cycle)).shuffle(
                indices
            )
            indices = [
                record_index
                for shuffled_index, record_index in enumerate(indices)
                if self.is_assigned_index(shuffled_index, context)
            ]
        else:
            indices = [
                record_index
                for record_index in indices
                if self.is_assigned_index(record_index, context)
            ]
        return indices

    def iter_samples(
        self,
        context: SourceContext,
        *,
        state: dict[str, Any] | None = None,
    ) -> Iterable[dict[str, Any]]:
        live_state = self.normalize_state(state)
        cycle = int(live_state["cycle"])
        cursor = int(live_state["cursor"])
        records = self._base_records()
        indices = self._indices_for_cycle(context, cycle=cycle)

        for position in range(cursor, len(indices)):
            sample = self._build_sample(records[indices[position]])
            sample["_adapter_state"] = {
                "cycle": cycle,
                "cursor": position + 1,
            }
            yield sample
