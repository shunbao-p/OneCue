# 短视频 V2 计划 04 隔离实验

本目录只承载图片与单镜头动态化的可行性验证，不属于包 A 正式管线。实验输入、原始输出、标准化输出、日志与 manifest 都写入被 `**/成片/` 忽略的工作区；不得写入正式 Job Bundle 的 `cache/manifest.json`。

## 固定边界

- 三图基准：`portrait`、`architecture`、`landscape`。
- 比较规格：4 秒、1080x1920、30 FPS、H.264、yuv420p、无字幕、无音频。
- FFmpeg 是默认基线；高级工具只生产单镜头视觉候选。
- 所有外部命令都经 `video_v2.runtime.CommandRunner` 以 `list[str]`、`shell=False` 执行。
- 每个 run 使用独立 `run_id`，分开保存 `raw/`、`normalized/` 与 `manifest.json`；已存在 run 拒绝覆盖。
- 不读取或写入 OpenAI API 密钥，不生成 BGM/SFX/TTS，不修改 Schema、正式缓存、时间线、字幕或 final。
- MFLUX、DepthFlow、HyperFrames、Draw Things/I2V 只有在获得下载/安装授权并实际进入实验时才新增 adapter；不要预留空壳模块。

## FFmpeg 基线

从包 A 根目录执行：

```text
程序文件/runtime/bin/python3 -B experiments/short_video_v2_phase4/benchmark.py \
  --provider ffmpeg \
  --case architecture \
  --input "/absolute/path/architecture.png" \
  --work-dir "/absolute/path/phase4-image-motion" \
  --duration 4 \
  --preset slow_push_in \
  --strength low \
  --focus-x 0.5 \
  --focus-y 0.5
```

程序会输出 JSON envelope，并在 `work-dir/ffmpeg/<case>-<run-id>/` 留下原始片、标准化片和 manifest。`manifest.json` 记录实际 argv、工具版本、墙钟、峰值资源、输入/输出哈希与媒体摘要。

## 测试

```text
程序文件/runtime/bin/python3 -B -m unittest discover -s tests -p 'test_v2_phase4_feasibility.py' -v
```

媒体视觉评分以 `templates/visual_scorecard.json` 为准。0–3 分只描述原始结果，不用锐化、插帧、重绘或强后处理掩盖工具缺陷。
