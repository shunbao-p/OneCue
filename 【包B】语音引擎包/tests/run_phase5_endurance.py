from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import threading
import time
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
for import_root in (PACKAGE_ROOT, SRC_ROOT):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from apps.gradio.service import (  # noqa: E402
    GradioAppService,
    SynthesisRequest,
    build_gradio_app_config,
    recommended_num_steps_for_model,
)
from run_phase4_model_acceptance import (  # noqa: E402
    CONTINUOUS_TEXTS,
    GIB,
    ResourceSampler,
    current_rss_bytes,
    inspect_wav,
    mps_memory,
    sha256,
    swap_used_bytes,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_request(
    model: Path,
    prompt_audio: Path,
    prompt_text: str,
    text: str,
    num_steps: int,
    seed: int,
) -> SynthesisRequest:
    return SynthesisRequest(
        model_name_or_path=str(model),
        text=text,
        prompt_audio_path=str(prompt_audio),
        prompt_text=prompt_text,
        execution_mode="generate",
        num_steps=num_steps,
        seed=seed,
        max_pause=0.3,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 native-MPS service endurance")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--prompt-audio", type=Path, required=True)
    parser.add_argument("--prompt-text", required=True)
    parser.add_argument("--prompt-name", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--min-duration-seconds", type=float, default=1800.0)
    parser.add_argument("--jobs", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Phase 5 endurance requires Darwin arm64.")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        raise RuntimeError("Phase 5 refuses PYTORCH_ENABLE_MPS_FALLBACK=1.")
    if args.jobs < 10:
        raise ValueError("Phase 5 requires at least ten jobs.")
    if args.min_duration_seconds < 1800:
        raise ValueError("Phase 5 requires at least 1800 seconds of service endurance.")
    if not args.prompt_text.strip() or "\n" in args.prompt_text or "\r" in args.prompt_text or "|" in args.prompt_text:
        raise ValueError("参考音频转写必须是单条精确文本，不能传入整个 prompt_text 音色库。")

    model = args.model.expanduser().resolve()
    prompt_audio = args.prompt_audio.expanduser().resolve()
    evidence = args.evidence_dir.expanduser().resolve()
    output_dir = evidence / "service-outputs"
    candidate_dir = evidence / "candidates"
    for directory in (evidence, output_dir, candidate_dir):
        directory.mkdir(parents=True, exist_ok=True)
    model_label = model.name.removeprefix("dots-tts-")
    report_path = evidence / f"phase5-{model_label}-endurance-report.json"

    report: dict[str, object] = {
        "schema_version": 1,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": sys.argv,
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "fixture": {
            "model_label": model_label,
            "model": str(model),
            "model_config_sha256": sha256(model / "config.json"),
            "model_weights_sha256": sha256(model / "model.safetensors"),
            "prompt_name": args.prompt_name,
            "prompt_audio": str(prompt_audio),
            "prompt_audio_sha256": sha256(prompt_audio),
            "prompt_text": args.prompt_text,
            "seed": args.seed,
            "requested_jobs": args.jobs,
            "minimum_duration_seconds": args.min_duration_seconds,
        },
        "runs": [],
        "failures": [],
        "result": "FAIL",
    }

    started = time.monotonic()
    swap_before = swap_used_bytes()
    rss_before = current_rss_bytes()
    mps_before = mps_memory()
    try:
        num_steps = recommended_num_steps_for_model(str(model), repo_root=PACKAGE_ROOT)
        report["fixture"]["num_steps"] = num_steps
        config = build_gradio_app_config(
            model_name_or_path=str(model),
            output_dir=output_dir,
            output_retention_count=15,
            execution_mode="generate",
            device="auto",
            precision="auto",
            optimize=False,
            max_generate_length=500,
            default_prompt_name=args.prompt_name,
        )
        service = GradioAppService(config)

        warmup = service.generate(
            build_request(
                model,
                prompt_audio,
                args.prompt_text,
                "这是最终耐久测试的预热语音。",
                num_steps,
                args.seed,
            )
        )
        warmup_wav = inspect_wav(Path(warmup.audio_path))
        require(warmup_wav["ok"], "预热 WAV 未通过媒体检查")
        report["warmup"] = {
            "metrics": warmup.metrics,
            "wav": warmup_wav,
            "rss_after_bytes": current_rss_bytes(),
            "swap_after_bytes": swap_used_bytes(),
            "mps_after": mps_memory(),
        }

        materialization = service.generate(
            build_request(
                model,
                prompt_audio,
                args.prompt_text,
                max(CONTINUOUS_TEXTS, key=len),
                num_steps,
                args.seed,
            )
        )
        materialization_wav = inspect_wav(Path(materialization.audio_path))
        require(materialization_wav["ok"], "最大工作集预热 WAV 未通过媒体检查")
        report["materialization_warmup"] = {
            "text_length": max(map(len, CONTINUOUS_TEXTS)),
            "metrics": materialization.metrics,
            "wav": materialization_wav,
            "rss_after_bytes": current_rss_bytes(),
            "swap_after_bytes": swap_used_bytes(),
            "mps_after": mps_memory(),
        }

        endurance_started = time.monotonic()
        rows: list[dict[str, object]] = []
        rows_lock = threading.Lock()

        def execute(index: int, text: str, queued_pair: bool = False) -> None:
            submitted = time.monotonic()
            result = service.generate(
                build_request(
                    model,
                    prompt_audio,
                    args.prompt_text,
                    text,
                    num_steps,
                    args.seed,
                )
            )
            finished = time.monotonic()
            wav = inspect_wav(Path(result.audio_path))
            row: dict[str, object] = {
                "index": index,
                "text": text,
                "queued_pair": queued_pair,
                "submitted_at_seconds": round(submitted - endurance_started, 3),
                "finished_at_seconds": round(finished - endurance_started, 3),
                "wall_seconds": round(finished - submitted, 3),
                "metrics": result.metrics,
                "wav": wav,
                "rss_after_bytes": current_rss_bytes(),
                "swap_after_bytes": swap_used_bytes(),
                "mps_after": mps_memory(),
                "output_file_count": len(list(output_dir.glob("*.wav"))),
            }
            if index in (1, args.jobs):
                candidate = candidate_dir / f"phase5-job-{index:02d}.wav"
                shutil.copy2(result.audio_path, candidate)
                row["candidate"] = inspect_wav(candidate)
            with rows_lock:
                rows.append(row)

        with ResourceSampler(interval=30.0) as sampler:
            first_pair = [
                threading.Thread(
                    target=execute,
                    args=(index, CONTINUOUS_TEXTS[index - 1], True),
                )
                for index in (1, 2)
            ]
            for thread in first_pair:
                thread.start()
            for thread in first_pair:
                thread.join()

            remaining_jobs = args.jobs - 2
            for offset, index in enumerate(range(3, args.jobs + 1), start=1):
                target_seconds = args.min_duration_seconds * offset / max(1, remaining_jobs)
                wait_seconds = target_seconds - (time.monotonic() - endurance_started)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                execute(index, CONTINUOUS_TEXTS[(index - 1) % len(CONTINUOUS_TEXTS)])

        rows.sort(key=lambda row: int(row["index"]))
        report["runs"] = rows
        report["resource_samples"] = sampler.samples
        endurance_seconds = time.monotonic() - endurance_started
        valid_samples = [sample for sample in sampler.samples if "rss_bytes" in sample]
        peak_rss = max(
            [rss_before, current_rss_bytes(), *(int(sample["rss_bytes"]) for sample in valid_samples)]
        )
        peak_swap = max(
            [swap_before, swap_used_bytes(), *(int(sample["swap_used_bytes"]) for sample in valid_samples)]
        )
        peak_mps_driver = max(
            [
                int(report["warmup"]["mps_after"]["driver_allocated_memory"] or 0),
                int(report["materialization_warmup"]["mps_after"]["driver_allocated_memory"] or 0),
                *(int(row["mps_after"]["driver_allocated_memory"] or 0) for row in rows),
            ]
        )
        first_rss = int(report["materialization_warmup"]["rss_after_bytes"])
        final_rss = int(rows[-1]["rss_after_bytes"])
        rss_growth = max(0, final_rss - first_rss)
        rss_growth_ratio = rss_growth / first_rss if first_rss else float("inf")
        swap_delta = max(0, peak_swap - swap_before)
        policies = [row["metrics"]["device_policy"] for row in rows]
        policy_ok = all(
            policy.get("actual_device") == "mps"
            and policy.get("actual_precision") == "float32"
            and policy.get("native_mps") is True
            and policy.get("fallback_used") is False
            for policy in policies
        )
        queued_rows = [row for row in rows if row["queued_pair"]]
        checks = {
            "duration_at_least_30_minutes": endurance_seconds >= 1800.0,
            "at_least_10_jobs": len(rows) >= 10,
            "all_wav_media": all(bool(row["wav"]["ok"]) for row in rows),
            "native_mps_float32_no_fallback": policy_ok,
            "swap_delta_at_most_2_gib": swap_delta <= 2 * GIB,
            "rss_growth_within_phase4_gate": rss_growth <= GIB or rss_growth_ratio <= 0.10,
            "queue_pair_completed": len(queued_rows) == 2,
            "output_retention_bounded": len(list(output_dir.glob("*.wav"))) <= 15,
            "resource_sampler_clean": all("error" not in sample for sample in sampler.samples),
        }
        report["summary"] = {
            "endurance_seconds": endurance_seconds,
            "completed_jobs": len(rows),
            "failed_jobs": 0,
            "failure_rate": 0.0,
            "peak_rss_bytes": peak_rss,
            "peak_mps_driver_allocated_bytes": peak_mps_driver,
            "swap_before_bytes": swap_before,
            "peak_swap_bytes": peak_swap,
            "swap_delta_bytes": swap_delta,
            "post_materialization_rss_baseline_bytes": first_rss,
            "post_warmup_rss_final_bytes": final_rss,
            "post_warmup_rss_growth_bytes": rss_growth,
            "post_warmup_rss_growth_ratio": rss_growth_ratio,
            "output_file_count": len(list(output_dir.glob("*.wav"))),
            "queue_pair_wall_seconds": [row["wall_seconds"] for row in queued_rows],
            "checks": checks,
            "result": "PASS" if all(checks.values()) else "FAIL",
        }
        report["result"] = report["summary"]["result"]
        if report["result"] != "PASS":
            report["failures"] = [name for name, ok in checks.items() if not ok]
    except Exception as exc:
        report["failures"].append(f"{type(exc).__name__}: {exc}")
        report["exception"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report["total_wall_seconds"] = time.monotonic() - started
        report["resources_before"] = {
            "rss_bytes": rss_before,
            "swap_used_bytes": swap_before,
            "mps": mps_before,
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
