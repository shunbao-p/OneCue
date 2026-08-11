from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
for import_root in (PACKAGE_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import soundfile as sf
import torch

from dots_tts.runtime import DotsTtsRuntime
from dots_tts.runtime_device import seed_everything


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mps_memory() -> dict[str, int | None]:
    backend = getattr(torch, "mps", None)
    result: dict[str, int | None] = {}
    for name in ("current_allocated_memory", "driver_allocated_memory", "recommended_max_memory"):
        function = getattr(backend, name, None)
        result[name] = int(function()) if callable(function) else None
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 1 native MPS smoke")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--prompt-audio", type=Path, required=True)
    parser.add_argument("--prompt-text", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--text", default="这是苹果芯片原生设备策略的稳定性验证。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs != 3:
        raise ValueError("Phase 1 acceptance requires exactly three runs.")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        raise RuntimeError("Native MPS smoke refuses PYTORCH_ENABLE_MPS_FALLBACK=1.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    runtime = DotsTtsRuntime.from_pretrained(
        str(args.model),
        device="auto",
        precision="auto",
        optimize=False,
        max_generate_length=500,
    )
    policy = runtime.device_policy.as_dict()
    if policy["actual_device"] != "mps" or policy["actual_precision"] != "float32":
        raise RuntimeError(f"Unexpected target policy: {policy}")
    if policy["fallback_used"] or not policy["native_mps"]:
        raise RuntimeError(f"MPS fallback is not accepted: {policy}")

    rows: list[dict[str, object]] = []
    for run_index in range(1, args.runs + 1):
        seed_everything(args.seed, torch_module=torch)
        result = runtime.generate(
            text=args.text,
            prompt_audio_path=str(args.prompt_audio),
            prompt_text=args.prompt_text,
            template_name="tts",
            language="zh",
            ode_method="euler",
            num_steps=4,
            guidance_scale=1.2,
            speaker_scale=1.5,
            normalize_text=False,
        )
        output_path = args.output_dir / f"phase1-mps-run-{run_index}.wav"
        waveform = result["audio"].detach().float().cpu().squeeze().numpy()
        if waveform.ndim != 1 or not math.isfinite(float(waveform.max())):
            raise RuntimeError(f"Invalid waveform for run {run_index}.")
        sf.write(output_path, waveform, result["sample_rate"])
        info = sf.info(output_path)
        clipping_samples = int((abs(waveform) >= 1.0).sum())
        if info.samplerate != 48000 or info.channels != 1 or info.frames <= 0:
            raise RuntimeError(f"Unexpected WAV contract for run {run_index}: {info}")
        if clipping_samples:
            raise RuntimeError(f"Clipping detected for run {run_index}: {clipping_samples}")
        rows.append(
            {
                "run": run_index,
                "output": str(output_path),
                "sha256": sha256(output_path),
                "sample_rate": info.samplerate,
                "channels": info.channels,
                "frames": info.frames,
                "audio_seconds": info.duration,
                "elapsed_seconds": float(result["time_used"]),
                "rtf": float(result["rtf"]),
                "clipping_samples": clipping_samples,
                "mps_memory": mps_memory(),
                "ru_maxrss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            }
        )

    durations = [float(row["audio_seconds"]) for row in rows]
    relative_duration_spread = (max(durations) - min(durations)) / max(durations)
    report = {
        "schema_version": 1,
        "ok": relative_duration_spread <= 0.02,
        "policy": policy,
        "fixture": {
            "text": args.text,
            "prompt_audio": str(args.prompt_audio),
            "prompt_audio_sha256": sha256(args.prompt_audio),
            "prompt_text": args.prompt_text,
            "seed": args.seed,
            "num_steps": 4,
        },
        "relative_duration_spread": relative_duration_spread,
        "runs": rows,
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
