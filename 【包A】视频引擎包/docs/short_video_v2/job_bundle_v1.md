# V2 Job Bundle Schema v1

本契约是 Codex 控制面与包 A V2 执行面的只读文件边界。两个输入 JSON 均使用整数 `schema_version: 1`；v1 验收后不可悄然扩展，未知字段会被拒绝。

## 目录与所有权

```text
job-<project_id>/
├── brief.md                    # 可选，只供人阅读
├── project.json                # 必需，只读输入
├── storyboard.json             # 必需，只读输入
├── style_bible.json            # 可选侧车，v1 不解析
├── characters.json             # 可选侧车，v1 不解析
├── references/                 # 可选；被引用时才校验
├── assets/keyframes/           # 必需输入素材，只读
├── audio/                      # 后续包 A 创建
├── shots/                      # 后续包 A 创建
├── captions/                   # 后续包 A 创建
├── cache/                      # 后续包 A 创建
├── evidence/                   # 后续包 A/质检创建
└── output/                     # 后续包 A 创建
```

验证命令不会创建任何运行产物目录，也不会修改输入文件。为避免异常巨大的 JSON 消耗本地资源，`project.json` 与 `storyboard.json` 各有 8 MiB 运行安全上限；此上限覆盖 v1 的 100 镜头及各字符串字段最大长度。

## `project.json`

必填字段为 `schema_version`、`project_id`、`title`、`language`、`canvas`、`defaults` 和 `captions`；`target_duration_sec` 可选，仅用于策划与报告，不拉伸语音。

- `project_id`：1–64 位小写字母、数字、点、下划线或连字符，首字符须为字母或数字。
- `language`：v1 固定 `zh-CN`。
- `canvas`：v1 固定 1080x1920、30 FPS。
- `defaults.voice`：安全的 `.wav` 文件名，不是路径；真实音色存在性由计划 03 的 TTS 预检负责。
- `defaults.timing`：头尾留白均为 0–3 秒有限数。
- `captions.style_preset`：v1 固定 `default_lower_third`。

## `storyboard.json`

顶层必填 `schema_version`、`project_id` 与 `shots`。`project_id` 必须与 `project.json` 相同；数组顺序就是时间顺序，镜头 ID 必须从 `shot-001` 连续排列，数量为 1–100。

每镜必填：

- `purpose`：叙事目的；
- `speech`：`narration|dialogue`、非空文本，可选镜头音色和 `speaker_id`；
- `visual.keyframe`：Bundle 内路径与真实 SHA-256；
- `visual.focus`：0–1 的主体焦点；
- `motion`：基础预设、`low|medium|high` 强度及可选意图；
- `caption`：`speech` 使用语音文本，`custom` 必须给文本，`none` 不得给文本；
- `transition_out`：`cut` 时长必须为 0；`crossfade` 为 0.1–1.0 秒；
- 可选 `timing` 覆盖项目默认留白；可选 `hero` 默认 `false`。

基础运动预设固定为：`static`、`slow_push_in`、`slow_pull_out`、`pan_left`、`pan_right`、`tilt_up`、`tilt_down`、`gentle_drift`。它们是高级工具缺失时仍可确定执行的语义，不代表绑定某个 Provider。

## 路径与完整性

JSON 中的文件路径统一使用 Bundle 内 POSIX 相对路径。允许中文和空格；拒绝空值、首尾空白、控制字符、反斜杠、URI、`~`、`.`/`..` 段、POSIX/Windows/UNC 绝对路径、解析后越界，以及 Bundle 根、祖先或目标符号链接。

关键帧只接受 `.png`、`.jpg`、`.jpeg`、`.webp`；必须存在、为非空常规文件，并与声明的 64 位小写 SHA-256 一致。哈希不匹配是错误，不能降为警告。

## 稳定错误与接口

Python 公共入口：

```python
from video_v2 import load_job_bundle, validate_job_bundle
```

- `validate_job_bundle(path)` 返回 `ValidationResult`，收集可预期问题。
- `load_job_bundle(path)` 返回不可变、已归一化的 `JobBundle`；无效时抛 `JobBundleValidationError`，其 `issues` 为结构化错误。

错误对象包含稳定 `code`、`document`、`location` 与可改进措辞的 `message`。v1 错误码包括：`bundle.root_invalid`、`bundle.file_missing`、`json.invalid`、`schema.version_unsupported`、`schema.required`、`schema.unknown_field`、`schema.type_invalid`、`schema.value_invalid`、`schema.condition_failed`、`project.id_mismatch`、`shot.id_duplicate`、`shot.order_invalid`、`path.format_invalid`、`path.outside_bundle`、`path.symlink_forbidden`、`asset.missing`、`asset.type_unsupported`、`asset.hash_mismatch`。

CLI：

```bash
cd "【包A】视频引擎包/程序文件/引擎"
"../runtime/bin/python3" -B -m video_v2 validate --job-dir "/absolute/job/path" --json
```

有效任务退出 0；可预期契约错误退出 2；验证器内部异常退出 1。`--json` 的 stdout 只输出一个 JSON 对象。内部异常沿用同一信封并使用 `internal.error`；该码只属于 CLI 故障面，不属于 `validate_job_bundle()` 的输入契约 issue 集合。

## 明确排除

v1 不提供服务 URL、网络素材、任意命令、FFmpeg/filtergraph、输出绝对目录、高级 Provider 私参、BGM、环境音或 SFX。有效发声区检测、尾静音裁剪、缓存键、报告 Schema、HTTP API 与正式渲染均由后续计划决定。
