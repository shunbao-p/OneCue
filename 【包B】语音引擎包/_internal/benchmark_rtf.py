# -*- coding: utf-8 -*-
"""Reproducible dots.tts RTF benchmark with explicit runtime policy."""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
for import_root in (PROJECT_DIR, PROJECT_DIR / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

os.environ.setdefault("HF_HOME", str(PROJECT_DIR / "hf_download"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(PROJECT_DIR / "tf_download"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

BENCHMARK_FIXTURES: tuple[tuple[str, str], ...] = (
    ("短句", "今天天气真不错，我们出去走走吧。"),
    (
        "中段",
        "人工智能正在深刻改变我们的生活方式，从语音助手到自动驾驶，"
        "技术的进步让许多曾经的梦想变成了现实。",
    ),
    (
        "长段",
        "在过去的十年里，深度学习推动了语音合成技术的飞速发展。"
        "如今的端到端模型不仅能够生成自然流畅的语音，还能精准还原说话人的音色与情感。"
        "这背后离不开大规模数据、强大算力以及一代又一代研究者的不懈努力。"
        "未来，随着模型效率的进一步提升，高质量语音合成将走进更多日常场景。",
    ),
)


def discover_models(only: list[str] | None) -> list[Path]:
    model_root = PROJECT_DIR / "pretrained_models"
    if not model_root.is_dir():
        return []
    return [
        child
        for child in sorted(model_root.iterdir())
        if child.is_dir()
        and (child / "config.json").is_file()
        and (not only or child.name in only)
    ]


def run_model(model_path: Path, args: argparse.Namespace) -> dict[str, object]:
    import torch

    from apps.gradio.service import recommended_num_steps_for_model
    from dots_tts.runtime import DotsTtsRuntime
    from dots_tts.runtime_device import seed_everything

    seed_everything(args.seed, torch_module=torch)
    num_steps = recommended_num_steps_for_model(str(model_path), repo_root=PROJECT_DIR)
    runtime = DotsTtsRuntime.from_pretrained(
        str(model_path),
        device=args.device,
        precision=args.precision,
        optimize=args.optimize,
        max_generate_length=args.max_generate_length,
    )
    rows: list[dict[str, object]] = []
    for label, text in BENCHMARK_FIXTURES:
        kwargs = {
            "text": text,
            "prompt_audio_path": args.ref_audio,
            "prompt_text": args.ref_text if args.ref_audio else None,
            "num_steps": num_steps,
            "ode_method": "euler",
            "guidance_scale": 1.2,
            "speaker_scale": 1.5,
        }
        def generate_fixture():
            if args.chunk_chars and len(text) > args.chunk_chars:
                return runtime.generate_chunked(
                    **kwargs,
                    max_chars_per_chunk=args.chunk_chars,
                )
            return runtime.generate(**kwargs)

        generate_fixture()
        rtfs: list[float] = []
        audio_seconds = 0.0
        for _ in range(args.repeats):
            result = generate_fixture()
            rtfs.append(float(result["rtf"]))
            audio_seconds = result["audio"].shape[-1] / runtime.sample_rate
        rows.append(
            {
                "label": label,
                "text": text,
                "characters": len(text),
                "audio_seconds": audio_seconds,
                "rtf_samples": rtfs,
                "median_rtf": statistics.median(rtfs),
            }
        )
    return {
        "model": model_path.name,
        "model_path": str(model_path),
        "num_steps": num_steps,
        "device_policy": runtime.device_policy.as_dict(),
        "seed": args.seed,
        "repeats": args.repeats,
        "optimize": args.optimize,
        "chunk_chars": args.chunk_chars,
        "rows": rows,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="dots.tts reproducible RTF benchmark")
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--ref-audio", default=None)
    parser.add_argument("--ref-text", default=None)
    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"), default="auto")
    parser.add_argument(
        "--precision",
        choices=("auto", "bfloat16", "float16", "float32"),
        default="auto",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-generate-length", type=int, default=500)
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=0,
        help="Use the existing chunked path above this character count; 0 disables it.",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Opt in to torch.compile on a supported CUDA policy; disabled by default.",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.repeats < 1:
        raise ValueError("--repeats must be positive")
    if args.chunk_chars < 0:
        raise ValueError("--chunk-chars must be non-negative")
    if bool(args.ref_audio) != bool(args.ref_text):
        raise ValueError("--ref-audio and --ref-text must be provided together")
    models = discover_models(args.models)
    if not models:
        raise FileNotFoundError("No requested model was found under pretrained_models/.")
    import torch

    from dots_tts.runtime_device import release_torch_accelerator_cache

    results: list[dict[str, object]] = []
    for model_path in models:
        try:
            results.append(run_model(model_path, args))
        finally:
            gc.collect()
            release_torch_accelerator_cache(torch)
    report = {
        "schema_version": 1,
        "fixture_version": "phase1-fixed-v1",
        "results": results,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
