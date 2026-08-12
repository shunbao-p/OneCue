# 短视频 V2 计划 05：端到端质量验证与 MVP 验收执行记录

> 工作区：`/Users/yuh/Desktop/项目/文本视音屏生成器`  
> 开始日期：2026-08-12（Asia/Shanghai）  
> 当前状态：六批全部完成；技术、可靠性、用户质量与总判定均为 `PASS`，允许进入计划 06，但本轮未实施计划 06

## 0. 起始现场、继承结论与保护边界

- Git 分支 `main`，HEAD `eaa3bf37e82be8822c70dc5dcad129cbbba08f7d`；开始时工作树已脏，本计划不执行 `reset`、`clean`，不回退、覆盖或删除不属于计划 05 的内容。
- 开始时受保护的 tracked 修改：包 A `tests/README.md`、`程序文件/config.ini`；包 B `apps/gradio/service.py`、`macOS使用说明.md`、`tests/test_phase3_api_contract.py`。
- 开始时受保护的 untracked 内容包括：计划 01–04 的规划、执行记录、文档、实验、V2 核心/测试/fixtures、A/B 发布信息、运行状态文件、样片与证据，以及根目录交接/需求文档。
- 包 A 服务 PID `9534`、端口 `8787`，`/api/health` 返回 `status=ok`；包 B 服务 PID `6297`、端口 `7860`，包 A `/api/dots_status` 返回 `ready=true`、`compatible=true`、API `dots-tts.synthesize.v1`。本计划不停止、重启或污染真实包 B。
- 计划 03 六镜头受保护产物：
  - `output/final.mp4` SHA-256 `1a93f1c6c37f3f3ab2c94a48588ba78850039d49ff5c7f24598f9a9992f31754`；
  - `output/render_report.json` SHA-256 `d919e3f2793f758e04c4af25101754e1a0367f45a4c7976740ddd7c1111c9b9d`；
  - `evidence/contact-sheet.png` SHA-256 `e95fea29b5ad3f738dbb8383cdba85fd978414cb6f357eedb283e9d97474376c`。
- Schema v1 受保护哈希：`project.schema.json` 为 `5eda9ab5bf6b577dd0ea64ff2dcffd273a6844c989041a300a28c40f8e25eeb0`；`storyboard.schema.json` 为 `0ddf9a57546e579d1177000121699ef3bb3ada0ebc78332d12fa5b5190769a49`。
- 计划 04 的结论保持不变：可行性决策阶段最终 `PASS`，但自然场景真正语义动态尚未实现，正式高级动态 Provider 为零；HyperFrames 仅保留信息设计型 `manual_only`，不得进入计划 05 正式路线。
- 计划 05 唯一正式路线为 Image 2 关键帧、包 B 人声、包 A 与 FFmpeg；不得下载或重新启用 MFLUX、DepthFlow、自然场景 HyperFrames、Draw Things、本地/云端 I2V；不得修改 Schema v1、接入图片/视频 API、加入 BGM/SFX/环境音或实施计划 06。
- 验收根固定为 `【包A】视频引擎包/成片/短视频V2样片/phase5-mvp-acceptance/`；所有可靠性副本只允许位于其 `reliability-copies/` 下。
- 默认案例冻结为：A《暴雪前的最后一班山村邮车》（人物叙事，含恰一处 dialogue/speaker_id）；B《一滴雨水如何穿过海绵城市》（知识解释，含 custom 字幕与必要事实来源）。
- 六批依次执行；前五批在硬门通过后自动续行，批次 6 必须呈现两条候选并暂停等待用户逐片终审。用户反馈前，任何自动评分或子代理都不能把总判定提升为 `PASS`。

## 1. 批次 1：冻结基线、验收协议与安全 runner

### 1.1 只读核对与本批边界

- 当前从批次 1 开始；计划 05 记录与验收根此前均不存在。
- 本批只允许新增计划 05 测试、runner、目录协议与事实记录；不生成图片、不运行长 TTS、不渲染两条正片，不修改 Schema、正式 pipeline、包 B、V1 或计划 01–04 产物。
- 实施顺序：只读代码/测试映射 → fresh 前置回归与计划 03 媒体复核 → 先红灯测试 → 最小 runner/helper → 自审与短媒体验证 → 回归 → 更新记录 → 判断批次 2 门。
- 主要风险：验收 runner 复制核心 pipeline、普通单元测试误触长任务、可靠性副本越界、外部命令使用 shell、错误地把案例特定哈希写入通用逻辑。控制方式是只编排既有 CLI/FFmpeg/ffprobe、list argv、`shell=False`、有限超时、默认只读、显式生成子命令与路径根约束。

### 1.2 当前进度

- 已完整阅读总体规划、计划 05、计划 05 执行提示词、计划 04 最终记录、`image_workflow_v1.md`、`motion_feasibility_v1.md`、计划 03 最终记录与 ImageGen/视频任务技能约束。
- V2 核心/五组测试只读映射已完成；确认 `render_job`、三层缓存、字幕、时间线、TTS、媒体、原子提交、取消和 static 回退均已有正式职责，计划 05 runner 不应复制实现。

### 1.3 fresh 基线与计划 03 保护

- 五组既有定向测试 fresh 通过：phase4 `15/15`、phase1 `10/10`、contract `32/32`、runtime `12/12`、pipeline `25/25`，共 `94/94`，退出码全为 0。
- 首轮 shell 循环在 phase4 `15/15` 通过后因 zsh 内建只读变量名 `status` 退出；这是测试编排变量名错误，不是代码或测试失败。改用 `result_code` 后完整五组 fresh 复跑通过。
- 计划 03 六镜头 `validate --json`：`ok=true`、6 shots、0 warning/error；fresh ffprobe 为 H.264 1080×1920/30/yuv420p + AAC 48 kHz stereo，format 30.289s，视频 30.266667s、音频 30.289s；完整解码 exit 0。
- 新 runner 对计划 03 final 的只读 audit：`ok=true`、probe/decode 均 0、音视频流差 `0.022333s`、报告时长误差 `0.051333s`；final/report 哈希仍为起始冻结值。
- 包 A `/api/health` 仍 `ok`；包 B `/api/dots_status` 仍 ready/compatible；服务 PID 9534/6297 未停止、未重启。

### 1.4 红灯、最小实现与自审

- 先新增 `tests/test_v2_mvp_acceptance.py`；首次运行 8 项均因 `tests/run_v2_mvp_acceptance.py` 尚不存在而 ERROR，合理红灯成立，没有旧代码意外失败。
- 新增薄 runner `tests/run_v2_mvp_acceptance.py`，能力仅含：
  - 创建/校验机器可读验收 manifest 与固定目录协议；
  - 以 raw ffprobe 流时长做规格、30–45 秒、音视频差和 report 误差判断；
  - 联系表 list argv 构造与隔离输出；
  - full-hit / selected-rerender 缓存统计判断；
  - 旧 final 大小/哈希快照保护；
  - 以 `subprocess.run(list argv, shell=False, timeout=有限正数)` 编排既有 `python -m video_v2 validate/render`；
  - 显式 `audit-final` 与 `contact-sheet`，默认不触发长渲染。
- runner 未导入 `video_v2.pipeline`、未调用 `render_job`，没有重写缓存、字幕、时间线、TTS 或媒体核心；`compileall` 通过，源码未出现 `shell=True` 或 `os.system`。
- 第一轮实现测试暴露 macOS `/var -> /private/var` 的系统祖先解析差异 1 ERROR、路径字符串归一化 1 FAIL；最小修复只保留调用者 argv 路径、用 resolved path 做越界判断，并仅检查验收根以下的 symlink。随后 Plan05 `8/8` 通过。
- `init` 已建立两个任务包目录、六类可靠性副本和 `final-review/manifest.json`；`acceptance-protocol.md` 冻结两案例、八项量表、内部/用户返修上限、终审问题和已知动态边界。
- manifest 已登记 Git HEAD、Schema、计划 03 final/report/contact sheet 哈希与包 A/B 服务基线；状态仍为 `in_progress / CONDITIONAL / plan06_allowed=false`。

### 1.5 最终验证与本批判定

- fresh 合并矩阵：Plan05 `8/8` + 既有 `94/94`，合计 `102/102` 全部 PASS、退出码 0；最大观察 RSS 来自 pipeline 短媒体测试约 `907,624,448 B`，swap 0。
- 计划 03 final/report/contact sheet、两份 Schema 哈希逐项未变；计划 05 根无 `.part-*`；开始时 5 个 tracked 修改与既有 untracked 保护范围仍在，没有 reset/clean/覆盖。
- 独立只读代码映射与证据审计均已完成并收束；其结论与主执行者 fresh 核验相符。另识别两个后续须如实处理的边界：final 已原子提交但 report/manifest 最后写盘失败的极窄窗口；取消在最终 decode 与 final 提交间的极窄竞态。批次 4 将按现有可控注入门验证，不为理论低概率窗口扩大核心改造。
- **批次 1 判定：PASS。**满足自动进入批次 2 的硬门。

## 2. 批次 2：两条内容、Image 2 关键帧与 Job Bundle

### 2.1 只读核对与制作控制面

- 批次 1 硬门已通过；本批只制作 A/B 的 Brief、文案、分镜、参考、Image 2 图片、生成账、联系表和严格 Schema v1 Job Bundle。
- 案例 A 目标：7–8 镜人物叙事，乡邮员跨至少 5 镜身份可辨，恰一处 dialogue/speaker_id，行动压力镜头为雪中邮车/邮员前行；参考顺序固定为角色基准在前、风格基准在后。
- 案例 B 目标：7–8 镜知识解释，包含透水铺装、下凹绿地、植被土壤、调蓄、安全排水和总览，恰一处 custom 字幕，降雨/流水压力镜头诚实暴露动态边界；不写无来源数字或绝对结论。
- 两案均使用半写实中文叙事/科普插画、独立 9:16 关键帧，画面不含文字/标签/水印，下方约 18% 留字幕安全区，四周留低强度 FFmpeg 运镜余量。
- 本批不调用真实包 B、不渲染 final、不下载或运行任何计划 04 高级/研究 Provider，不修改核心管线或 Schema。

### 2.2 Image 2 生成、只读复核与生成账

- 已用内置 ImageGen/Image 2 生成并保留 3 张参考与 16 张互相独立的 9:16 关键帧；所有图片均为 `941×1672` PNG，原始生成文件保留在 Codex 生成目录，工作区只复制正式资产，未删除原图。
- 案例 A 的角色参考 SHA-256 为 `d4ef57ab...e199`，风格参考为 `302d7909...f45`；8 张关键帧哈希逐项写入 `storyboard.json`、`generation-ledger.json` 与 `image-inventory.json`。
- 案例 B 的风格参考 SHA-256 为 `8d220a30...87b5`；初次并行请求在尚无输出时遇到一次网络错误，核对生成目录确认无部分成功后改为顺序补齐，不重复已成功图片。8 张正式关键帧均为首次成功结果，内部返图数 0。
- 主执行者逐张查看原尺寸图并查看两张总联系表：A 的周远在 shot-001 至 007 均可辨，方脸、左眉疤、绿冬衣、藏青围巾、棕手套、橄榄邮袋红结与绿车连续；shot-006 无烧录对白，递信手部与单一信封可读。B 的八镜从落雨到总览顺序完整，调蓄表现为有限容积，强降雨镜保留浅积水和常规排水，未把能力夸为“消灭内涝”。
- 联系表：A SHA-256 `1ecd1aec...a958`，B SHA-256 `8f6ff9d5...0e5d`。本批没有使用自动评分替代人工复核，也没有以裁切或后期隐藏原图硬伤。

### 2.3 文案、来源与严格 Job Bundle

- A 为 8 镜人物叙事，含且仅含一镜 `dialogue`：shot-006“到了，这是你的信。”，`speaker_id=zhou-yuan`；其余均为 narration。行动压力由结冰旧桥与铲雪镜承担。
- B 为 8 镜知识解释，shot-007 含且仅含一个 custom 字幕“海绵城市：减缓、分散、协同排水”。事实依据采用住建部技术指南与国务院办公厅指导意见（财政部转载），只作“渗、滞、蓄、净、用、排”等定性机制说明，不写未经核验的比例或防洪等级，不宣称完全净化或消灭所有内涝。
- 两包均已保存 `brief.md`、`script.md`、`style_bible.json`、提示词、生成账、参考映射、图片清单；A 另存 `characters.json`，B 另存 `evidence/sources.md`。
- 两包严格使用 Schema v1 允许字段；A `project.json/storyboard.json` SHA-256 为 `8ca80f36...4852` / `b284d079...3e77`，B 为 `df0bc869...9313` / `f11ac08f...f710`。在包 A 正式 engine 目录 fresh 执行 `video_v2 validate --json`，两包均 `ok=true`、`shot_count=8`、0 warning、0 error、退出码 0。
- `final-review/manifest.json` 已登记输入哈希、生成账、联系表、镜头/对白/custom 字幕计数；状态保持 `in_progress / CONDITIONAL / plan06_allowed=false`。

### 2.4 自审与本批判定

- 全部镜头均为独立图片；未用单张图切成多镜、未接图片/视频 API、未启用 MFLUX、DepthFlow、Draw Things、自然场景 HyperFrames 或任何 I2V。
- 文案、图片与引用均无阻断项；两包均具真实渲染所需的 8 张已锁哈希关键帧。动态仍只允许包 A 的基础虚拟摄影机运动，雨水流动和人物自然动作未实现。
- **批次 2 判定：PASS。** 满足顺序进入批次 3 的硬门。

## 3. 批次 3：真实包 B + 包 A 顺序渲染与媒体审计

### 3.1 启动前只读门

- 将按 A 后 B 顺序渲染，避免两个长任务并发争抢 CPU/内存；每条仅用包 B 真实 Dots.tts、包 A 正式渲染核心与随包 FFmpeg。
- 渲染前将 fresh 核对包 A/B 健康、磁盘、内存与计划 03/Schema 保护哈希；不停止或重启服务，不接入任何新增声音或高级运动路线。

### 3.2 真实顺序渲染

- 启动前包 A `/api/health=status:ok`；包 A `/api/dots_status` 显示包 B `installed/running/ready/compatible=true`、API `dots-tts.synthesize.v1`、PID 6297；包 A PID 9534。磁盘可用约 290 GiB。两份 Schema 与计划 03 final/report 哈希均与冻结基线一致。
- 案例 A 首渲：run id `f130f18422d6449291552478435c491e`，退出 0、status success，真实包 B 逐镜 TTS 8/8，包 A 镜头 8/8，final 1/1；缓存为 audio `0 hit / 8 rebuilt`、shot `0/8`、final `0/1`；墙钟 `223.30s`，最大 RSS `1,741,651,968 B`，swap 0；final SHA-256 `3c38aca5...62d6`，时长 `37.833008s`，无 warning/error。
- 案例 B 首渲：run id `5f6de4737e5b45bb8f86cd6f52e7e9a4`，退出 0、status success，真实包 B 逐镜 TTS 8/8，包 A 镜头 8/8，final 1/1；缓存同为 `0/8、0/8、0/1`；墙钟 `197.02s`，最大 RSS `1,372,127,232 B`，swap 0；final SHA-256 `8d8bda90...0abf`，时长 `36.466667s`，无 warning/error。
- 两条成片均在 30–45 秒内，无须使用本批仅允许的时长文案修正机会；未并发争用包 B。

### 3.3 全媒体审计与联系表

- 两包各 8 WAV + 8 shot + 1 final，共各 17 个媒体逐项 ffprobe；各 17 个均以 `ffmpeg -map 0 -f null` 完整解码，错误日志 0 字节。
- A final：恰 2 流，H.264 1080×1920、30fps、yuv420p + AAC 48kHz stereo；音视频流差 `0.010008s`，报告时长误差 `0.028992s`，report SHA-256 `f991d576...13b6`。
- B final：同一正式规格；音视频流差 `0.030667s`，报告时长误差 `0.023985s`，report SHA-256 `07f17d55...7d58`。
- blackdetect：两片均 0 个 ≥0.3 秒黑段。silencedetect：两片均 8 段，A 每段约 `0.45–0.68s`、B 约 `0.55–0.69s`，均位于镜间/尾部 pad，结合时间线不是漏音。A 响度约 `-16.7 LUFS`、LRA `4.3 LU`、真峰值 `-3.1 dBFS`；B 为 `-16.6 LUFS`、LRA `3.9 LU`、真峰值 `-3.5 dBFS`。
- final 联系表显示 8 镜均到达，字幕位于下方安全区且未遮挡主脸/信件/关键机理；B shot-007 显示 custom 字幕，而非旁白原文。A 联系表 SHA-256 `be310362...5bb1`，B 为 `4c6e7c8b...6412`。
- 初次 contact-sheet 因指定 JPG 被 runner 的 PNG 安全门拒绝；改用 PNG 后又实证随包 FFmpeg 无 `drawtext`。以新增测试先红灯，最小移除时间戳滤镜、保留固定间隔+缩放+tile，Plan05 `8/8` 复绿并生成两表；未改核心渲染、字幕或媒体职责。

### 3.4 macOS 完整播放与批次判定

- 通过 QuickTime Player 分别从 0 播至末尾，UI 时间线到达 A `37.833s`、B `36.467s`，播放开关回到 off，首尾画面到达且无播放器错误。
- Computer Use 不回传扬声器真实听感，故这里只确认可打开、完整播放、画面/字幕到达，不虚构音色自然度；主观人声质量留给批次 6 用户终审。
- 播放后包 A/B 仍健康，服务 PID 未变；Plan05 + core pipeline fresh `33/33` 通过；验收根无 `.part-*`，无遗留 `video_v2`、`dots_synth` 或 FFmpeg 子进程；磁盘仍约 292 GiB 可用。
- **批次 3 判定：PASS。** 两条正式 final 均成功、规格与媒体硬门通过，可进入批次 4 隔离可靠性验证。

## 4. 批次 4：缓存、选择性重渲与故障注入

### 4.1 只读门与隔离原则

- 原验收包两条 final、report、cache manifest 与输入哈希已经冻结；先在原包做第二次无参数渲染验证全缓存命中与 final 哈希稳定。
- 其余选择性重渲、坏哈希/路径/字段、缓存条目损坏、TTS unavailable、motion static 回退与取消均在 `reliability-copies/` 隔离副本或单元临时目录执行；不停止真实包 B，不修改原验收包故障状态。

### 4.2 原包全缓存与选择性重建

- 原 A 第二次 render：run id `5972c2d9d586429f9727b2d1060f7a68`，墙钟 `7.239s`，audio `8 hit / 0 rebuilt`、shot `8/0`、final `1/0`；final SHA-256 仍为 `3c38aca5...62d6`。
- 原 B 第二次 render：run id `0087de1aaa3f488d994777bc1f65bdad`，墙钟 `8.074s`，缓存统计同为 `8/0、8/0、1/0`；final SHA-256 仍为 `8d8bda90...0abf`。两次均未触发包 B 合成。
- 在 `reliability-copies/selected-rerender/story-mail-car/` 仅把 shot-003 的 `motion.strength` 从 low 改为 medium，再以 `--shot shot-003` 渲染：run id `ff8daef9293444179cdf6ec8b86ac296`，audio `8/0`、shot `7 hit / 1 rebuilt`、final `0/1`，其余镜头保持命中；副本 final 为 `9527b336...1861`，原 A final 未变。
- 在 `reliability-copies/corrupted-cache/story-mail-car/` 只把 shot-003 的缓存声明哈希改成错误值；run id `c5214b5817c648a38a9a17a20c8aa618` 将其识别为 miss，audio `8/0`、shot `7/1`、final `1/0`。shot-003 确定性重建后原 final key 仍成立，副本 final 命中且 SHA-256 为 `3c38aca5...62d6`；没有无差别重做。

### 4.3 契约拒绝、TTS、运动回退与取消

- 三个独立非法副本均在 `0.09s` 内、退出码 2、TTS/FFmpeg 前拒绝：错误图片声明哈希为 `asset.hash_mismatch`，`..` 路径为 `path.outside_bundle`，未知 `bgm` 字段为 `schema.unknown_field`；三个旧 final 快照均未改变。
- Plan05 专属回归以无缓存最小 bundle 注入 `DotsTtsProvider(installed=False)`：稳定得到 `tts.not_installed`、stage `tts`、shot id `shot-001`、`retryable=false`；report 为 failed，旧 final 字节不变，无 `.part-*`。真实包 B PID 6297 全程未停止，随后仍为 ready/compatible。
- 真实 FFmpeg 隔离回退：在 `reliability-copies/motion-fallback/story-mail-car/` 对 shot-003 首次非 static 命令注入一次返回码 1，随后真实 static 命令成功；run id `plan05-motion-fallback`，report 明确 `fallback_used=true`、`actual_preset=static`、warning `render.motion_fallback`，缓存为 audio `8/0`、shot `7/1`、final `0/1`。
- 双失败隔离副本中先后令非 static 与 static 两次命令失败，稳定得到 `render.fallback_failed`、stage `shot_render`、shot id `shot-003`；report 为 failed，旧 final 哈希不变，无 part 残留。
- 受控预取消测试得到 `pipeline.cancelled` 与 cancelled report，旧 final 字节不变。既有 core runtime 回归又 fresh 覆盖真实存活子进程取消、terminate→kill、KeyboardInterrupt 收束，core pipeline 覆盖 CLI 取消退出码 130；未为形式验收停止包 A/B。

### 4.4 自审、回归与本批判定

- 新增的故障测试只调用既有 `render_job`/Provider/Runtime 注入点，不改 Schema、生产 pipeline、包 B 或 V1；两个真实 FFmpeg 场景为显式环境变量 opt-in，普通 discover 不触发长媒体。
- fresh 矩阵发现 106 项：Plan05 12 项中 10 项常规通过、2 项真实 FFmpeg opt-in 跳过；其余 phase4、phase1、contract、runtime、pipeline 全部通过，总结果 `OK (skipped=2)`。两个 opt-in 场景另分别 fresh 运行并各 `1/1` 通过。
- 原 A/B final 哈希保持 `3c38aca5...62d6` / `8d8bda90...0abf`；验收根无 `.part-*`，无残留 `video_v2`、`dots_synth` 或 FFmpeg 子进程；包 A PID 9534、包 B PID 6297 未变；磁盘可用约 290 GiB。
- **批次 4 判定：PASS。** 全缓存、选择性重建、契约预拒绝、缓存损坏、TTS unavailable、static 回退/双失败与取消保护均具可复核证据，可进入批次 5。

## 5. 批次 5：综合质量审查与一次内部返修

### 5.1 冻结候选与审查边界

- 返修前候选 final 冻结为 A `3c38aca5...62d6`、B `8d8bda90...0abf`；两片技术门、可靠性门均已通过。
- 本批只按八项 0–3 量表逐镜审查，至多各使用一次内部返修、2 张图与 2 个文案/字幕镜头；真正语义动态缺口不以晃动、滤镜或新 Provider 掩盖。
- 已生成每条 8 镜的首/中/尾三帧总表：A SHA-256 `cad52a93...697a`，B `dea30e9a...d5c3`；并重新查看关键帧联系表、final 联系表、ASS、storyboard、report 与媒体探测。

### 5.2 独立评分、问题分类与一次有限返修

- 返修前按 8 项量表审查：A 的内容、抓点与人物/风格稳定，没有硬失败；有限问题主要是 shot-001 姓名断行、shot-004 文案中“护进怀里”与铲雪画面不完全相符。B 的事实链、图像风格和 custom 字幕成立；有限问题是 shot-005 “一部分”被跨行拆开且表达略滞。
- 当前工具边界问题不进入返修：A shot-003 的轮胎打滑、shot-007 的灯亮、shot-008 的驶离，以及 B 的雨落、渗流、流水均是动作性语义，而正式链只有静帧虚拟摄影机运动。它们不是技术硬失败，也不能以新增晃动、滤镜或 Provider 冒充已解决。
- A 使用且仅使用一次内部返修：shot-001 改为“暴雪封路前两小时，周远发动了山里最后一班邮车。”；shot-004 改为“他停下铲开积雪，邮袋始终没有离身。”。未重生图片。
- B 使用且仅使用一次内部返修：shot-005 改为“强降雨时，调蓄设施让部分雨水多停留一会儿。”。未重生图片。
- 返修前 storyboard、script、final、report、cache manifest 与 final 联系表均保存于各包 `evidence/iterations/batch5-before-internal-revision/`，旧 final 哈希分别为 A `3c38aca5...62d6`、B `8d8bda90...0abf`。
- 两包返修后 fresh validate 均 `ok=true`、8 shots、0 warning/error。

### 5.3 选择性重渲与缓存范围

- A 以 `--shot shot-001 --shot shot-004` 选择性重渲：run id `b9d99c35d03c4d97a3d6fd8e7345f486`，墙钟 `53.215s`，最大 RSS `1,602,437,120 B`，swap 0；audio `6 hit / 2 rebuilt`、shot `6/2`、final `0/1`。返修后 final SHA-256 `ab08594f...e43c`，时长 `35.882s`。
- B 以 `--shot shot-005` 选择性重渲：run id `0a9afcd6a834445689d1628f5740bcdb`，墙钟 `35.47s`，最大 RSS `1,462,894,592 B`，swap 0；audio `7/1`、shot `7/1`、final `0/1`。返修后 final SHA-256 `58e21700...702d`，时长 `36.133333s`。
- 缓存重建范围与文案变更严格一致；没有重做其他音频、镜头或图片，也没有污染批次 4 隔离证据。

### 5.4 返修后媒体、字幕与播放器复核

- 两包各 8 WAV + 8 shot + 1 final，共各 17 个媒体 fresh ffprobe；各 17 个均完整解码，decode 错误日志为 0 字节。两片仍为 H.264 1080×1920、30fps、yuv420p + AAC 48kHz stereo。
- A：音视频流差 `0.015333s`、report 时长误差 `0.041s`；blackdetect 0；8 段静音约 `0.42–0.65s`，均为镜间/尾垫；`-16.7 LUFS`、LRA `4.2 LU`、真峰值 `-3.0 dBFS`。
- B：音视频流差 `0.017333s`、report 时长误差 `0.000651s`；blackdetect 0；8 段静音约 `0.44–0.68s`，均为镜间/尾垫；`-16.7 LUFS`、LRA `3.7 LU`、真峰值 `-3.6 dBFS`。
- ASS 复核确认 A shot-001 为“暴雪封路前两小时，\N周远发动了山里最后一班邮车。”，shot-004 为“他停下铲开积雪，\N邮袋始终没有离身。”；B shot-005 为“强降雨时，\N调蓄设施让部分雨水多停留一会儿。”，姓名与词组不再被拆断。
- 返修后 final 联系表 SHA-256：A `f0d23342...9461`，B `62c3dc00...5cc`。返修后 8 镜首/中/尾总表重建并亲自复核，SHA-256：A `a9d40032...188`，B `e6fb2bbb...943`；字幕安全区、主体和信息焦点未出现硬失败。
- 通过 Computer Use 驱动 QuickTime Player 对返修后两片由 0 完整播放至末尾：A 时间线 `35.867s`，B `36.134s`，播放开关均回到 off，无播放器错误。该工具不能证明扬声器主观听感，故不捏造音色、错读、断句与语气评价。

### 5.5 冻结评分与本批判定

- A 评分：内容完整 3、开头抓点 3、图像一致 3、镜头语义 2、基础运动 2、字幕 3、人声 2、整体可看性 2，总分 **20/24**。
- B 评分：内容完整 3、开头抓点 2、图像一致 3、镜头语义 2、基础运动 2、字幕 3、人声 2、整体可看性 2，总分 **19/24**。
- 人声只按客观“清楚可用、无削波”给 2，不以静态证据冒称语气自然；用户终审可以覆盖这项主观判断。
- `final-review/manifest.json` 已冻结返修后输入、final/report/cache/contact sheet/audit 哈希、两次正式运行、内部返修、评分、技术与可靠性判定；`technical-summary.md` 已形成。两包 `technical_verdict=PASS`、`reliability_verdict=PASS`，用户质量仍为 `CONDITIONAL`。
- 返修后 fresh 合并矩阵共发现 106 项：104 项 PASS、2 项批次 4 真实 FFmpeg opt-in 按设计 SKIP，退出码 0；最大 RSS `911,671,296 B`，swap 0。两个 opt-in 已在批次 4 分别 fresh 通过，本批未无故重做。
- 两包经薄 runner fresh `validate` 均退出 0、8 shots、0 warning/error；`audit-final` 均退出 0、`ok=true`、probe/decode 0，final/report 哈希与冻结 manifest 一致。
- 包 A/B 服务仍为 PID 9534/6297 且健康；Schema v1 与计划 03 final/report/contact sheet 哈希仍等于冻结基线；磁盘约 290 GiB 可用；验收根无 `.part-*`，无遗留渲染/TTS/FFmpeg 子进程。
- **批次 5 判定：PASS。** 两个候选均无未处理硬失败，允许进入批次 6 正式用户质量门；不得据 Codex 评分宣布 MVP 完成。

## 6. 批次 6：用户终审与暂停点

### 6.1 当前呈现状态

- 两条返修后 final、时长、镜头数、媒体摘要、Codex 评分与真实动态边界已准备向用户呈现。
- manifest 的两片 `user_review.status` 均为 `awaiting`，总状态为 `awaiting_user_review / CONDITIONAL / plan06_allowed=false`。
- 技术门与可靠性门均为 PASS；当前唯一未完成的硬门是用户分别对内容、人声、字幕、图片一致性、基础运动、整体是否像电子相册及 MVP 可接受性的实际审片。
- 在收到逐片反馈前暂停，不运行用户定向返修、最终 Plan01–05 fresh 回归或 `mvp_acceptance_v1.md` 终章，也不实施计划 06。

### 6.2 用户终审结果

- 用户明确回复：“A：通过”“B：通过”。两片均获逐片接受，没有提出问题镜头或时间点，也没有要求有限返修。
- 依批次 6 约束，不再额外润色；A/B 用户定向返修次数均保持 0，返修额度未使用，两条 final 哈希保持 `ab08594f...e43c` / `58e21700...702d`。
- 此反馈完成唯一强制人工质量门。Codex 分数未代替用户裁定；计划 04 的真实动态边界亦未被改写。

### 6.3 最终 fresh 回归与一次测试确定性修正

- 收到用户反馈后，fresh 运行 Plan05、phase4、phase1、contract、runtime、pipeline 合并矩阵，共发现 106 项：104 项 PASS、2 项真实 FFmpeg opt-in 按设计 SKIP，退出码 0；最大 RSS `910,852,096 B`，swap 0。
- 首次单独复跑 static fallback opt-in 时，隔离副本已有上次回退产生的有效 static 缓存，shot-003 直接命中，故注入器计数为 0，测试 FAIL；这是测试复用持久副本时缺少确定性缓存 miss，不是生产回退失败。
- 仅修改 `tests/test_v2_mvp_acceptance.py`：两个显式 opt-in 测试在运行前把各自隔离副本的 shot-003 cache key 改成测试专用 miss 值。未改生产 pipeline、Schema 或正式任务包。
- 修正后 static fallback 显式 fresh `1/1` PASS：真实触发一次非 static 失败，随后 static 成功，report 为 `fallback_used=true`、`actual_preset=static`、warning `render.motion_fallback`；最大 RSS `864,419,840 B`、swap 0。
- double failure 显式 fresh `1/1` PASS：稳定得到 `render.fallback_failed`，旧 final 保护成立；最大 RSS `110,919,680 B`、swap 0。
- 修改测试后再次 fresh 运行完整 106 项矩阵：104 PASS、2 opt-in SKIP，退出码 0；因此没有以局部绿灯掩盖回归。测试文件最终 SHA-256 `a69d95bd...b37d`。

### 6.4 最终两包、缓存与保护审计

- 两包薄 runner fresh validate 均退出 0、8 shots、0 warning/error；fresh final audit 均 `ok=true`、probe/decode exit 0，final/report 哈希与用户通过时一致。
- 两个正式 cache manifest 各含 8 audio + 8 shots + 1 final；共 34 个实体的实际 SHA-256 逐项与清单一致。
- Schema v1 哈希保持 project `5eda9ab5...eeb0`、storyboard `0ddf9a57...9a49`。
- 四份 V1 文档哈希冻结为：`core_pipeline_v1.md` `25661b10...8336`、`job_bundle_v1.md` `c380dc80...3c32`、`image_workflow_v1.md` `c199c89b...f692`、`motion_feasibility_v1.md` `a7f01950...e404`。
- 计划 03 final/report/contact sheet 仍为 `1a93f1c6...1754`、`d919e3f2...9b9d`、`e95fea29...376c`；计划 04匿名 manifest/scorecard 仍为 `619b358b...6c1f`、`7b37e2cd...c345`。
- 计划 04 结论严格保持：可行性决策 `PASS`，但真正自然语义动态尚未实现，正式高级 Provider 为零。
- 包 A PID 9534 health ok；包 B PID 6297 installed/running/ready/compatible、API `dots-tts.synthesize.v1`。未停止或重启服务。
- 验收根约 494 MiB，其中可靠性隔离副本约 308 MiB，均为已登记产物；无未知 >100 MiB 文件。磁盘约 290 GiB 可用。
- 无孤儿 `video_v2`、`dots_synth` 或 FFmpeg 进程；`.part-*` 数量 0。Git HEAD 仍为 `eaa3bf37...7d`，起始 tracked 脏修改与既有 untracked 范围仍保留，未 reset/clean/删除。

### 6.5 文档、manifest 与最终判定

- 已完成 `docs/short_video_v2/mvp_acceptance_v1.md`，记录正式路线、两片结果、媒体/缓存/故障证据、用户反馈、回归、动态边界与计划 06 交接。
- `final-review/manifest.json` 已将两片 `user_review` 更新为 `received/accepted`，`quality_verdict=PASS`；总状态为 `complete`、总判定 `PASS`、`plan06_allowed=true`，并登记计划 04 与 V1 文档保护哈希。
- 技术判定：**PASS**。
- 可靠性判定：**PASS**。
- 用户质量判定：**PASS**。
- **计划 05 总判定：PASS。** 两片均被用户接受且全部硬门通过，允许进入计划 06；本轮只解除门禁，未实施计划 06。
- 已知边界继续有效：FFmpeg 仅有虚拟摄影机运动；雨落、流水、车辆、人物等真正自然语义动态尚未实现，正式高级 Provider 为零。用户接受本次 MVP 不等于该能力缺口已经解决。
