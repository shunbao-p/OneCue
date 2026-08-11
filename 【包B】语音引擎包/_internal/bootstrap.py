# -*- coding: utf-8 -*-
"""dots.tts 便携启动引导脚本
在 import 任何第三方库之前完成全部环境变量设置。
"""

# ── 最早：灭掉所有 Python 警告 ──
import warnings as _w
_w.simplefilter("ignore")

import os
import sys
from pathlib import Path

# ── 灭掉 transformers / huggingface_hub / tokenizers 废话 ──
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import logging as _logging
for _name in ("transformers", "huggingface_hub", "datasets", "tokenizers"):
    _logging.getLogger(_name).setLevel(_logging.ERROR)

# ── 项目根路径推导（路径无关）──
PROJECT_DIR = Path(__file__).resolve().parent.parent

# ── 1. 离线模式（阻止一切远程请求）──
os.environ.setdefault("HF_HOME", str(PROJECT_DIR / "hf_download"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(PROJECT_DIR / "tf_download"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ.setdefault("GRADIO_TEMP_DIR", str(PROJECT_DIR / "tmp"))
os.environ["DOTS_TTS_LOG_LEVEL"] = "WARNING"  # 干净输出

# ── 2. 清空代理 + 设 NO_PROXY（防 Gradio 503）──
for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(key, None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

# ── 3. SSL 证书（便携 Python 自包含）──
_cert_file = PROJECT_DIR / "wzf" / "Lib" / "site-packages" / "certifi" / "cacert.pem"
if _cert_file.is_file():
    os.environ["SSL_CERT_FILE"] = str(_cert_file)

# ── 4. PYTHONPATH（替代 pip install -e .）──
_project_root = str(PROJECT_DIR)
_src_dir = str(PROJECT_DIR / "src")
for _p in (_project_root, _src_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── 5. UTF-8 编码 ──
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ── 6. 签名横幅 ──
print("=" * 62)
print("  dots.tts — 2B 全连续自回归 TTS · 48kHz · 语音克隆")
print("  离线整合包 · 王知风  https://wangzhifeng.vip  ·  QQ群 957732664")
print("=" * 62)

# ── 7. 启动 Gradio ──
def main() -> None:
    """查找默认模型并启动 Gradio WebUI。"""
    pretrained_dir = PROJECT_DIR / "pretrained_models"

    # 自动发现模型：优先 soar (最佳质量) > mf (快速)
    model_dirs = []
    for name in ("dots-tts-soar", "dots-tts-mf", "dots-tts-base"):
        candidate = pretrained_dir / name
        if candidate.is_dir() and (candidate / "config.json").is_file():
            model_dirs.append(name)
    # 也扫描 pretrained_models 下的任意有效子目录
    if pretrained_dir.is_dir():
        for child in sorted(pretrained_dir.iterdir()):
            if child.is_dir() and (child / "config.json").is_file():
                if child.name not in model_dirs:
                    model_dirs.append(child.name)

    if not model_dirs:
        print("\n[错误] 未找到任何模型检查点。")
        print(f"   请将模型文件放到 {pretrained_dir}/ 目录下。")
        print("   模型目录应包含 config.json、model.safetensors 等文件。")
        input("\n按回车键退出...")
        sys.exit(1)

    # 由启动器通过环境变量 DOTS_TTS_MODEL 指定模型（两个 .bat 各选其一）；
    # 未指定时回退到第一个可用模型。
    requested = os.environ.get("DOTS_TTS_MODEL", "").strip()
    if requested and requested in model_dirs:
        selected = requested
    else:
        if requested:
            print(f"[提示] 指定的模型 {requested!r} 不存在，回退到 {model_dirs[0]}")
        selected = model_dirs[0]

    selected_path = str(PROJECT_DIR / "pretrained_models" / selected)
    requested_device = os.environ.get("DOTS_TTS_DEVICE", "auto").strip() or "auto"
    requested_precision = os.environ.get("DOTS_TTS_PRECISION", "auto").strip() or "auto"

    # MeanFlow 蒸馏模型用 4 步，其余 flow-matching 模型用 10 步
    from apps.gradio.service import recommended_num_steps_for_model
    num_steps = recommended_num_steps_for_model(selected_path, repo_root=PROJECT_DIR)

    print(f"\n[模型] 可用: {', '.join(model_dirs)}")
    print(f"[当前] {selected}  (采样步数 num_steps={num_steps})")
    print(f"[设备] device={requested_device} precision={requested_precision}")
    print(f"\n正在加载模型，首次启动约需 30-60 秒...\n")

    # 命令行参数：传递给 app.py
    sys.argv = [
        sys.argv[0],
        "--model-name-or-path", selected_path,
        "--output-dir", str(PROJECT_DIR / "outputs"),
        "--log-file", str(PROJECT_DIR / "logs" / "gradio.log"),
        "--host", "127.0.0.1",
        "--default-num-steps", str(num_steps),
        "--execution-mode", "generate",  # 非流式：整句一次性生成，避免流式拼接断句
        "--device", requested_device,
        "--precision", requested_precision,
        # "--optimize",  # torch.compile + CUDA graph 加速；warmup 要编译 5 个 bucket 内核(32/64/128/256/512),首次启动 5-15 分钟。先关掉快速起 Gradio,首次生成时再按需编译。需要加速时把本行还原。
    ]

    # 导入并运行 Gradio 应用
    from apps.gradio.app import main as gradio_main
    gradio_main()


if __name__ == "__main__":
    main()
