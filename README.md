# OneCue · 文本到短视频工作流

OneCue 是一套面向 Apple Silicon Mac 的本地短视频 MVP：Codex 负责理解内容、文案与分镜，Image 2 生成逐镜图片，包 B 生成逐镜人声，包 A/FFmpeg 校验 Schema v1 Job Bundle 并合成竖屏视频。当前已能从一段自然语言需求推进到候选成片，并保留校验、缓存、执行报告和镜头级返修能力。

当前不使用 BGM；音频只来自包 B 的解说或角色对话。基础动态仍是 FFmpeg 虚拟摄影机推拉、平移与轻漂移，并非物体级自然动画；雨落、流水、人物动作等尚未实现。这是当前最明显的质量边界，不在此处夸大。

## 系统构成

- `【包A】视频引擎包`：Job Bundle 契约、TTS 编排、ASS 字幕、基础运镜、转场、缓存、报告与最终合成。
- `【包B】语音引擎包`：基于 dots.tts 的本地 TTS 服务，默认监听 `127.0.0.1:7860`。
- `skills/short-video-director`：可选但强烈推荐的 Codex 薄导演层，识别策划、新建、续接、检查、渲染和返修模式；它不实现另一套视频能力。
- `【包A】视频引擎包/docs/short_video_v2`：V2 的权威工作流、Schema 说明、图片约定、核心管线、动态边界与验收文档。

## 仓库不包含的内容

模型权重、内置 Python、FFmpeg/ffprobe 二进制、Windows `wzf` 环境、成片、缓存、日志、临时文件和本机服务状态不进入 Git。这些内容可在本地由安装脚本、实际任务或发布构建重建，从而避免仓库膨胀与 GitHub 单文件限制。

## 环境要求

- Apple Silicon Mac（arm64），macOS 11 或更高版本；
- Homebrew；
- Python 3.12 arm64 和 FFmpeg；
- 默认 MF 模型需要数 GiB 下载与本地存储，建议预留至少 12 GiB 可用空间；
- 若要从自然语言一次生成候选短片，需在支持 Image 2 图片生成的 Codex 会话中使用本项目 Skill；也可手动提供关键帧。

## 从私有仓库克隆

先保证 GitHub SSH 账号有访问权限，再执行：

```bash
git clone git@github.com:shunbao-p/OneCue.git
cd OneCue
```

## 准备源码运行环境

```bash
brew install python@3.12 ffmpeg
python3.12 scripts/setup_macos_source.py --model mf
```

该脚本会在包 B 内创建 `runtime/python`，安装锁定依赖，以 editable 方式安装包 B，下载 `rednote-hilab/dots.tts-mf`，并按仓库中的 manifest 校验大小与 SHA-256。校验不通过时不应启动服务。

可选质量版模型速度更慢、占用更大：

```bash
python3.12 scripts/download_macos_models.py --model soar
```

模型来源：[dots.tts-mf](https://huggingface.co/rednote-hilab/dots.tts-mf) 与 [dots.tts-soar](https://huggingface.co/rednote-hilab/dots.tts-soar)。模型本身遵循各自上游页面的许可与使用条件。

## 启动包 B 和包 A

从仓库根目录执行：

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

包 A 默认使用 `127.0.0.1:8787`。连接脚本会把当前包 B 绝对路径写入本机 `config.ini`；该本机路径不应提交到共享分支。

停止服务：

```bash
python3.12 -B "【包A】视频引擎包/程序文件/mac_launcher.py" stop
"【包B】语音引擎包/runtime/python/bin/python3.12" -B \
  "【包B】语音引擎包/_internal/macos_launcher.py" stop
```

## 安装可选 Codex Skill

Skill 已随仓库版本化，不需要额外下载视频框架。在仓库根目录执行：

```bash
onecue_skill_root="${CODEX_HOME:-$HOME/.codex}/skills/short-video-director"
mkdir -p "$onecue_skill_root"
cp -R skills/short-video-director/. "$onecue_skill_root/"
```

重新打开 Codex 任务后，可直接说：

```text
用 $short-video-director 帮我生成一个 20–40 秒关于西瓜生长过程的中文竖屏短视频。
```

Skill 会导航现有 Codex → Image 2 → 包 B → 包 A/FFmpeg 链路，在候选成片准备好后留给用户审片。没有 Skill 时主链仍可依据 `director_workflow_v1.md` 手动执行。

## 手动校验与渲染 Job Bundle

```bash
cd "【包A】视频引擎包"
env "PYTHONPATH=$PWD/程序文件/引擎" \
  python3 -m video_v2 validate --job-dir "/absolute/path/to/job" --json
env "PYTHONPATH=$PWD/程序文件/引擎" \
  python3 -m video_v2 render --job-dir "/absolute/path/to/job" --json
```

Job Bundle 必须是自包含的 Schema v1 目录。请先阅读 `【包A】视频引擎包/docs/short_video_v2/job_bundle_v1.md`。

## 测试

包 A 当前支持的 Mac/V2 契约测试：

```bash
"【包B】语音引擎包/runtime/python/bin/python3.12" -m unittest \
  "【包A】视频引擎包/tests/test_director_workflow_docs.py" -v
"【包B】语音引擎包/runtime/python/bin/python3.12" -m unittest discover \
  -s "【包A】视频引擎包/tests" -p 'test_v2_*.py' -v
```

包 B 的运行策略与 API 契约测试：

```bash
"【包B】语音引擎包/runtime/python/bin/python3.12" -m unittest discover \
  -s "【包B】语音引擎包/tests" -p 'test_*.py' -v
```

包 A 目录仍保留原 Windows 边界测试；它们中有断言在 macOS 上会刻意期待 `ffmpeg.exe` 和 `C:/Windows/Fonts`，因此不属于上述 Mac/V2 发布门。

只想检查 Skill 结构时，可用当前 Codex 的 Skill Creator `quick_validate.py` 对 `skills/short-video-director` 执行校验。

## 发布边界

此仓库是源码与工作流仓库，不是已签名、已公证的 macOS 最终用户安装包。如需构建包含受控 Python、FFmpeg、ffprobe 和模型的发布包，请阅读 `【包A】视频引擎包/macOS使用与构建说明.md`。当前尚未处理 Developer ID 签名与 Apple 公证。

## 许可证

本项目自有修改与文档依根目录 [LICENSE](LICENSE) 采用 Apache License 2.0。仓库中已有的上游项目、模型、字体、依赖和可选 FFmpeg 发布构建仍受各自许可、归属和使用条件约束；请同时阅读包内 `LICENSE` 及 `THIRD_PARTY_NOTICES.md`。
