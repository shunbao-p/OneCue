# 包 B Apple Silicon macOS 使用说明

## 适用范围

- Apple Silicon Mac（arm64），已在 M1 Pro、32 GiB 内存上验收。
- 包内自带 Python 3.12 arm64、PyTorch、ffmpeg 和 ffprobe，不使用包 A 的 Python，也不要求 Homebrew 或系统 Python 作为普通用户前置。调整语速时会优先使用可选的 Rubber Band；未安装时自动使用包内 ffmpeg，无需额外配置。
- 推理使用 PyTorch MPS、float32；不会静默回退到 CPU。

## 启动

1. 首次使用先双击 `启动-快速版.command`。
2. 等待浏览器打开 `http://127.0.0.1:7860`。首次模型加载会比后续请求慢。
3. 与包 A 联用时，保持包 B 已启动，再双击包 A 的 `②连接语音引擎.command`。
4. 包 A 与包 B 使用各自独立运行时，只通过本机 `127.0.0.1` HTTP 通信。

## 两种模型

- 快速版 `dots-tts-mf`：默认生产路径，4 步 MeanFlow，适合日常本地生成和包 A 联合出片。
- 质量版 `dots-tts-soar`：10 步质量模型，可以在 MPS 上正确生成，但明显更慢；不适合作为实时路径。在 M1 Pro 实测稳态 RTF 约 9.4。

两种模式不能同时占用默认端口 7860。切换模型前应先停止当前包 B 服务，再启动另一模式。

## 内置测试音色

- 名称：`女播音.wav`
- 转写：`我相信很多听友听到这首歌应该是在96年90年代的那个夏天`
- 该音色来自包内既有素材；本次 macOS 适配没有加入新的真人录音。

## 已知限制

- 快速版在 M1 Pro 上连续 10 次合成的稳态中位 RTF 为 2.82455，属于可用但非实时级速度。
- 人工试听发现超过 200 字的分段长文可能出现局部音量突然变小；短句、数字、标点和包 A 联合样本正常。该问题不影响文件生成或 A+B 视频链路，当前作为低优先级限制保留。
- 当前包未签名、未公证。本地技术使用不受影响；公开分发给普通用户前仍需独立完成 Developer ID 签名、公证和 Gatekeeper 验证。

## 故障诊断

终端中进入包 B 根目录后，可使用：

```bash
runtime/python/bin/python3.12 _internal/macos_launcher.py preflight --model dots-tts-mf
runtime/python/bin/python3.12 _internal/macos_launcher.py status
runtime/python/bin/python3.12 _internal/macos_launcher.py stop
```

日志位于 `logs/gradio.log`。启动器只会停止身份、启动时间、工作目录和端口均匹配的本包进程；状态不一致时不会盲目终止其他进程。
