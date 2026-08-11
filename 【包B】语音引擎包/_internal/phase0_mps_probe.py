from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import resource
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch

from dots_tts.models.dots_tts.model import DotsTtsModel
from dots_tts.runtime import DotsTtsRuntime
from dots_tts.utils.util import get_dtype


GIB = 1024**3
MPS_FALLBACK_ENV = "PYTORCH_ENABLE_MPS_FALLBACK"
TRUTHY = {"1", "true", "yes", "on"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _run_text(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def _fallback_enabled() -> bool:
    return os.environ.get(MPS_FALLBACK_ENV, "").strip().lower() in TRUTHY


def _mps_memory() -> tuple[int, int]:
    allocated = 0
    driver = 0
    try:
        allocated = int(torch.mps.current_allocated_memory())
    except Exception:
        pass
    try:
        driver = int(torch.mps.driver_allocated_memory())
    except Exception:
        pass
    return allocated, driver


def _rss_bytes() -> int:
    result = _run_text(["/bin/ps", "-o", "rss=", "-p", str(os.getpid())])
    try:
        return int(result["stdout"].strip()) * 1024
    except (TypeError, ValueError):
        return 0


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _system_memory_snapshot() -> dict[str, Any]:
    swap = _run_text(["/usr/sbin/sysctl", "vm.swapusage"])
    pressure = _run_text(["/usr/bin/memory_pressure", "-Q"])
    vm_stat = _run_text(["/usr/bin/vm_stat"])
    swap_used_mib = None
    match = re.search(r"used\s*=\s*([0-9.]+)M", swap["stdout"])
    if match:
        swap_used_mib = float(match.group(1))
    free_percent = None
    match = re.search(
        r"System-wide memory free percentage:\s*([0-9.]+)%",
        pressure["stdout"],
    )
    if match:
        free_percent = float(match.group(1))
    return {
        "captured_at_unix": time.time(),
        "swap_used_mib": swap_used_mib,
        "memory_free_percent": free_percent,
        "swap_raw": swap,
        "pressure_raw": pressure,
        "vm_stat_raw": vm_stat,
    }


class ResourceSampler:
    def __init__(self, interval_seconds: float = 0.25):
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)

    def _sample_once(self) -> None:
        allocated, driver = _mps_memory()
        self.samples.append(
            {
                "at_unix": time.time(),
                "rss_bytes": _rss_bytes(),
                "mps_allocated_bytes": allocated,
                "mps_driver_bytes": driver,
            }
        )

    def _sample_loop(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self.interval_seconds)

    def __enter__(self) -> ResourceSampler:
        self._sample_once()
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self._sample_once()

    def summary(self) -> dict[str, Any]:
        return {
            "sample_count": len(self.samples),
            "max_rss_bytes": max((row["rss_bytes"] for row in self.samples), default=0),
            "max_mps_allocated_bytes": max(
                (row["mps_allocated_bytes"] for row in self.samples), default=0
            ),
            "max_mps_driver_bytes": max(
                (row["mps_driver_bytes"] for row in self.samples), default=0
            ),
            "samples": self.samples,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capabilities() -> dict[str, Any]:
    fallback_value = os.environ.get(MPS_FALLBACK_ENV)
    return {
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "machine": platform.machine(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "torch": {
            "version": torch.__version__,
            "torchaudio_version": _module_version("torchaudio"),
            "mps_built": bool(torch.backends.mps.is_built()),
            "mps_available": bool(torch.backends.mps.is_available()),
            "fallback_env_value": fallback_value,
            "fallback_enabled": _fallback_enabled(),
        },
        "tools": {
            "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"),
        },
        "disk": shutil.disk_usage(Path.cwd())._asdict(),
        "memory": _system_memory_snapshot(),
    }


def _module_version(name: str) -> str | None:
    try:
        module = __import__(name)
        return str(getattr(module, "__version__", "unknown"))
    except Exception as exc:
        return f"import-error: {type(exc).__name__}: {exc}"


def _validate_capabilities(capabilities: dict[str, Any]) -> None:
    errors = []
    if capabilities["python"]["machine"] != "arm64":
        errors.append("Python is not arm64")
    if not capabilities["python"]["version"].startswith("3.12."):
        errors.append("Python is not 3.12.x")
    if not capabilities["torch"]["mps_built"]:
        errors.append("PyTorch was not built with MPS")
    if not capabilities["torch"]["mps_available"]:
        errors.append("MPS is not available")
    if capabilities["torch"]["fallback_enabled"]:
        errors.append(f"{MPS_FALLBACK_ENV} is enabled")
    if errors:
        raise RuntimeError("; ".join(errors))


def _experimental_mps_runtime(
    model_path: Path,
    *,
    precision: str,
    max_generate_length: int,
) -> tuple[DotsTtsRuntime, dict[str, Any]]:
    device = torch.device("mps")
    started = time.perf_counter()
    model = DotsTtsModel.from_pretrained(model_path)
    cpu_load_seconds = time.perf_counter() - started
    after_cpu_load = {
        "rss_bytes": _rss_bytes(),
        "peak_rss_bytes": _peak_rss_bytes(),
    }

    target_dtype = get_dtype(precision)
    move_started = time.perf_counter()
    model.core.to(dtype=target_dtype)
    model = model.to(device).eval()
    model.set_optimize(False)
    torch.mps.synchronize()
    move_seconds = time.perf_counter() - move_started
    parameter_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    if not parameter_devices or any(not item.startswith("mps") for item in parameter_devices):
        raise RuntimeError(f"Model parameters are not entirely on MPS: {parameter_devices}")

    runtime = DotsTtsRuntime.__new__(DotsTtsRuntime)
    runtime.model = model
    runtime.pretrained_path = model_path
    runtime.precision = precision
    runtime.device = device
    runtime.optimize = False
    runtime.max_generate_length = int(max_generate_length)
    runtime.sample_rate = int(model.config.vocoder.sample_rate)
    return runtime, {
        "cpu_load_seconds": cpu_load_seconds,
        "mps_move_seconds": move_seconds,
        "after_cpu_load": after_cpu_load,
        "parameter_devices": parameter_devices,
        "target_dtype": str(target_dtype),
        "sample_rate": runtime.sample_rate,
    }


def _seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    manual_seed = getattr(torch.mps, "manual_seed", None)
    if callable(manual_seed):
        manual_seed(seed)


def _audio_metrics(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    values = np.asarray(audio, dtype=np.float32).reshape(-1)
    finite = bool(np.isfinite(values).all())
    absolute = np.abs(values) if values.size else np.asarray([], dtype=np.float32)
    peak = float(absolute.max()) if absolute.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(values)))) if values.size else 0.0
    clipping_ratio = float(np.mean(absolute >= 0.999)) if absolute.size else 1.0
    duration = float(values.size / sample_rate) if sample_rate > 0 else 0.0
    return {
        "sample_count": int(values.size),
        "sample_rate": int(sample_rate),
        "channels": 1,
        "duration_seconds": duration,
        "finite": finite,
        "peak_abs": peak,
        "rms": rms,
        "non_silent": bool(finite and rms > 1e-6),
        "clipping_ratio": clipping_ratio,
    }


def _validate_audio(metrics: dict[str, Any]) -> list[str]:
    failures = []
    if metrics["sample_rate"] != 48000:
        failures.append("sample_rate != 48000")
    if metrics["channels"] != 1:
        failures.append("channels != 1")
    if not metrics["finite"]:
        failures.append("non-finite samples")
    if not metrics["non_silent"]:
        failures.append("silent output")
    if metrics["duration_seconds"] <= 0.5:
        failures.append("duration <= 0.5 seconds")
    if metrics["clipping_ratio"] >= 0.001:
        failures.append("clipping ratio >= 0.1%")
    return failures


def _run_generation(args: argparse.Namespace) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "phase": "phase0",
        "status": "running",
        "started_at_unix": time.time(),
        "precision": args.precision,
        "seed": args.seed,
        "fixture": {
            "text": args.text,
            "prompt_audio": str(args.prompt_audio),
            "prompt_text": args.prompt_text,
            "model": str(args.model),
            "num_steps": args.num_steps,
            "max_generate_length": args.max_generate_length,
        },
        "capabilities": _capabilities(),
        "runs": [],
    }
    _atomic_json(args.report, report)
    try:
        _validate_capabilities(report["capabilities"])
        for path in (args.model, args.prompt_audio):
            if not path.exists():
                raise FileNotFoundError(path)

        load_memory_before = _system_memory_snapshot()
        with ResourceSampler() as load_sampler:
            runtime, load = _experimental_mps_runtime(
                args.model,
                precision=args.precision,
                max_generate_length=args.max_generate_length,
            )
        load["resources"] = load_sampler.summary()
        load["memory_before"] = load_memory_before
        load["memory_after"] = _system_memory_snapshot()
        report["load"] = load
        _atomic_json(args.report, report)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        for run_index in range(1, args.runs + 1):
            _seed(args.seed)
            memory_before = _system_memory_snapshot()
            with ResourceSampler() as sampler:
                torch.mps.synchronize()
                started = time.perf_counter()
                result = runtime.generate(
                    text=args.text,
                    prompt_audio_path=str(args.prompt_audio),
                    prompt_text=args.prompt_text,
                    template_name="tts",
                    speaker_scale=1.5,
                    ode_method="euler",
                    num_steps=args.num_steps,
                    guidance_scale=1.2,
                    normalize_text=False,
                    profile_inference=False,
                )
                torch.mps.synchronize()
                wall_seconds = time.perf_counter() - started
                audio_device = str(result["audio"].device)
                audio = result["audio"].detach().float().cpu().numpy().squeeze()
            memory_after = _system_memory_snapshot()

            metrics = _audio_metrics(audio, int(result["sample_rate"]))
            output = args.output_dir / (
                f"phase0-{args.precision}-seed{args.seed}-run{run_index:02d}.wav"
            )
            sf.write(str(output), audio, int(result["sample_rate"]))
            decoded, decoded_rate = sf.read(str(output), always_2d=True, dtype="float32")
            decoded_metrics = _audio_metrics(decoded[:, 0], int(decoded_rate))
            decoded_metrics["channels"] = int(decoded.shape[1])
            failures = _validate_audio(metrics) + [
                f"decoded: {item}" for item in _validate_audio(decoded_metrics)
            ]
            if not audio_device.startswith("mps"):
                failures.append(f"audio tensor device is {audio_device!r}, not MPS")
            resources = sampler.summary()
            if resources["max_mps_driver_bytes"] <= 0:
                failures.append("MPS driver memory did not show active allocation")
            max_memory = max(
                resources["max_rss_bytes"],
                resources["max_mps_driver_bytes"],
                _peak_rss_bytes(),
            )
            if max_memory > 26 * GIB:
                failures.append("peak memory exceeded 26 GiB")
            audio_seconds = metrics["duration_seconds"]
            run_report = {
                "run": run_index,
                "output": str(output),
                "sha256": _sha256(output),
                "size_bytes": output.stat().st_size,
                "audio_tensor_device": audio_device,
                "wall_seconds": wall_seconds,
                "runtime_reported_seconds": float(result["time_used"]),
                "audio_seconds": audio_seconds,
                "rtf": wall_seconds / audio_seconds if audio_seconds > 0 else math.inf,
                "raw_audio": metrics,
                "decoded_audio": decoded_metrics,
                "resources": resources,
                "peak_rss_bytes": _peak_rss_bytes(),
                "memory_before": memory_before,
                "memory_after": memory_after,
                "failures": failures,
                "passed": not failures,
            }
            report["runs"].append(run_report)
            _atomic_json(args.report, report)

        rtf_values = [float(item["rtf"]) for item in report["runs"]]
        hot_variation = None
        if len(rtf_values) >= 3:
            denominator = max(rtf_values[-2], rtf_values[-1])
            hot_variation = (
                abs(rtf_values[-2] - rtf_values[-1]) / denominator
                if denominator > 0
                else math.inf
            )
        report["hot_rtf_relative_difference"] = hot_variation
        report["hot_rtf_gate_passed"] = bool(
            hot_variation is not None and hot_variation <= 0.20
        )
        report["native_mps"] = bool(
            not report["capabilities"]["torch"]["fallback_enabled"]
            and report["capabilities"]["torch"]["mps_available"]
            and all(item["audio_tensor_device"].startswith("mps") for item in report["runs"])
        )
        report["status"] = (
            "passed"
            if len(report["runs"]) == args.runs
            and all(item["passed"] for item in report["runs"])
            and report["hot_rtf_gate_passed"]
            and report["native_mps"]
            else "failed"
        )
    except Exception as exc:
        report["status"] = "error"
        report["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    report["finished_at_unix"] = time.time()
    _atomic_json(args.report, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Disposable Phase 0 native-MPS probe")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capabilities = subparsers.add_parser("capabilities")
    capabilities.add_argument("--report", type=Path, required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--model", type=Path, required=True)
    run.add_argument("--prompt-audio", type=Path, required=True)
    run.add_argument("--prompt-text", required=True)
    run.add_argument("--text", required=True)
    run.add_argument("--precision", choices=("bfloat16", "float16", "float32"), required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.add_argument("--runs", type=int, default=3)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--num-steps", type=int, default=4)
    run.add_argument("--max-generate-length", type=int, default=160)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "capabilities":
        payload = _capabilities()
        _atomic_json(args.report, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    report = _run_generation(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
