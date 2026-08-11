# 文本视音屏生成器 · macOS Apple Silicon 版本

这是从原始 Windows 项目改造出的 macOS Apple Silicon 版本，当前目标为
M1/M2/M3/M4 等 arm64 Mac。项目由两个本地包组成：

- `【包A】视频引擎包`：文字、素材、音频到视频的生成和网页界面。
- `【包B】语音引擎包`：基于 dots.tts 的本地文字转语音服务，通过
  `127.0.0.1:7860` 与包 A 通信。

本仓库只保存源码、启动器、配置、测试、许可证和模型清单，不保存多 GB
模型权重、内置 Python、FFmpeg 二进制、Windows 环境、缓存或日志。这样可以
避免 GitHub 单文件限制，也避免把平台相关运行环境误当作源码发布。

## 快速准备

在 Apple Silicon Mac 的终端执行：

```bash
brew install python@3.12 ffmpeg
python3.12 scripts/setup_macos_source.py --model mf
```

首次准备会：

1. 在包 B 内创建 `runtime/python`，使用 Python 3.12 arm64；
2. 按 `【包B】语音引擎包/constraints/macos-arm64-py312.lock` 安装锁定依赖；
3. 以 editable 方式安装包 B 源码；
4. 下载 `rednote-hilab/dots.tts-mf`；
5. 按 `manifests/macos-mf-model.json` 校验每个文件的大小和 SHA-256。

质量版模型体积很大且速度更慢，可另外执行：

```bash
python3.12 scripts/download_macos_models.py --model soar
```

两个模型都下载：

```bash
python3.12 scripts/download_macos_models.py --model all
```

模型下载失败、文件不完整或上游模型内容已变化时，脚本会返回错误，不能
通过校验的模型不会被当作可运行模型使用。模型来源为：

- [dots.tts-mf](https://huggingface.co/rednote-hilab/dots.tts-mf)
- [dots.tts-soar](https://huggingface.co/rednote-hilab/dots.tts-soar)

模型本身遵循上游仓库的许可和使用限制；发布本项目时请同时阅读其模型页及
`【包B】语音引擎包/LICENSE`。

## 启动源码版本

源码仓库不是已经打包好的最终用户发布包，因此使用开发模式启动。先启动包 B：

```bash
cd "【包B】语音引擎包"
runtime/python/bin/python3.12 -B _internal/macos_launcher.py preflight --model dots-tts-mf
runtime/python/bin/python3.12 -B _internal/macos_launcher.py start --model dots-tts-mf
```

再启动包 A：

```bash
cd "【包A】视频引擎包"
python3.12 -B "程序文件/mac_launcher.py" preflight --mode development
python3.12 -B "程序文件/mac_launcher.py" start --mode development
```

如果 FFmpeg 不在 PATH 中，可显式指定：

```bash
python3.12 -B "程序文件/mac_launcher.py" start --mode development \
  --ffmpeg "$(command -v ffmpeg)" \
  --ffprobe "$(command -v ffprobe)"
```

包 A 和包 B 放在同一目录时，可执行：

```bash
python3.12 -B "【包A】视频引擎包/程序文件/connect_dots.py" \
  "$(pwd)/【包B】语音引擎包"
```

如果只使用现有 WAV 制作视频，可以不启动包 B。停止服务：

```bash
runtime/python/bin/python3.12 -B _internal/macos_launcher.py stop
python3.12 -B "【包A】视频引擎包/程序文件/mac_launcher.py" stop
```

## 运行测试

包 A 的纯契约测试：

```bash
python3.12 -m unittest discover -s "【包A】视频引擎包/tests" -p 'test_*.py'
```

包 B 的运行策略和 API 契约测试：

```bash
cd "【包B】语音引擎包"
runtime/python/bin/python3.12 -m unittest discover -s tests -p 'test_*.py'
```

## 从源码构建可分发包

如需给普通用户使用，应在 Apple Silicon Mac 上按
`【包A】视频引擎包/macOS使用与构建说明.md` 构建带受控 Python、FFmpeg、
ffprobe 和模型的发布包。源码仓库不等同于已经签名、公证的安装包。

当前版本仍未处理 Developer ID 签名和 Apple 公证。

## 项目来源与修改说明

本项目基于原始 Windows 项目进行 macOS Apple Silicon 适配，主要改动包括：

- macOS 启动、停止、端口和路径处理；
- MPS/float32 运行策略；
- 包 A 与包 B 的本机 HTTP 串联；
- macOS FFmpeg 和 Python 运行时边界；
- 子进程 stdout/stderr 并发消费，避免管道满导致低概率死锁。

原始项目及第三方组件的版权、许可证和商标声明仍然有效。包 B 当前明确
使用 Apache License 2.0；修改过的文件应以 Git 历史和文件中的说明为准。
