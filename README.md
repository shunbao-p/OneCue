# OneCue · 一句话生成本地短视频

OneCue 是一套面向 Apple Silicon Mac 的本地短视频工作流。使用者在 Codex 中调用仓库自带的 `$short-video-director`，输入一句自然语言需求，即可沿既有链路生成候选视频：

`Codex 内容与分镜 → Image 2 独立静态关键帧 → 包 B 本地人声 → 包 A/FFmpeg 字幕与硬切 → final.mp4`

当前 v1.0.0 采用“多张静态分镜图随叙事硬切”的产品路线：默认不使用 BGM、环境音、SFX、I2V、图片推拉平移、拆层微动态或动态转场。每个镜头使用独立静态图，包 A 将其编码为与该镜头人声等长的视频片段，再烧录字幕并合成为竖屏成片。

## 支持范围

- Apple Silicon Mac（arm64）；
- macOS 11 或更高版本；
- Codex Plus 或以上会员账号，且当前账号/工作区可使用内置图片生成；
- Homebrew、Python 3.12 arm64、FFmpeg/ffprobe；
- 首次安装需要联网下载 Python 依赖与 dots.tts 模型；
- 默认 MF 模型及运行环境建议预留至少 12 GiB 可用空间。
- 其他可正常满足运行 codex 的可能型号设备

本仓库只提供本地使用方式，不包含 Gateway、Cloudflare、访问码、公网隧道、在线部署或远程多人服务。它也不是已签名、已公证的 macOS 安装包。

## 仓库构成

- `.agents/skills/short-video-director/`：Codex 可自动发现的仓库级短视频导演 Skill；
- `【包A】视频引擎包/`：Job Bundle、TTS 编排、静态镜头编码、ASS 字幕、缓存、报告与最终合成；
- `【包B】语音引擎包/`：基于 dots.tts 的本地 TTS 服务，只监听 `127.0.0.1:7860`；
- `【包A】视频引擎包/docs/short_video_v2/`：当前工作流、Schema、图片约定、核心管线与验收合同；
- `scripts/`：Apple Silicon Mac 源码安装与模型下载脚本。

模型权重、Python runtime、FFmpeg 二进制、真实配置、成片、缓存、日志和本机服务状态不会进入 Git。它们由安装脚本或实际任务在本机生成。

## 1. 克隆公开仓库

使用 HTTPS：

```bash
git clone https://github.com/shunbao-p/OneCue.git
cd OneCue
```

也可以使用已经配置好的 GitHub SSH：

```bash
git clone git@github.com:shunbao-p/OneCue.git
cd OneCue
```

## 2. 准备本地环境

```bash
brew install python@3.12 ffmpeg
python3 scripts/setup_macos_source.py --model mf
```

安装脚本会：

1. 拒绝非 Apple Silicon macOS；
2. 在包 B 内建立 `runtime/python`；
3. 安装锁定的 Python 依赖并以 editable 方式安装包 B；
4. 从固定 Hugging Face revision 下载默认 MF 模型；
5. 按仓库 manifest 校验每个模型文件的大小与 SHA-256；
6. 检查 FFmpeg/ffprobe 和核心 Python 导入。

模型校验失败时不要继续启动服务。质量版 SOAR 模型不是默认工作流所需，仅在另行比较音质时下载：

```bash
"【包B】语音引擎包/runtime/python/bin/python3.12" \
  scripts/download_macos_models.py --model soar
```

模型来源：

- [rednote-hilab/dots.tts-mf](https://huggingface.co/rednote-hilab/dots.tts-mf)
- [rednote-hilab/dots.tts-soar](https://huggingface.co/rednote-hilab/dots.tts-soar)

仓库只保存来源、固定 revision、文件大小与 SHA-256，不保存模型权重。

## 3. 启动本地服务

在仓库根目录执行：

```bash
"【包B】语音引擎包/runtime/python/bin/python3.12" -B \
  "【包B】语音引擎包/_internal/macos_launcher.py" \
  preflight --model dots-tts-mf

"【包B】语音引擎包/runtime/python/bin/python3.12" -B \
  "【包B】语音引擎包/_internal/macos_launcher.py" \
  start --model dots-tts-mf

python3.12 -B "【包A】视频引擎包/程序文件/connect_dots.py" \
  "$PWD/【包B】语音引擎包"

python3.12 -B "【包A】视频引擎包/程序文件/mac_launcher.py" \
  preflight --mode development

python3.12 -B "【包A】视频引擎包/程序文件/mac_launcher.py" \
  start --mode development
```

包 A 只监听 `127.0.0.1:8787`，包 B 只监听 `127.0.0.1:7860`。连接命令会在本机生成或更新 `【包A】视频引擎包/程序文件/config.ini`；该文件不会被 Git 跟踪。公共默认值位于 `config.example.ini`。

## 4. 在 Codex 中一句话生成视频

从本仓库根目录或其子目录打开 Codex。Skill 位于官方仓库级发现位置 `.agents/skills/short-video-director/`，不需要复制到个人 Skill 目录。

核对仓库 Skill 版本：

```bash
cat .agents/skills/short-video-director/VERSION
```

当前应输出：

```text
1.0.0
```

如果刚刚更新仓库而 Codex 尚未显示该 Skill，请重新打开 Codex 任务。随后输入一句话：

```text
用 $short-video-director 帮我生成一个 20–40 秒关于西瓜生长过程的中文竖屏短视频。
```

Skill 会导航现有主链完成内容规划、独立 Image 2 分镜、Schema v1 Job Bundle、包 B 人声、字幕、硬切与渲染，并在候选 `final.mp4` 准备好后暂停，等待使用者主观终审。它不会实现或启动另一套视频框架。

## 5. 停止服务

```bash
python3.12 -B "【包A】视频引擎包/程序文件/mac_launcher.py" stop
"【包B】语音引擎包/runtime/python/bin/python3.12" -B \
  "【包B】语音引擎包/_internal/macos_launcher.py" stop
```

## 手动校验与渲染 Job Bundle

```bash
cd "【包A】视频引擎包"
env "PYTHONPATH=$PWD/程序文件/引擎" \
  python3 -m video_v2 validate --job-dir "/absolute/path/to/job" --json
env "PYTHONPATH=$PWD/程序文件/引擎" \
  python3 -m video_v2 render --job-dir "/absolute/path/to/job" --json
```

Job Bundle 必须是自包含的 Schema v1 目录。权威合同见 `【包A】视频引擎包/docs/short_video_v2/job_bundle_v1.md`。

## 验证

核心本地发布门：

```bash
"【包B】语音引擎包/runtime/python/bin/python3.12" -m unittest \
  "【包A】视频引擎包/tests/test_director_workflow_docs.py" \
  "【包A】视频引擎包/tests/test_portable_config_baseline.py" \
  "【包A】视频引擎包/tests/test_v2_job_bundle_contract.py" \
  "【包A】视频引擎包/tests/test_v2_core_runtime.py" \
  "【包A】视频引擎包/tests/test_v2_core_pipeline.py" \
  "【包A】视频引擎包/tests/test_v2_mvp_acceptance.py" -v
```

包 B 测试：

```bash
"【包B】语音引擎包/runtime/python/bin/python3.12" -m unittest discover \
  -s "【包B】语音引擎包/tests" -p 'test_*.py' -v
```

README 未列出的旧平台兼容、发布构建与人工实机脚本不属于 v1.0.0 日常发布门；它们也不得改变静态分镜正式路线。

## 常见问题

- **Codex 找不到 Skill**：确认从仓库根目录或子目录打开项目；检查 `.agents/skills/short-video-director/SKILL.md`，然后重新打开 Codex 任务。
- **模型校验失败**：使用包 B runtime 重新运行 `scripts/download_macos_models.py --model mf`；脚本仍失败时不要启动服务。
- **缺少 Python 3.12**：执行 `brew install python@3.12`，并确认 `python3.12` 是 arm64。
- **缺少 FFmpeg**：执行 `brew install ffmpeg`，再确认 `ffmpeg` 和 `ffprobe` 可用。
- **端口占用**：先执行停止命令；包 A 启动器可选择其他本地端口，包 B 默认使用 7860。
- **磁盘不足**：清理与本项目无关的本机文件后重试；不要把模型或成片提交到 Git。
- **图片生成不可用或达到限额**：检查当前 Codex 账号与工作区的图片生成权限/用量，或手动提供每镜关键帧。

## 许可证

本项目自有代码与文档依根目录 [LICENSE](LICENSE) 采用 Apache License 2.0。包 B 及已发布 dots.tts checkpoints 同样声明为 Apache-2.0。其他依赖、字体与 FFmpeg 仍受各自许可证和归属要求约束，请同时阅读包内 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。
