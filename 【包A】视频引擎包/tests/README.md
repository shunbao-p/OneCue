# Phase 0 / Phase 1 回归护栏

本目录冻结包 A 当前 Windows 行为，并对 Phase 1 的薄平台边界模拟 Windows / Darwin 分支。测试不访问包 B，也不把模拟 Darwin 当成真实 Mac 验收。

## 运行

从 `【包A】视频引擎包` 目录执行：

```text
Windows 便携运行时：
程序文件\runtime\python.exe -m unittest discover -s tests -v

WSL / Linux 主机 Python：
python3 -m unittest discover -s tests -v
```

`generate_fixtures.py` 只用于以标准库确定性生成两个很小的 PCM WAV 夹具。测试不会自动重写 ASS 快照。

## 范围

- 对齐：文本切块、精确 0.25 秒数字静音、匹配与不匹配。
- 字幕：清洗、分词、时间线、卡片、固定 seed 的完整 ASS 快照。
- Web：MP4 最小有效性、错误 WAV、包 B 未安装、TTS 友好拒绝。
- Windows 边界：便携 Python/FFmpeg 路径、FFmpeg 参数、端口顺延、`.bat` 启动契约。
- 平台边界：系统识别，显式配置 → 随包工具 → PATH → 受控候选的解析顺序，缺失/错误路径，中文空格路径，Windows/Darwin 字体环境。
- 系统操作：Finder/Explorer、浏览器、端口候选、监听诊断和进程终止命令均只构造参数数组，不使用拼接 shell。
- 降级契约：Darwin 下即使给出伪 Windows 包 B 目录，仍报未安装且不扫描盘符。
- 真实短片：由包内 Windows Python 与 FFmpeg 生成，证据保存在 `evidence/`。

`ffprobe` 当前不存在，因此 Phase 0 使用 FFmpeg 自身读取成片并记录等价流元数据；这不替代 Phase 2 的 Mac 原生 ffprobe 验收。

## Phase 5 实机验收

最终 macOS 发布包使用外部 HTTP 客户端运行 `run_phase5_mac_acceptance.py`，覆盖 44.1/48 kHz 单双声道、Unicode/特殊字符、损坏/错配、连续 10 任务、双并发、停止、60 秒和 10 分钟性能。Windows 使用 `run_phase5_windows_http.py` 做真实生成、下载和媒体解码回归。

场景矩阵、机器报告和人类报告位于 `evidence/phase5-macos-019fe9b7/`。脚本不访问包 B；macOS 报告中的原始进程、媒体和原生应用证据保存在目标机对应证据目录。
