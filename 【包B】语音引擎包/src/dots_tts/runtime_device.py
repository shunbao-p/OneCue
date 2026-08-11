from __future__ import annotations

import importlib
import os
import platform
import random
import sys
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from typing import Any

SUPPORTED_DEVICES = ("auto", "cuda", "mps", "cpu")
SUPPORTED_PRECISIONS = ("auto", "bfloat16", "float16", "float32")
_PRECISION_ALIASES = {
    "auto": "auto",
    "bf16": "bfloat16",
    "bfloat16": "bfloat16",
    "torch.bfloat16": "bfloat16",
    "fp16": "float16",
    "float16": "float16",
    "torch.float16": "float16",
    "fp32": "float32",
    "float32": "float32",
    "torch.float32": "float32",
}


class RuntimeDeviceError(RuntimeError):
    """Raised when the requested runtime policy cannot be honored safely."""


@dataclass(frozen=True)
class RuntimeCapabilities:
    platform: str
    machine: str
    cuda_available: bool
    mps_built: bool
    mps_available: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeDevicePolicy:
    requested_device: str
    actual_device: str
    requested_precision: str
    actual_precision: str
    optimize: bool
    fallback_used: bool
    fallback_reason: str | None
    capabilities: RuntimeCapabilities

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["native_mps"] = (
            self.actual_device == "mps"
            and os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "1"
        )
        return payload


def _call_bool(owner: Any, name: str) -> bool:
    value = getattr(owner, name, None)
    return bool(value()) if callable(value) else False


def detect_runtime_capabilities(
    torch_module: Any,
    *,
    platform_name: str | None = None,
    machine: str | None = None,
) -> RuntimeCapabilities:
    backends = getattr(torch_module, "backends", None)
    mps = getattr(backends, "mps", None)
    cuda = getattr(torch_module, "cuda", None)
    return RuntimeCapabilities(
        platform=(platform_name or sys.platform).lower(),
        machine=(machine or platform.machine()).lower(),
        cuda_available=_call_bool(cuda, "is_available"),
        mps_built=_call_bool(mps, "is_built"),
        mps_available=_call_bool(mps, "is_available"),
    )


def normalize_precision(value: str) -> str:
    normalized = _PRECISION_ALIASES.get(str(value).strip().lower())
    if normalized is None:
        raise RuntimeDeviceError(
            f"Unsupported precision {value!r}; expected one of {SUPPORTED_PRECISIONS}."
        )
    return normalized


def resolve_runtime_device_policy(
    torch_module: Any,
    *,
    requested_device: str = "auto",
    requested_precision: str = "auto",
    optimize: bool = False,
    platform_name: str | None = None,
    machine: str | None = None,
) -> RuntimeDevicePolicy:
    device = str(requested_device).strip().lower()
    if device not in SUPPORTED_DEVICES:
        raise RuntimeDeviceError(
            f"Unsupported device {requested_device!r}; expected one of {SUPPORTED_DEVICES}."
        )

    capabilities = detect_runtime_capabilities(
        torch_module,
        platform_name=platform_name,
        machine=machine,
    )
    fallback_used = False
    fallback_reason = None
    if device == "auto":
        if capabilities.cuda_available:
            actual_device = "cuda"
        elif (
            capabilities.mps_available
            and capabilities.platform == "darwin"
            and capabilities.machine in {"arm64", "aarch64"}
        ):
            actual_device = "mps"
        else:
            actual_device = "cpu"
            fallback_used = True
            fallback_reason = "auto_no_cuda_or_mps"
    else:
        actual_device = device

    if actual_device == "cuda" and not capabilities.cuda_available:
        raise RuntimeDeviceError("CUDA was requested but torch.cuda.is_available() is false.")
    if actual_device == "mps":
        if capabilities.platform != "darwin" or capabilities.machine not in {
            "arm64",
            "aarch64",
        }:
            raise RuntimeDeviceError(
                "MPS is supported by this package only on Darwin arm64/aarch64."
            )
        if not capabilities.mps_built:
            raise RuntimeDeviceError("MPS was requested but this PyTorch build has no MPS support.")
        if not capabilities.mps_available:
            raise RuntimeDeviceError("MPS was requested but torch.backends.mps.is_available() is false.")

    precision = normalize_precision(requested_precision)
    if precision == "auto":
        precision = "bfloat16" if actual_device == "cuda" else "float32"
    if actual_device in {"mps", "cpu"} and precision != "float32":
        raise RuntimeDeviceError(
            f"{actual_device.upper()} is validated only with float32 in this package; "
            f"requested precision was {requested_precision!r}."
        )
    if optimize and actual_device != "cuda":
        raise RuntimeDeviceError(
            f"optimize/torch.compile is disabled for {actual_device}; use optimize=false."
        )

    return RuntimeDevicePolicy(
        requested_device=device,
        actual_device=actual_device,
        requested_precision=normalize_precision(requested_precision),
        actual_precision=precision,
        optimize=bool(optimize),
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        capabilities=capabilities,
    )


def torch_dtype_for_precision(torch_module: Any, precision: str) -> Any:
    normalized = normalize_precision(precision)
    if normalized == "auto":
        raise RuntimeDeviceError("Precision must be resolved before requesting a torch dtype.")
    return getattr(torch_module, normalized)


def configure_torch_runtime(torch_module: Any, policy: RuntimeDevicePolicy) -> None:
    if policy.actual_device == "cpu":
        set_num_threads = getattr(torch_module, "set_num_threads", None)
        if callable(set_num_threads):
            set_num_threads(1)
        return
    if policy.actual_device != "cuda":
        return

    cuda_backend = getattr(getattr(torch_module, "backends", None), "cuda", None)
    enable_flash_sdp = getattr(cuda_backend, "enable_flash_sdp", None)
    enable_cudnn_sdp = getattr(cuda_backend, "enable_cudnn_sdp", None)
    if callable(enable_flash_sdp):
        enable_flash_sdp(True)
    if callable(enable_cudnn_sdp):
        enable_cudnn_sdp(False)
    if policy.actual_precision == "float32":
        set_matmul_precision = getattr(torch_module, "set_float32_matmul_precision", None)
        if callable(set_matmul_precision):
            set_matmul_precision("high")


def inference_autocast(torch_module: Any, device: Any, dtype: Any):
    """Return CUDA AMP only when it is active; avoid constructing MPS autocast."""
    device_type = getattr(device, "type", str(device).split(":", 1)[0])
    if device_type == "cuda" and dtype in {
        torch_module.float16,
        torch_module.bfloat16,
    }:
        autocast = getattr(torch_module, "autocast", None)
        if not callable(autocast):
            raise RuntimeDeviceError("CUDA reduced precision requires torch.autocast().")
        return autocast(device_type="cuda", dtype=dtype, enabled=True)
    return nullcontext()


def release_torch_accelerator_cache(torch_module: Any) -> None:
    """Release allocator caches between isolated benchmark model runs."""
    for backend_name in ("cuda", "mps"):
        backend = getattr(torch_module, backend_name, None)
        empty_cache = getattr(backend, "empty_cache", None)
        if callable(empty_cache):
            empty_cache()


def seed_everything(seed: int = 42, *, torch_module: Any | None = None) -> None:
    import numpy as np  # noqa: PLC0415

    if torch_module is None:
        import torch as torch_module  # noqa: PLC0415

    random.seed(seed)
    np.random.seed(seed)
    torch_module.manual_seed(seed)
    cuda = getattr(torch_module, "cuda", None)
    if not _call_bool(cuda, "is_available"):
        return
    manual_seed = getattr(cuda, "manual_seed", None)
    manual_seed_all = getattr(cuda, "manual_seed_all", None)
    if callable(manual_seed):
        manual_seed(seed)
    if callable(manual_seed_all):
        manual_seed_all(seed)
    cudnn = getattr(getattr(torch_module, "backends", None), "cudnn", None)
    if cudnn is not None:
        cudnn.deterministic = True
        cudnn.benchmark = False


def install_windows_asyncio_cleanup_patch(*, platform_name: str | None = None) -> bool:
    """Install the existing Proactor disconnect workaround only on Windows."""
    if (platform_name or sys.platform).lower() != "win32":
        return False
    try:
        module = importlib.import_module("asyncio.proactor_events")
        transport = module._ProactorBasePipeTransport
    except (ImportError, AttributeError):
        return False
    if getattr(transport, "_dots_tts_connection_patch", False):
        return True
    original = transport._call_connection_lost

    def patched(instance, arg):
        try:
            original(instance, arg)
        except ConnectionResetError:
            pass

    transport._call_connection_lost = patched
    transport._dots_tts_connection_patch = True
    return True
