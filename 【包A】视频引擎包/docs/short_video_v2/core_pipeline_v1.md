# 短视频 V2 核心管线 v1

本文描述包 A 的本地渲染核心。它只读取已通过 Schema v1 验证的 Job Bundle，逐镜生成人声、字幕与基础运镜，再以 FFmpeg 合成 `output/final.mp4`。本版不提供 Web API，不接入 BGM、环境音、SFX 或高级图片动态化。

## Python 入口

```python
from video_v2.pipeline import render_job

result = render_job(
    "/absolute/path/to/job",
    selected_shot_ids=None,
    force=False,
    cancel_event=None,
    on_event=None,
    tts_provider=None,
    runtime=None,
)
print(result.to_dict())
```

`render_job` 始终首先调用 `load_job_bundle()`，只消费已归一化的 `JobBundle` 和 `ShotSpec`；它不重读 JSON、不绕过素材路径与 SHA-256 校验。默认 TTS Provider 使用包 B Python 直接调用包 A 既有 `dots_synth.py`，不回调包 A Web。

`RenderResult` 包含状态、run id、项目与镜头数、final 相对路径/哈希/时长、三层缓存摘要、warnings 和 errors，并提供 `to_dict()`。输入契约错误抛 `JobBundleValidationError`；可预期运行错误抛 `RenderError`；取消抛 `PipelineCancelled`。

## 产物与验证

```text
job/
├── audio/<shot-id>.wav
├── captions/<shot-id>.ass
├── shots/<shot-id>.mp4
├── cache/manifest.json
└── output/
    ├── final.mp4
    └── render_report.json
```

WAV、镜头、final 和 JSON 均先写本 run 的同目录临时文件。媒体须通过 ffprobe、完整解码、规格/时长检查和 SHA-256 计算，JSON 须能重新解析，才以 `os.replace` 原子提交。失败或取消只清理本 run 的临时文件，不覆盖旧的有效 WAV、镜头或 final。

单镜头固定输出 1080×1920、30 FPS、H.264/yuv420p、AAC 48 kHz 双声道。镜头时长以真实 WAV 时长加头尾留白为准；镜头误差不超过 0.15 秒，final 相对时间线误差不超过 0.20 秒。

## 缓存与选择性重渲

`cache/manifest.json` 为内部索引，分为 audio、shots 和 final 三层。每次命中仍会核对相对路径、实际文件哈希与最小媒体规格；索引损坏或产物不匹配时不会误命中。

- audio key：文本、音色、Provider 名称/版本与固定选项版本。
- shot key：关键帧实际哈希、WAV 实际哈希/时长、焦点、运镜、可见字幕、留白、画布与渲染器版本。
- final key：有序镜头产物哈希、有效转场序列、合成器与输出规格版本。

`purpose`、`motion_intent`、`hero` 和 `target_duration_sec` 只进报告，不使渲染缓存失效。

`selected_shot_ids=None` 会评估全部依赖。指定镜头时，管线只允许生成所选镜头的新 TTS/镜头；未选镜头必须已有哈希有效的缓存，否则以 `pipeline.dependency_missing` 失败。`force=True` 在完整渲染中禁用全范围复用，在选择性渲染中只禁用所选镜头的 audio/shot 复用。

## 取消、进度与并发限制

`cancel_event` 可为 `threading.Event` 或兼容对象。管线在阶段边界检查它，外部进程也会在执行期间检查；取消时先 terminate，限时后再 kill。`on_event` 接收包含 `code`、`stage`、`run_id` 及可选 `shot_id` 的结构化字典。回调异常不会取代真实渲染结果。

core v1 只支持单进程写一个 Job Bundle；不应同时对同一目录发起两次渲染。队列、后台任务和跨进程取消属于后续 Web 计划。

## CLI 与错误

```bash
cd "【包A】视频引擎包/程序文件/引擎"
"../runtime/bin/python3" -B -m video_v2 render \
  --job-dir "/absolute/path/to/job" \
  --json

# 仅重新评估 shot-003；可重复 --shot
"../runtime/bin/python3" -B -m video_v2 render \
  --job-dir "/absolute/path/to/job" \
  --shot shot-003 --json
```

render 退出码：成功 `0`；Job Bundle 契约错误 `2`；可预期运行失败 `3`；取消 `130`；未预期内部错误 `1`。`--json` 模式的 stdout 只有最终一个 JSON envelope，进度写 stderr。可预期错误使用稳定代码，详细证据可查 `output/render_report.json`。

