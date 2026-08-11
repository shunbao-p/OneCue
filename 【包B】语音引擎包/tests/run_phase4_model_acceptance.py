from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import shutil
import subprocess
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

import numpy as np
import soundfile as sf
import torch

from apps.gradio.service import (
    GradioAppService,
    SynthesisRequest,
    build_gradio_app_config,
    recommended_num_steps_for_model,
)


GIB = 1024**3
CONTINUOUS_TEXTS = (
    "这是连续稳定性验证的第一条短句。",
    "2026年8月10日，编号A-17，价格是123.45元。",
    "Hello Apple Silicon，MPS local speech test number three。",
    "逗号，句号。问号？感叹号！冒号：分号；停顿应当清楚。",
    "中文、English and digits 456 are mixed in one local request。",
    "这是第六次连续合成，服务不应切换到中央处理器。",
    "第七次任务检查输出仍为四万八千赫兹单声道。",
    "第八次任务检查固定随机种子和内置音色。",
    "第九次任务检查内存与交换空间增量。",
    (
        "这是超过二百个字符的长文本稳定性检查。系统需要在苹果芯片上使用金属加速完成本地语音合成，"
        "不能静默回退到中央处理器，也不能因为文本较长而丢失句子。数字一二三、英文MPS、标点停顿和"
        "连续段落都应当正常处理。为了覆盖自动分段路径，这段文字会继续延伸，并明确说明：每一个输出"
        "都必须可以解码、包含有限数值、不是静音，而且削波比例低于验收阈值。最后一句用于确认分段拼接"
        "之后仍然能够形成完整、连续、可供试听的语音文件。"
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_version(argv: list[str]) -> dict[str, object]:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    output = (result.stdout or result.stderr).splitlines()
    return {
        "command": argv,
        "exit_code": result.returncode,
        "first_line": output[0] if output else "",
    }


def current_rss_bytes() -> int:
    result = subprocess.run(
        ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip()) * 1024


def swap_used_bytes() -> int:
    result = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "vm.swapusage"],
        check=True,
        capture_output=True,
        text=True,
    )
    for token_index, token in enumerate(result.stdout.split()):
        if token == "used" and token_index + 2 < len(result.stdout.split()):
            value = result.stdout.split()[token_index + 2]
            units = {"M": 1024**2, "G": 1024**3}
            return int(float(value[:-1]) * units[value[-1]])
    raise RuntimeError(f"无法解析 vm.swapusage：{result.stdout.strip()}")


def mps_memory() -> dict[str, int | None]:
    backend = getattr(torch, "mps", None)
    values: dict[str, int | None] = {}
    for name in (
        "current_allocated_memory",
        "driver_allocated_memory",
        "recommended_max_memory",
    ):
        function = getattr(backend, name, None)
        values[name] = int(function()) if callable(function) else None
    return values


class ResourceSampler:
    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self.samples: list[dict[str, object]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        started = time.monotonic()
        while not self._stop.is_set():
            try:
                self.samples.append(
                    {
                        "at_seconds": round(time.monotonic() - started, 3),
                        "rss_bytes": current_rss_bytes(),
                        "swap_used_bytes": swap_used_bytes(),
                    }
                )
            except Exception as exc:  # evidence must retain sampler failures
                self.samples.append(
                    {
                        "at_seconds": round(time.monotonic() - started, 3),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            self._stop.wait(self.interval)

    def __enter__(self) -> "ResourceSampler":
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


def inspect_wav(path: Path) -> dict[str, object]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    finite = bool(np.isfinite(audio).all())
    mono = int(audio.shape[1]) == 1
    duration = float(audio.shape[0]) / float(sample_rate)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = float(math.sqrt(float(np.mean(np.square(audio))))) if audio.size else 0.0
    clipping_ratio = float(np.mean(np.abs(audio) >= 0.999)) if audio.size else 1.0
    checks = {
        "sample_rate_48000": sample_rate == 48000,
        "mono": mono,
        "duration_over_0_5": duration > 0.5,
        "finite": finite,
        "non_silent": rms > 1e-5 and peak > 1e-4,
        "clipping_below_0_1_percent": clipping_ratio < 0.001,
    }
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "sample_rate": sample_rate,
        "channels": int(audio.shape[1]),
        "frames": int(audio.shape[0]),
        "duration_seconds": duration,
        "peak_absolute": peak,
        "rms": rms,
        "clipping_ratio": clipping_ratio,
        "checks": checks,
        "ok": all(checks.values()),
    }


def classify(value: float, pass_limit: float, conditional_limit: float) -> str:
    if value <= pass_limit:
        return "PASS"
    if value <= conditional_limit:
        return "CONDITIONAL"
    return "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4 native-MPS model acceptance")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--prompt-audio", type=Path, required=True)
    parser.add_argument("--prompt-text", required=True)
    parser.add_argument("--prompt-name", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Phase 4 model acceptance requires Darwin arm64.")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        raise RuntimeError("Phase 4 refuses PYTORCH_ENABLE_MPS_FALLBACK=1.")
    if len(CONTINUOUS_TEXTS) != 10 or len(CONTINUOUS_TEXTS[-1]) <= 200:
        raise RuntimeError("Phase 4 fixtures must contain ten jobs and a >200 character case.")

    model = args.model.expanduser().resolve()
    prompt_audio = args.prompt_audio.expanduser().resolve()
    evidence = args.evidence_dir.expanduser().resolve()
    output_dir = evidence / "generated"
    candidate_dir = evidence / "candidates"
    for directory in (evidence, output_dir, candidate_dir):
        directory.mkdir(parents=True, exist_ok=True)

    report_path = evidence / f"{model.name}-phase4-model-report.json"
    started_wall = time.time()
    started_monotonic = time.monotonic()
    swap_before = swap_used_bytes()
    rss_before = current_rss_bytes()
    num_steps = recommended_num_steps_for_model(str(model), repo_root=PACKAGE_ROOT)
    report: dict[str, object] = {
        "schema_version": 1,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": sys.argv,
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
            "torch": torch.__version__,
            "torch_mps_built": bool(torch.backends.mps.is_built()),
            "torch_mps_available": bool(torch.backends.mps.is_available()),
            "ffmpeg": command_version(["ffmpeg", "-version"]),
            "ffprobe": command_version(["ffprobe", "-version"]),
        },
        "fixture": {
            "model": str(model),
            "model_config_sha256": sha256(model / "config.json"),
            "model_weights_sha256": sha256(model / "model.safetensors"),
            "prompt_name": args.prompt_name,
            "prompt_audio": str(prompt_audio),
            "prompt_audio_sha256": sha256(prompt_audio),
            "prompt_text": args.prompt_text,
            "seed": args.seed,
            "num_steps": num_steps,
            "continuous_job_count": len(CONTINUOUS_TEXTS),
        },
        "resources_before": {
            "rss_bytes": rss_before,
            "swap_used_bytes": swap_before,
            "mps": mps_memory(),
        },
        "runs": [],
        "failures": [],
    }

    try:
        config = build_gradio_app_config(
            model_name_or_path=str(model),
            output_dir=output_dir,
            output_retention_count=30,
            execution_mode="generate",
            device="auto",
            precision="auto",
            optimize=False,
            max_generate_length=500,
            default_prompt_name=args.prompt_name,
        )
        service = GradioAppService(config)
        cold_request = SynthesisRequest(
            model_name_or_path=str(model),
            text="你好，这是苹果芯片原生MPS冷启动与第一条语音的联合验证。",
            prompt_audio_path=str(prompt_audio),
            prompt_text=args.prompt_text,
            execution_mode="generate",
            num_steps=num_steps,
            seed=args.seed,
            max_pause=0.3,
        )
        with ResourceSampler() as cold_sampler:
            cold_run_started = time.monotonic()
            cold_result = service.generate(cold_request)
            cold_wall_seconds = time.monotonic() - cold_run_started
        cold_wav = inspect_wav(Path(cold_result.audio_path))
        cold_candidate = candidate_dir / f"{model.name}-01-cold.wav"
        shutil.copy2(cold_result.audio_path, cold_candidate)
        report["cold"] = {
            "wall_seconds": cold_wall_seconds,
            "process_wall_seconds": time.monotonic() - started_monotonic,
            "classification": classify(cold_wall_seconds, 180.0, 300.0),
            "metrics": cold_result.metrics,
            "wav": cold_wav,
            "candidate": inspect_wav(cold_candidate),
            "resource_samples": cold_sampler.samples,
            "rss_after_bytes": current_rss_bytes(),
            "swap_after_bytes": swap_used_bytes(),
            "mps_after": mps_memory(),
        }

        # A model whose first native-MPS generation is already beyond the
        # Phase 4 alternative-route line gets one warmed short confirmation.
        # If both generations remain above RTF 5, the steady-state hard gate
        # is already lost; do not spend many more minutes on the long prewarm
        # and ten-job stress suite merely to reproduce the same blocker.
        cold_rtf = float(cold_result.metrics["rtf"])
        if cold_rtf > 5.0:
            screen_request = SynthesisRequest(
                model_name_or_path=str(model),
                text=CONTINUOUS_TEXTS[0],
                prompt_audio_path=str(prompt_audio),
                prompt_text=args.prompt_text,
                execution_mode="generate",
                num_steps=num_steps,
                seed=args.seed,
                max_pause=0.3,
            )
            with ResourceSampler() as screen_sampler:
                screen_started = time.monotonic()
                screen_result = service.generate(screen_request)
                screen_wall_seconds = time.monotonic() - screen_started
            screen_wav = inspect_wav(Path(screen_result.audio_path))
            screen_rtf = float(screen_result.metrics["rtf"])
            report["performance_screen"] = {
                "reason": "cold_rtf_over_5_requires_one_warmed_short_confirmation",
                "threshold_rtf": 5.0,
                "cold_rtf": cold_rtf,
                "warm_rtf": screen_rtf,
                "warm_wall_seconds": screen_wall_seconds,
                "warm_metrics": screen_result.metrics,
                "warm_wav": screen_wav,
                "resource_samples": screen_sampler.samples,
                "rss_after_bytes": current_rss_bytes(),
                "swap_after_bytes": swap_used_bytes(),
                "mps_after": mps_memory(),
            }
            if screen_rtf > 5.0:
                samples = [
                    *cold_sampler.samples,
                    *screen_sampler.samples,
                ]
                valid_samples = [row for row in samples if "rss_bytes" in row]
                peak_rss = max(
                    [
                        rss_before,
                        current_rss_bytes(),
                        *(int(row["rss_bytes"]) for row in valid_samples),
                    ]
                )
                peak_swap = max(
                    [
                        swap_before,
                        swap_used_bytes(),
                        *(int(row["swap_used_bytes"]) for row in valid_samples),
                    ]
                )
                peak_mps_driver = max(
                    int(report[name]["mps_after"]["driver_allocated_memory"] or 0)
                    for name in ("cold", "performance_screen")
                )
                peak_memory = max(peak_rss, peak_mps_driver)
                swap_delta = max(0, peak_swap - swap_before)
                policy = cold_result.metrics["device_policy"]
                policy_ok = (
                    policy.get("actual_device") == "mps"
                    and policy.get("actual_precision") == "float32"
                    and policy.get("native_mps") is True
                    and policy.get("fallback_used") is False
                )
                classifications = {
                    "cold_start": classify(cold_wall_seconds, 180.0, 300.0),
                    "steady_rtf": "FAIL",
                    "peak_memory": classify(peak_memory / GIB, 24.0, 26.0),
                }
                hard_checks = {
                    "native_mps_float32_no_fallback": policy_ok,
                    "cold_wav_media": bool(cold_wav["ok"]),
                    "warm_wav_media": bool(screen_wav["ok"]),
                    "cold_not_fail": classifications["cold_start"] != "FAIL",
                    "steady_rtf_not_fail": False,
                    "peak_memory_not_fail": classifications["peak_memory"] != "FAIL",
                    "swap_delta": swap_delta <= 2 * GIB,
                }
                report["summary"] = {
                    "device_policy": policy,
                    "performance_screen": "FAIL_FAST_CONFIRMED",
                    "cold_rtf": cold_rtf,
                    "warm_rtf": screen_rtf,
                    "cold_wall_seconds": cold_wall_seconds,
                    "peak_rss_bytes": peak_rss,
                    "peak_mps_driver_allocated_bytes": peak_mps_driver,
                    "peak_memory_gate_bytes": peak_memory,
                    "swap_before_bytes": swap_before,
                    "peak_swap_bytes": peak_swap,
                    "swap_delta_bytes": swap_delta,
                    "classifications": classifications,
                    "hard_checks": hard_checks,
                    "not_executed": [
                        "long_text_stability_prewarm",
                        "continuous_10_job_suite",
                    ],
                    "not_executed_reason": (
                        "Two native-MPS short generations exceeded RTF 5; "
                        "the Phase 4 steady-performance hard gate is already lost."
                    ),
                    "result": "FAIL",
                }
                report["failures"].append("steady_rtf_not_fail")
                return 1

        # The cold short request loads the model but does not materialize the
        # MPS allocations used by the chunked long-text path. Exercise that
        # path before the measured ten-job stability window so RSS growth is
        # genuinely measured after warm-up, as required by the Phase 4 gate.
        prewarm_request = SynthesisRequest(
            model_name_or_path=str(model),
            text=CONTINUOUS_TEXTS[-1],
            prompt_audio_path=str(prompt_audio),
            prompt_text=args.prompt_text,
            execution_mode="generate",
            num_steps=num_steps,
            seed=args.seed,
            max_pause=0.3,
        )
        with ResourceSampler() as prewarm_sampler:
            prewarm_started = time.monotonic()
            prewarm_result = service.generate(prewarm_request)
            prewarm_wall_seconds = time.monotonic() - prewarm_started
        prewarm_wav = inspect_wav(Path(prewarm_result.audio_path))
        report["stability_prewarm"] = {
            "text": CONTINUOUS_TEXTS[-1],
            "characters": len(CONTINUOUS_TEXTS[-1]),
            "wall_seconds": prewarm_wall_seconds,
            "metrics": prewarm_result.metrics,
            "wav": prewarm_wav,
            "resource_samples": prewarm_sampler.samples,
            "rss_after_bytes": current_rss_bytes(),
            "swap_after_bytes": swap_used_bytes(),
            "mps_after": mps_memory(),
        }

        runs: list[dict[str, object]] = []
        for index, text in enumerate(CONTINUOUS_TEXTS, start=1):
            request = SynthesisRequest(
                model_name_or_path=str(model),
                text=text,
                prompt_audio_path=str(prompt_audio),
                prompt_text=args.prompt_text,
                execution_mode="generate",
                num_steps=num_steps,
                seed=args.seed,
                max_pause=0.3,
            )
            with ResourceSampler() as sampler:
                run_started = time.monotonic()
                result = service.generate(request)
                wall_seconds = time.monotonic() - run_started
            wav = inspect_wav(Path(result.audio_path))
            row = {
                "index": index,
                "text": text,
                "characters": len(text),
                "wall_seconds": wall_seconds,
                "metrics": result.metrics,
                "wav": wav,
                "rss_after_bytes": current_rss_bytes(),
                "swap_after_bytes": swap_used_bytes(),
                "mps_after": mps_memory(),
                "resource_samples": sampler.samples,
            }
            runs.append(row)
            if index in (2, 4, 10):
                candidate = candidate_dir / f"{model.name}-{index + 1:02d}-job-{index:02d}.wav"
                shutil.copy2(result.audio_path, candidate)
                row["candidate"] = inspect_wav(candidate)
        report["runs"] = runs

        resource_samples = [*cold_sampler.samples, *prewarm_sampler.samples]
        for row in runs:
            resource_samples.extend(row["resource_samples"])
        valid_resource_samples = [row for row in resource_samples if "rss_bytes" in row]
        peak_rss = max([rss_before, current_rss_bytes(), *(int(row["rss_bytes"]) for row in valid_resource_samples)])
        peak_swap = max([swap_before, swap_used_bytes(), *(int(row["swap_used_bytes"]) for row in valid_resource_samples)])
        mps_rows = [
            report["cold"]["mps_after"],
            report["stability_prewarm"]["mps_after"],
            *(row["mps_after"] for row in runs),
        ]
        peak_mps_driver = max(
            int(row["driver_allocated_memory"] or 0) for row in mps_rows
        )
        peak_memory = max(peak_rss, peak_mps_driver)
        rtfs = [float(row["metrics"]["rtf"]) for row in runs]
        median_rtf = float(np.median(np.asarray(rtfs, dtype=np.float64)))
        first_rss = int(runs[0]["rss_after_bytes"])
        final_rss = int(runs[-1]["rss_after_bytes"])
        rss_growth = max(0, final_rss - first_rss)
        rss_growth_ratio = rss_growth / first_rss if first_rss else float("inf")
        swap_delta = max(0, peak_swap - swap_before)
        media_ok = (
            all(bool(row["wav"]["ok"]) for row in runs)
            and bool(cold_wav["ok"])
            and bool(prewarm_wav["ok"])
        )
        continuous_ok = len(runs) == 10 and media_ok
        rss_growth_ok = rss_growth <= GIB or rss_growth_ratio <= 0.10
        swap_ok = swap_delta <= 2 * GIB
        policy = cold_result.metrics["device_policy"]
        policy_ok = (
            policy.get("actual_device") == "mps"
            and policy.get("actual_precision") == "float32"
            and policy.get("native_mps") is True
            and policy.get("fallback_used") is False
        )
        classifications = {
            "cold_start": classify(cold_wall_seconds, 180.0, 300.0),
            "steady_rtf": classify(median_rtf, 2.0, 3.0),
            "peak_memory": classify(peak_memory / GIB, 24.0, 26.0),
        }
        hard_checks = {
            "native_mps_float32_no_fallback": policy_ok,
            "continuous_10": continuous_ok,
            "wav_media": media_ok,
            "rss_growth": rss_growth_ok,
            "swap_delta": swap_ok,
            "cold_not_fail": classifications["cold_start"] != "FAIL",
            "steady_rtf_not_fail": classifications["steady_rtf"] != "FAIL",
            "peak_memory_not_fail": classifications["peak_memory"] != "FAIL",
        }
        report["summary"] = {
            "device_policy": policy,
            "median_steady_rtf": median_rtf,
            "steady_rtf_samples": rtfs,
            "cold_wall_seconds": cold_wall_seconds,
            "peak_rss_bytes": peak_rss,
            "peak_mps_driver_allocated_bytes": peak_mps_driver,
            "peak_memory_gate_bytes": peak_memory,
            "swap_before_bytes": swap_before,
            "peak_swap_bytes": peak_swap,
            "swap_delta_bytes": swap_delta,
            "post_warmup_rss_first_bytes": first_rss,
            "post_warmup_rss_final_bytes": final_rss,
            "post_warmup_rss_growth_bytes": rss_growth,
            "post_warmup_rss_growth_ratio": rss_growth_ratio,
            "classifications": classifications,
            "hard_checks": hard_checks,
            "result": (
                "FAIL"
                if not all(hard_checks.values())
                else "CONDITIONAL"
                if "CONDITIONAL" in classifications.values()
                else "PASS"
            ),
        }
        if not all(hard_checks.values()):
            report["failures"].extend(
                name for name, ok in hard_checks.items() if not ok
            )
    except Exception as exc:
        report["failures"].append(f"{type(exc).__name__}: {exc}")
        report["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        raise
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report["wall_seconds"] = time.time() - started_wall
        report["resources_after"] = {
            "rss_bytes": current_rss_bytes(),
            "ru_maxrss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "swap_used_bytes": swap_used_bytes(),
            "mps": mps_memory(),
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report.get("summary", report), ensure_ascii=False, indent=2))

    return 0 if report["summary"]["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
