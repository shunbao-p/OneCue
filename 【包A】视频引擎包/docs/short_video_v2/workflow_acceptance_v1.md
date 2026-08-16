# 短视频 V2 工作流验收 v1

> 状态：`complete`  
> 日期：2026-08-12  
> 当前总判定：`PASS`；首轮六份计划全部完成。
>
> 2026-08-13 产品配置更新：本记录继续证明 Schema v1、包 A/B 主链和导演 Skill 可用，但新任务的视觉默认已收束为多张静态分镜图与硬切。记录中的基础运镜/动态边界措辞只反映当时验收现场，不再指导第一版执行。

## 1. 分拆判定

| 维度 | 判定 | 证据 |
| --- | --- | --- |
| `core_workflow_verdict` | PASS | 权威流程、Brief/review 模板、真实 CLI/Schema 对齐、计划 05 主链保护与隔离全缓存演练通过 |
| `skill_verdict` | PASS | 仓库级 `.agents/skills/short-video-director/`；`quick_validate.py` PASS；薄 Skill、三份 references、零 scripts；六模式前向测试 48/48 |
| 行为与安全 | PASS | 策划/检查不误跑；validate 优先；非法包门前停止；最小 `--shot`；用户门、外部授权、脏树和旧 final 保护成立 |
| 隔离演练 | PASS | 8 audio hit、8 shot hit、1 final hit，零重建；完整解码 PASS；正式包未改 |
| 用户工作流可用性 | PASS | 用户已通过实际操作生成一条符合要求的视频，并明确判定“工作流通过” |
| 计划 06 总判定 | PASS | 文档、Skill、行为、演练、保护检查与用户真实使用门全部通过；首轮六份计划完成 |

Skill 不是视频主链的技术依赖。即使它暂时未被某个会话发现，Codex 内容与静态分镜 → Image 2 静态关键帧 → 包 B 逐镜人声 → 包 A/FFmpeg 校验、静态镜头编码与硬切合成的主链仍可直接按 `director_workflow_v1.md` 和模板执行；不得把 Skill 问题反写成计划 05 主链失败。

## 2. 最短使用方式

随仓库版本位置：`.agents/skills/short-video-director/`。Codex 从仓库根目录或其子目录启动时会自动发现该 Skill；更新后若尚未出现，请重新打开 Codex 任务。仓库根目录 `README.md` 给出了完整核验方式。

在新任务中可直接说：

- `用 $short-video-director 把这个故事做成中文竖屏短视频：……`
- `用 $short-video-director 先策划“城市树木如何缓解热岛”，不要生成媒体。`
- `用 $short-video-director 检查这个 Job Bundle 是否能继续：<绝对路径>`
- `用 $short-video-director 返修 shot-004：字幕太长，焦点偏左；先给最小方案。`

用户无需复制总体规划或六批提示词。Skill 识别策划、新建、续接、检查、渲染、返修六种模式，按需读取项目权威流程，并在候选成片用户终审、外部授权、破坏性删除或真实范围扩张前暂停。

## 3. 上游借鉴与拒绝

- 借鉴 [OpenMontage](https://github.com/calesthio/OpenMontage) 的分阶段导演、检查点、人工审批、失败续接与证据留痕。
- 借鉴 [PixVerse Skills](https://github.com/PixVerseAI/skills) 的入口 Skill、能力/工作流分层、决策树和渐进披露。
- 借鉴 [ffmpeg-ai](https://github.com/numbpill3d/ffmpeg-ai) 的缓存续接、机器可读运行报告、dry-run 与局部失败保护表达。

明确拒绝三者的媒体 Provider、Remotion、HyperFrames、音乐、云服务、认证/订阅、运行时、Schema、缓存、状态机、任务格式、GUI 与代码。本阶段没有 clone 或安装这些项目，也没有替换 Image 2、包 A、包 B、FFmpeg 或 Schema v1。

## 4. 前向行为与演练

- 六个新鲜上下文分别覆盖 Plan、Inspect、Render-invalid、Revise、Create dry-run、Resume。
- 独立评估按模式、输入、职责、Schema/CLI、安全、暂停、动态边界、续接/最小返修八项计分：六案均 8/8，总计 48/48。
- 非法包以 `asset.hash_mismatch`、退出码 2 在 TTS/FFmpeg 前停止。
- 返修案定位 `shot-004`，保留语音，建议只改字幕/焦点并用 `--shot`，无证据不加 `--force`。
- 隔离演练复用计划 05 A 包：validate PASS，8+8+1 全缓存命中，final SHA-256 保持 `ab08594f8150e8b89103c49a31654b04c6fb092866f9d8d8668770ab24bbe43c`，完整解码退出码 0。

## 5. 真实能力边界

- 当前正式路线仍只有 Image 2 + 包 B + 包 A/FFmpeg；正式高级 Provider 数量为 0。
- FFmpeg 的 push/pull/pan/tilt/drift 是虚拟摄影机运动，不是真正自然语义动态。
- 雨落、流水、车辆真实行驶、人物呼吸/摆动、鸟翼扇动等尚未实现。
- 候选成片仍须用户观看；技术探测和自动评分不能代替内容、人声、字幕、图片与整体观感判断。
- 新外部/付费/云 API、凭据、下载、发布、删除或核心范围扩张仍须暂停。

## 6. 后续自动化路线

| 优先级 | 触发证据 | 后续方向 | 本计划动作 |
| --- | --- | --- | --- |
| P0 | 用户认为自然语言入口仍不能完成基本任务 | 修一处模式/触发/模板硬缺口并复测 | 仅有限修订 |
| P1 | 两个以上真实任务反复卡在同一安全机械步骤 | 先测试与最小设计，再判断是否需要极薄 helper | 默认不建 wrapper |
| P2 | 三个以上真实任务需要状态浏览、镜头返修与产物预览 | 独立评估 V2 UI | 本计划不开发 UI |
| P3 | 用户明确要求自然场景语义动态且接受新成本/风险 | 另立 Provider/模型可行性与质量计划 | 不重开旧实验 |
| P4 | 需要多人、队列、权限、发布或云协作 | 独立产品与安全设计 | 不纳入本地 MVP |

## 7. 最终用户门

2026-08-12，用户回复：

> 我已经通过实际操作生成了了一个视频，发现符合要求，工作流通过

据此，用户已用真实操作验证自然语言入口、阶段导航、暂停/续接及产出路径能够服务实际任务，并明确接受工作流。该判断不是自动评分替代，而是计划 06 要求的最终人工可用性终审。

用户未在本次回复中提供新视频的路径、哈希或逐项媒体规格；因此本记录不虚构这些技术细节，也不把该视频追加为新的保护基线。计划 06 的技术基线仍由计划 05 两片、六模式前向证据、隔离演练和最终 fresh 检查承担。

最终结论：`core_workflow_verdict=PASS`、`skill_verdict=PASS`、`user_workflow_verdict=PASS`、计划 06 `overall_verdict=PASS`，`six_plan_round_complete=true`。
