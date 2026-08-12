from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

for import_root in (REPO_ROOT, SRC_ROOT):
    import_root_str = str(import_root)
    if import_root_str not in sys.path:
        sys.path.insert(0, import_root_str)

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from loguru import logger  # noqa: E402


_CHINESE_CHARACTER_RE = re.compile(r"[\u3400-\u9fff]")


def _require_chinese_prompt_transcript(
    audio_path: str | None, prompt_text: str | None
) -> None:
    """Reject placeholder filenames in the Chinese reference-audio workflow."""
    if not audio_path:
        return
    transcript = (prompt_text or "").strip()
    if not transcript:
        raise ValueError("已选择参考音频，请填写其实际朗读的中文转写。")
    if not _CHINESE_CHARACTER_RE.search(transcript):
        raise ValueError("参考音频转写必须包含与音频内容一致的中文，不能使用文件名或临时标识。")

from apps.gradio.constants import (  # noqa: E402
    DEFAULT_EXECUTION_MODE,
    DEFAULT_GUIDANCE_SCALE,
    DEFAULT_HOST,
    DEFAULT_MAX_GENERATE_LENGTH,
    DEFAULT_NUM_STEPS,
    DEFAULT_ODE_METHOD,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_RETENTION,
    DEFAULT_PORT,
    DEFAULT_PRECISION,
    DEFAULT_PROMPT_MAPPING_FILE,
    DEFAULT_PROMPT_NAME,
    DEFAULT_PROMPT_NONE,
    DEFAULT_PROMPT_SOURCE_DIR,
    DEFAULT_PROMPTS_DIR,
    DEFAULT_SEED,
    DEFAULT_SPEAKER_SCALE,
    DEFAULT_WARMUP_TEXT,
    PROMPT_AUDIO_SUFFIXES,
)
from apps.gradio.languages import (  # noqa: E402
    SUPPORTED_LANGUAGE_CODE_BY_NAME,
    build_language_choice_items,
)
from dots_tts.external_tools import resolve_external_tool  # noqa: E402
from dots_tts.runtime import DotsTtsRuntime  # noqa: E402
from dots_tts.utils.util import seed_everything  # noqa: E402

ExecutionMode = Literal["generate", "generate_stream"]
GRADIO_SYNTHESIS_MODE_CHOICES = (
    ("tts", "tts"),
    ("instruct_tts", "instruction_tts"),
    ("instruct_tts_general", "text_to_audio"),
)
GRADIO_SYNTHESIS_MODE_TEMPLATE_NAMES = tuple(
    value for _, value in GRADIO_SYNTHESIS_MODE_CHOICES
)
DEFAULT_MAX_CHARS_PER_CHUNK = 120
MPS_MAX_CHARS_PER_CHUNK = 32


def chunk_chars_for_device(device_type: str) -> int:
    return (
        MPS_MAX_CHARS_PER_CHUNK
        if str(device_type).lower() == "mps"
        else DEFAULT_MAX_CHARS_PER_CHUNK
    )


@dataclass(frozen=True)
class PromptPreset:
    name: str
    audio_path: str
    prompt_text: str


def _is_prompt_asset(path: Path) -> bool:
    return path.is_file() and (
        path.name == "prompt_text" or path.suffix.lower() in PROMPT_AUDIO_SUFFIXES
    )


def sync_default_prompt_library(
    source_dir: Path = DEFAULT_PROMPT_SOURCE_DIR,
    target_dir: Path = DEFAULT_PROMPTS_DIR,
) -> None:
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        logger.info(
            "Prompt library sync skipped: source_dir={} does not exist.",
            source_dir,
        )
        return

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Prompt library sync started: source_dir={} target_dir={}",
        source_dir,
        target_dir,
    )

    source_assets = {
        asset.name: asset for asset in sorted(source_dir.iterdir()) if _is_prompt_asset(asset)
    }
    copied_count = 0
    for asset_name, source_asset in source_assets.items():
        target_asset = target_dir / asset_name
        if (
            not target_asset.exists()
            or target_asset.stat().st_size != source_asset.stat().st_size
            or target_asset.stat().st_mtime_ns != source_asset.stat().st_mtime_ns
        ):
            shutil.copy2(source_asset, target_asset)
            copied_count += 1

    removed_count = 0
    for target_asset in sorted(target_dir.iterdir()):
        if _is_prompt_asset(target_asset) and target_asset.name not in source_assets:
            target_asset.unlink(missing_ok=True)
            removed_count += 1
    logger.info(
        "Prompt library sync completed: copied_assets={} removed_assets={} "
        "available_assets={}",
        copied_count,
        removed_count,
        len(source_assets),
    )


def _load_prompt_text_map(mapping_file: Path) -> dict[str, str]:
    if not mapping_file.is_file():
        return {}

    prompt_text_map: dict[str, str] = {}
    with mapping_file.open(encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = raw_line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            name, text = line.split("|", 1)
            prompt_text_map[name.strip()] = text.strip()
    return prompt_text_map


def discover_prompt_presets(
    prompts_dir: Path = DEFAULT_PROMPTS_DIR,
    mapping_file: Path = DEFAULT_PROMPT_MAPPING_FILE,
) -> tuple[PromptPreset, ...]:
    prompts_dir = Path(prompts_dir)
    if not prompts_dir.is_dir():
        return ()

    prompt_text_map = _load_prompt_text_map(Path(mapping_file))
    prompt_audio_paths = [
        audio_path
        for audio_path in sorted(prompts_dir.iterdir(), key=lambda path: (path.stem == "child", path.stem))
        if audio_path.is_file() and audio_path.suffix.lower() in PROMPT_AUDIO_SUFFIXES
    ]
    return tuple(
        PromptPreset(
            name=audio_path.stem,
            audio_path=str(audio_path.resolve()),
            prompt_text=prompt_text_map.get(audio_path.stem, ""),
        )
        for audio_path in prompt_audio_paths
    )


def build_prompt_choice_items(
    prompt_presets: tuple[PromptPreset, ...],
) -> list[tuple[str, str]]:
    return [("No Preset", DEFAULT_PROMPT_NONE), *[(preset.name, preset.name) for preset in prompt_presets]]


def resolve_default_prompt_selection(
    prompt_presets: tuple[PromptPreset, ...],
    default_prompt_name: str = DEFAULT_PROMPT_NAME,
) -> tuple[str, str | None, str]:
    if not prompt_presets:
        return DEFAULT_PROMPT_NONE, None, ""

    preset_by_name = {preset.name: preset for preset in prompt_presets}
    selected_name = default_prompt_name if default_prompt_name in preset_by_name else prompt_presets[0].name
    selected_preset = preset_by_name[selected_name]
    return selected_name, selected_preset.audio_path, selected_preset.prompt_text


def resolve_prompt_selection(
    prompt_name: str,
    prompt_presets: tuple[PromptPreset, ...],
) -> tuple[str | None, str]:
    if prompt_name == DEFAULT_PROMPT_NONE:
        return None, ""

    for preset in prompt_presets:
        if preset.name == prompt_name:
            return preset.audio_path, preset.prompt_text
    return None, ""


def discover_local_model_choices(repo_root: Path = REPO_ROOT) -> list[str]:
    model_root = Path(repo_root) / "pretrained_models"
    if not model_root.is_dir():
        return []
    choices: list[str] = []
    # 模式1：训练保存的检查点（含 model/ 子目录）
    for path in model_root.glob("**/model"):
        if path.is_dir():
            choices.append(path.relative_to(repo_root).as_posix())
    # 模式2：HF 直接下载的平铺检查点（目录内有 config.json）
    for path in model_root.iterdir():
        if path.is_dir() and (path / "config.json").is_file():
            rel = path.relative_to(repo_root).as_posix()
            if rel not in choices:
                choices.append(rel)
    return sorted(choices)


def resolve_model_name_or_path(model_name_or_path: str, repo_root: Path = REPO_ROOT) -> str:
    normalized = model_name_or_path.strip()
    if not normalized:
        raise ValueError("model_name_or_path 不能为空。")

    direct_path = Path(normalized).expanduser()
    if direct_path.exists():
        return str(direct_path.resolve())

    repo_relative_path = Path(repo_root) / normalized
    if repo_relative_path.exists():
        return str(repo_relative_path.resolve())

    return normalized


def recommended_num_steps_for_model(
    model_name_or_path: str,
    repo_root: Path = REPO_ROOT,
) -> int:
    """MeanFlow 蒸馏模型推荐 4 步；其余 flow-matching 模型用默认 10 步。

    通过读取模型目录下 config.json 的 meanflow.enabled 判断，避免依赖文件夹名。
    """
    try:
        resolved = resolve_model_name_or_path(model_name_or_path, repo_root=repo_root)
        config_data = json.loads(
            (Path(resolved) / "config.json").read_text(encoding="utf-8")
        )
        meanflow = config_data.get("meanflow")
        if isinstance(meanflow, dict) and meanflow.get("enabled"):
            return 4
    except Exception:  # noqa: BLE001 - 配置缺失/损坏时回退默认步数
        pass
    return DEFAULT_NUM_STEPS


def default_model_name_or_path(repo_root: Path = REPO_ROOT) -> str:
    discovered = discover_local_model_choices(repo_root=repo_root)
    if not discovered:
        return ""
    return discovered[0]


@dataclass(frozen=True)
class GradioAppConfig:
    host: str
    port: int
    execution_mode: ExecutionMode
    device: str
    precision: str
    optimize: bool
    output_dir: Path
    prompts_dir: Path
    output_retention_count: int
    max_generate_length: int
    default_model_name_or_path: str
    prompt_presets: tuple[PromptPreset, ...]
    default_prompt_name: str
    default_prompt_audio_path: str | None
    default_prompt_text: str
    default_precision: str
    default_num_steps: int
    default_guidance_scale: float
    default_speaker_scale: float
    default_max_generate_length: int
    local_model_choices: tuple[str, ...]
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    rubberband_path: str | None = None
    repo_root: Path = REPO_ROOT


def build_gradio_app_config(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    execution_mode: ExecutionMode = DEFAULT_EXECUTION_MODE,
    device: str = "auto",
    precision: str = DEFAULT_PRECISION,
    optimize: bool = False,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    output_retention_count: int = DEFAULT_OUTPUT_RETENTION,
    max_generate_length: int = DEFAULT_MAX_GENERATE_LENGTH,
    model_name_or_path: str | None = None,
    default_prompt_name: str = DEFAULT_PROMPT_NAME,
    default_precision: str = DEFAULT_PRECISION,
    default_num_steps: int = DEFAULT_NUM_STEPS,
    default_guidance_scale: float = DEFAULT_GUIDANCE_SCALE,
    default_speaker_scale: float = DEFAULT_SPEAKER_SCALE,
    default_max_generate_length: int = DEFAULT_MAX_GENERATE_LENGTH,
    repo_root: Path = REPO_ROOT,
    prompts_dir: Path = DEFAULT_PROMPTS_DIR,
    prompt_source_dir: Path = DEFAULT_PROMPT_SOURCE_DIR,
    ffmpeg_path: str | None = None,
    ffprobe_path: str | None = None,
    rubberband_path: str | None = None,
) -> GradioAppConfig:
    sync_default_prompt_library(
        source_dir=prompt_source_dir,
        target_dir=prompts_dir,
    )
    discovered_models = discover_local_model_choices(repo_root=repo_root)
    prompt_presets = discover_prompt_presets(
        prompts_dir=prompts_dir,
        mapping_file=prompts_dir / "prompt_text",
    )
    resolved_default_prompt_name, default_prompt_audio_path, default_prompt_text = (
        resolve_default_prompt_selection(
            prompt_presets,
            default_prompt_name=default_prompt_name,
        )
    )
    selected_model_name_or_path = (
        model_name_or_path.strip()
        if model_name_or_path is not None
        else default_model_name_or_path(repo_root=repo_root)
    )
    if not selected_model_name_or_path:
        raise ValueError("No default model found. Please pass --model-name-or-path.")
    if execution_mode not in ("generate", "generate_stream"):
        raise ValueError(f"Unsupported execution_mode: {execution_mode}")
    resolved_max_generate_length = int(max_generate_length)
    if resolved_max_generate_length <= 0:
        raise ValueError("max_generate_length must be positive.")
    resolved_precision = precision.strip() or DEFAULT_PRECISION
    logger.info(
        "Gradio app config prepared: host={} port={} output_dir={} "
        "output_retention_count={} max_generate_length={} execution_mode={} device={} precision={} optimize={} "
        "default_model_name_or_path={} prompt_preset_count={} language_count={} local_model_choice_count={}",
        host,
        port,
        output_dir,
        output_retention_count,
        resolved_max_generate_length,
        execution_mode,
        device,
        resolved_precision,
        bool(optimize),
        selected_model_name_or_path,
        len(prompt_presets),
        len(SUPPORTED_LANGUAGE_CODE_BY_NAME),
        len(discovered_models),
    )
    return GradioAppConfig(
        host=host,
        port=int(port),
        execution_mode=execution_mode,
        device=device,
        precision=resolved_precision,
        optimize=bool(optimize),
        output_dir=Path(output_dir),
        prompts_dir=Path(prompts_dir),
        output_retention_count=int(output_retention_count),
        max_generate_length=resolved_max_generate_length,
        default_model_name_or_path=selected_model_name_or_path,
        prompt_presets=prompt_presets,
        default_prompt_name=resolved_default_prompt_name,
        default_prompt_audio_path=default_prompt_audio_path,
        default_prompt_text=default_prompt_text,
        default_precision=default_precision,
        default_num_steps=int(default_num_steps),
        default_guidance_scale=float(default_guidance_scale),
        default_speaker_scale=float(default_speaker_scale),
        default_max_generate_length=int(default_max_generate_length),
        local_model_choices=tuple(discovered_models),
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        rubberband_path=rubberband_path,
        repo_root=repo_root,
    )


@dataclass(frozen=True)
class SynthesisRequest:
    model_name_or_path: str
    text: str
    prompt_audio_path: str | None = None
    prompt_text: str | None = None
    execution_mode: ExecutionMode = DEFAULT_EXECUTION_MODE
    template_name: str = "tts"
    language: str | None = None
    ode_method: str = DEFAULT_ODE_METHOD
    num_steps: int = DEFAULT_NUM_STEPS
    guidance_scale: float = DEFAULT_GUIDANCE_SCALE
    speaker_scale: float = DEFAULT_SPEAKER_SCALE
    normalize_text: bool = False
    seed: int = DEFAULT_SEED
    speed: float = 1.0
    max_pause: float = 0.0  # 标点处最长停顿(秒)，0=不压缩


@dataclass(frozen=True)
class SynthesisResult:
    audio_path: str
    metrics: dict[str, Any]
    status: str


class GradioAppService:
    def __init__(self, config: GradioAppConfig):
        self.config = config
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._runtime: DotsTtsRuntime | None = None
        self._runtime_model_name_or_path: str | None = None
        logger.info(
            "Gradio service initialized: output_dir={} default_model_name_or_path={} "
            "output_retention_count={} max_generate_length={} execution_mode={} device={} precision={} optimize={}",
            self.config.output_dir,
            self.config.default_model_name_or_path,
            self.config.output_retention_count,
            self.config.max_generate_length,
            self.config.execution_mode,
            self.config.device,
            self.config.precision,
            self.config.optimize,
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "repo_root": str(self.config.repo_root),
            "default_model_name_or_path": self.config.default_model_name_or_path,
            "local_model_choices": list(self.config.local_model_choices),
            "prompts_dir": str(self.config.prompts_dir),
            "prompt_preset_names": [preset.name for preset in self.config.prompt_presets],
            "default_prompt_name": self.config.default_prompt_name,
            "output_dir": str(self.config.output_dir),
            "output_retention_count": self.config.output_retention_count,
            "configured_max_generate_length": self.config.max_generate_length,
            "configured_execution_mode": self.config.execution_mode,
            "configured_device": self.config.device,
            "configured_precision": self.config.precision,
            "optimize": self.config.optimize,
            "loaded_model_name_or_path": self._runtime_model_name_or_path,
            "loaded_max_generate_length": (
                self.config.max_generate_length if self._runtime is not None else None
            ),
            "loaded_device": self._runtime.device.type if self._runtime is not None else None,
            "loaded_precision": self._runtime.precision if self._runtime is not None else None,
            "loaded_device_policy": (
                self._runtime.device_policy.as_dict() if self._runtime is not None else None
            ),
            "model_loaded": self._runtime is not None,
            "host": self.config.host,
            "port": self.config.port,
            "default_precision": self.config.default_precision,
            "default_num_steps": self.config.default_num_steps,
            "default_guidance_scale": self.config.default_guidance_scale,
            "default_speaker_scale": self.config.default_speaker_scale,
            "default_max_generate_length": self.config.default_max_generate_length,
            "supported_languages": build_language_choice_items()[1:],
            "supported_template_names": list(GRADIO_SYNTHESIS_MODE_TEMPLATE_NAMES),
        }

    def _get_runtime(
        self,
        model_name_or_path: str,
    ) -> tuple[DotsTtsRuntime, str]:
        resolved_model_name_or_path = resolve_model_name_or_path(
            model_name_or_path,
            repo_root=self.config.repo_root,
        )
        if (
            self._runtime is None
            or self._runtime_model_name_or_path != resolved_model_name_or_path
        ):
            logger.info(
                "Gradio runtime cache miss: requested_model={} resolved_model={} "
                "max_generate_length={} execution_mode={} device={} precision={} optimize={}",
                model_name_or_path,
                resolved_model_name_or_path,
                self.config.max_generate_length,
                self.config.execution_mode,
                self.config.device,
                self.config.precision,
                self.config.optimize,
            )
            self._runtime = DotsTtsRuntime.from_pretrained(
                resolved_model_name_or_path,
                device=self.config.device,
                precision=self.config.precision,
                optimize=self.config.optimize,
                max_generate_length=self.config.max_generate_length,
            )
            self._runtime_model_name_or_path = resolved_model_name_or_path
        else:
            logger.info(
                "Gradio runtime cache hit: requested_model={} resolved_model={} "
                "max_generate_length={} execution_mode={} device={} precision={} optimize={}",
                model_name_or_path,
                resolved_model_name_or_path,
                self.config.max_generate_length,
                self.config.execution_mode,
                self.config.device,
                self.config.precision,
                self.config.optimize,
            )
        return self._runtime, resolved_model_name_or_path

    def _build_stream_request_id(
        self,
        runtime: DotsTtsRuntime,
        request: SynthesisRequest,
    ) -> str:
        normalized_text, normalized_language = runtime._process_text(  # noqa: SLF001
            request.text,
            language=request.language,
            normalize=request.normalize_text,
        )
        normalized_prompt_text = runtime._process_prompt_text(  # noqa: SLF001
            request.prompt_text,
            language=normalized_language,
        )
        if normalized_language is not None and not normalized_prompt_text:
            from dots_tts.utils.text import attach_language_tag  # noqa: PLC0415

            normalized_text = attach_language_tag(
                normalized_text,
                normalized_language,
            )
        request_id_kwargs = {
            "text": normalized_text,
            "prompt_audio_path": request.prompt_audio_path,
            "prompt_text": normalized_prompt_text,
            "template_name": request.template_name,
        }
        if normalized_language is not None:
            request_id_kwargs["language"] = normalized_language
        return runtime._build_request_id(  # noqa: SLF001
            **request_id_kwargs,
        )

    @staticmethod
    def _build_runtime_generate_kwargs(request: SynthesisRequest) -> dict[str, Any]:
        runtime_kwargs: dict[str, Any] = {
            "text": request.text,
            "prompt_audio_path": request.prompt_audio_path,
            "prompt_text": request.prompt_text,
            "template_name": request.template_name,
            "ode_method": request.ode_method,
            "num_steps": request.num_steps,
            "guidance_scale": request.guidance_scale,
            "speaker_scale": request.speaker_scale,
            "normalize_text": request.normalize_text,
        }
        if request.language is not None:
            runtime_kwargs["language"] = request.language
        return runtime_kwargs

    def _run_stream_generation(
        self,
        runtime: DotsTtsRuntime,
        request: SynthesisRequest,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        start_time = time.time()
        chunks = [
            chunk.detach().float().cpu()
            for chunk in runtime.generate_stream(
                **self._build_runtime_generate_kwargs(request),
                progress_cb=progress_cb,
            )
        ]
        if not chunks:
            raise ValueError("流式生成未返回任何音频块。")

        audio = torch.cat(chunks, dim=-1)
        elapsed_seconds = time.time() - start_time
        audio_seconds = audio.shape[-1] / runtime.sample_rate
        rtf = elapsed_seconds / audio_seconds if audio_seconds > 0 else float("inf")
        return {
            "fid": self._build_stream_request_id(runtime, request),
            "audio": audio,
            "sample_rate": runtime.sample_rate,
            "time_used": elapsed_seconds,
            "rtf": rtf,
            "chunk_count": len(chunks),
        }

    def warmup(self, text: str | None = None) -> dict[str, Any]:
        warmup_text = (text or "").strip() or DEFAULT_WARMUP_TEXT.strip()
        if not warmup_text:
            raise ValueError("DEFAULT_WARMUP_TEXT 不能为空。")

        with self._lock:
            logger.info(
                "Gradio warmup requested: default_model_name_or_path={} execution_mode={} precision={} optimize={} seed={}",
                self.config.default_model_name_or_path,
                self.config.execution_mode,
                self.config.precision,
                self.config.optimize,
                DEFAULT_SEED,
            )
            try:
                seed_everything(DEFAULT_SEED)
                runtime, resolved_model_name_or_path = self._get_runtime(
                    self.config.default_model_name_or_path,
                )
                warmup_request = SynthesisRequest(
                    model_name_or_path=self.config.default_model_name_or_path,
                    text=warmup_text,
                    execution_mode=self.config.execution_mode,
                    template_name="tts",
                    ode_method=DEFAULT_ODE_METHOD,
                    num_steps=self.config.default_num_steps,
                    guidance_scale=self.config.default_guidance_scale,
                    speaker_scale=self.config.default_speaker_scale,
                    normalize_text=False,
                    seed=DEFAULT_SEED,
                )
                request_id = self._build_stream_request_id(runtime, warmup_request)
                if self.config.execution_mode == "generate_stream":
                    result = self._run_stream_generation(runtime, warmup_request)
                else:
                    start_time = time.time()
                    result = runtime.generate(**self._build_runtime_generate_kwargs(warmup_request))
                    result["time_used"] = time.time() - start_time
                    result["chunk_count"] = 1
                audio_samples = int(result["audio"].shape[-1])
            except Exception:
                logger.exception(
                    "Gradio warmup failed: default_model_name_or_path={}",
                    self.config.default_model_name_or_path,
                )
                raise
            audio_seconds = audio_samples / runtime.sample_rate
            metrics = {
                "request_id": request_id,
                "execution_mode": self.config.execution_mode,
                "chunk_count": int(result["chunk_count"]),
                "resolved_model_name_or_path": resolved_model_name_or_path,
                "sample_rate": runtime.sample_rate,
                "elapsed_seconds": round(float(result["time_used"]), 3),
                "audio_seconds": round(float(audio_seconds), 3),
                "rtf": round(float(result["rtf"]), 4),
                "seed": DEFAULT_SEED,
                "text": warmup_text,
                "device_policy": runtime.device_policy.as_dict(),
            }
            logger.info(
                "Gradio warmup ready: request_id={} execution_mode={} resolved_model_name_or_path={}",
                metrics["request_id"],
                metrics["execution_mode"],
                metrics["resolved_model_name_or_path"],
            )
            return metrics

    # region 音色库（参考音频预设的保存 / 删除 / 列举）
    def list_prompt_presets(self) -> tuple[PromptPreset, ...]:
        return discover_prompt_presets(
            self.config.prompts_dir,
            self.config.prompts_dir / "prompt_text",
        )

    @staticmethod
    def _sanitize_preset_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("音色名称不能为空。")
        illegal = set('\\/|:*?"<>') | {"\n", "\r", "\t"}
        if any(ch in illegal for ch in name):
            raise ValueError('音色名称含非法字符（不能包含 \\ / | : * ? " < > 及换行）。')
        return name

    def _rewrite_prompt_text(self, name: str, transcript: str | None) -> None:
        """在 prompt_text 映射文件中新增/更新（transcript 非 None）或删除（None）一条。

        保留注释和其它条目，只动目标 name 这一行。
        """
        mapping = self.config.prompts_dir / "prompt_text"
        existing = (
            mapping.read_text(encoding="utf-8").splitlines()
            if mapping.is_file()
            else []
        )
        out: list[str] = []
        replaced = False
        for line in existing:
            stripped = line.strip()
            is_entry = (
                stripped
                and not stripped.startswith("#")
                and "|" in stripped
                and stripped.split("|", 1)[0].strip() == name
            )
            if is_entry:
                if transcript is not None and not replaced:
                    out.append(f"{name} | {transcript}")
                    replaced = True
                # transcript is None -> 删除该行（跳过）
                continue
            out.append(line)
        if transcript is not None and not replaced:
            out.append(f"{name} | {transcript}")
        mapping.parent.mkdir(parents=True, exist_ok=True)
        mapping.write_text("\n".join(out) + "\n", encoding="utf-8")

    def save_prompt_preset(
        self,
        name: str,
        audio_path: str | None,
        prompt_text: str,
    ) -> str:
        """把当前参考音频+转写保存为音色库条目。转写为必填项。"""
        with self._lock:
            name = self._sanitize_preset_name(name)
            transcript = (prompt_text or "").strip()
            if not audio_path:
                raise ValueError("请先上传参考音频。")
            _require_chinese_prompt_transcript(audio_path, transcript)
            src = Path(audio_path)
            if not src.is_file():
                raise ValueError("参考音频文件不存在。")
            suffix = src.suffix.lower()
            if suffix not in PROMPT_AUDIO_SUFFIXES:
                raise ValueError(
                    f"音频格式需为 {', '.join(PROMPT_AUDIO_SUFFIXES)} 之一。"
                )
            prompts_dir = self.config.prompts_dir
            prompts_dir.mkdir(parents=True, exist_ok=True)
            destination = prompts_dir / f"{name}{suffix}"
            # 清掉同名但不同扩展名的旧音频，避免一名多文件
            for ext in PROMPT_AUDIO_SUFFIXES:
                stale = prompts_dir / f"{name}{ext}"
                if stale.exists() and stale != destination:
                    stale.unlink(missing_ok=True)
            shutil.copy2(src, destination)
            self._rewrite_prompt_text(name, transcript)
            logger.info("音色已保存: name={} path={}", name, destination)
            return name

    def delete_prompt_preset(self, name: str) -> None:
        """删除音色库条目（音频文件 + 转写映射）。"""
        with self._lock:
            if not name or name == DEFAULT_PROMPT_NONE:
                raise ValueError("请选择一个要删除的音色。")
            prompts_dir = self.config.prompts_dir
            removed = False
            for ext in PROMPT_AUDIO_SUFFIXES:
                target = prompts_dir / f"{name}{ext}"
                if target.exists():
                    target.unlink(missing_ok=True)
                    removed = True
            self._rewrite_prompt_text(name, None)
            logger.info("音色已删除: name={} removed_audio={}", name, removed)
    # endregion 音色库

    def _normalize_request(self, request: SynthesisRequest) -> SynthesisRequest:
        normalized_text = request.text.strip()
        if not normalized_text:
            raise ValueError("text 不能为空。")

        normalized_prompt_audio_path = request.prompt_audio_path or None
        normalized_prompt_text = (request.prompt_text or "").strip() or None
        if normalized_prompt_text and not normalized_prompt_audio_path:
            raise ValueError("prompt_text requires prompt_audio_path.")
        _require_chinese_prompt_transcript(
            normalized_prompt_audio_path, normalized_prompt_text
        )
        normalized_template_name = request.template_name.strip() or "tts"
        if normalized_template_name not in GRADIO_SYNTHESIS_MODE_TEMPLATE_NAMES:
            raise ValueError(
                f"Unsupported template_name={normalized_template_name!r}. "
                f"Expected one of {list(GRADIO_SYNTHESIS_MODE_TEMPLATE_NAMES)}."
            )
        normalized_language = (request.language or "").strip() or None
        supported_language_codes = set(SUPPORTED_LANGUAGE_CODE_BY_NAME.values())
        if (
            normalized_language is not None
            and normalized_language not in supported_language_codes
        ):
            raise ValueError(
                f"Unsupported language={normalized_language!r}. "
                f"Expected one of {sorted(supported_language_codes)}."
            )

        resolved_seed = int(request.seed)
        resolved_speed = min(2.0, max(0.5, float(request.speed)))
        resolved_max_pause = max(0.0, float(request.max_pause))
        return SynthesisRequest(
            model_name_or_path=request.model_name_or_path.strip(),
            text=normalized_text,
            prompt_audio_path=normalized_prompt_audio_path,
            prompt_text=normalized_prompt_text,
            execution_mode=request.execution_mode,
            template_name=normalized_template_name,
            language=normalized_language,
            ode_method=request.ode_method.strip() or DEFAULT_ODE_METHOD,
            num_steps=int(request.num_steps),
            guidance_scale=float(request.guidance_scale),
            speaker_scale=float(request.speaker_scale),
            normalize_text=bool(request.normalize_text),
            seed=resolved_seed,
            speed=resolved_speed,
            max_pause=resolved_max_pause,
        )

    def _build_output_path(self) -> Path:
        output_name = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.wav"
        return self.config.output_dir / output_name

    def _cleanup_outputs(self) -> None:
        if self.config.output_retention_count <= 0:
            return

        wav_files = sorted(
            self.config.output_dir.glob("*.wav"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        removed_count = 0
        for stale_file in wav_files[self.config.output_retention_count :]:
            stale_file.unlink(missing_ok=True)
            removed_count += 1
        if removed_count > 0:
            logger.info(
                "Gradio output cleanup completed: removed_files={} retention_limit={}",
                removed_count,
                self.config.output_retention_count,
            )

    @staticmethod
    def _waveform_to_numpy(audio: torch.Tensor):
        waveform = audio.detach().float().cpu().squeeze()
        if waveform.ndim == 0:
            raise ValueError("生成音频为空。")
        return waveform.numpy()

    def _apply_speed(self, waveform, sample_rate: int, speed: float):
        """用 Rubber Band 做高音质时间拉伸调语速（保持音调，输出仍为无损 PCM）。

        speed>1 加快（变短），speed<1 放慢（变长）。优先使用 Rubber Band；
        最终包未携带 Rubber Band 时，回退到包内 FFmpeg 的 atempo 滤镜。
        """
        rubberband = resolve_external_tool(
            "rubberband",
            explicit_path=self.config.rubberband_path,
            package_root=self.config.repo_root,
            required=False,
        )
        tmp_dir = self.config.repo_root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex[:8]
        in_path = tmp_dir / f"_stretch_in_{token}.wav"
        out_path = tmp_dir / f"_stretch_out_{token}.wav"
        try:
            sf.write(str(in_path), waveform, sample_rate)
            if rubberband is not None:
                command = [
                    rubberband.path,
                    "-3",
                    "--tempo",
                    f"{speed:.4f}",
                    str(in_path),
                    str(out_path),
                ]
                tool_name = f"Rubber Band（{rubberband.path}）"
            else:
                ffmpeg = resolve_external_tool(
                    "ffmpeg",
                    explicit_path=self.config.ffmpeg_path,
                    package_root=self.config.repo_root,
                    required=True,
                )
                command = [
                    ffmpeg.path,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(in_path),
                    "-filter:a",
                    f"atempo={speed:.4f}",
                    "-c:a",
                    "pcm_s16le",
                    str(out_path),
                ]
                tool_name = f"FFmpeg atempo（{ffmpeg.path}）"
                logger.info(
                    "Rubber Band is unavailable; using bundled FFmpeg atempo for speed={}",
                    speed,
                )
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"").decode("utf-8", "replace").strip()
                raise RuntimeError(
                    f"音频变速失败：{tool_name}。\n工具输出：{stderr}"
                ) from exc
            stretched, _ = sf.read(str(out_path))
            return stretched
        finally:
            in_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)

    @staticmethod
    def _compress_silence(
        waveform,
        sample_rate: int,
        max_pause: float,
        threshold_db: float = -40.0,
    ):
        """把超过 max_pause 秒的静音段压短到 max_pause，只动静音不碰说话。

        用于缩短模型在标点处生成的过长停顿，让语句更连贯。
        """
        wave = np.asarray(waveform).reshape(-1)
        if wave.size == 0 or max_pause <= 0:
            return wave
        peak = float(np.abs(wave).max())
        if peak <= 0:
            return wave
        threshold = peak * (10.0 ** (threshold_db / 20.0))
        max_pause_samples = max(1, int(sample_rate * max_pause))
        silent = np.abs(wave) < threshold
        # 找静音/非静音的分段边界
        change_points = np.flatnonzero(np.diff(silent.astype(np.int8)))
        bounds = np.concatenate(([0], change_points + 1, [wave.size]))
        pieces: list[np.ndarray] = []
        for b in range(len(bounds) - 1):
            start, end = int(bounds[b]), int(bounds[b + 1])
            segment = wave[start:end]
            if silent[start] and (end - start) > max_pause_samples:
                segment = segment[:max_pause_samples]  # 静音段压到上限
            pieces.append(segment)
        compressed = np.concatenate(pieces) if pieces else wave
        return compressed.astype(wave.dtype, copy=False)

    def _write_audio(
        self,
        audio: torch.Tensor,
        sample_rate: int,
        speed: float = 1.0,
        max_pause: float = 0.0,
    ) -> tuple[str, float]:
        waveform = self._waveform_to_numpy(audio)
        if max_pause > 0:
            waveform = self._compress_silence(waveform, sample_rate, max_pause)
        if abs(speed - 1.0) > 1e-3:
            waveform = self._apply_speed(waveform, sample_rate, speed)
        output_path = self._build_output_path()
        logger.info(
            "Writing synthesized audio: output_path={} sample_rate={} samples={} speed={} max_pause={}",
            output_path,
            sample_rate,
            waveform.shape[-1],
            speed,
            max_pause,
        )
        sf.write(output_path, waveform, sample_rate)
        self._cleanup_outputs()
        logger.info("Synthesized audio written: output_path={}", output_path)
        return str(output_path), waveform.shape[-1] / sample_rate

    def generate(
        self,
        request: SynthesisRequest,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> SynthesisResult:
        normalized_request = self._normalize_request(request)

        with self._lock:
            try:
                seed_everything(normalized_request.seed)
                runtime, resolved_model_name_or_path = self._get_runtime(
                    normalized_request.model_name_or_path,
                )
                logger.info(
                    "Gradio request accepted: resolved_model_name_or_path={} execution_mode={} seed={}",
                    resolved_model_name_or_path,
                    normalized_request.execution_mode,
                    normalized_request.seed,
                )
                if normalized_request.execution_mode == "generate_stream":
                    result = self._run_stream_generation(
                        runtime,
                        normalized_request,
                        progress_cb=progress_cb,
                    )
                else:
                    gen_kwargs = self._build_runtime_generate_kwargs(normalized_request)
                    # MPS 上自回归时延随单段长度明显增长；使用同一现有分段路径，
                    # 保持模型、精度和 NFE 不变，只限制单段上下文长度。
                    chunk_chars = chunk_chars_for_device(runtime.device.type)
                    if len(normalized_request.text) > chunk_chars:
                        result = runtime.generate_chunked(
                            **gen_kwargs,
                            max_chars_per_chunk=chunk_chars,
                            progress_cb=progress_cb,
                        )
                    else:
                        result = runtime.generate(**gen_kwargs, progress_cb=progress_cb)
                        result["chunk_count"] = 1
                audio_path, output_audio_seconds = self._write_audio(
                    result["audio"],
                    result["sample_rate"],
                    speed=normalized_request.speed,
                    max_pause=normalized_request.max_pause,
                )
            except Exception:
                logger.exception(
                    "Gradio request failed: model_name_or_path={} execution_mode={} text_len={} has_prompt_audio={} has_prompt_text={} template_name={} language={} "
                    "precision={} ode_method={} num_steps={} guidance_scale={} speaker_scale={} max_generate_length={} "
                    "normalize_text={} seed={}",
                    normalized_request.model_name_or_path,
                    normalized_request.execution_mode,
                    len(normalized_request.text),
                    bool(normalized_request.prompt_audio_path),
                    bool(normalized_request.prompt_text),
                    normalized_request.template_name,
                    normalized_request.language,
                    self.config.precision,
                    normalized_request.ode_method,
                    normalized_request.num_steps,
                    normalized_request.guidance_scale,
                    normalized_request.speaker_scale,
                    self.config.max_generate_length,
                    normalized_request.normalize_text,
                    normalized_request.seed,
                )
                raise
            audio_seconds = output_audio_seconds
            metrics = {
                "request_id": result["fid"],
                "execution_mode": normalized_request.execution_mode,
                "chunk_count": int(result["chunk_count"]),
                "template_name": normalized_request.template_name,
                "language": normalized_request.language,
                "resolved_model_name_or_path": resolved_model_name_or_path,
                "sample_rate": result["sample_rate"],
                "elapsed_seconds": round(float(result["time_used"]), 3),
                "audio_seconds": round(float(audio_seconds), 3),
                "rtf": round(float(result["rtf"]), 4),
                "seed": normalized_request.seed,
                "output_path": audio_path,
                "device_policy": runtime.device_policy.as_dict(),
            }
            logger.info(
                "Gradio request output ready: request_id={} execution_mode={} resolved_model_name_or_path={} output_path={}",
                metrics["request_id"],
                metrics["execution_mode"],
                metrics["resolved_model_name_or_path"],
                metrics["output_path"],
            )
            status = (
                f"完成：{Path(audio_path).name} | "
                f"模式 {metrics['execution_mode']} | "
                f"耗时 {metrics['elapsed_seconds']}s | "
                f"音频 {metrics['audio_seconds']}s | "
                f"RTF {metrics['rtf']}"
            )
            return SynthesisResult(
                audio_path=audio_path,
                metrics=metrics,
                status=status,
            )
