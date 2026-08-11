# -*- coding: utf-8 -*-
# 调用已在 127.0.0.1:7860 运行的 DOTS-TTS（不重复加载模型，省显存）
# 参数以 view_api() 实测为准：text, prompt_audio_path, prompt_text, num_steps,
# guidance_scale, normalize_text, seed, speed, max_pause -> 返回单个音频路径
import os, shutil
from pathlib import Path

PROJECT = Path(r"F:\TTS\Dots.tts")
PROMPT_DIR = PROJECT / "pretrained_models" / "prompts"
REF_WAV = str(PROMPT_DIR / "女播音.wav")
# 与 prompts/prompt_text 中“女播音”对应的真实中文转写
REF_TXT = "我相信很多听友听到这首歌应该是在96年90年代的那个夏天"

from gradio_client import Client

print("Connecting to DOTS gradio @ http://127.0.0.1:7860 ...")
c = Client("http://127.0.0.1:7860")

text = "你好，我是惠子。这是用 DOTS 语音合成模型做的测试，声音听起来自然吗？"
print("Synthesizing:", text)
audio_path = c.predict(
    api_name="/run_synthesis",
    text=text,
    prompt_audio_path=REF_WAV,
    prompt_text=REF_TXT,
    num_steps=10,
    guidance_scale=1.2,
    normalize_text=False,
    seed=42,
    speed=1.0,
    max_pause=0.3,
)
print("returned audio_path:", audio_path)
if audio_path and os.path.exists(audio_path):
    out = PROJECT / "outputs" / "dots_client_test.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(audio_path, out)
    print("SAVED ->", out)
else:
    print("ERROR: no audio file returned")
