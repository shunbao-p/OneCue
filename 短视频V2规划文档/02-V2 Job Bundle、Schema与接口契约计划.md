# 短视频 V2 实施计划 02：V2 Job Bundle、Schema 与接口契约

> 文档性质：可直接执行的阶段计划。
>
> 上位依据：`短视频V2规划文档/短视频V2总体目标与阶段规划.md`。
>
> 前置证据：`短视频V2规划文档/执行记录/01-Mac基线与三镜头技术样片执行记录.md`、计划 01 的实验代码、正式样片任务目录与 `render_report.json`。
>
> 本计划只把已经跑通的三镜头经验沉淀为正式、版本化、可执行验证的 V2 任务契约；它不实现包 A V2 正式渲染管线、Web API/UI、高级图片动态化 Provider、BGM/SFX，也不重构包 B。

---

## 1. 前置阶段结论

### 1.1 计划 01 验收结论

计划 01 判定为 **PASS**，可进入本计划。依据不是单一日志，而是以下证据共同成立：

- 包 A 与包 B 在当前 Mac 上真实运行，包 A 可调用包 B MF 路径生成三段 WAV；
- 三个镜头与最终视频均已生成，完整解码通过；
- 最终片为 H.264、1080x1920、30 FPS、yuv420p、AAC 48 kHz；
- 三个镜头使用 `slow_push_in`、`gentle_drift`、`slow_pull_out`，满足计划 01 的“基础可见运镜”门；
- 字幕溢出已经在唯一一次修复循环中解决，新增测试为 10/10 通过；
- `final.mp4` 已在 QuickTime 中从头至尾实际播放，无中断或解码警告；
- `render_report.json` 的 `quality_gate.status` 为 `PASS`，且 `plan_02_allowed` 为 `true`；
- 用户已经实际观看成片，并确认图片、声音与完整成片基本满足当前要求。

### 1.2 图片动态化问题的阶段归属

用户指出图片动态处理仍不够理想，此观察成立，但不构成计划 01 失败，也不阻塞本计划，原因如下：

1. 计划 01 明确只验证 FFmpeg 基础轻运镜，不要求 2.5D 视差、分层动画或生成式 I2V；
2. 三种轻运镜已经可见，人物未持续越出安全区，达到了原计划的最低动态门；
3. 高级图片动态化的工具、质量与耗时验证原本属于第 04 份《图片生成与高级动态化可行性计划》；
4. 本计划只需让契约保留“语义化动态意图、稳定基础预设、强度、焦点与未来替换空间”，不能因当前观感一般而提前安装或绑定高级工具。

因此，本问题应记作后续动态化计划的设计输入，不回改计划 01，也不扩张计划 02。

### 1.3 计划 01 留给本计划的有效事实

- 临时 `storyboard.sample.json` 已证明以下最小信息确有用途：标题、画布、帧率、默认音色、镜头 ID、旁白、关键帧、运镜预设、主体焦点、头尾留白与字幕；
- 镜头时长必须以真实 WAV 时长为主，再叠加头尾留白，而非以文案预估强制拉伸语音；
- 三个镜头实际目标/输出时长误差均远低于 0.15 秒；
- 图片、旁白、字幕、渲染器版本等输入需要进入镜头缓存键或报告；
- 路径逃逸、绝对路径、越界符号链接、未知字段、重复镜头 ID、非法运镜预设必须在执行前拒绝；
- 字幕需允许自动使用语音文本，也需保留单镜头自定义或关闭的语义；
- 包 A TTS 接口当前可用，但服务 URL、FFmpeg 路径和任意 filtergraph 不应由任务包自由注入；
- 包 B 自然尾音加配置留白会产生约 0.69–0.93 秒尾端静音。正式契约保留头尾留白语义，但“有效发声区检测、尾静音裁剪阈值”留给计划 03 的内部实现与实测，不在 Schema 中暴露底层算法参数；
- 实验 JSON 只服务三镜头样片，不应被原样扩张为永久正式契约。

---

## 2. 计划目标

### 2.1 核心目标

建立 V2 Job Bundle Schema v1，使 Codex 与包 A 之间形成一个稳定、可验证、可测试的文件接口：

1. 冻结 `project.json` 与 `storyboard.json` 的字段、默认值、枚举与条件规则；
2. 冻结 Job Bundle 的输入、运行产物和输出目录所有权；
3. 提供 JSON Schema Draft 2020-12 文件，供编辑器、文档和外部工具理解结构；
4. 在包 A 内建立独立、纯标准库的 Python 契约模块，完成结构、跨文件、路径与哈希校验；
5. 提供只读 CLI 校验入口和稳定 JSON 结果；
6. 建立明确错误码、版本兼容策略、有效/无效测试夹具和契约测试；
7. 把计划 01 的三镜头事实迁移成一份符合正式契约的示例任务包，以证明设计不是纸上结构；
8. 为计划 03 的 V2 核心管线提供唯一的任务加载入口，避免未来 CLI、Web API 与渲染器各写一套校验。

### 2.2 本阶段成功判定

同时满足以下条件，方可判定本计划完成：

- 两份 Schema 均为有效 JSON，具备稳定 `$id`、`$schema` 与 `schema_version=1` 约束；
- 一份最小有效任务包与一份计划 01 事实迁移任务包均通过 Python 校验和 CLI 校验；
- 缺文件、错误 JSON、未知字段、版本错误、路径逃逸、Windows 绝对路径、符号链接、素材缺失、哈希不匹配、重复/乱序镜头等均返回预期稳定错误码；
- 中文、空格和常见标点可以正常存在于标题、文案、字幕和素材文件名中；
- Schema 与 Python 常量、枚举、必填字段之间有自动一致性测试；
- 校验过程不修改任务包，不创建输出目录，不调用包 B，不启动渲染；
- 不新增第三方 Python 依赖，不修改包 B，不破坏 V1；
- 新增测试全部通过，包 A 全量测试未出现本计划造成的新回归；
- 执行记录完整说明实际决定、改动、测试、已知基线失败和计划 03 输入。

### 2.3 本阶段不是要完成什么

本计划不要求：

- 用正式 V2 内核重新渲染成片；
- 实现镜头级 TTS、时间线、字幕渲染、转场、缓存、取消或重渲；
- 新增 `/api/v2/*` Web 接口或修改现有网页；
- 安装或验证 DepthFlow、HyperFrames、MFLUX、Draw Things、本地 I2V；
- 改善计划 01 的图片动态观感；
- 为 BGM、环境音、SFX 预留暗字段；
- 冻结高级 Provider 的底层参数；
- 处理认证、签名、公证、自动停止、包 B `ResourceWarning` 等不影响本阶段的问题；
- 修复包 A 旧 Windows 测试中的 `ffmpeg.exe`、`python.exe`、`C:/Windows/Fonts` 硬编码，除非本计划确实触及同一契约且修复极小、证据充分；
- 进行完整发布包构建、长时间耐久或视觉质量验收。

---

## 3. 当前工程事实与约束

### 3.1 工作树保护

当前仓库并非干净工作树。至少存在以下已修改或未跟踪内容：

- 包 A `程序文件/config.ini`；
- 包 B `apps/gradio/service.py`、`macOS使用说明.md`、`tests/test_phase3_api_contract.py`；
- 包 A 计划 01 的 `experiments/short_video_v2_phase1/` 与 `tests/test_v2_phase1_sample.py`；
- A/B 发布信息、服务状态文件、规划文档和执行记录。

执行本计划时必须先重新读取 `git status --short` 与相关 diff，只新增或修改本计划明确负责的文件，不得回退、覆盖、删除或顺手整理用户及前序计划的工作。

### 3.2 运行时与依赖边界

- 包 A 当前 Mac 运行时为 Python 3.13.13；
- 包 A 正式 Web 服务保持纯标准库；
- 包 A 随包 FFmpeg/ffprobe 为 8.1.2 arm64，但本计划的契约校验不依赖 FFmpeg；
- 包 A 发布构建脚本会递归复制 `程序文件/引擎/`，故新的 `video_v2` 包放在该目录下即可自然进入未来发布产物，无须为本计划改写发布布局；
- 现有测试使用 `unittest`，本计划沿用，不引入 pytest、Pydantic、jsonschema 等依赖；
- JSON Schema 是机器可读结构契约；运行时由标准库校验器执行同等结构规则，并额外处理跨文件、路径、哈希和条件语义。

### 3.3 V1 与实验代码边界

- 不修改 `程序文件/引擎/kt_video.py`；
- 不修改 `程序文件/网站/kt_web.py`；
- 不把计划 01 的 `render_sample.py` 政名后直接当正式核心；
- 可读取和提炼实验脚本中的已验证规则，但正式实现应位于独立 `video_v2` 包；
- 计划 01 实验测试继续保留，作为历史纵向样片回归，不替代新的正式契约测试；
- 计划 03 以后只能通过本计划形成的公共加载函数读取正式任务包，不能继续直接读取 `storyboard.sample.json`。

---

## 4. 核心设计决定

### 4.1 版本命名

- 产品代际：短视频 V2；
- 首个正式任务契约：**V2 Job Bundle Schema v1**；
- 两份 JSON 均使用整数 `"schema_version": 1`；
- 文件名保持 `project.json` 与 `storyboard.json`，Schema 文件保持 `project.schema.json` 与 `storyboard.schema.json`；
- JSON Schema 的 `$id` 使用项目自有稳定 URN，不依赖网络地址；
- `schema_version` 不支持隐式升级、字符串/数字互转或“尽量猜测”；不支持的版本直接报错。
- Schema v1 一经本计划验收便视为不可变契约；文字说明、错误文案或不改变行为的实现修正无需升版，但新增字段、扩大枚举、改变默认值、放宽/收紧路径规则或改变字段语义，均应建立新的 Schema 版本与显式迁移，而不是悄然改写 v1；
- 计划 03 首先只接受 `schema_version=1`，不得用“忽略不认识字段”伪装向前兼容。

这样可避免把“产品 V2”与“契约版本 1”混为一谈，也为未来不兼容变更保留 `schema_version=2`。

### 4.2 权威来源

| 层级 | 负责内容 | 权威文件 |
| --- | --- | --- |
| 结构契约 | 字段、类型、必填、枚举、简单范围、未知字段 | 两份 JSON Schema |
| 运行语义 | 跨文件一致性、条件规则、默认值、路径、素材、哈希、顺序 | `video_v2.contract` |
| 人类说明 | 目录所有权、例子、兼容策略、错误解释 | Job Bundle v1 说明文档 |
| 回归证据 | 有效/无效示例与稳定结果 | 契约测试和 fixtures |

任何示例、注释或聊天内容都不能覆盖 Schema 与运行语义。Schema 和 Python 实现若发生漂移，测试必须失败。

### 4.3 最小而可演进

- 正式契约只表达 Codex 确定的叙事、素材和语义意图；
- 包 A 内部工具路径、服务 URL、FFmpeg filtergraph、线程数、临时目录和模型命令不进入任务包；
- 任务包中只保留基础动态语义，不固定高级 Provider；
- 输出位置由包 A 根据 Job Bundle 根目录固定推导，不接受任意输出路径；
- 第一版不为“也许以后会用”而增加未实现字段；
- 对成片质量、主链路、可维护性或真实使用几乎无影响的问题，只记录，不延长本阶段。

---

## 5. Job Bundle 目录契约

### 5.1 推荐目录

```text
job-<project_id>/
├── brief.md                         # 可选，Codex/用户阅读
├── project.json                     # 必需，正式 Schema v1
├── storyboard.json                  # 必需，正式 Schema v1
├── style_bible.json                 # 可选，控制面侧车；v1 执行器不解析其结构
├── characters.json                  # 可选，控制面侧车；v1 执行器不解析其结构
├── references/                      # 可选，参考素材
│   ├── style/
│   └── characters/
├── assets/                          # 必需输入区
│   └── keyframes/
│       └── shot-001.png
├── audio/                           # 包 A 运行时创建
├── shots/                           # 包 A 运行时创建
├── captions/                        # 包 A 运行时创建
├── cache/                           # 包 A 运行时创建
├── evidence/                        # 包 A/质检创建
└── output/                          # 包 A 运行时创建
    ├── preview.mp4
    ├── final.mp4
    └── render_report.json
```

### 5.2 输入与输出所有权

| 路径 | 角色 | 本计划校验 | 后续包 A 是否可写 |
| --- | --- | --- | --- |
| `project.json` | 必需输入 | 是 | 否 |
| `storyboard.json` | 必需输入 | 是 | 否 |
| `assets/keyframes/**` | 必需输入素材 | 路径、存在、常规文件、后缀、非空、哈希 | 否 |
| `brief.md` | 可选人类说明 | 不解析 | 否 |
| `style_bible.json`、`characters.json` | 可选控制面元数据 | v1 不解析其结构 | 否 |
| `references/**` | 可选参考素材 | 仅在 storyboard 明确引用时校验 | 否 |
| `audio/`、`shots/`、`captions/` | 可再生中间产物 | 本计划不要求存在 | 是 |
| `cache/` | 可再生缓存 | 本计划不要求存在 | 是 |
| `evidence/`、`output/` | 证据与最终产物 | 本计划不要求存在 | 是 |

验证器不得因 Bundle 中存在未引用的普通侧车文件而失败，但必须拒绝在输入 JSON 中引用越界、链接或不存在的文件。

### 5.3 不允许出现的输入能力

Schema v1 不提供以下字段或等价逃生口：

- BGM、音乐、环境音、SFX、混音轨；
- 任意 shell 命令；
- 任意 FFmpeg/ffprobe 可执行文件路径；
- 任意 filtergraph、编码器参数串或浏览器脚本；
- 包 A/包 B 服务 URL 与端口；
- 任意绝对输出目录；
- 网络图片 URL；
- Provider 私有模型参数；
- 未经枚举的任意动态插件名。

未知字段使用 `additionalProperties: false` 拒绝，避免拼写错误或未实现参数被静默忽略。

---

## 6. `project.json` Schema v1

### 6.1 建议结构

```json
{
  "schema_version": 1,
  "project_id": "phase1-three-shot",
  "title": "风雨城门",
  "language": "zh-CN",
  "target_duration_sec": 16.0,
  "canvas": {
    "width": 1080,
    "height": 1920,
    "fps": 30
  },
  "defaults": {
    "voice": "女播音.wav",
    "timing": {
      "head_pad_sec": 0.15,
      "tail_pad_sec": 0.25
    }
  },
  "captions": {
    "enabled": true,
    "style_preset": "default_lower_third"
  }
}
```

### 6.2 字段语义

| 字段 | 必需 | 规则 | 语义 |
| --- | --- | --- | --- |
| `schema_version` | 是 | 整数且恒为 `1` | 契约主版本 |
| `project_id` | 是 | `^[a-z0-9][a-z0-9._-]{0,63}$` | 稳定任务标识，不直接使用标题作路径 |
| `title` | 是 | 去除首尾空白后非空，最长 120 字符 | 人类可读标题，可含中文 |
| `language` | 是 | v1 先接受 `zh-CN` | 文案与默认字幕语言 |
| `target_duration_sec` | 否 | 1–600 秒有限数 | 规划目标，只用于提示/报告，不拉伸 TTS |
| `canvas` | 是 | v1 固定 1080x1920、30 FPS | 首版竖屏输出规格 |
| `defaults.voice` | 是 | 单个安全 `.wav` 文件名，不含路径与控制字符 | 包 B 默认音色 |
| `defaults.timing.head_pad_sec` | 是 | 0–3 秒有限数 | 默认镜头开头留白 |
| `defaults.timing.tail_pad_sec` | 是 | 0–3 秒有限数 | 默认镜头结尾留白 |
| `captions.enabled` | 是 | 布尔值 | 项目级字幕总开关 |
| `captions.style_preset` | 是 | v1 固定 `default_lower_third` | 只表达稳定样式预设，不暴露 ASS 底层参数 |

### 6.3 关键语义

- `target_duration_sec` 仅是策划目标，真实总时长由包 B WAV 与镜头时间线决定；
- `voice` 是包 B 音色文件名，不是任意本地路径；是否确实存在由计划 03 的 TTS 预检负责；
- v1 固定竖屏规格，避免本阶段同时设计横屏、多分辨率和可变帧率；
- 字幕具体字号、描边、每行字符数和安全区像素属于包 A 稳定样式预设，不由每个任务任意调参；
- 自然尾音检测和裁剪阈值不是任务契约字段。

---

## 7. `storyboard.json` Schema v1

### 7.1 建议结构

```json
{
  "schema_version": 1,
  "project_id": "phase1-three-shot",
  "shots": [
    {
      "id": "shot-001",
      "purpose": "建立暴雨、古城与信使抵达的紧迫处境",
      "speech": {
        "kind": "narration",
        "text": "暮色压向古城时，一名浑身湿透的信使赶到了城门。"
      },
      "visual": {
        "keyframe": {
          "path": "assets/keyframes/shot-001.png",
          "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        },
        "focus": {
          "x": 0.5,
          "y": 0.46
        }
      },
      "motion": {
        "preset": "slow_push_in",
        "strength": "low",
        "intent": "缓慢靠近信使，同时保留城门环境"
      },
      "timing": {
        "head_pad_sec": 0.15,
        "tail_pad_sec": 0.25
      },
      "caption": {
        "mode": "speech"
      },
      "transition_out": {
        "type": "cut",
        "duration_sec": 0
      },
      "hero": false
    }
  ]
}
```

### 7.2 顶层规则

- `schema_version` 必须为整数 `1`；
- `project_id` 必须与 `project.json` 完全一致；
- `shots` 必须是数组，v1 接受 1–100 个镜头；
- 数组顺序就是时间顺序，不再增加重复的 `order` 字段；
- 镜头 ID 必须唯一，并按数组位置连续为 `shot-001`、`shot-002`……；
- 顶层与镜头对象均拒绝未知字段。

### 7.3 镜头字段

| 字段 | 必需 | 规则 | 语义 |
| --- | --- | --- | --- |
| `id` | 是 | `shot-NNN` 且与数组顺序一致 | 镜头级缓存、报告、返修主键 |
| `purpose` | 是 | 非空，最长 300 字符 | 叙事目的，供 Codex/质检理解 |
| `speech` | 是 | 见下节 | 解说或对白任务 |
| `visual` | 是 | 见下节 | 关键帧与焦点 |
| `motion` | 是 | 见下节 | 稳定基础动态语义 |
| `timing` | 否 | 0–3 秒有限数 | 覆盖项目默认头尾留白 |
| `caption` | 是 | `speech/custom/none` | 单镜头字幕来源 |
| `transition_out` | 是 | `cut/crossfade` | 镜头离场方式；最后一镜也保留明确值 |
| `hero` | 否 | 布尔，默认 `false` | 重点镜头提示，不保证高级 Provider |

### 7.4 `speech`

- `kind`：`narration` 或 `dialogue`；
- `text`：去除首尾空白后为 1–1000 字符，内部标点与换行不得被静默改写；
- `voice`：可选安全 `.wav` basename；存在时覆盖项目默认音色；
- `speaker_id`：可选 1–64 字符稳定 ID，用于角色对白追踪；v1 不要求 `characters.json` 已有正式 Schema；
- 不允许把整片长文一次塞入某个隐藏字段，也不允许提供音频文件替代包 B 的正式生成职责。

### 7.5 `visual`

- `keyframe.path`：必需，使用 `/` 分隔的 Bundle 内相对路径；
- `keyframe.sha256`：必需，64 位小写十六进制，验证器必须读取文件并比对；
- `focus.x/y`：必需，0–1 有限数；
- v1 支持 `.png`、`.jpg`、`.jpeg`、`.webp`；
- 文件必须存在、为普通非空文件，且引用路径及其祖先不得是符号链接；
- 不允许网络 URL、绝对路径、反斜杠路径或任务目录外素材；
- 图片提示词、风格说明、角色参考可存于可选侧车文档，不把包 A 不消费的创作细节塞入执行 Schema。

### 7.6 `motion`

正式基础预设白名单：

- `static`；
- `slow_push_in`；
- `slow_pull_out`；
- `pan_left`；
- `pan_right`；
- `tilt_up`；
- `tilt_down`；
- `gentle_drift`。

字段规则：

- `preset`：必需，是高级工具全部不可用时的确定性 FFmpeg 路径；
- `strength`：必需，为 `low`、`medium`、`high`；
- `intent`：可选、最长 300 字符的人类可读短句，表达希望画面如何运动，而非提供底层参数；
- Schema 不包含 Provider 名、模型名、命令、filtergraph 或生成式参数；
- 图片动态效果一般这一事实，应推动计划 04 比较增强方案，但不得让本字段与某个未验证工具绑定。

### 7.7 `caption`

- `mode=speech`：字幕采用 `speech.text`；
- `mode=custom`：必须提供非空 `text`；
- `mode=none`：不得提供 `text`；
- 若 `project.captions.enabled=false`，计划 03 应统一不渲染字幕；本计划只验证结构一致；
- 字幕换行、样式与实际时间轴由计划 03 处理。

### 7.8 `transition_out`

- `type=cut` 时 `duration_sec` 必须为 `0`；
- `type=crossfade` 时 `duration_sec` 必须位于 0.1–1.0 秒；
- v1 不加入花哨转场枚举；
- 真实音频与跨镜头重叠的时间线算法由计划 03 实现，本计划只冻结意图与合法范围。

---

## 8. 路径、安全与完整性契约

### 8.1 路径格式

任务 JSON 内所有文件路径统一使用 POSIX 相对形式：

- 允许中文、空格、括号、连字符与常见 Unicode；
- 不允许空字符串、首尾空白、NUL 或控制字符；
- 不允许 `/` 开头、`~`、`.`、`..` 路径段；
- 不允许反斜杠；
- 不允许 Windows 盘符、UNC、设备路径；
- 不允许 `http:`、`https:`、`file:` 等 URI；
- 不允许解析后越出 Job Bundle 根目录。

应同时使用 `Path` 与 `PureWindowsPath` 检查跨平台绝对路径语义，不能只在 macOS 上通过 `Path.is_absolute()` 判断。

### 8.2 符号链接与 TOCTOU 边界

- Job Bundle 根目录不得是符号链接；
- 被引用文件以及从根目录到文件之间的任何路径段不得是符号链接；
- 校验后返回已解析的内部绝对 `Path` 供包 A 使用，但 CLI 结果和错误位置优先报告 Bundle 相对路径；
- 本计划不承诺抵御校验后由其他进程恶意替换文件的所有竞态，但文件哈希必须成为计划 03 的缓存与执行前复核依据。

### 8.3 哈希

- v1 使用 SHA-256；
- 关键帧哈希为必填并在校验时实际核对；
- `project.json`、`storyboard.json`、旁白与规范化字段的运行哈希由包 A 内部计算，不要求 Codex 手填；
- 哈希不匹配是错误，不得以警告继续；
- 计划 03 的报告应记录实际输入哈希，但报告 Schema 不在本计划冻结。

---

## 9. 错误码与结果接口

### 9.1 稳定错误对象

```json
{
  "code": "path.outside_bundle",
  "document": "storyboard.json",
  "location": "$.shots[0].visual.keyframe.path",
  "message": "关键帧路径越出任务目录"
}
```

字段含义：

- `code`：稳定、可供测试与未来 UI 分支判断；
- `document`：`project.json`、`storyboard.json` 或 `bundle`；
- `location`：JSON Pointer 风格或接近 JSONPath 的稳定字段位置；
- `message`：清楚中文说明，可改进措辞但不能替代错误码。

### 9.2 最小错误码集合

| 错误码 | 场景 |
| --- | --- |
| `bundle.root_invalid` | 根目录不存在、不是目录或为链接 |
| `bundle.file_missing` | 必需 JSON 缺失 |
| `json.invalid` | 编码或 JSON 语法错误 |
| `schema.version_unsupported` | `schema_version` 不支持 |
| `schema.required` | 必填字段缺失 |
| `schema.unknown_field` | 出现未知字段 |
| `schema.type_invalid` | 类型错误 |
| `schema.value_invalid` | 枚举、范围、格式错误 |
| `schema.condition_failed` | caption/transition 等条件关系错误 |
| `project.id_mismatch` | 两个 JSON 的 `project_id` 不一致 |
| `shot.id_duplicate` | 镜头 ID 重复 |
| `shot.order_invalid` | 镜头 ID 与数组位置不一致 |
| `path.format_invalid` | 反斜杠、URI、控制字符等非法格式 |
| `path.outside_bundle` | 绝对路径或解析后越界 |
| `path.symlink_forbidden` | 根、祖先或目标为符号链接 |
| `asset.missing` | 引用素材不存在 |
| `asset.type_unsupported` | 后缀不支持或不是普通非空文件 |
| `asset.hash_mismatch` | 实际 SHA-256 与声明不同 |

执行中若发现确有必要的新错误族，可以新增；不得为同一语义随意产生多个近义错误码。

### 9.3 CLI 成功结果

```json
{
  "ok": true,
  "contract": "short-video-v2-job-bundle",
  "schema_version": 1,
  "project_id": "phase1-three-shot",
  "shot_count": 3,
  "warnings": [],
  "errors": []
}
```

### 9.4 CLI 失败与退出码

- `0`：任务包有效；
- `2`：可预期的契约错误；
- `1`：验证器自身未预期异常；
- `--json` 模式 stdout 只输出一个 JSON 对象；
- 人类说明或内部异常写 stderr，不把 Python traceback 当稳定接口；
- 错误按 `project.json`、`storyboard.json`、镜头数组顺序确定性排列，便于复现与测试。

---

## 10. Python 与 CLI 接口边界

### 10.1 推荐模块

```text
【包A】视频引擎包/程序文件/引擎/video_v2/
├── __init__.py
├── __main__.py
├── models.py
├── contract.py
└── schemas/
    ├── project.schema.json
    └── storyboard.schema.json
```

模块职责：

- `models.py`：不可变数据类 `ContractIssue`、`ValidationResult`、`ProjectSpec`、`ShotSpec`、`JobBundle`；
- `contract.py`：读取、结构检查、默认值归一化、跨文件规则、路径与哈希校验；
- `__init__.py`：只导出稳定公共入口与数据类型；
- `__main__.py`：`python -m video_v2 validate` CLI；
- `schemas/`：机器可读结构契约。

若实际实现发现两个小文件合并更清楚，可合并，但不得把逻辑塞回 `kt_video.py` 或 `kt_web.py`。

### 10.2 稳定公共入口

计划至少提供：

```python
validate_job_bundle(job_dir) -> ValidationResult
load_job_bundle(job_dir) -> JobBundle
```

- `validate_job_bundle` 收集可预期契约错误，供 CLI、未来 Web API 和测试使用；
- `load_job_bundle` 在有效时返回归一化、不可变的 `JobBundle`，无效时抛出携带结构化 issues 的专用异常；
- 两个入口共享同一内部校验流程，不得重复实现；
- 返回模型可以包含包内已解析绝对路径，但序列化结果不得把内部 Python 对象直接暴露给任务 JSON；
- 不在导入模块时创建目录、读取服务状态、启动线程或执行外部命令。

### 10.3 CLI

推荐命令：

```bash
cd "/Users/yuh/Desktop/项目/文本视音屏生成器/【包A】视频引擎包/程序文件/引擎"
"../runtime/bin/python3" -B -m video_v2 validate \
  --job-dir "/absolute/path/to/job" \
  --json
```

本阶段 CLI 只有 `validate`；不加入 `render`、`submit`、`cancel`、`clean` 或 `migrate`。计划 03 可在同一入口扩展子命令。

### 10.4 暂缓 HTTP API

本计划不冻结 `/api/v2/jobs` 的上传方式、异步状态或下载接口，因为正式 V2 执行器尚未存在。计划 03 若新增 Web API，必须：

1. 先调用本计划的 `load_job_bundle`；
2. 复用同一错误码；
3. 不在 Handler 内复制 Schema/路径校验；
4. 保持现有 `/api/generate` 与 `/api/tts` 行为不变。

---

## 11. 计划内文件

### 11.1 预计新增

```text
【包A】视频引擎包/
├── docs/
│   └── short_video_v2/
│       └── job_bundle_v1.md
├── 程序文件/
│   └── 引擎/
│       └── video_v2/
│           ├── __init__.py
│           ├── __main__.py
│           ├── models.py
│           ├── contract.py
│           └── schemas/
│               ├── project.schema.json
│               └── storyboard.schema.json
└── tests/
    ├── test_v2_job_bundle_contract.py
    └── fixtures/
        └── v2_job_bundle/
            ├── valid_minimal/
            └── phase1_migrated/

短视频V2规划文档/
└── 执行记录/
    └── 02-V2 Job Bundle、Schema与接口契约执行记录.md
```

无效场景优先在测试临时目录中由辅助函数构造，避免为了每个错误提交大量重复 fixture。若某一无效样例对文档价值很高，方可增加独立 fixture。

### 11.2 允许按需修改

- `【包A】视频引擎包/tests/README.md`：补充正式 V2 契约测试与 CLI 命令；
- 本计划文档：若执行中发现已确认事实与字段规则冲突，可更新并在执行记录中写明理由；
- 计划 01 样片任务目录：只允许新增一份正式契约映射副本或证据，不覆盖原始 `storyboard.sample.json`、WAV、镜头和成片。

### 11.3 不应修改

- `程序文件/引擎/kt_video.py`；
- `程序文件/网站/kt_web.py` 与 `index.html`；
- 包 B 任意文件；
- 计划 01 实验渲染器与既有样片产物，除非只修复本计划测试确实暴露的契约提取错误；
- 当前用户已有修改与服务状态文件。

---

## 12. 分批实施步骤

### 批次 1：现场保护、证据收口与契约红线

#### 目标

确认计划 01 确已通过，冻结本计划实际起点，并用测试先表达正式契约的关键边界。

#### 操作

1. 重新读取总体规划、本计划、计划 01 执行记录、实验 storyboard、实验校验函数与最终报告；
2. 记录 Git HEAD、分支、工作树、包 A 运行时版本及本计划负责/不负责文件；
3. 若执行记录不存在，创建并写入批次 1；若存在，按实际状态续写；
4. 在执行记录建立“采用、迁移、废弃”表：逐项判断计划 01 字段和行为；
5. 建立 `test_v2_job_bundle_contract.py`，先覆盖 Schema 文件应存在、最小有效 Bundle、版本、未知字段、镜头顺序、路径与哈希等核心期望；
6. 首次运行新增测试并保存预期失败证据；
7. 不调用真实 TTS、不渲染视频、不停止或重启健康服务。

#### 退出条件

- 计划 01 的 PASS 证据和当前工作树已记录；
- 正式字段决定与不纳入 Schema 的内容已明确；
- 新测试因正式实现尚不存在而按预期失败，失败原因与本计划一致；
- 未修改 V1 与包 B。

### 批次 2：正式 Schema、说明文档与有效夹具

#### 目标

先让 Job Bundle 的静态结构成为可读、可复用、可测试的正式资产。

#### 操作

1. 编写 `project.schema.json` 与 `storyboard.schema.json`；
2. 使用 Draft 2020-12、稳定 URN、`additionalProperties: false`、明确 required/enum/const/range；
3. 编写 `job_bundle_v1.md`，说明目录、字段、默认值、路径、版本、错误与示例；
4. 建立 `valid_minimal` fixture，使用一张真实、极小、可识别哈希的本地图片；
5. 从计划 01 的三镜头事实迁移 `phase1_migrated` fixture：保留三段文案、三张关键帧的一一对应关系、焦点、留白和基础运镜，不照抄实验专用字段；为避免把三张 1080x1920 原图重复提交到测试目录，可生成三张小型确定性派生图，正式 JSON 填写派生文件的真实哈希，并在执行记录保存原图与派生图的映射及原图哈希；
6. 原始计划 01 文件保持不变，迁移映射写入说明或执行记录；
7. 运行 Schema/fixture 相关测试并修正结构错误。

#### 退出条件

- 两份 Schema 可被标准库解析；
- 两份有效 fixture 与说明文档字段一致；
- Schema 不含 BGM/SFX、服务 URL、任意命令或高级 Provider 私有参数；
- Schema 与测试对未知字段采取明确拒绝策略。

### 批次 3：Python 模型、验证器与路径安全

#### 目标

建立计划 03 可直接复用的正式加载与校验边界。

#### 操作

1. 实现不可变模型、结构化 issue、验证结果和专用异常；
2. 实现 JSON 大小/编码/对象检查、字段类型、枚举、默认值与条件规则；
3. 实现 `project_id` 跨文件一致、镜头 ID 唯一连续、caption/transition 条件；
4. 实现 POSIX/Windows 路径语义、越界、控制字符、URI、反斜杠与符号链接检查；
5. 实现素材常规文件、非空、后缀与 SHA-256 校验；
6. 保证错误排序确定、错误码稳定、中文路径正常；
7. 增加 Schema 与 Python 枚举/必填规则一致性测试；
8. 检查源码不得使用 `shell=True`、`os.system`，不得导入或调用渲染/TTS 服务。

#### 退出条件

- 两份有效 fixture 可得到归一化 `JobBundle`；
- 所有预期无效场景返回正确错误码；
- 校验器只读、纯标准库、无导入副作用；
- 新增单元测试全部通过。

### 批次 4：CLI 与计划 01 事实迁移验证

#### 目标

证明契约既能被 Python 内核使用，也能被 Codex/用户以稳定命令独立检查。

#### 操作

1. 实现 `python -m video_v2 validate --job-dir ... --json`；
2. 实现 0/2/1 退出码与稳定 JSON envelope；
3. 测试成功、契约失败和内部异常路径；
4. 分别用 CLI 校验 `valid_minimal` 与 `phase1_migrated`；
5. 验证 CLI 前后 Job Bundle 文件清单与哈希不变，未创建 `audio/`、`shots/`、`output/`；
6. 在包 A 随包 Python 3.13.13 中运行，不借用系统额外依赖；
7. 在 `tests/README.md` 补充最小命令。

#### 退出条件

- 两个有效 Bundle 的 CLI 返回 0 与 `ok=true`；
- 代表性无效 Bundle 返回 2 与预期错误码；
- 校验失败不会留下半成品或修改输入；
- phase1 迁移示例证明三镜头事实可被正式 Schema 表达。

### 批次 5：回归、契约审计与计划 03 交接

#### 目标

用最小充分证据确认契约可以冻结，并明确下一阶段如何接入。

#### 操作

1. 运行正式契约测试与计划 01 实验测试；
2. 运行包 A 全量 `test_*.py`，将既有 Windows 路径失败与新增回归分开；
3. 检查包 B diff，确认本计划未修改包 B；
4. 检查 V1 核心文件与 Web API 未被本计划侵入；
5. 检查 `程序文件/引擎/video_v2/` 会被现有发布构建的 `copytree` 自然纳入，不执行昂贵完整发布构建；
6. 逐项对照 Schema、说明、fixture、Python 常量、错误码与 CLI 输出；
7. 对影响低或几乎无影响的问题只记录；
8. 更新执行记录，给出 PASS、CONDITIONAL 或 FAIL；
9. 形成计划 03 必须使用的公共入口、数据模型、时间线输入与未冻结边界清单。

#### 退出条件

- 本计划全部硬门通过；
- 全量测试没有本计划新增失败；
- 已知旧 Windows 断言若仍失败，名称和原因与计划 01 基线一致；
- 正式契约、CLI 与执行记录足以让计划 03 无须重新猜测输入格式；
- 已明确是否允许制定和执行计划 03。

---

## 13. 测试矩阵

### 13.1 正向

- 最小 1 镜头 Bundle；
- 计划 01 迁移的 3 镜头 Bundle；
- 中文标题、中文音色与带空格图片名；
- 项目默认 timing 与镜头覆盖 timing；
- narration/dialogue；
- caption speech/custom/none；
- cut/crossfade；
- 8 个 motion preset 与 3 个 strength；
- 可选 target duration、voice override、speaker ID、hero、intent。

### 13.2 结构与条件错误

- 顶层不是对象；
- 缺必填字段；
- 未知字段；
- `schema_version` 类型错误或不支持；
- canvas 不是 1080x1920/30；
- 空标题、空 speech、非法 voice；
- caption custom 无 text、none 带 text；
- cut 非零、crossfade 超范围；
- NaN/Infinity 通过直接 Python 构造或非标准 JSON 尝试进入数值字段。

### 13.3 跨文件与镜头

- `project_id` 不一致；
- shots 空数组或超过上限；
- 重复镜头 ID；
- `shot-002` 先于 `shot-001`；
- ID 与数组位置不一致；
- 未知运镜、强度或转场。

### 13.4 路径与素材

- 合法中文与空格路径；
- `../`、绝对 POSIX 路径；
- `C:\\...`、UNC、混合分隔符；
- `file://`、`https://`；
- 空路径、控制字符、首尾空白；
- Bundle 根符号链接；
- 中间目录符号链接；
- 目标文件符号链接；
- 素材缺失、目录冒充文件、空文件、后缀不支持；
- 哈希长度/大小写/字符错误；
- 声明哈希与真实文件不一致。

### 13.5 接口与副作用

- Python 公共入口类型与异常；
- CLI stdout JSON 可解析；
- 退出码 0/2/1；
- 错误顺序稳定；
- 校验前后文件清单和输入哈希不变；
- 导入 `video_v2` 不创建目录、不联网、不启动线程；
- 源码无 `shell=True`、`os.system`、任意命令字段；
- Schema 与 Python 枚举/必填项一致。

---

## 14. 推荐验证命令

先从项目根目录定义任务专用变量：

```bash
V2_PROJECT_ROOT="/Users/yuh/Desktop/项目/文本视音屏生成器"
V2_A_ROOT="$V2_PROJECT_ROOT/【包A】视频引擎包"
V2_A_PY="$V2_A_ROOT/程序文件/runtime/bin/python3"
V2_ENGINE="$V2_A_ROOT/程序文件/引擎"
V2_FIXTURE="$V2_A_ROOT/tests/fixtures/v2_job_bundle/phase1_migrated"
```

### 14.1 JSON 可解析性

```bash
"$V2_A_PY" -B -m json.tool \
  "$V2_ENGINE/video_v2/schemas/project.schema.json" >/dev/null
"$V2_A_PY" -B -m json.tool \
  "$V2_ENGINE/video_v2/schemas/storyboard.schema.json" >/dev/null
```

### 14.2 正式契约测试

```bash
"$V2_A_PY" -B -m unittest discover \
  -s "$V2_A_ROOT/tests" \
  -p 'test_v2_job_bundle_contract.py' -v
```

### 14.3 计划 01 实验回归

```bash
"$V2_A_PY" -B -m unittest discover \
  -s "$V2_A_ROOT/tests" \
  -p 'test_v2_phase1_sample.py' -v
```

### 14.4 CLI

```bash
cd "$V2_ENGINE"
"$V2_A_PY" -B -m video_v2 validate \
  --job-dir "$V2_FIXTURE" \
  --json
```

### 14.5 包 A 全量回归

```bash
"$V2_A_PY" -B -m unittest discover \
  -s "$V2_A_ROOT/tests" \
  -p 'test_*.py' -v
```

全量结果必须与计划 01 基线比较：旧 Windows 硬编码导致的已知失败可以保持为已记录非阻塞项，但任何新增失败都必须定位并修复后才能通过本计划。

---

## 15. 验收标准

### 15.1 Schema 硬门

- 两份 Schema 均有效且版本明确；
- 结构、枚举、required 与未知字段规则完整；
- 文档示例与 Schema 一致；
- 不含本阶段排除字段。

### 15.2 运行校验硬门

- 正向 Bundle 通过；
- 负向矩阵返回结构化稳定错误；
- 路径越界、符号链接与哈希不匹配不可绕过；
- 不依赖第三方库；
- 校验只读且无导入副作用。

### 15.3 接口硬门

- `validate_job_bundle` 与 `load_job_bundle` 可直接供计划 03 复用；
- CLI 的 JSON envelope 与退出码通过测试；
- CLI 不要求 A/B 服务运行；
- 不建立尚未验证的 HTTP V2 接口。

### 15.4 回归硬门

- 新增契约测试全部通过；
- 计划 01 实验测试继续通过；
- 包 A 全量测试无新增失败；
- 包 B 与 V1 核心未被本计划修改；
- 当前工作树既有改动仍被保留。

### 15.5 结论等级

- **PASS**：全部硬门通过，可进入计划 03；
- **CONDITIONAL**：契约主路径完整，仅有不影响计划 03 接入的文档、跨平台实机或低影响事项；记录后可进入计划 03；
- **FAIL**：Schema 与运行校验不一致、路径边界可绕过、有效 Bundle 无法稳定加载、CLI 接口不确定或出现 V1 新回归；不得进入计划 03。

---

## 16. 风险与应对

| 风险 | 预防 | 失败后处理 |
| --- | --- | --- |
| 把实验 JSON 原样永久化 | 逐字段采用/迁移/废弃 | 回到实际样片证据，只保留已证明或下一阶段必需语义 |
| Schema 与 Python 校验漂移 | 同源常量、同步测试、有效 fixture | 先修一致性，不以文档解释掩盖代码差异 |
| 为未来 Provider 过度设计 | 只保留 intent/preset/strength/focus | 高级工具字段留给实测后的新版本 |
| 手写校验器漏规则 | 负向矩阵、确定性错误、交叉审查 | 补最小回归测试，再修对应规则 |
| macOS 上漏掉 Windows 路径语义 | 同时使用 PureWindowsPath 测试 | 增加盘符、UNC、混合分隔符用例 |
| 校验器意外修改任务包 | 文件清单/哈希前后对比 | 把所有写入移出 validate 路径 |
| 把服务 URL 写进 Job Bundle | URL 由包 A 配置解析 | 删除字段并增加 unknown-field 测试 |
| 尾静音策略过早固化 | Schema 只保留语义化 pad | 计划 03 用实测决定内部裁剪策略 |
| 图片动态观感牵引范围扩张 | 本阶段只冻结语义字段 | 记录到计划 04，不安装高级工具 |
| 已知旧测试噪声遮住新回归 | 保存测试名和基线分类 | 新旧失败逐项对比，不只看总数 |
| 低影响细节耗时 | 按成片、主链路、维护、使用影响分级 | 无明显影响者记录后退出本阶段 |

---

## 17. 执行记录与完成报告

执行记录固定为：

```text
/Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/执行记录/02-V2 Job Bundle、Schema与接口契约执行记录.md
```

每批至少记录：

- 开始前读取了哪些事实；
- 实际新增/修改文件；
- 字段或接口决定及理由；
- 实际命令、退出码、测试数与失败分类；
- fixture 与 CLI 结果；
- 已处理问题和未处理低影响事项；
- 工作树保护情况；
- 是否满足本批退出条件；
- 下一批输入。

最终报告至少包括：

1. 计划 01 最终 PASS 确认与图片动态问题归属；
2. 正式 Job Bundle 目录与输入/输出所有权；
3. 两份 Schema 的实际字段、版本和哈希；
4. Python 公共入口和 CLI 命令；
5. 错误码清单与代表性负向证据；
6. 两份有效 fixture 的校验结果；
7. 正式测试、计划 01 测试和包 A 全量回归；
8. 已知旧 Windows 测试失败是否保持原状；
9. 未触碰但原本已有修改的文件；
10. PASS / CONDITIONAL / FAIL；
11. 是否允许进入计划 03；
12. 计划 03 必须继承与不得擅自改变的契约边界。

---

## 18. 进入计划 03 的输入

本计划完成后，下一份《包 A V2 核心管线实施计划》至少应收到：

- V2 Job Bundle Schema v1 两份正式 Schema；
- `JobBundle`、`ProjectSpec`、`ShotSpec` 等归一化模型；
- `validate_job_bundle`、`load_job_bundle` 公共入口；
- 稳定错误码与 CLI envelope；
- 两份有效 fixture 与完整负向测试矩阵；
- 关键帧安全路径和哈希结果；
- 项目默认/镜头覆盖后的音色与头尾留白；
- narration/dialogue、caption、transition、motion 的归一化语义；
- 计划 01 的真实 WAV 时长、尾静音观察、字幕换行与镜头报告经验；
- 明确未冻结的内容：HTTP V2 API、报告 Schema、缓存键细节、尾静音裁剪算法、Provider 私有参数和高级动态化。

计划 03 应直接消费归一化 `JobBundle`，不得重新解析原始 JSON 或另造一套字段名。

---

## 19. 最短执行说明

> 先以计划 01 的真实样片证据筛出必需语义，再用两份 JSON Schema、纯标准库 Python 校验器、只读 CLI、稳定错误码和正反测试夹具冻结 V2 Job Bundle Schema v1；保持 V1、包 B 和现有服务不动，不提前实现渲染或高级动态化。契约若稳，后续管线便可循此生长；根基若虚，越早堆代码，返工越深。
