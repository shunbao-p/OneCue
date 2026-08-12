# 短视频 V2 计划 02 执行记录

> 计划：V2 Job Bundle、Schema 与接口契约  
> 工作区：`/Users/yuh/Desktop/项目/文本视音屏生成器`  
> 开始日期：2026-08-11（Asia/Shanghai）  
> 当前状态：批次 1–5 已 PASS；计划 02 最终 PASS

## 0. 执行边界与现场保护

- 已完整阅读总体规划、计划 02、计划 02 分批执行提示词、计划 01 实施计划与执行记录、核心需求与完整方案、项目交接文档、根目录 README，以及计划 01 的实验 storyboard、渲染器、测试和 `render_report.json`。
- 工作区未发现实体 `AGENTS.md`；本会话按注入的工作区 AGENTS 约束执行。
- 开始时分支为 `main`，HEAD 为 `eaa3bf37e82be8822c70dc5dcad129cbbba08f7d`，包 A 随包 Python 为 3.13.13。
- 开始时工作树不干净；必须保护的既有内容包括包 A `程序文件/config.ini`、包 B `apps/gradio/service.py`、`macOS使用说明.md`、`tests/test_phase3_api_contract.py`，计划 01 的实验目录与测试，以及 A/B 发布信息、服务状态文件、规划文档和交接文档。
- 本计划只新增或修改计划 02 明确允许的 `video_v2/`、契约文档、契约测试、fixtures、`tests/README.md` 与本执行记录；不修改 `kt_video.py`、`kt_web.py`、包 B 或计划 01 原始任务与产物。
- 明确排除正式渲染、Web API/UI、真实 TTS、重新出片、高级动态化、BGM/SFX、认证、公证与完整发布构建；不新增第三方依赖。

## 1. 批次 1：现场保护、证据收口与契约红线

### 开始前事实

- 计划 01 执行记录最终等级为 **PASS**，明确允许制定并执行计划 02。
- 计划 01 `render_report.json` 同时给出 `status=PASS`、`quality_gate.status=PASS`、`quality_gate.full_decode_passed=true` 与 `quality_gate.plan_02_allowed=true`。
- 三镜头最终事实：`slow_push_in`、`gentle_drift`、`slow_pull_out`；真实关键帧哈希分别为 `a69a953a…a659`、`ddc298c9…429d`、`2402cc7e…e48`；真实 WAV 时长约 4.730、5.033979、5.077167 秒。
- 图片动态感一般属于计划 04 的高级动态化输入，不阻塞本计划；TTS 自然尾音与配置留白的裁剪算法属于计划 03 内部实现，不进入 Schema v1。

### 计划 01 字段与行为的采用、迁移、废弃

| 计划 01 内容 | 决定 | Schema v1 落点或理由 |
| --- | --- | --- |
| `title` | 采用 | `project.title` |
| 1080x1920、30 FPS | 采用并冻结 | `project.canvas` 常量约束 |
| `voice` | 采用并迁移 | `project.defaults.voice`；镜头可安全 basename 覆盖 |
| `shots[].id` 与数组顺序 | 采用并强化 | 唯一且连续 `shot-NNN`，不再设重复 `order` |
| `narration` | 迁移 | `speech.kind/text/voice/speaker_id`，支持 narration/dialogue |
| `image` | 迁移并强化 | `visual.keyframe.path/sha256`，增加路径、链接、常规文件与哈希门 |
| `motion_preset` | 迁移并扩展基础白名单 | `motion.preset/strength/intent`，仍不接受 filtergraph 或 Provider 私参 |
| `focus` | 采用 | `visual.focus.x/y`，有限数且 0–1 |
| `head_pad_sec`、`tail_pad_sec` | 采用并分层 | 项目默认值，可由镜头 `timing` 覆盖 |
| `caption` 文本 | 迁移 | `caption.mode=speech/custom/none`，不固定实验期直接字符串形态 |
| `sample_version` | 废弃 | 改为两个文件均使用整数 `schema_version=1` |
| `resolution`、`fps` 顶层散字段 | 废弃原形 | 归入 `project.canvas` |
| `package_a_url` | 废弃 | 属包 A 配置，不允许任务包注入服务 URL |
| 实验渲染器参数与版本 | 不入 Schema | 缓存键/报告内部事实由计划 03 处理 |
| 真实 WAV、镜头 MP4、最终片、报告 | 不作输入字段 | 属运行产物区，由包 A 创建和拥有 |
| 有效发声区/尾静音裁剪阈值 | 暂缓 | 计划 03 内部算法，不暴露为 v1 契约参数 |
| BGM、环境音、SFX | 明确排除 | v1 不预留暗字段 |

### 契约红线

- 未知字段一律拒绝；版本不猜测、不隐式升级。
- 输入路径只接受 Bundle 内 POSIX 相对路径；拒绝绝对路径、反斜杠、Windows 盘符/UNC、URI、`.`/`..`、控制字符、越界及任何路径段符号链接。
- 关键帧必须存在、为非空常规文件、后缀受支持且 SHA-256 实际匹配。
- 验证器只读、纯标准库、无导入副作用；不得联网、调用 TTS/FFmpeg、创建产物目录或执行 shell。
- 稳定入口为 `validate_job_bundle(job_dir)` 与 `load_job_bundle(job_dir)`；可预期错误返回稳定结构化错误码。

### 本批改动、命令与退出结论

- 新增 `【包A】视频引擎包/tests/test_v2_job_bundle_contract.py`，先表达 Schema、有效 Bundle、默认值、版本、未知字段、条件规则、镜头顺序、路径、符号链接、素材、哈希、不可变模型、只读验证与 CLI 的关键期望。
- 首次命令：`【包A】视频引擎包/程序文件/runtime/bin/python3 -B -m unittest discover -s 【包A】视频引擎包/tests -p 'test_v2_job_bundle_contract.py' -v`。
- 首次结果：退出码 1；发现 22 个测试，2 个失败、27 个含子测试的错误。共同根因是正式 `video_v2` 包、两份 Schema 与 fixtures 尚不存在；代表性证据为 `ModuleNotFoundError: No module named 'video_v2'`、`project.schema.json` 不存在、CLI 报 `No module named video_v2`。这正是批次 1 要求的实现前红灯，没有出现与计划相悖的失败。
- 本批实际改动仅为本执行记录和新增契约测试；未调用 TTS、未渲染、未停止/重启服务，未修改 V1、包 B 或计划 01 产物。
- 批次 1 硬门全部满足，结论 **PASS**；下一批输入为已冻结的字段表、红灯测试与路径/哈希红线。

## 2. 批次 2：正式 Schema、说明文档与有效夹具

### 开始前复核

- 已重新读取本记录，确认批次 1 为 PASS，正式实现仍缺失，红灯只源于计划内资产尚未建立。
- 本批只建立静态结构、说明与有效 fixtures，不提前实现 Python 校验器或 CLI。

### 实际新增文件

- `【包A】视频引擎包/程序文件/引擎/video_v2/schemas/project.schema.json`
- `【包A】视频引擎包/程序文件/引擎/video_v2/schemas/storyboard.schema.json`
- `【包A】视频引擎包/docs/short_video_v2/job_bundle_v1.md`
- `【包A】视频引擎包/tests/fixtures/v2_job_bundle/valid_minimal/` 下两个 JSON 与一张 18x32 PNG
- `【包A】视频引擎包/tests/fixtures/v2_job_bundle/phase1_migrated/` 下两个 JSON 与三张 36x64 PNG

### Schema 与 fixture 哈希

| 文件 | SHA-256 |
| --- | --- |
| `project.schema.json` | `e8bee8c9ac7675c40b3af80e4843d162b60b1fef6b2916bb7ad195d3511755a9` |
| `storyboard.schema.json` | `a83ca6fc621e1cac91f4eca49a12dfc2af71c20687d7e905caeea6c58ae2add2` |
| `valid_minimal/project.json` | `64a74872705e6c6869e27befb672f320d7cd660a6dec22ebafbfe338a7bf74cd` |
| `valid_minimal/storyboard.json` | `85ae65f714636b080f40f9dcbd06293407da30142fbb1be69282ed76e6f7b607` |
| `valid_minimal/assets/keyframes/最小 关键帧.png` | `f70fc29ce5aa54753b7a5c787b3f24520ec62ccae6e3a485b8f8fa0c87031848` |
| `phase1_migrated/project.json` | `333db15a3a55e0a14a778be9f174776ec42dc593edadb67aa8053ef61ce51421` |
| `phase1_migrated/storyboard.json` | `f339463015b8b652d5ac1c6a2b20635711954b4d54186ab654601d3a09abf63a` |
| `phase1_migrated/shot-001.png` | `7f00ebd35a4f475ea387ebb76a97d822814840528f0457075f235df5ae4b880b` |
| `phase1_migrated/shot-002.png` | `d4f896b978e9a5f06c6732540c7bee231884502b9fe8a0067b73074699916482` |
| `phase1_migrated/shot-003.png` | `0c2c58aa2fd4e75466101c96a74db7e3cde9a68b5f0c9520158815a25bd08bf6` |

### 计划 01 原图与派生图映射

| 镜头 | 计划 01 原图 SHA-256 | 本批派生方式与哈希 |
| --- | --- | --- |
| `shot-001` | `a69a953ae6fc428ed55f31ad4b4ea86d908ae22647484ed5a6500d406e32a659` | `sips -Z 64` → `7f00ebd3…880b` |
| `shot-002` | `ddc298c9a9c8e80e904f29ff12999359134033a48ca1b23f39651f38c2b9429d` | `sips -Z 64` → `d4f896b9…6482` |
| `shot-003` | `2402cc7e27475a8df15386397ff6346cee7e9bfbabfade4f8ef7a538c0dfde48` | `sips -Z 64` → `0c2c58aa…8bf6` |

原始计划 01 图片、storyboard、WAV、镜头、成片与报告均未覆盖或修改。

### 字段与范围决定

- 两份 Schema 使用 Draft 2020-12 和稳定 URN，顶层及全部对象均明确 `additionalProperties: false`；`schema_version` 为整数常量 1。
- `project.json` 冻结项目、画布、默认音色/留白和字幕总策略；`storyboard.json` 冻结 speech、关键帧/哈希、focus、基础 motion、caption、transition 与可选 hero/timing。
- Schema 中无 BGM/SFX、服务 URL、任意命令/filtergraph、输出目录或高级 Provider 私参；说明文档明确这些排除项与输入/输出所有权。

### 实际验证

- 两份 Schema 分别经包 A Python `-m json.tool` 解析，退出码均为 0。
- 标准库脚本解析四份 fixture JSON，核对跨文件 `project_id` 并逐一读取四张 PNG 计算 SHA-256；`valid_minimal` 的 1 个素材与 `phase1_migrated` 的 3 个素材全部匹配，命令退出码 0。
- 四张派生图片均经 `file` 确认为非空 RGB PNG；未复制原始 1080 级素材或任何视频。

### 批次 2 退出结论

- 两份 Schema、说明文档与两份有效 fixture 结构一致，未知字段拒绝策略及排除边界清楚；批次 2 判定 **PASS**。
- 下一批输入为机器可读 Schema、真实小型 fixtures、红灯测试与完整稳定错误码清单。

## 3. 批次 3：Python 模型、验证器与路径安全

### 开始前复核与实现边界

- 已重新读取最新记录、两份 Schema 与 `phase1_migrated` fixture，确认批次 2 PASS。
- 公共入口固定为 `validate_job_bundle` 与 `load_job_bundle`；公共模型固定为不可变 `ContractIssue`、`ValidationResult`、`ProjectSpec`、`ShotSpec`、`JobBundle` 与 `JobBundleValidationError`。
- 最高风险用例为 Windows/UNC/URI/反斜杠、`..` 越界、根/祖先/目标符号链接、非空常规文件与真实 SHA-256；均通过同一只读校验流程处理。

### 实际新增文件

- `【包A】视频引擎包/程序文件/引擎/video_v2/models.py`
- `【包A】视频引擎包/程序文件/引擎/video_v2/contract.py`
- `【包A】视频引擎包/程序文件/引擎/video_v2/__init__.py`

并扩充 `test_v2_job_bundle_contract.py`，覆盖全部 8 个 motion preset 与 3 个 strength，以及非标准 JSON 的 NaN 拒绝。

### 实现结果

- 模型均为 frozen dataclass；`load_job_bundle` 返回解析后的 Bundle 内绝对 `Path`，同时保留相对路径与声明/实际一致的 SHA-256。
- 批次 3 初版将 JSON 限制为 UTF-8、对象顶层、单文件不超过 1 MiB；Python JSON 接受的非标准 NaN/Infinity 通过 `parse_constant` 明确拒绝为 `json.invalid`。最终审查时安全上限已按 Schema 合法规模改为 8 MiB，见批次 5。
- 完成 required/unknown/type/value、默认值、跨文件 project ID、镜头唯一连续、caption/transition 条件、项目默认与镜头覆盖语义。
- 路径同时按 POSIX 与 Windows 语义检查；校验根、全部路径段与目标符号链接，并核对存在性、常规非空文件、后缀及 SHA-256。
- 验证失败不创建目录、不写文件、不联网、不调用 TTS/FFmpeg；导入无副作用。

### 实际验证

- 首轮含尚未实现 CLI 的全部测试：22 项中仅 CLI 相关 2 失败、1 错误，另发现 NaN 被正确归为 `json.invalid` 而测试原先期待 `schema.value_invalid`；按 JSON 语法错误语义修正测试，不改实现为错误分类迁就。
- 批次 3 范围命令：在 tests 目录运行 `../程序文件/runtime/bin/python3 -B -m unittest -v`，指定 Static、Positive、Structural、PathAndAsset 四个测试类；结果 19/19 通过，退出码 0。
- `compileall -q video_v2` 退出码 0。
- 源码检索 `shell=True|os.system|subprocess|http.client|urllib` 无命中；校验器不含外部命令或网络入口。
- 代表性错误对象：`{"code":"path.outside_bundle","document":"storyboard.json","location":"$.shots[0].visual.keyframe.path","message":"路径不得包含 . 或 .. 段"}`。

### 批次 3 退出结论

- 两份有效 fixtures 均能返回归一化不可变 `JobBundle`；结构、条件、路径、链接、素材和哈希负向场景返回稳定错误码；批次 3 判定 **PASS**。
- CLI 尚未实现，严格留给批次 4；下一批只建立 `validate` 子命令、0/2/1 envelope 与输入不变证据。

## 4. 批次 4：CLI 与计划 01 事实迁移验证

### 开始前复核

- 已重新读取最新记录、`models.py`、`contract.py` 与 `tests/README.md`，确认批次 3 的 19 项范围测试通过。
- 本批只增加只读 `validate` 子命令、退出码/JSON envelope 测试与最小使用说明，不增加 render/submit/cancel/migrate 或 HTTP API。

### 实际改动

- 新增 `【包A】视频引擎包/程序文件/引擎/video_v2/__main__.py`。
- 修改 `【包A】视频引擎包/tests/README.md`，加入正式契约测试和只读 CLI 的最小命令。
- CLI 成功/契约失败/内部异常测试随现有 `test_v2_job_bundle_contract.py` 一并转绿。

### CLI 结果

以包 A 随包 Python 3.13.13、工作目录 `程序文件/引擎` 运行：

1. `valid_minimal`：退出码 0；stdout 为 `{"ok":true,"contract":"short-video-v2-job-bundle","schema_version":1,"project_id":"minimal-contract","shot_count":1,"warnings":[],"errors":[]}`。
2. `phase1_migrated`：退出码 0；stdout 同一 envelope，`project_id=phase1-three-shot`、`shot_count=3`。
3. 不存在的 Bundle：退出码 2；首个错误为 `bundle.root_invalid`，无 traceback。
4. 内部异常由 mock 单元测试注入：退出码 1，stdout 仍为单一 JSON envelope，stderr 给出简短内部错误说明，不暴露 traceback。

### 输入不变证据

- CLI 前后对整个 `tests/fixtures/v2_job_bundle/` 的全部普通文件逐一计算 SHA-256 并以 `cmp` 比较，退出码 0，清单与内容完全一致。
- 两个 fixture 根目录在校验后仍只有既有 `assets/` 输入子目录；未创建 `audio/`、`shots/`、`captions/`、`cache/`、`evidence/` 或 `output/`。
- 正式契约测试全量运行 23/23 通过，退出码 0。

### 批次 4 退出结论

- CLI 的 0/2/1、稳定 JSON、可预期错误无 traceback、输入不变与三镜头事实迁移均已证明；批次 4 判定 **PASS**。
- 下一批只做回归、静态契约一致性审计、发布复制边界确认和计划 03 交接。

## 5. 批次 5：全量回归、独立审查与计划 03 交接

### 开始前复核

- 已重新读取最新记录，确认批次 1–4 均为 PASS；本批不引入渲染、服务、TTS、UI 或发布构建，只做契约加固、静态审计与回归。
- 包 A 全量基线须与计划 01 的既有 macOS/Windows 断言不相容集合逐项比较：两个 FAIL 与一个 ERROR；不得借本计划修改这些旧测试或平台实现。

### 独立只读审查与实际修复

独立审查先给出 `REQUEST CHANGES`，所列输入边界均在本批以小改动和回归测试闭环：

- 必需 JSON 本身为符号链接时，稳定返回 `path.symlink_forbidden`，不读取 Bundle 外文件。
- 原 1 MiB JSON 上限不足以覆盖 Schema 允许的 100 镜头最坏规模，改为文档化的 8 MiB 运行安全上限；超限仍稳定拒绝。
- 在 `PurePosixPath` 归一化前检查原始分段，明确拒绝 `.`、`..` 与空段（含 `./`、`//`）。
- 路径段过长、根路径过长/过深、未知 `~user` 与文件系统探测异常不再逸出：素材路径归为 `path.format_invalid`，根归为 `bundle.root_invalid`，CLI 均走契约退出码 2。
- 深层 JSON 的 `RecursionError` 归为 `json.invalid`，不误报内部异常。
- Voice 的 Schema/Python 规则统一：安全 basename、`.wav`、5–255 字符、无首尾空白、`.wav` 前不得为空白；可归一化文本按原始输入长度执行 Schema 的 `maxLength`。
- 加强 Schema/Python 同步测试，锁定对象 required/allowed、枚举、版本、voice 定义、镜头数量与 `hero` 默认值；另以边界用例锁定条件和范围。
- 加入多个错误的完整 `(code, document, location)` 确定性顺序测试；CLI 内部异常解析并锁定为单 JSON 中的 `internal.error`。说明文档明确该码只属于 CLI 故障面，不属于输入契约 issue 集合。

最终正式契约测试由批次 4 的 23 项扩为 32 项，全部通过。独立审查此前报告的所有具体问题均已修复；对最终代码的只读复核结论为 **APPROVE**，未再发现未闭环的计划 02 硬门问题。

### 最终 Schema 与 fixture 哈希

批次 2 的 fixture 内容未变；Schema 因 voice 规则加固而有新哈希。计划 02 最终交接以本表为准：

| 文件 | SHA-256 |
| --- | --- |
| `project.schema.json` | `5eda9ab5bf6b577dd0ea64ff2dcffd273a6844c989041a300a28c40f8e25eeb0` |
| `storyboard.schema.json` | `0ddf9a57546e579d1177000121699ef3bb3ada0ebc78332d12fa5b5190769a49` |
| `valid_minimal/project.json` | `64a74872705e6c6869e27befb672f320d7cd660a6dec22ebafbfe338a7bf74cd` |
| `valid_minimal/storyboard.json` | `85ae65f714636b080f40f9dcbd06293407da30142fbb1be69282ed76e6f7b607` |
| `valid_minimal/assets/keyframes/最小 关键帧.png` | `f70fc29ce5aa54753b7a5c787b3f24520ec62ccae6e3a485b8f8fa0c87031848` |
| `phase1_migrated/project.json` | `333db15a3a55e0a14a778be9f174776ec42dc593edadb67aa8053ef61ce51421` |
| `phase1_migrated/storyboard.json` | `f339463015b8b652d5ac1c6a2b20635711954b4d54186ab654601d3a09abf63a` |
| `phase1_migrated/shot-001.png` | `7f00ebd35a4f475ea387ebb76a97d822814840528f0457075f235df5ae4b880b` |
| `phase1_migrated/shot-002.png` | `d4f896b978e9a5f06c6732540c7bee231884502b9fe8a0067b73074699916482` |
| `phase1_migrated/shot-003.png` | `0c2c58aa2fd4e75466101c96a74db7e3cde9a68b5f0c9520158815a25bd08bf6` |

### 公共入口、CLI 与稳定错误码

- Python：`validate_job_bundle(job_dir) -> ValidationResult`；`load_job_bundle(job_dir) -> JobBundle`，无效时抛带 `.issues` 的 `JobBundleValidationError`。
- CLI：在 `程序文件/引擎` 执行 `../runtime/bin/python3 -B -m video_v2 validate --job-dir "/absolute/job/path" --json`；有效 0、契约错误 2、内部错误 1。
- 输入契约稳定码：`bundle.root_invalid`、`bundle.file_missing`、`json.invalid`、`schema.version_unsupported`、`schema.required`、`schema.unknown_field`、`schema.type_invalid`、`schema.value_invalid`、`schema.condition_failed`、`project.id_mismatch`、`shot.id_duplicate`、`shot.order_invalid`、`path.format_invalid`、`path.outside_bundle`、`path.symlink_forbidden`、`asset.missing`、`asset.type_unsupported`、`asset.hash_mismatch`。
- CLI 非契约内部错误码：`internal.error`。

### 最终验证命令与证据

1. 两份 Schema 分别以包 A Python `-m json.tool` 校验，均退出 0。
2. `python3 -B -m compileall -q 程序文件/引擎/video_v2` 退出 0；生成的 `__pycache__` 随即只在新增包内清理，未留下缓存产物。
3. `test_v2_job_bundle_contract.py`：32/32 通过；覆盖两个有效 fixture、结构与条件、Schema 对齐、路径/链接/长段、素材与哈希、深层/超限 JSON、只读性、公共模型及 CLI 0/2/1。
4. 计划 01 `test_v2_phase1_sample.py`：10/10 通过。
5. 包 A 全量 `test_*.py`：共 141 项，结果仍恰为 2 FAIL + 1 ERROR；三项名称与原因逐项等同计划 01 基线：
   - FAIL `test_phase0_contracts.WindowsBoundaryContractTests.test_current_packaged_tool_paths_and_missing_dots`：在 Darwin 上仍硬断言 `ffmpeg.exe`。
   - ERROR `test_phase0_contracts.WindowsBoundaryContractTests.test_render_video_keeps_current_ffmpeg_contract`：在 Darwin 上仍硬取仅 Windows 应有的 `FONTCONFIG_PATH`。
   - FAIL `test_phase1_platform_support.PathsAndDiagnosticsIntegrationTests.test_current_windows_bundle_paths_remain_compatible`：在 Darwin 上仍硬断言 Windows 工具路径。
   因此本计划新增回归为 0。一次中间全量曾出现 Web 端口顺延测试的瞬时 address-in-use；该测试随后定向 5/5 通过，最终全量亦恢复为上述固定三项，未纳入遗留集合。
6. 两个 fixture 的 CLI 实跑均退出 0：`minimal-contract` 为 1 镜头，`phase1-three-shot` 为 3 镜头；fixture 前后逐文件哈希一致，未创建任何输出目录。
7. 静态检索未在 `video_v2` 中发现 subprocess、shell、网络或服务调用；文档中的 FFmpeg/BGM/SFX 等仅位于明确排除段。
8. `scripts/build_macos_release.py` 的 `_copy_release_application` 在第 278 行递归复制整个 `程序文件/引擎` 并排除 `__pycache__`/`*.pyc`，故 `video_v2/` 与 schemas 会自然进入发布树，无须修改 builder，也未运行完整发布构建。
9. 全量 Web 测试会清理真实运行目录中的 `.port` 与 `.package-a-server.json`。本轮按测试前已确认的进程事实恢复：release 模式、PID 9534、端口 8787、脚本 `kt_web.py`、启动时间 `2026-08-11T15:19:07+08:00`；`mac_launcher.find_running_service()` 与 `/api/health` 均再次确认健康，服务未停止或重启。
10. 工作树保护核验：`kt_video.py`、`kt_web.py`、包 B、计划 01 实验目录/任务/产物均未被本计划修改；既有 `config.ini` 与包 B 脏改仍保持原状。未新增依赖。

### 批次 5 与计划 02 最终结论

- 批次 5 硬门满足，结论 **PASS**。
- 计划 02 总结论为 **PASS**，不是 CONDITIONAL 或 FAIL；Schema v1、fixtures、只读标准库校验器、稳定公共接口、路径/哈希安全与 CLI 已形成可审、可逆的正式契约层。
- 已知未处理事项均属后续范围：计划 03 的真实 TTS 调用、有效发声区与尾静音处理、镜头编排/缓存/报告内部实现；计划 04 的高级动态化与质感；其后才是正式渲染接线、Web API/UI、音效、认证及发布构建。
- **允许进入计划 03**。计划 03 应只消费此处冻结的 `JobBundle`/`ShotSpec`，不得重新解释 Schema、绕过哈希/路径校验或让内部缓存/报告字段反向污染公共输入契约。
