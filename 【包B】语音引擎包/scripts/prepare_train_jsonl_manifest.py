#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ID = "alibabasglab/LJSpeech-1.1-48kHz"
ARCHIVE_NAME = "LJSpeech-1.1-48kHz.tar.bz2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=REPO_ROOT / "downloaded_data" / "hf_cache",
    )
    parser.add_argument(
        "--extract-dir",
        type=Path,
        default=REPO_ROOT / "downloaded_data" / "hf_cache",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "downloaded_data",
    )
    parser.add_argument("--valid-size", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.valid_size < 0:
        raise ValueError("valid_size must be >= 0")

    cache_dir = args.cache_dir.resolve()
    extract_dir = args.extract_dir.resolve()
    output_dir = args.output_dir.resolve()
    train_manifest_path = output_dir / "ljspeech_48khz_manifest_train.jsonl"
    valid_manifest_path = output_dir / "ljspeech_48khz_manifest_valid.jsonl"

    cache_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_path = Path(
        hf_hub_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            filename=ARCHIVE_NAME,
            local_dir=str(cache_dir),
        )
    )

    dataset_root = extract_dir / "LJSpeech-1.1-48kHz"
    if not dataset_root.exists():
        print("extracting archive...")
        subprocess.run(
            [
                "tar",
                "-xjf",
                str(archive_path),
                "-C",
                str(extract_dir),
                "--checkpoint=2000",
                "--checkpoint-action=echo=extracting...",
            ],
            check=True,
        )

    metadata_path = dataset_root / "metadata.csv"
    audio_dir = dataset_root / "wavs" / "MossFormer2_SR_48K"

    if not metadata_path.is_file():
        raise FileNotFoundError(f"metadata.csv not found: {metadata_path}")
    if not audio_dir.is_dir():
        raise FileNotFoundError(f"audio dir not found: {audio_dir}")

    train_count = 0
    valid_count = 0
    with (
        metadata_path.open("r", encoding="utf-8", newline="") as fin,
        train_manifest_path.open("w", encoding="utf-8") as train_fout,
        valid_manifest_path.open("w", encoding="utf-8") as valid_fout,
    ):
        reader = csv.reader(fin, delimiter="|")
        for row in reader:
            if not row:
                continue

            fid = row[0].strip()
            text = (
                row[2].strip() if len(row) >= 3 and row[2].strip() else row[1].strip()
            )
            audio_path = (audio_dir / f"{fid}.wav").resolve()

            if not audio_path.is_file():
                raise FileNotFoundError(f"audio not found: {audio_path}")

            record = json.dumps(
                {
                    "fid": fid,
                    "audio": str(audio_path),
                    "text": text,
                },
                ensure_ascii=False,
            )
            if valid_count < args.valid_size:
                valid_fout.write(record)
                valid_fout.write("\n")
                valid_count += 1
            else:
                train_fout.write(record)
                train_fout.write("\n")
                train_count += 1

    print(f"archive: {archive_path}")
    print(f"dataset_root: {dataset_root}")
    print(f"train_manifest: {train_manifest_path}")
    print(f"valid_manifest: {valid_manifest_path}")
    print(f"train_records: {train_count}")
    print(f"valid_records: {valid_count}")


if __name__ == "__main__":
    main()
