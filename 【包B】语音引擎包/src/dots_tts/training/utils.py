"""Shared helpers for the dots_tts training entrypoints."""

from __future__ import annotations

import math
import os
import sys
import traceback
from collections import Counter
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

import torch
import torch.distributed as dist

from dots_tts.training import losses as loss_ops

# ---------------------------------------------------------------------------
# Training State
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TrainProgress:
    """Minimal progress counters that must survive checkpoint save/load."""

    global_step: int = 0
    epoch: int = 0
    total_tokens: int = 0
    audio_tokens: int = 0
    text_tokens: int = 0


@dataclass(slots=True)
class TrainStepReport:
    log_values: dict[str, float]
    console_line: str


# ---------------------------------------------------------------------------
# Distributed Helpers
# ---------------------------------------------------------------------------


def any_rank_true(flag: bool, *, device: torch.device) -> bool:
    """Return ``True`` if any distributed rank reports ``flag=True``."""
    packed = torch.tensor(int(flag), device=device, dtype=torch.int32)
    if dist.is_available() and dist.is_initialized():
        dist.all_reduce(packed, op=dist.ReduceOp.MAX)
    return bool(packed.item())


def sum_integer_counters_across_ranks(
    values: list[int],
    *,
    device: torch.device,
) -> list[int]:
    """All-reduce integer counters and return their cross-rank sums."""
    packed = torch.tensor(values, device=device, dtype=torch.int64)
    if dist.is_available() and dist.is_initialized():
        dist.all_reduce(packed, op=dist.ReduceOp.SUM)
    return [int(value) for value in packed.tolist()]


def move_to_device(value, device):
    """Recursively move nested tensors/dataclasses onto ``device``."""
    if isinstance(value, torch.Tensor):
        return value.to(device, non_blocking=True)
    if isinstance(value, dict):
        return {key: move_to_device(item, device) for key, item in value.items()}
    if isinstance(value, list):
        return [move_to_device(item, device) for item in value]
    if isinstance(value, tuple):
        return tuple(move_to_device(item, device) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return type(value)(
            **{
                field.name: move_to_device(getattr(value, field.name), device)
                for field in fields(value)
            }
        )
    return value


# ---------------------------------------------------------------------------
# Failure Handling
# ---------------------------------------------------------------------------


def abort_on_out_of_memory(
    exc: BaseException,
    *,
    stage: str,
    batch: dict[str, object] | None,
    progress: TrainProgress,
    device: torch.device,
    process_index: int,
    num_processes: int,
) -> None:
    if not _is_out_of_memory_error(exc):
        return

    message = (
        "Fatal out-of-memory during training. "
        f"stage={stage}, "
        f"epoch={progress.epoch}, "
        f"global_step={progress.global_step}, "
        f"rank={process_index}/{num_processes}. "
        f"{_build_batch_memory_summary(batch)}. "
        f"{_build_cuda_memory_summary(device)}."
    )
    print(message, file=sys.stderr, flush=True)
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
    sys.stderr.flush()

    if num_processes > 1:
        os._exit(1)


def _is_out_of_memory_error(exc: BaseException) -> bool:
    oom_error_type = getattr(torch, "OutOfMemoryError", None)
    if oom_error_type is not None and isinstance(exc, oom_error_type):
        return True
    if not isinstance(exc, RuntimeError):
        return False
    return "out of memory" in str(exc).lower()


def _build_batch_memory_summary(batch: dict[str, object] | None) -> str:
    if not isinstance(batch, dict):
        return "batch=unavailable"

    fields = []
    input_ids = batch.get("input_ids")
    if isinstance(input_ids, torch.Tensor):
        fields.append(f"input_ids_shape={tuple(input_ids.shape)}")
    sample = batch.get("sample")
    if isinstance(sample, torch.Tensor):
        fields.append(f"sample_shape={tuple(sample.shape)}")
    input_ids_lengths = batch.get("input_ids_lengths")
    if isinstance(input_ids_lengths, torch.Tensor) and input_ids_lengths.numel() > 0:
        fields.append(
            f"max_input_ids_length={int(input_ids_lengths.max().detach().item())}"
        )
    num_audio_tokens = batch.get("num_audio_tokens")
    if isinstance(num_audio_tokens, torch.Tensor) and num_audio_tokens.numel() > 0:
        fields.append(f"max_audio_tokens={int(num_audio_tokens.max().detach().item())}")
    num_text_tokens = batch.get("num_text_tokens")
    if isinstance(num_text_tokens, torch.Tensor) and num_text_tokens.numel() > 0:
        fields.append(f"max_text_tokens={int(num_text_tokens.max().detach().item())}")
    return ", ".join(fields) if fields else "batch=unavailable"


def _build_cuda_memory_summary(device: torch.device) -> str:
    if device.type != "cuda" or not torch.cuda.is_available():
        return "device_memory=unavailable"
    allocated = torch.cuda.memory_allocated(device) / (1024**3)
    reserved = torch.cuda.memory_reserved(device) / (1024**3)
    max_allocated = torch.cuda.max_memory_allocated(device) / (1024**3)
    max_reserved = torch.cuda.max_memory_reserved(device) / (1024**3)
    return (
        f"device={device}, "
        f"allocated_gb={allocated:.2f}, "
        f"reserved_gb={reserved:.2f}, "
        f"max_allocated_gb={max_allocated:.2f}, "
        f"max_reserved_gb={max_reserved:.2f}"
    )


# ---------------------------------------------------------------------------
# Debug Helpers
# ---------------------------------------------------------------------------


def build_data_debug_lines(
    batch: dict[str, object],
    *,
    batch_index: int,
    tokenizer: Any,
    sample_rate: int,
) -> list[str]:
    input_ids = batch["input_ids"]
    input_ids_lengths = batch["input_ids_lengths"]
    sample = batch["sample"]
    sample_lengths = batch["sample_lengths"]
    num_audio_tokens = batch["num_audio_tokens"]
    num_text_tokens = batch["num_text_tokens"]

    if not isinstance(input_ids, torch.Tensor) or not isinstance(
        input_ids_lengths, torch.Tensor
    ):
        raise TypeError("Debug batch requires tensor input_ids and input_ids_lengths.")
    if not isinstance(sample, torch.Tensor) or not isinstance(
        sample_lengths, torch.Tensor
    ):
        raise TypeError("Debug batch requires tensor sample and sample_lengths.")
    if not isinstance(num_audio_tokens, torch.Tensor) or not isinstance(
        num_text_tokens, torch.Tensor
    ):
        raise TypeError(
            "Debug batch requires tensor num_audio_tokens and num_text_tokens."
        )

    source_names = batch.get("source_names")
    debug_lines = [
        (
            "[debug:data] "
            f"batch_index={batch_index} "
            f"batch_size={int(input_ids.size(0))} "
            f"input_ids_shape={tuple(input_ids.shape)} "
            f"sample_shape={tuple(sample.shape)} "
            f"sample_rate={sample_rate} "
            f"sources={dict(Counter(source_names or []))}"
        ),
        (
            "[debug:data] "
            f"input_tokens(min/mean/max)={_format_tensor_triplet(input_ids_lengths)} "
            f"text_tokens(min/mean/max)={_format_tensor_triplet(num_text_tokens)} "
            f"audio_tokens(min/mean/max)={_format_tensor_triplet(num_audio_tokens)} "
            f"audio_seconds(min/mean/max)={_format_audio_seconds_triplet(sample_lengths, sample_rate)}"
        ),
    ]

    fbank = batch.get("fbank")
    fbank_lengths = batch.get("fbank_lengths")
    if isinstance(fbank, torch.Tensor):
        debug_lines.append(
            "[debug:data] "
            f"fbank_shape={tuple(fbank.shape)} "
            f"fbank_frames(min/mean/max)={_format_tensor_triplet(fbank_lengths)}"
        )

    loss_masks = batch.get("loss_masks")
    if isinstance(loss_masks, dict):
        debug_lines.append(
            "[debug:data] "
            "loss_masks="
            + ", ".join(
                f"{name}:{_format_mask_density(mask)}"
                for name, mask in sorted(loss_masks.items())
            )
        )

    fids = batch.get("fids") or []
    sample_count = min(int(input_ids.size(0)), 3)
    for sample_idx in range(sample_count):
        input_length = int(input_ids_lengths[sample_idx].item())
        audio_length = int(sample_lengths[sample_idx].item())
        fbank_shape = "unavailable"
        if isinstance(fbank, torch.Tensor) and isinstance(fbank_lengths, torch.Tensor):
            fbank_shape = (
                f"({int(fbank_lengths[sample_idx].item())}, {int(fbank.size(-1))})"
            )
        debug_lines.append(
            "[debug:data] "
            f"sample_index={sample_idx} "
            f"fid={str(fids[sample_idx]) if sample_idx < len(fids) else f'sample_{sample_idx:02d}'} "
            f"source_name={source_names[sample_idx] if source_names else None} "
            f"input_ids_shape=({input_length},) "
            f"sample_shape=(1, {audio_length}) "
            f"fbank_shape={fbank_shape} "
            f"num_text_tokens={int(num_text_tokens[sample_idx].item())} "
            f"num_audio_tokens={int(num_audio_tokens[sample_idx].item())} "
            f"audio_seconds={audio_length / float(sample_rate):.2f} "
            "text="
            f"{tokenizer.decode(input_ids[sample_idx, :input_length].detach().cpu().tolist(), skip_special_tokens=False, clean_up_tokenization_spaces=False)!r}"
        )
    return debug_lines


def should_print_gradient_debug(
    *,
    debug_enabled: bool,
    is_main_process: bool,
    next_global_step: int,
    log_interval: int,
    early_step_limit: int,
) -> bool:
    return bool(
        debug_enabled
        and is_main_process
        and (
            next_global_step <= early_step_limit
            or next_global_step % log_interval == 0
        )
    )


def build_gradient_debug_lines(
    model: torch.nn.Module,
    *,
    global_step: int,
    grad_norm: float,
    grad_clip_norm: float,
) -> list[str]:
    top_param_candidates: list[tuple[str, float, float, float]] = []
    nonfinite_grad_params: list[str] = []
    nonfinite_param_count = 0
    params_with_grad = 0
    params_without_grad = 0
    abs_sum = 0.0
    abs_count = 0
    max_abs_grad = 0.0

    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        grad = parameter.grad
        if grad is None:
            params_without_grad += 1
            continue

        grad_tensor = grad.detach().float()
        params_with_grad += 1
        if not bool(torch.isfinite(grad_tensor).all().item()):
            nonfinite_param_count += 1
            if len(nonfinite_grad_params) < 8:
                nonfinite_grad_params.append(name)
        grad_abs = grad_tensor.abs()
        param_norm = float(torch.linalg.vector_norm(grad_tensor).item())
        param_max_abs = float(grad_abs.max().item())
        param_mean_abs = float(grad_abs.mean().item())
        max_abs_grad = max(max_abs_grad, param_max_abs)
        abs_sum += float(grad_abs.sum().item())
        abs_count += int(grad_abs.numel())
        top_param_candidates.append((name, param_norm, param_max_abs, param_mean_abs))

    mean_abs_grad = math.nan if abs_count == 0 else abs_sum / float(abs_count)
    top_param_norms = sorted(
        top_param_candidates,
        key=lambda item: item[1],
        reverse=True,
    )[:6]

    debug_lines = [
        (
            "[debug:grad] "
            f"step={global_step} "
            f"pre_clip_grad_norm={format_scalar(grad_norm)} "
            f"clip_ratio={format_scalar(_safe_grad_clip_ratio(grad_norm, grad_clip_norm))} "
            f"params_with_grad={params_with_grad} "
            f"params_without_grad={params_without_grad} "
            f"nonfinite_param_count={nonfinite_param_count} "
            f"max_abs_grad={format_scalar(max_abs_grad)} "
            f"mean_abs_grad={format_scalar(mean_abs_grad)}"
        )
    ]
    if top_param_norms:
        debug_lines.append(
            "[debug:grad] top_params="
            + ", ".join(
                (
                    f"{name}:{param_norm:.4f}"
                    f"(max={param_max_abs:.4e},mean={param_mean_abs:.4e})"
                )
                for name, param_norm, param_max_abs, param_mean_abs in top_param_norms
            )
        )
    if nonfinite_grad_params:
        debug_lines.append(
            "[debug:grad] nonfinite_params=" + ", ".join(nonfinite_grad_params)
        )
    return debug_lines


def _format_tensor_triplet(values: object) -> str:
    if not isinstance(values, torch.Tensor) or values.numel() == 0:
        return "n/a"
    flattened = values.detach().cpu().to(torch.float32)
    return (
        f"{int(flattened.min().item())}/"
        f"{flattened.mean().item():.2f}/"
        f"{int(flattened.max().item())}"
    )


def _format_audio_seconds_triplet(values: object, sample_rate: int) -> str:
    if not isinstance(values, torch.Tensor) or values.numel() == 0:
        return "n/a"
    seconds = values.detach().cpu().to(torch.float32) / float(sample_rate)
    return (
        f"{seconds.min().item():.2f}/"
        f"{seconds.mean().item():.2f}/"
        f"{seconds.max().item():.2f}"
    )


def _format_mask_density(mask: object) -> str:
    if not isinstance(mask, torch.Tensor) or mask.numel() == 0:
        return "n/a"
    return f"{int(mask.detach().gt(0).sum().item())}/{int(mask.numel())}"


def _safe_grad_clip_ratio(grad_norm: float, grad_clip_norm: float) -> float:
    if not math.isfinite(grad_norm):
        return math.nan
    return grad_norm / float(grad_clip_norm)


# ---------------------------------------------------------------------------
# Step Reporting
# ---------------------------------------------------------------------------


def should_log_training_step(global_step: int, log_interval: int) -> bool:
    return global_step % log_interval == 0


def reduce_source_metrics(
    source_loss_totals: dict[str, dict[str, float]],
    source_loss_denominators: dict[str, dict[str, float]],
    *,
    device: torch.device,
    loss_config: Any,
) -> dict[str, dict[str, float]]:
    reduced_source_totals = loss_ops.sum_grouped_named_scalars_across_ranks(
        source_loss_totals,
        device=device,
    )
    reduced_source_denominators = loss_ops.sum_grouped_named_scalars_across_ranks(
        source_loss_denominators,
        device=device,
    )
    return loss_ops.reduce_loss_statistics_by_source(
        reduced_source_totals,
        reduced_source_denominators,
        loss_config=loss_config,
    )


def build_train_step_report(
    metrics: dict[str, Any],
    *,
    learning_rate: float,
    grad_norm: float,
    current_time: float,
    last_log_step: int,
    last_log_time: float,
    progress: TrainProgress,
    max_train_steps: int,
    reduced_by_source: dict[str, dict[str, float]],
) -> TrainStepReport:
    logged_steps = progress.global_step - last_log_step
    elapsed = current_time - last_log_time
    steps_per_second = (
        math.nan
        if logged_steps <= 0 or elapsed <= 0.0
        else float(logged_steps) / elapsed
    )
    eta_seconds = (
        math.nan
        if not math.isfinite(steps_per_second) or steps_per_second <= 0.0
        else float(max_train_steps - progress.global_step) / steps_per_second
    )
    return TrainStepReport(
        log_values=build_train_log_dict(
            metrics,
            learning_rate=learning_rate,
            grad_norm=grad_norm,
            steps_per_second=steps_per_second,
            eta_seconds=eta_seconds,
            progress=progress,
            reduced_by_source=reduced_by_source,
        ),
        console_line=format_train_line(
            metrics,
            learning_rate=learning_rate,
            grad_norm=grad_norm,
            steps_per_second=steps_per_second,
            eta_seconds=eta_seconds,
            progress=progress,
            max_train_steps=max_train_steps,
            reduced_by_source=reduced_by_source,
        ),
    )


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------


def flatten_config(values, parent_key="", sep="/"):
    """Flatten a nested config dict into ``path/to/key -> value`` pairs."""
    items = []
    for key, value in values.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_config(value, new_key, sep).items())
        elif isinstance(value, (list, tuple)):
            items.append((new_key, str(value)))
        elif value is None:
            items.append((new_key, "None"))
        else:
            items.append((new_key, value))
    return dict(items)


def format_scalar(value: float) -> str:
    """Format a scalar for concise console logging."""
    if not math.isfinite(value):
        return "nan"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}"


def _format_eta(eta_seconds: float) -> str:
    """Render ETA seconds as ``HH:MM:SS`` or ``n/a``."""
    if not math.isfinite(eta_seconds) or eta_seconds < 0.0:
        return "n/a"
    total_seconds = int(round(eta_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_train_log_dict(
    metrics: dict[str, Any],
    *,
    learning_rate: float,
    grad_norm: float,
    steps_per_second: float,
    eta_seconds: float,
    progress: TrainProgress,
    reduced_by_source: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Build the flat metric dict sent to experiment trackers."""
    log_dict = {
        "train/epoch": float(progress.epoch),
        "train/learning_rate": learning_rate,
        "train/grad_norm": grad_norm,
        "train/steps_per_second": steps_per_second,
        "train/eta_seconds": eta_seconds,
        "train/consumed_tokens": float(progress.total_tokens),
        "train/consumed_audio_tokens": float(progress.audio_tokens),
        "train/consumed_text_tokens": float(progress.text_tokens),
    }
    for name, value in metrics.items():
        log_dict[f"train/{name}"] = float(value)
    for source_name, source_metrics in reduced_by_source.items():
        log_dict.update(
            {
                f"train/{source_name}/{name}": float(value)
                for name, value in source_metrics.items()
            }
        )
    return log_dict


def format_train_line(
    metrics: dict[str, Any],
    *,
    learning_rate: float,
    grad_norm: float,
    steps_per_second: float,
    eta_seconds: float,
    progress: TrainProgress,
    max_train_steps: int,
    reduced_by_source: dict[str, dict[str, Any]],
) -> str:
    """Build a single human-readable console line for one training step."""
    parts = [
        f"iteration {progress.global_step}/{max_train_steps}",
        f"epoch: {progress.epoch}",
        f"consumed_tokens: {progress.total_tokens}",
        f"consumed_audio_tokens: {progress.audio_tokens}",
        f"consumed_text_tokens: {progress.text_tokens}",
        f"learning_rate: {learning_rate:.2e}",
        f"steps_per_second: {format_scalar(steps_per_second)}",
        f"job_eta: {_format_eta(eta_seconds)}",
        f"grad_norm: {format_scalar(grad_norm)}",
    ]
    for name in sorted(name for name in metrics if name != "loss"):
        parts.append(f"{name}: {format_scalar(float(metrics[name]))}")
    if "loss" in metrics:
        parts.append(f"loss: {format_scalar(float(metrics['loss']))}")
    for source_name, source_metrics in reduced_by_source.items():
        for name in sorted(name for name in source_metrics if name != "loss"):
            parts.append(
                f"{source_name}_{name}: {format_scalar(float(source_metrics[name]))}"
            )
        if "loss" in source_metrics:
            parts.append(
                f"{source_name}_loss: {format_scalar(float(source_metrics['loss']))}"
            )
    return " | ".join(parts)


def build_validation_log_dict(
    metrics: dict[str, Any],
    *,
    reduced_by_source: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Build the flat validation metric dict sent to experiment trackers."""
    log_dict = {f"val/{name}": float(value) for name, value in metrics.items()}
    for source_name, source_metrics in reduced_by_source.items():
        log_dict.update(
            {
                f"val/{source_name}/{name}": float(value)
                for name, value in source_metrics.items()
            }
        )
    return log_dict


def format_validation_line(
    metrics: dict[str, Any],
    *,
    global_step: int,
    reduced_by_source: dict[str, dict[str, Any]],
) -> str:
    """Build the console summary line printed after a validation pass."""
    parts = [f"validation at iteration {global_step}"]
    for name in sorted(name for name in metrics if name != "loss"):
        parts.append(f"{name}: {format_scalar(float(metrics[name]))}")
    if "loss" in metrics:
        parts.append(f"loss: {format_scalar(float(metrics['loss']))}")
    for source_name, source_metrics in reduced_by_source.items():
        for name in sorted(name for name in source_metrics if name != "loss"):
            parts.append(
                f"{source_name}_{name}: {format_scalar(float(source_metrics[name]))}"
            )
        if "loss" in source_metrics:
            parts.append(
                f"{source_name}_loss: {format_scalar(float(source_metrics['loss']))}"
            )
    return " | ".join(parts)


__all__ = [
    "TrainProgress",
    "TrainStepReport",
    "abort_on_out_of_memory",
    "any_rank_true",
    "build_data_debug_lines",
    "build_gradient_debug_lines",
    "build_train_step_report",
    "build_train_log_dict",
    "build_validation_log_dict",
    "flatten_config",
    "format_scalar",
    "format_train_line",
    "format_validation_line",
    "move_to_device",
    "reduce_source_metrics",
    "should_log_training_step",
    "should_print_gradient_debug",
    "sum_integer_counters_across_ranks",
]
