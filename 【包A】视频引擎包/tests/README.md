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

短视频 V2 Job Bundle Schema v1 契约测试：

```text
程序文件/runtime/bin/python3 -B -m unittest discover -s tests -p 'test_v2_job_bundle_contract.py' -v
```

只读校验一个任务包：

```text
cd 程序文件/引擎
../runtime/bin/python3 -B -m video_v2 validate --job-dir "/absolute/path/to/job" --json
```

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

## 短视频 V2 核心管线

计划 03 的默认单元/短媒体测试：

```text
程序文件/runtime/bin/python3 -B -m unittest discover -s tests -p 'test_v2_core_runtime.py' -v
程序文件/runtime/bin/python3 -B -m unittest discover -s tests -p 'test_v2_core_pipeline.py' -v
```

真实 TTS、缓存登记与三镜头显式 e2e 只由 `run_v2_core_e2e.py` 子命令触发，不参与默认 discovery，避免无意重复昂贵模型工作。正式渲染命令与 0/2/3/130/1 退出码见 `docs/short_video_v2/core_pipeline_v1.md`。

核心当前只支持对一个 Job Bundle 单写；不要并发渲染同一任务目录。失败或取消应查阅 `output/render_report.json`，并保留旧的有效 WAV、镜头和 final。

## 短视频 V2 计划 04 可行性实验（历史、非第一版日常门）

以下仅用于复核旧隔离实验协议、评分模板与 FFmpeg 基线，不由当前静态工作流自动运行：

```text
程序文件/runtime/bin/python3 -B -m unittest discover -s tests -p 'test_v2_phase4_feasibility.py' -v
```

实验入口和输出布局见 `experiments/short_video_v2_phase4/README.md`。模型、浏览器、原始/标准化视频及 run manifest 只写入被忽略的 `成片/短视频V2样片/phase4-image-motion/`，不得写入正式 Job Bundle 的缓存 manifest。
