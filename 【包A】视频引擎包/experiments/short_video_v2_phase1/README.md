# 短视频 V2 计划 01：隔离实验渲染器

此目录只用于“Mac 基线与三镜头技术样片”。它不会被包 A 正式 Web 入口导入，也不代表正式 V2 Schema/API。

## 能力边界

- 读取恰好三个镜头的临时 `storyboard.sample.json`。
- 拒绝任务目录外路径、未知字段、未知运镜预设和空旁白。
- 通过包 A 现有 `/api/tts` 链路调用包 B MF，按实际 WAV 时长确定镜头长度。
- 只提供 `static`、`slow_push_in`、`gentle_drift`、`slow_pull_out` 四个固定 FFmpeg 预设。
- 生成镜头级/合并 ASS、三个标准镜头、硬切 `final.mp4`、代表帧、联系表与 JSON 报告。
- 只使用 Python 标准库和包 A 随包 FFmpeg/ffprobe；所有外部命令均为参数数组，不启用 shell。
- 不含 BGM、环境音、SFX、I2V、高级 Provider、正式缓存或正式状态机。

## 运行

从项目根目录执行：

```bash
V2_SAMPLE_DIR="/Users/yuh/Desktop/项目/文本视音屏生成器/【包A】视频引擎包/成片/短视频V2样片/phase1-three-shot"

"【包A】视频引擎包/程序文件/runtime/bin/python3" -B \
  "【包A】视频引擎包/experiments/short_video_v2_phase1/render_sample.py" \
  --job-dir "$V2_SAMPLE_DIR" \
  --storyboard "$V2_SAMPLE_DIR/storyboard.sample.json" \
  --package-a-url "http://127.0.0.1:8787" \
  --ffmpeg "【包A】视频引擎包/程序文件/bin/ffmpeg" \
  --ffprobe "【包A】视频引擎包/程序文件/bin/ffprobe"
```

默认拒绝覆盖不能由既有实验报告证明可复用的关键产物。只有明确要重做本实验受管产物时才传 `--overwrite`。

## 测试

```bash
"【包A】视频引擎包/程序文件/runtime/bin/python3" -B -m unittest discover \
  -s "【包A】视频引擎包/tests" -p "test_v2_phase1_sample.py"
```

