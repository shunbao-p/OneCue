from __future__ import annotations

import argparse
import hashlib
import html
import os
import shutil
import subprocess
import sys
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

for import_root in (REPO_ROOT, SRC_ROOT):
    import_root_str = str(import_root)
    if import_root_str not in sys.path:
        sys.path.insert(0, import_root_str)

# ── 离线整合包：清代理 + 防 localhost 503 ──
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

from apps.gradio.constants import (  # noqa: E402
    DEFAULT_EXECUTION_MODE,
    DEFAULT_DEVICE,
    DEFAULT_GUIDANCE_SCALE,
    DEFAULT_HOST,
    DEFAULT_INPUT_TEXT,
    DEFAULT_LOG_FILE,
    DEFAULT_MAX_GENERATE_LENGTH,
    DEFAULT_NUM_STEPS,
    DEFAULT_ODE_METHOD,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_RETENTION,
    DEFAULT_PORT,
    DEFAULT_PRECISION,
    DEFAULT_PROMPT_NAME,
    DEFAULT_PROMPT_NONE,
    DEFAULT_SEED,
    DEFAULT_SPEAKER_SCALE,
)
from apps.gradio.api_contract import (  # noqa: E402
    API_NAME,
    error_response,
    normalize_request,
    success_response,
)
from dots_tts.external_tools import resolve_external_tool  # noqa: E402
from dots_tts.runtime_device import install_windows_asyncio_cleanup_patch  # noqa: E402

if TYPE_CHECKING:
    import gradio as gr

DEBUG_GRADIO_ENABLED = os.environ.get("DEBUG_GRADIO", "0") == "1"


def make_synthesize_v1_handler(app_config, app_service, request_type):
    """构建可脱离模型测试的 v1 处理器。"""

    def synthesize_v1(request: dict):
        try:
            values = normalize_request(request)
            num_steps = (
                values["num_steps"]
                if "num_steps" in request
                else app_config.default_num_steps
            )
            synthesis_request = request_type(
                model_name_or_path=app_config.default_model_name_or_path,
                text=values["text"],
                prompt_audio_path=values["prompt_audio_path"],
                prompt_text=values["prompt_text"],
                execution_mode=app_config.execution_mode,
                template_name="tts",
                ode_method=DEFAULT_ODE_METHOD,
                num_steps=num_steps,
                guidance_scale=values["guidance_scale"],
                speaker_scale=app_config.default_speaker_scale,
                normalize_text=values["normalize_text"],
                seed=values["seed"],
                speed=values["speed"],
                max_pause=values["max_pause"],
            )
            result = app_service.generate(synthesis_request)
            return result.audio_path, success_response(result, app_service.metadata())
        except Exception as exc:
            return None, error_response(exc)

    return synthesize_v1


PLAYGROUND_CSS = """
/* ============================================================
   知风伴 Design System · dots.tts 暗玻璃 + 暖金
   Brand: 王知风 / 知风·伴 — 禁蓝紫，用暖金光源
   ============================================================ */

.gradio-container {
    width: min(1500px, calc(100vw - 48px)) !important;
    max-width: none !important;
    margin: 0 auto !important;
    padding: 26px 0 56px !important;
    position: relative;
    z-index: 1;
    color: #c9c3b8 !important;
    font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif !important;
}

body, gradio-app {
    background:
      radial-gradient(900px 520px at 8% -12%, rgba(214,162,95,0.16), transparent 60%),
      radial-gradient(680px 440px at 100% -6%, rgba(214,162,95,0.05), transparent 58%),
      linear-gradient(180deg, #0b0e12 0%, #10151b 45%, #0c1116 100%) !important;
    background-attachment: fixed !important;
    color: #c9c3b8 !important;
}
body::before {
    content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-image:
      linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px);
    background-size: 64px 64px;
    -webkit-mask-image: linear-gradient(180deg, #000, transparent 72%);
    mask-image: linear-gradient(180deg, #000, transparent 72%);
}

/* ---- Labels -> 暖金（替换原蓝色 chip），保留 strong-label 加粗 ---- */
.gradio-container,
.gradio-container .gradio-container {
    --block-label-background-fill: transparent;
    --block-label-text-color: #e0c097;
    --block-label-border-color: transparent;
    --block-title-background-fill: transparent;
    --block-title-text-color: #e0c097;
    --block-title-border-color: transparent;
}
.gradio-container label[data-testid="block-label"],
.gradio-container label[data-testid="block-label"] *,
.gradio-container span[data-testid="block-info"],
.gradio-container span[data-testid="block-info"] *,
.gradio-container [data-testid="block-title"],
.gradio-container [data-testid="block-title"] *,
.gradio-container .block-title,
.gradio-container .block-title * {
    background: transparent !important;
    border-color: transparent !important;
    color: #e0c097 !important;
    fill: #e0c097 !important;
    font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif !important;
    font-style: normal !important;
    letter-spacing: 0.01em !important;
    text-transform: none !important;
}
.gradio-container label[data-testid="block-label"],
.gradio-container span[data-testid="block-info"],
.gradio-container [data-testid="block-title"],
.gradio-container .block-title {
    border: none !important;
    box-shadow: none !important;
    padding: 0 0 2px 0 !important;
    font-size: 0.8rem !important;
}
.gradio-container [data-testid="block-title"],
.gradio-container .block-title,
.gradio-container label[data-testid="block-label"] *,
.gradio-container [data-testid="block-title"] *,
.gradio-container .block-title *,
.strong-label label > span:first-child,
.strong-label label > span:first-child * {
    font-weight: 600 !important;
}
/* info（label 下方说明）走弱化暖灰 */
.gradio-container span[data-testid="block-info"],
.gradio-container span[data-testid="block-info"] *,
.gradio-container .info-text,
.gradio-container .info-text * {
    color: #8c887f !important;
    fill: #8c887f !important;
    font-weight: 400 !important;
    font-size: 0.74rem !important;
}
.gradio-container input,
.gradio-container textarea,
.gradio-container select,
.gradio-container [role="textbox"],
.gradio-container [contenteditable="true"] {
    font-weight: 400 !important;
}
.gradio-container label[data-testid="block-label"] > span:first-child {
    display: none !important;
}

/* ---- 输入控件：深底 + 暖金聚焦 ---- */
.gradio-container input[type="text"],
.gradio-container input[type="number"],
.gradio-container textarea,
.gradio-container select,
.gradio-container [contenteditable="true"] {
    background: rgba(11,14,18,0.55) !important;
    color: #f2ede4 !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 12px !important;
}
.gradio-container input:focus,
.gradio-container textarea:focus,
.gradio-container select:focus,
.gradio-container [contenteditable="true"]:focus {
    border-color: rgba(224,192,151,0.50) !important;
    box-shadow: 0 0 0 3px rgba(214,162,95,0.12) !important;
}
/* 下拉选项弹层：实底，杜绝透明叠字 */
.gradio-container ul.options,
.gradio-container .options,
.gradio-container ul[role="listbox"] {
    background: #10151c !important;
    border: 1px solid rgba(224,192,151,0.22) !important;
    border-radius: 10px !important;
    box-shadow: 0 18px 44px rgba(0,0,0,0.55) !important;
    backdrop-filter: none !important;
    z-index: 60 !important;
}
.gradio-container ul.options li,
.gradio-container .options .item,
.gradio-container li[role="option"] {
    background: transparent !important;
    color: #d8d2c6 !important;
}
.gradio-container ul.options li:hover,
.gradio-container .options .item:hover,
.gradio-container li[role="option"]:hover,
.gradio-container .options .item.selected,
.gradio-container li[role="option"][aria-selected="true"] {
    background: rgba(224,192,151,0.14) !important;
    color: #f2ede4 !important;
}

/* ---- Banner（品牌页眉）---- */
#playground-banner {
    position: relative; overflow: hidden;
    display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; flex-wrap: wrap;
    padding: 22px 28px; margin-bottom: 18px; border-radius: 16px;
    background: linear-gradient(100deg, rgba(23,29,37,0.90), rgba(15,19,25,0.72));
    border: 1px solid rgba(224,192,151,0.20);
    box-shadow: 0 18px 44px rgba(0,0,0,0.40), inset 0 1px 0 rgba(255,255,255,0.05);
    backdrop-filter: blur(18px);
}
#playground-banner::before {
    content: ""; position: absolute; left: 0; right: 0; top: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(224,192,151,0.75), transparent);
}
#playground-banner .pt-brand { display: flex; flex-direction: column; gap: 9px; }
#playground-banner h1 {
    margin: 0; font-family: Georgia, "Songti SC", serif; font-weight: 600;
    font-size: 2rem; line-height: 1; letter-spacing: 0.01em;
    background: linear-gradient(180deg, #fbf4e8, #e0c097);
    -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
#playground-banner h1 em {
    font-style: normal; font-family: "JetBrains Mono", "SF Mono", Consolas, monospace;
    font-size: 0.86rem; letter-spacing: 0.16em; margin-left: 11px;
    -webkit-text-fill-color: #d6a25f; color: #d6a25f;
}
#playground-banner .subtitle { margin: 0; color: #8c887f; font-size: 0.82rem; letter-spacing: 0.04em; }
#playground-banner .subtitle .dot { color: #d6a25f; margin: 0 8px; }
#playground-banner .pt-credits { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
#playground-banner .pt-credit {
    color: #c9c3b8; font-size: 0.78rem; white-space: nowrap;
    padding-right: 13px; border-right: 1px solid rgba(224,192,151,0.28);
}
#playground-banner .pt-credit b { color: #e7cba4; font-weight: 600; }
#playground-banner a.pt-link {
    display: inline-flex; align-items: center; gap: 6px; text-decoration: none !important;
    font-size: 0.78rem; font-weight: 500; white-space: nowrap; padding: 7px 15px; border-radius: 999px;
    color: #e0c097 !important; background: transparent; border: 1px solid rgba(224,192,151,0.32);
    transition: transform .18s cubic-bezier(0.16,1,0.3,1), background .18s ease, box-shadow .18s ease;
}
#playground-banner a.pt-link:hover { transform: translateY(-1px); background: rgba(224,192,151,0.10); }
#playground-banner a.pt-link-primary {
    color: #1c1408 !important; border-color: transparent;
    background: linear-gradient(180deg, #e7cba4, #d6a25f); box-shadow: 0 10px 26px rgba(214,162,95,0.26);
}
#playground-banner a.pt-link-primary:hover { box-shadow: 0 14px 32px rgba(214,162,95,0.34); }

/* ---- 使用说明卡 ---- */
.info-card {
    padding: 14px 18px; border-radius: 14px; box-sizing: border-box; margin-bottom: 18px;
    background: rgba(22,28,36,0.50);
    border: 1px solid rgba(255,255,255,0.08); border-left: 3px solid #d6a25f;
    font-size: 0.84rem; line-height: 1.6; color: #c9c3b8; backdrop-filter: blur(12px);
}
.info-card .card-title,
.info-card .notice-title {
    display: block; font-family: Georgia, serif; font-weight: 600; font-size: 0.92rem; color: #e7cba4;
}
.info-card .card-title { margin-bottom: 5px; }
.info-card .notice-title { margin-top: 8px; margin-bottom: 4px; }
.info-card ol, .info-card ul { margin: 0; padding-left: 18px; }
.info-card li { margin: 3px 0; }
.info-card b { color: #e0c097; }

/* ---- 工作区两栏：玻璃面板 ---- */
.main-workspace { gap: 18px !important; align-items: stretch !important; }
.prompt-column,
.synthesis-column {
    gap: 14px !important; padding: 18px !important; border-radius: 18px !important;
    background: rgba(22,28,36,0.55) !important; border: 1px solid rgba(255,255,255,0.09) !important;
    box-shadow: 0 20px 54px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.04) !important;
    /* 注意：不要在这里加 backdrop-filter/filter/transform —— 会改变定位上下文，
       导致下拉浮层(音色库)定位错乱跑到下面去 */
}
.prompt-column .block,
.synthesis-column .block,
.prompt-column .form,
.synthesis-column .form {
    background: transparent !important; border: none !important; box-shadow: none !important;
}

.control-row { gap: 12px !important; }
.settings-slider-row { gap: 14px !important; }
/* 音色操作小按钮：靠左、按内容自然宽度，不撑满整行 */
.voice-actions { justify-content: flex-start !important; flex-wrap: wrap !important; }
.voice-actions button { flex: 0 0 auto !important; width: auto !important; }

/* 次级按钮（保存/删除）：暖金描边 pill；删除偏暖红 */
.control-row button {
    border-radius: 999px !important; font-weight: 500 !important;
    color: #e0c097 !important; background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(224,192,151,0.28) !important;
    transition: transform .18s cubic-bezier(0.16,1,0.3,1), background .18s ease !important;
}
.control-row button:hover { transform: translateY(-1px); background: rgba(255,255,255,0.08) !important; }
.control-row button:last-child {
    color: #e6a99a !important; border-color: rgba(214,120,95,0.34) !important;
    background: rgba(214,120,95,0.06) !important;
}

/* 设置折叠面板 */
.settings-card {
    margin-top: 2px !important; border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 14px !important; background: rgba(11,14,18,0.32) !important; overflow: hidden;
}
.settings-card > button,
.settings-card .label-wrap,
.settings-card .label-wrap span { color: #cfc8bb !important; font-family: Georgia, serif !important; }

/* 滑块 -> 暖金 */
.gradio-container input[type="range"] { accent-color: #d6a25f !important; }

/* 生成按钮：暖金渐变 pill */
.generate-button {
    margin-top: 4px !important; width: 100% !important; box-sizing: border-box !important;
    flex: 0 0 auto !important; min-height: 50px !important; border: 0 !important; border-radius: 999px !important;
    color: #1c1408 !important; background: linear-gradient(180deg, #e7cba4, #d6a25f) !important;
    font-family: Georgia, serif !important; font-size: 1.02rem !important; font-weight: 700 !important;
    letter-spacing: 0.18em !important; padding-top: 12px !important; padding-bottom: 12px !important;
    box-shadow: 0 14px 38px rgba(214,162,95,0.28) !important;
    transition: transform .18s cubic-bezier(0.16,1,0.3,1), box-shadow .18s ease !important;
}
.generate-button:hover { transform: translateY(-1px); box-shadow: 0 18px 46px rgba(214,162,95,0.38) !important; }

/* 输出音频 */
.output-audio {
    flex: 0 0 auto !important; min-height: 170px !important;
    border: 1px solid rgba(255,255,255,0.09) !important; border-radius: 14px !important;
    background: rgba(11,14,18,0.40) !important;
}
.output-audio audio { width: 100% !important; }

@media (max-width: 768px) {
    .gradio-container { width: calc(100vw - 20px) !important; }
}
"""

def build_playground_theme(gr):
    # 知风伴：暗玻璃 + 暖金。light 与 _dark 两套都设深色，强制暗色；离线只用系统字体。
    return gr.themes.Base(
        primary_hue=gr.themes.colors.amber,
        secondary_hue=gr.themes.colors.amber,
        neutral_hue=gr.themes.colors.gray,
        radius_size="lg",
        text_size="md",
        spacing_size="md",
        font=["Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Segoe UI", "system-ui", "sans-serif"],
        font_mono=["JetBrains Mono", "SF Mono", "Consolas", "monospace"],
    ).set(
        body_background_fill="#0b0e12",
        body_background_fill_dark="#0b0e12",
        body_text_color="#c9c3b8",
        body_text_color_dark="#c9c3b8",
        background_fill_primary="rgba(22,28,36,0.0)",
        background_fill_primary_dark="rgba(22,28,36,0.0)",
        background_fill_secondary="rgba(17,21,27,0.5)",
        background_fill_secondary_dark="rgba(17,21,27,0.5)",
        block_background_fill="rgba(0,0,0,0)",
        block_background_fill_dark="rgba(0,0,0,0)",
        block_border_color="rgba(255,255,255,0.0)",
        block_border_color_dark="rgba(255,255,255,0.0)",
        block_label_text_color="#e0c097",
        block_label_text_color_dark="#e0c097",
        block_title_text_color="#e0c097",
        block_title_text_color_dark="#e0c097",
        border_color_primary="rgba(255,255,255,0.10)",
        border_color_primary_dark="rgba(255,255,255,0.10)",
        input_background_fill="rgba(11,14,18,0.55)",
        input_background_fill_dark="rgba(11,14,18,0.55)",
        input_border_color="rgba(255,255,255,0.10)",
        input_border_color_dark="rgba(255,255,255,0.10)",
        button_primary_background_fill="linear-gradient(180deg,#e7cba4,#d6a25f)",
        button_primary_background_fill_dark="linear-gradient(180deg,#e7cba4,#d6a25f)",
        button_primary_text_color="#1c1408",
        button_primary_text_color_dark="#1c1408",
        button_secondary_background_fill="rgba(255,255,255,0.04)",
        button_secondary_background_fill_dark="rgba(255,255,255,0.04)",
        button_secondary_text_color="#e0c097",
        button_secondary_text_color_dark="#e0c097",
        slider_color="#d6a25f",
        slider_color_dark="#d6a25f",
        color_accent_soft="rgba(214,162,95,0.16)",
        color_accent_soft_dark="rgba(214,162,95,0.16)",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="dots.tts Gradio app.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument(
        "--execution-mode",
        choices=("generate", "generate_stream"),
        default=DEFAULT_EXECUTION_MODE,
        help="Runtime execution mode fixed for the app",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "mps", "cpu"),
        default=DEFAULT_DEVICE,
        help="Inference device policy fixed for the app runtime",
    )
    parser.add_argument(
        "--precision",
        choices=("auto", "bfloat16", "float16", "float32"),
        default=DEFAULT_PRECISION,
        help="Inference precision fixed for the app runtime",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Enable runtime optimize acceleration",
    )
    parser.add_argument(
        "--ffmpeg-path",
        default=None,
        help="Explicit ffmpeg executable or containing directory",
    )
    parser.add_argument(
        "--ffprobe-path",
        default=None,
        help="Explicit ffprobe executable or containing directory",
    )
    parser.add_argument(
        "--rubberband-path",
        default=None,
        help="Explicit optional rubberband executable or containing directory",
    )
    parser.add_argument(
        "--model-name-or-path",
        default=None,
        help="Default model directory or Hugging Face repo id",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for generated wav outputs",
    )
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_FILE),
        help="Path to the Gradio log file",
    )
    parser.add_argument(
        "--output-retention-count",
        type=int,
        default=DEFAULT_OUTPUT_RETENTION,
        help="Maximum number of generated wav files to keep",
    )
    parser.add_argument(
        "--max-generate-length",
        type=int,
        default=DEFAULT_MAX_GENERATE_LENGTH,
        help="Maximum generation schedule length fixed for the app runtime",
    )
    parser.add_argument(
        "--default-prompt-name",
        default=DEFAULT_PROMPT_NAME,
        help="Default built-in voice preset name",
    )
    parser.add_argument(
        "--default-precision",
        default=DEFAULT_PRECISION,
        choices=["auto", "bfloat16", "float32", "float16"],
        help="Default precision selected in the UI",
    )
    parser.add_argument(
        "--default-num-steps",
        type=int,
        default=DEFAULT_NUM_STEPS,
        help="Default Num Steps selected in the UI",
    )
    parser.add_argument(
        "--default-guidance-scale",
        type=float,
        default=DEFAULT_GUIDANCE_SCALE,
        help="Default Guidance Scale selected in the UI",
    )
    parser.add_argument(
        "--default-speaker-scale",
        type=float,
        default=DEFAULT_SPEAKER_SCALE,
        help="Default Speaker Scale selected in the UI",
    )
    parser.add_argument(
        "--default-max-generate-length",
        type=int,
        default=DEFAULT_MAX_GENERATE_LENGTH,
        help="Default Max Generate Length selected in the UI",
    )
    parser.add_argument(
        "--skip-warmup",
        action="store_true",
        help="Start the Gradio server without running an initial synthesis warmup.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser from the service process.",
    )
    return parser.parse_args(argv)


def build_startup_config_panel(gr, app_config) -> None:
    with gr.Accordion("启动固定参数", open=False):
        gr.Markdown("只读。修改这部分需要重启服务并传入新的启动参数。")
        gr.Textbox(
            label="Model",
            value=app_config.default_model_name_or_path,
            interactive=False,
        )
        with gr.Row():
            gr.Textbox(
                label="Device",
                value=app_config.device,
                interactive=False,
            )
            gr.Textbox(
                label="Execution Mode",
                value=app_config.execution_mode,
                interactive=False,
            )
            gr.Textbox(
                label="Precision",
                value=app_config.precision,
                interactive=False,
            )
        with gr.Row():
            gr.Number(
                label="Max Generate Length",
                value=app_config.max_generate_length,
                precision=0,
                interactive=False,
            )
            gr.Checkbox(
                label="Optimize",
                value=app_config.optimize,
                interactive=False,
            )


def build_demo(gr, app_config, app_service) -> "gr.Blocks":
    from apps.gradio.service import (
        GRADIO_SYNTHESIS_MODE_CHOICES,
        SynthesisRequest,
        build_prompt_choice_items,
        resolve_prompt_selection,
    )
    synthesize_v1 = make_synthesize_v1_handler(app_config, app_service, SynthesisRequest)

    def select_prompt_preset(prompt_name: str):
        # 用实时音色库列表（保存/删除后即时生效），而非启动时的静态列表
        audio_path, prompt_text = resolve_prompt_selection(
            prompt_name,
            app_service.list_prompt_presets(),
        )
        preview_path = _build_audio_preview(audio_path)
        return prompt_text, _render_audio_preview(preview_path), audio_path

    def _prompt_cache_dir() -> Path:
        cache_root = Path(os.environ.get("GRADIO_TEMP_DIR") or REPO_ROOT / "tmp")
        cache_dir = cache_root / "prompts_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _build_audio_preview(audio_path: str | None) -> str | None:
        """Return an ASCII-named M4A solely for the browser preview player."""
        if not audio_path:
            return None
        source = Path(audio_path)
        if not source.is_file():
            return None
        cache_dir = _prompt_cache_dir()
        fingerprint = hashlib.sha256(
            f"{source.resolve()}:{source.stat().st_size}:{source.stat().st_mtime_ns}".encode()
        ).hexdigest()[:20]
        preview = cache_dir / f"preview_{fingerprint}.m4a"
        if preview.is_file() and preview.stat().st_size > 0:
            return str(preview)
        if source.suffix.lower() == ".m4a":
            shutil.copy2(source, preview)
            return str(preview)
        ffmpeg = resolve_external_tool(
            "ffmpeg",
            explicit_path=app_config.ffmpeg_path,
            package_root=app_config.repo_root,
            required=True,
        ).path
        try:
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(source), "-vn",
                    "-codec:a", "aac", "-b:a", "192k", str(preview),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.CalledProcessError as exc:
            preview.unlink(missing_ok=True)
            raise RuntimeError("参考音频转换为 M4A 预览失败。") from exc
        return str(preview)

    def _render_audio_preview(preview_path: str | None) -> str:
        """Use the browser's native player, bypassing Gradio 6.3 Audio state bugs."""
        if not preview_path:
            return (
                '<div class="prompt-native-player">'
                '<div class="prompt-native-label">参考音频预览 · Prompt Audio</div>'
                '<div class="prompt-native-empty">上传音频或选择音色后可播放</div>'
                '</div>'
            )
        preview = Path(preview_path)
        url = "/gradio_api/file=" + quote(str(preview), safe="")
        safe_url = html.escape(url, quote=True)
        return (
            '<div class="prompt-native-player">'
            '<div class="prompt-native-label">参考音频预览 · Prompt Audio</div>'
            f'<audio controls preload="metadata" src="{safe_url}" '
            'style="display:block;width:100%;min-height:54px"></audio>'
            '</div>'
        )

    def prepare_uploaded_prompt(audio_path: str | None):
        """Keep source WAV for the model, expose a separate full MP3 preview."""
        if not audio_path:
            return None, None, ""
        source = Path(audio_path)
        if not source.is_file():
            raise RuntimeError("上传的参考音频文件不存在。")
        suffix = source.suffix.lower()
        if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
            raise RuntimeError("参考音频格式不受支持，请上传 WAV、MP3、FLAC、OGG 或 M4A。")
        source_copy = _prompt_cache_dir() / f"prompt_{uuid.uuid4().hex[:16]}{suffix}"
        shutil.copy2(source, source_copy)
        preview_path = _build_audio_preview(str(source_copy))
        title = source.stem.strip()
        transcript = title if any("\u3400" <= char <= "\u9fff" for char in title) else ""
        # Put transcript first.  A media-rendering failure must never prevent
        # the Chinese title from reaching its textbox.
        return transcript, _render_audio_preview(preview_path), str(source_copy)

    def save_voice(name: str, audio_path: str | None, prompt_text_val: str):
        try:
            saved = app_service.save_prompt_preset(name, audio_path, prompt_text_val)
        except ValueError as exc:
            raise gr.Error(str(exc))
        items = build_prompt_choice_items(app_service.list_prompt_presets())
        gr.Info(f"已保存音色：{saved}")
        return gr.update(choices=items, value=saved)

    def delete_voice(prompt_name: str):
        try:
            app_service.delete_prompt_preset(prompt_name)
        except ValueError as exc:
            raise gr.Error(str(exc))
        items = build_prompt_choice_items(app_service.list_prompt_presets())
        gr.Info(f"已删除音色：{prompt_name}")
        return (
            gr.update(choices=items, value=DEFAULT_PROMPT_NONE),
            "",
            _render_audio_preview(None),
            None,
        )

    def run_synthesis(
        text: str,
        synthesis_mode: str,
        prompt_audio_path: str | None,
        prompt_text: str,
        ode_method: str,
        num_steps: float,
        guidance_scale: float,
        speaker_scale: float,
        normalize_text: bool,
        seed: float,
        speed: float,
        max_pause: float,
    ):
        resolved_synthesis_mode = synthesis_mode if DEBUG_GRADIO_ENABLED else "tts"
        request = SynthesisRequest(
            model_name_or_path=app_config.default_model_name_or_path,
            text=text,
            prompt_audio_path=prompt_audio_path,
            prompt_text=prompt_text,
            execution_mode=app_config.execution_mode,
            template_name=resolved_synthesis_mode,
            ode_method=ode_method,
            num_steps=int(num_steps),
            guidance_scale=float(guidance_scale),
            speaker_scale=float(speaker_scale),
            normalize_text=normalize_text,
            seed=int(seed),
            speed=float(speed),
            max_pause=float(max_pause),
        )
        try:
            # Gradio 6.3's Progress is callable but is not a context manager.
            progress = gr.Progress()
            progress(0.0, desc="准备中...")
            result = app_service.generate(
                request,
                progress_cb=lambda f, d: progress(f, desc=d),
            )
        except Exception as exc:
            error_log = REPO_ROOT / "logs" / "gradio-generate-errors.log"
            error_log.parent.mkdir(parents=True, exist_ok=True)
            with error_log.open("a", encoding="utf-8") as file_obj:
                file_obj.write(traceback.format_exc())
                file_obj.write("\n")
            raise gr.Error(f"生成失败：{exc}") from exc
        return result.audio_path, result.metrics

    with gr.Blocks(title="dots.tts") as demo:
        gr.HTML(
            "<style>\n"
            + PLAYGROUND_CSS
            + "\n</style>\n"
            + """
            <div id="playground-banner">
              <div class="pt-brand">
                <h1>dots.tts<em>VOICE CLONING</em></h1>
                <p class="subtitle">全连续自回归语音合成<span class="dot">·</span>48 kHz 高保真<span class="dot">·</span>声音克隆<span class="dot">·</span>本地离线</p>
              </div>
              <div class="pt-credits">
                <span class="pt-credit">整合包制作 · <b>王知风</b></span>
                <a class="pt-link" href="https://wangzhifeng.vip/" target="_blank" rel="noopener">更多 AI 工具 →</a>
                <a class="pt-link pt-link-primary" href="https://wangzhifeng.vip/" target="_blank" rel="noopener">详细教程 →</a>
              </div>
            </div>
            """,
        )

        gr.HTML(
            """
            <div class="info-card">
              <span class="card-title">使用说明 · Instructions</span>
              <ol>
                <li>上传参考音频并填写对应转写文本 · Upload prompt audio and fill in its transcript.</li>
                <li>在文本框中输入要合成的内容 · Enter the text to synthesize.</li>
                <li>点击 <b>Generate</b> 合成声音 · Click <b>Generate</b> to synthesize speech.</li>
              </ol>
            </div>
            """,
        )

        with gr.Row(equal_height=True, elem_classes="main-workspace"):
            with gr.Column(scale=1, min_width=480, elem_classes="prompt-column"):
                prompt_preset = gr.Dropdown(
                    label="音色库 · Voice Library",
                    choices=build_prompt_choice_items(app_config.prompt_presets),
                    value=app_config.default_prompt_name,
                    info="选择已保存音色自动填入参考音频与转写；下方可保存/删除。",
                    elem_id="voice-preset-dropdown",
                    elem_classes="strong-label",
                )
                prompt_audio_upload = gr.File(
                    label="上传参考音频 · Prompt Audio",
                    file_types=["audio"],
                    type="filepath",
                    elem_classes="strong-label",
                )
                prompt_audio_preview = gr.HTML(
                    value=_render_audio_preview(
                        _build_audio_preview(app_config.default_prompt_audio_path)
                    ),
                    elem_classes="strong-label prompt-audio-preview",
                )
                # The model consumes this original (lossless) source path;
                # the visible player consumes only the separately generated MP3.
                # A hidden Textbox is used instead of gr.State because Gradio
                # 6.3 does not consistently propagate State updates from an
                # upload event to the next queued click event.
                prompt_audio_path = gr.Textbox(
                    value=app_config.default_prompt_audio_path,
                    visible=False,
                )
                prompt_text = gr.Textbox(
                    label="参考音频中文转写 · Prompt Text",
                    lines=5,
                    value=app_config.default_prompt_text,
                    placeholder="请准确填写参考音频里实际朗读的中文；不能填写文件名或临时标识。",
                    info="上传后请手填与音频一致的中文转写；生成和保存音色时会校验。",
                    elem_classes="strong-label",
                )
                with gr.Row(elem_classes="control-row"):
                    voice_name = gr.Textbox(
                        label="音色名称 · Name",
                        placeholder="保存时用作音色名（不含 \\ / | : * ? 等）",
                        scale=2,
                        min_width=180,
                    )
                with gr.Row(elem_classes="control-row voice-actions"):
                    load_voice_btn = gr.Button(
                        "📂 加载", size="sm", scale=1, min_width=72
                    )
                    save_voice_btn = gr.Button(
                        "💾 保存", size="sm", scale=1, min_width=72
                    )
                    delete_voice_btn = gr.Button(
                        "🗑️ 删除", size="sm", scale=1, min_width=72
                    )

            with gr.Column(scale=1, min_width=480, elem_classes="synthesis-column"):
                text = gr.Textbox(
                    label="待合成文本 · Text",
                    lines=5,
                    max_lines=8,
                    value=DEFAULT_INPUT_TEXT,
                    placeholder="输入待合成的文本",
                    elem_classes="strong-label",
                )
                with gr.Accordion("⚙️ Settings", open=False, elem_classes="settings-card"):
                    with gr.Row(elem_classes="settings-slider-row"):
                        num_steps = gr.Slider(
                            label="Num Steps",
                            minimum=1,
                            maximum=32,
                            step=1,
                            value=app_config.default_num_steps,
                        )
                    with gr.Row(elem_classes="settings-slider-row"):
                        guidance_scale = gr.Slider(
                            label="Guidance Scale",
                            minimum=1.0,
                            maximum=3.0,
                            step=0.1,
                            value=app_config.default_guidance_scale,
                        )
                    with gr.Row(elem_classes="settings-slider-row"):
                        speed = gr.Slider(
                            label="语速 · Speed",
                            minimum=0.5,
                            maximum=2.0,
                            step=0.05,
                            value=1.0,
                            info="高音质变速（Rubber Band，保持音调、无损 WAV）。1.0=原速。",
                        )
                    with gr.Row(elem_classes="settings-slider-row"):
                        max_pause = gr.Slider(
                            label="停顿上限 · Max Pause (秒)",
                            minimum=0.0,
                            maximum=1.5,
                            step=0.05,
                            value=0.3,
                            info="标点处停顿超过此秒数就压短，让语句更连贯。0=不压缩。",
                        )
                    with gr.Row(elem_classes="control-row"):
                        seed = gr.Number(
                            label="Seed",
                            value=DEFAULT_SEED,
                            precision=0,
                            scale=1,
                            min_width=180,
                        )
                        normalize_text = gr.Checkbox(
                            label="Normalize Text",
                            value=False,
                            scale=1,
                            min_width=180,
                        )
                generate = gr.Button(
                    "Generate",
                    variant="primary",
                    size="lg",
                    elem_classes="generate-button",
                )
                audio_out = gr.Audio(
                    label="生成音频 · Output",
                    type="filepath",
                    elem_classes="output-audio",
                )

        if DEBUG_GRADIO_ENABLED:
            with gr.Accordion("Debug", open=False):
                synthesis_mode = gr.Dropdown(
                    label="SynthesisMode",
                    choices=list(GRADIO_SYNTHESIS_MODE_CHOICES),
                    value="tts",
                    info="选择合成模式；界面显示名会自动映射到 runtime 对应模板。",
                )
                ode_method = gr.Textbox(
                    label="ODE Method",
                    value=DEFAULT_ODE_METHOD,
                    lines=1,
                )
                speaker_scale = gr.Slider(
                    label="Speaker Scale",
                    minimum=0.0,
                    maximum=3.0,
                    step=0.1,
                    value=app_config.default_speaker_scale,
                    info="说话人 x-vector 强度",
                )
                metrics = gr.JSON(label="Metrics", value=app_service.metadata())
                build_startup_config_panel(gr, app_config)
        else:
            synthesis_mode = gr.State(value="tts")
            ode_method = gr.State(value=DEFAULT_ODE_METHOD)
            speaker_scale = gr.State(value=app_config.default_speaker_scale)
            metrics = gr.State(value={})

        generate.click(
            fn=run_synthesis,
            inputs=[
                text,
                synthesis_mode,
                prompt_audio_path,
                prompt_text,
                ode_method,
                num_steps,
                guidance_scale,
                speaker_scale,
                normalize_text,
                seed,
                speed,
                max_pause,
            ],
            outputs=[audio_out, metrics],
            concurrency_limit=1,
        )
        api_request = gr.JSON(label="synthesize_v1 request", value={}, visible=False)
        api_audio = gr.File(label="synthesize_v1 audio", visible=False)
        api_response = gr.JSON(label="synthesize_v1 response", visible=False)
        api_trigger = gr.Button("synthesize_v1", visible=False)
        api_trigger.click(
            fn=synthesize_v1,
            inputs=[api_request],
            outputs=[api_audio, api_response],
            api_name=API_NAME.removeprefix("/"),
            concurrency_limit=1,
        )
        prompt_preset.change(
            fn=select_prompt_preset,
            inputs=[prompt_preset],
            outputs=[prompt_text, prompt_audio_preview, prompt_audio_path],
            concurrency_limit=1,
        )
        prompt_audio_upload.upload(
            fn=prepare_uploaded_prompt,
            inputs=[prompt_audio_upload],
            outputs=[prompt_text, prompt_audio_preview, prompt_audio_path],
            concurrency_limit=1,
        )
        prompt_audio_upload.clear(
            fn=lambda: ("", _render_audio_preview(None), None),
            outputs=[prompt_text, prompt_audio_preview, prompt_audio_path],
            concurrency_limit=1,
        )
        load_voice_btn.click(
            fn=select_prompt_preset,
            inputs=[prompt_preset],
            outputs=[prompt_text, prompt_audio_preview, prompt_audio_path],
            concurrency_limit=1,
        )
        save_voice_btn.click(
            fn=save_voice,
            inputs=[voice_name, prompt_audio_path, prompt_text],
            outputs=[prompt_preset],
            concurrency_limit=1,
        )
        delete_voice_btn.click(
            fn=delete_voice,
            inputs=[prompt_preset],
            outputs=[prompt_preset, prompt_text, prompt_audio_preview, prompt_audio_path],
            concurrency_limit=1,
        )

    return demo.queue(default_concurrency_limit=1, max_size=8)


def main() -> None:
    args = parse_args()
    import gradio as gr
    from loguru import logger

    from apps.gradio.service import GradioAppService, build_gradio_app_config
    from dots_tts.utils.logging import configure_logging

    configure_logging(log_file=args.log_file)
    logger.info(
        "Gradio app starting: host={} port={} model_name_or_path={} output_dir={} "
        "log_file={} output_retention_count={} max_generate_length={} execution_mode={} device={} precision={} optimize={} "
        "default_prompt_name={} skip_warmup={}",
        args.host,
        args.port,
        args.model_name_or_path,
        args.output_dir,
        args.log_file,
        args.output_retention_count,
        args.max_generate_length,
        args.execution_mode,
        args.device,
        args.precision,
        args.optimize,
        args.default_prompt_name,
        args.skip_warmup,
    )
    app_config = build_gradio_app_config(
        host=args.host,
        port=args.port,
        execution_mode=args.execution_mode,
        device=args.device,
        precision=args.precision,
        optimize=args.optimize,
        model_name_or_path=args.model_name_or_path,
        output_dir=Path(args.output_dir),
        output_retention_count=args.output_retention_count,
        max_generate_length=args.max_generate_length,
        default_prompt_name=args.default_prompt_name,
        default_precision=args.default_precision,
        default_num_steps=args.default_num_steps,
        default_guidance_scale=args.default_guidance_scale,
        default_speaker_scale=args.default_speaker_scale,
        default_max_generate_length=args.default_max_generate_length,
        ffmpeg_path=args.ffmpeg_path,
        ffprobe_path=args.ffprobe_path,
        rubberband_path=args.rubberband_path,
    )
    app_service = GradioAppService(app_config)
    if args.skip_warmup:
        logger.info("Gradio app warmup skipped by --skip-warmup.")
    else:
        warmup_metrics = app_service.warmup()
        logger.info("Gradio app warmup metrics: {}", warmup_metrics)
    demo = build_demo(gr, app_config, app_service)
    logger.info(
        "Gradio app ready: host={} port={} execution_mode={} device={} precision={} optimize={} default_model_name_or_path={}",
        app_config.host,
        app_config.port,
        app_config.execution_mode,
        app_config.device,
        app_config.precision,
        app_config.optimize,
        app_config.default_model_name_or_path,
    )
    install_windows_asyncio_cleanup_patch()

    demo.launch(
        server_name="127.0.0.1",
        server_port=app_config.port,
        # Gradio 6 only serves files under its temp directory by default.  The
        # bundled voice library lives outside it, so explicitly allow that
        # read-only asset directory for the browser audio player.
        allowed_paths=[str(app_config.prompts_dir.resolve())],
        inbrowser=not args.no_browser,
        theme=build_playground_theme(gr),
        css=PLAYGROUND_CSS,
    )


if __name__ == "__main__":
    main()
