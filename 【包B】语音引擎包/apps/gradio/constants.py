from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # apps/gradio/ → apps/ → REPO_ROOT
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"
DEFAULT_LOG_FILE = REPO_ROOT / "logs" / "gradio.log"
DEFAULT_PROMPTS_DIR = REPO_ROOT / "pretrained_models" / "prompts"
DEFAULT_PROMPT_SOURCE_DIR = REPO_ROOT / "apps" / "gradio" / "default_prompts"
DEFAULT_PROMPT_MAPPING_FILE = DEFAULT_PROMPTS_DIR / "prompt_text"
DEFAULT_OUTPUT_RETENTION = 20
DEFAULT_EXECUTION_MODE = "generate_stream"
DEFAULT_DEVICE = "auto"
DEFAULT_PRECISION = "auto"
DEFAULT_ODE_METHOD = "euler"
DEFAULT_NUM_STEPS = 10
DEFAULT_GUIDANCE_SCALE = 1.2
DEFAULT_SPEAKER_SCALE = 1.5
DEFAULT_MAX_GENERATE_LENGTH = 500
DEFAULT_SEED = 42
DEFAULT_INPUT_TEXT = ""
DEFAULT_WARMUP_TEXT = "dots.tts is a 2B-parameter fully continuous, end-to-end autoregressive (AR) text-to-speech system. The backbone pairs a semantic encoder, an LLM, and an autoregressive flow-matching acoustic head over a 48 kHz AudioVAE"
DEFAULT_PROMPT_NAME = "女播音"
DEFAULT_PROMPT_NONE = "__none__"
PROMPT_AUDIO_SUFFIXES = (".wav", ".mp3", ".flac", ".m4a", ".ogg")
