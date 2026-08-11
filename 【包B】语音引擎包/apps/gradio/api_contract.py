from __future__ import annotations

from typing import Any, Mapping


API_VERSION = "dots-tts.synthesize.v1"
API_NAME = "/synthesize_v1"
REQUEST_PARAMETER = "request"

REQUEST_DEFAULTS: dict[str, Any] = {
    "prompt_audio_path": None,
    "prompt_text": "",
    "num_steps": 10,
    "guidance_scale": 1.2,
    "normalize_text": False,
    "seed": 42,
    "speed": 1.0,
    "max_pause": 0.3,
}
REQUEST_FIELDS = ("text", *REQUEST_DEFAULTS)


class ContractError(ValueError):
    """可稳定返回给本机客户端的契约校验错误。"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _number(value: Any, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("invalid_type", f"{name} 必须是数字")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ContractError("out_of_range", f"{name} 必须在 {minimum}..{maximum} 之间")
    return result


def normalize_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractError("invalid_request", "request 必须是 JSON 对象")
    unknown = sorted(set(payload) - set(REQUEST_FIELDS))
    if unknown:
        raise ContractError("unknown_field", f"未知字段：{', '.join(unknown)}")

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ContractError("invalid_text", "text 必须是非空字符串")

    result = dict(REQUEST_DEFAULTS)
    result.update(payload)
    result["text"] = text.strip()

    prompt_audio = result["prompt_audio_path"]
    if prompt_audio is not None and not isinstance(prompt_audio, str):
        raise ContractError("invalid_type", "prompt_audio_path 必须是字符串或 null")
    if isinstance(prompt_audio, str):
        result["prompt_audio_path"] = prompt_audio.strip() or None
    if not isinstance(result["prompt_text"], str):
        raise ContractError("invalid_type", "prompt_text 必须是字符串")
    if result["prompt_audio_path"] and not result["prompt_text"].strip():
        raise ContractError("missing_prompt_text", "使用参考音频时必须提供 prompt_text")

    steps = _number(result["num_steps"], "num_steps", minimum=1, maximum=32)
    if not steps.is_integer():
        raise ContractError("invalid_type", "num_steps 必须是整数")
    result["num_steps"] = int(steps)
    result["guidance_scale"] = _number(
        result["guidance_scale"], "guidance_scale", minimum=1.0, maximum=3.0
    )
    result["speed"] = _number(result["speed"], "speed", minimum=0.5, maximum=2.0)
    result["max_pause"] = _number(
        result["max_pause"], "max_pause", minimum=0.0, maximum=1.5
    )
    seed = result["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ContractError("invalid_type", "seed 必须是整数")
    if not isinstance(result["normalize_text"], bool):
        raise ContractError("invalid_type", "normalize_text 必须是布尔值")
    return result


def success_response(result: Any, metadata: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(result.metrics)
    return {
        "ok": True,
        "api_version": API_VERSION,
        "status": result.status,
        "model": {
            "configured": metadata.get("default_model_name_or_path"),
            "loaded": metadata.get("loaded_model_name_or_path"),
            "resolved": metrics.get("resolved_model_name_or_path"),
        },
        "device": {
            "configured": metadata.get("configured_device"),
            "loaded": metadata.get("loaded_device"),
            "policy": metrics.get("device_policy"),
        },
        "precision": {
            "configured": metadata.get("configured_precision"),
            "loaded": metadata.get("loaded_precision"),
        },
        "metrics": metrics,
    }


def error_response(exc: Exception) -> dict[str, Any]:
    code = exc.code if isinstance(exc, ContractError) else "synthesis_failed"
    return {
        "ok": False,
        "api_version": API_VERSION,
        "error": {"code": code, "message": str(exc)},
    }
