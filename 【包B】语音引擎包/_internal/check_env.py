# -*- coding: utf-8 -*-
"""Structured dots.tts environment diagnostics for CPU, CUDA, and Apple MPS."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

from dots_tts.external_tools import (  # noqa: E402
    ExternalToolNotFoundError,
    resolve_external_tool,
)
from dots_tts.runtime_device import (  # noqa: E402
    RuntimeDeviceError,
    resolve_runtime_device_policy,
)


def check_python() -> dict[str, Any]:
    version = sys.version_info[:3]
    compatible = (3, 10) <= version[:2] < (3, 13)
    return {
        "ok": compatible,
        "version": ".".join(str(item) for item in version),
        "executable": sys.executable,
        "required": ">=3.10,<3.13",
    }


def check_torch(device: str, precision: str) -> dict[str, Any]:
    try:
        import torch
    except ImportError as exc:
        return {"ok": False, "error": f"PyTorch import failed: {exc}"}
    try:
        policy = resolve_runtime_device_policy(
            torch,
            requested_device=device,
            requested_precision=precision,
            optimize=False,
        )
    except RuntimeDeviceError as exc:
        return {"ok": False, "version": torch.__version__, "error": str(exc)}
    return {
        "ok": True,
        "version": torch.__version__,
        "policy": policy.as_dict(),
        "mps_fallback_env": os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK"),
    }


def check_dependencies() -> dict[str, Any]:
    modules = (
        "gradio",
        "transformers",
        "librosa",
        "soundfile",
        "safetensors",
        "einops",
        "lingua",
        "torchdiffeq",
    )
    status: dict[str, bool] = {}
    errors: dict[str, str] = {}
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            status[module_name] = True
        except ImportError as exc:
            status[module_name] = False
            errors[module_name] = str(exc)
    return {"ok": all(status.values()), "modules": status, "errors": errors}


def check_models() -> dict[str, Any]:
    required_files = (
        "config.json",
        "model.safetensors",
        "vocoder.safetensors",
        "speaker_encoder.safetensors",
        "llm_config.json",
        "latent_stats.pt",
        "tokenizer.json",
        "tokenizer_config.json",
    )
    model_root = PROJECT_DIR / "pretrained_models"
    models: list[dict[str, Any]] = []
    if model_root.is_dir():
        for child in sorted(model_root.iterdir()):
            if not child.is_dir() or not (child / "config.json").is_file():
                continue
            missing = [name for name in required_files if not (child / name).is_file()]
            models.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "ok": not missing,
                    "missing": missing,
                }
            )
    return {
        "ok": bool(models) and all(item["ok"] for item in models),
        "root": str(model_root),
        "models": models,
    }


def check_tool(name: str, explicit_path: str | None, *, required: bool) -> dict[str, Any]:
    try:
        resolution = resolve_external_tool(
            name,
            explicit_path=explicit_path,
            package_root=PROJECT_DIR,
            required=required,
        )
    except ExternalToolNotFoundError as exc:
        return {
            "ok": False,
            "required": required,
            "error": str(exc),
            "checked_locations": list(exc.checked_locations),
        }
    if resolution is None:
        return {"ok": True, "available": False, "required": False}
    completed = subprocess.run(
        [resolution.path, "-version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    first_line = (completed.stdout or completed.stderr).splitlines()
    return {
        "ok": completed.returncode == 0,
        "available": True,
        "required": required,
        "resolution": resolution.as_dict(),
        "version_line": first_line[0] if first_line else "",
        "returncode": completed.returncode,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    checks = {
        "python": check_python(),
        "torch": check_torch(args.device, args.precision),
        "dependencies": check_dependencies(),
        "ffmpeg": check_tool("ffmpeg", args.ffmpeg_path, required=True),
        "ffprobe": check_tool("ffprobe", args.ffprobe_path, required=True),
        "rubberband": check_tool("rubberband", args.rubberband_path, required=False),
    }
    if not args.skip_model_check:
        checks["models"] = check_models()
    required_names = {"python", "torch", "dependencies", "ffmpeg", "ffprobe", "models"}
    required_results = [value["ok"] for name, value in checks.items() if name in required_names]
    return {
        "schema_version": 1,
        "requested": {"device": args.device, "precision": args.precision},
        "project_dir": str(PROJECT_DIR),
        "checks": checks,
        "ok": all(required_results),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="dots.tts structured environment diagnostics")
    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"), default="auto")
    parser.add_argument(
        "--precision",
        choices=("auto", "bfloat16", "float16", "float32"),
        default="auto",
    )
    parser.add_argument("--ffmpeg-path", default=None)
    parser.add_argument("--ffprobe-path", default=None)
    parser.add_argument("--rubberband-path", default=None)
    parser.add_argument("--skip-model-check", action="store_true")
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_stdout")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    if args.json_stdout:
        print(payload)
    else:
        print(f"dots.tts 环境诊断: {'通过' if report['ok'] else '失败'}")
        for name, result in report["checks"].items():
            print(f"  [{'OK' if result['ok'] else 'FAIL'}] {name}")
            if result.get("error"):
                print(f"    {result['error']}")
        if args.json_output is not None:
            print(f"  JSON: {args.json_output}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
