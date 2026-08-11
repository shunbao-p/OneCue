from __future__ import annotations

from typing import Any

import torch
from torch.nn.utils.rnn import pad_sequence


class PadCollator:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.pad_token_id = tokenizer.pad_token_id
        if self.pad_token_id is None:
            self.pad_token_id = tokenizer.eos_token_id or 0

    def __call__(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        if not samples:
            raise ValueError("PadCollator received an empty sample list.")

        order = sorted(
            range(len(samples)),
            key=lambda idx: samples[idx]["sample_length"],
            reverse=True,
        )
        ordered = [samples[idx] for idx in order]

        input_ids = [
            torch.tensor(sample["input_ids"], dtype=torch.long) for sample in ordered
        ]
        labels = [
            torch.tensor(sample["labels"], dtype=torch.long) for sample in ordered
        ]
        loss_masks = [
            torch.tensor(sample["loss_mask"], dtype=torch.float32) for sample in ordered
        ]
        waveforms = [sample["sample"].squeeze(0) for sample in ordered]
        fbank = [sample["fbank"] for sample in ordered]

        return {
            "fids": [sample["fid"] for sample in ordered],
            "source_names": [sample.get("source_name") for sample in ordered],
            "input_ids": pad_sequence(
                input_ids,
                batch_first=True,
                padding_value=self.pad_token_id,
            ),
            "input_ids_lengths": torch.tensor(
                [len(sample["input_ids"]) for sample in ordered],
                dtype=torch.long,
            ),
            "labels": pad_sequence(
                labels,
                batch_first=True,
                padding_value=self.pad_token_id,
            ),
            "loss_mask": pad_sequence(
                loss_masks,
                batch_first=True,
                padding_value=0.0,
            ),
            "sample": pad_sequence(
                waveforms,
                batch_first=True,
                padding_value=0.0,
            ).unsqueeze(1),
            "sample_lengths": torch.tensor(
                [sample["sample_length"] for sample in ordered],
                dtype=torch.long,
            ),
            "num_text_tokens": torch.tensor(
                [sample["num_text_tokens"] for sample in ordered],
                dtype=torch.long,
            ),
            "num_audio_tokens": torch.tensor(
                [sample["num_audio_tokens"] for sample in ordered],
                dtype=torch.long,
            ),
            "fbank": pad_sequence(
                fbank,
                batch_first=True,
                padding_value=0.0,
            ),
            "fbank_lengths": torch.tensor(
                [sample["fbank_length"] for sample in ordered],
                dtype=torch.long,
            ),
        }
