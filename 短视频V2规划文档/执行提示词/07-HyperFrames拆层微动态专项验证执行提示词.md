# 短视频 V2 计划 07：分批执行提示词

> 状态（2026-08-13）：历史执行提示词，计划已完成，第一版动态路线已关闭。新会话不得复制本文继续运行；仅供复盘当时的实验步骤与证据。

本文档服务于《07-HyperFrames拆层微动态专项验证计划》。通常无需逐段复制：用户在新会话粘贴由规划会话单独提供的“总执行提示词”后，执行会话应完整阅读本文，从第一个未完成批次连续推进。背景提示词和六个批次提示词用于只读预热、局部重跑、断点恢复、用户审片后的续接，或用户主动要求分批控制。

分工如下：

- 总提示词负责完整阅读、调用正确的 HyperFrames 技能、连续推进、工作树保护、执行记录、用户审片门和最终完成条件；
- 实施计划负责旧测试纠偏、图片分层、动作 Brief、案例 A/B、S/W/L 对照、资源门、技术门和最终分类；
- 背景提示词只做只读熟悉，不实施、不创建执行记录；
- 分批提示词是可独立复制的局部执行合同，每段重申本批不可缺少的边界；
- 执行记录是断点续接和最终验收的事实来源；
- 总提示词不写入本文，只在规划会话最终答复中单独展示。

主要依据：

- /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/07-HyperFrames拆层微动态专项验证计划.md
- /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/短视频V2总体目标与阶段规划.md
- /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/执行记录/04-图片生成与高级动态化可行性执行记录.md
- /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/执行记录/06-半自动工作流固化与后续自动化执行记录.md
- /Users/yuh/Desktop/项目/文本视音屏生成器/【包A】视频引擎包/docs/short_video_v2/motion_feasibility_v1.md
- /Users/yuh/Desktop/项目/文本视音屏生成器/【包A】视频引擎包/docs/short_video_v2/director_workflow_v1.md
- /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2核心需求与完整方案.md
- /Users/yuh/Desktop/项目/文本视音屏生成器/项目交接文档.md

旧实验重点核对：

- /Users/yuh/Library/Caches/text-video-plan04-feasibility/hyperframes/project/rainy-messenger-motion/shot-plans/03-narrative-character.json
- /Users/yuh/Library/Caches/text-video-plan04-feasibility/hyperframes/project/rainy-messenger-motion/compositions/narrative-character.html
- /Users/yuh/Desktop/项目/文本视音屏生成器/【包A】视频引擎包/experiments/short_video_v2_phase4/providers/hyperframes_adapter.py

本计划执行记录：

- /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/执行记录/07-HyperFrames拆层微动态专项验证执行记录.md

计划 07 隔离根：

- /Users/yuh/Library/Caches/text-video-plan07-hyperframes/

计划 07 项目证据根：

- /Users/yuh/Desktop/项目/文本视音屏生成器/【包A】视频引擎包/成片/短视频V2样片/phase7-hyperframes-micro-motion/

明确排除：修改 Schema v1、重写包 A/B 正式管线、把 HyperFrames 变成整片时间线或 TTS/字幕内核、重开 MFLUX/DepthFlow/Draw Things/I2V、下载超过计划上限的新模型、加入 BGM/SFX/环境音、自动提交或推送 GitHub、清理旧计划证据，以及处理对动态效果影响很低的问题。

---

## 建议执行模型（非复制区）

以下只作为新会话的模型与推理强度建议，不要复制到具体提示词正文中。由于前次测试曾因范围理解错误产生错误结论，本计划各批宁可使用较强模型减少返工。

| 提示词/批次 | 建议模型/推理强度 | 原因 |
| --- | --- | --- |
| 背景交代 | frontier/high，例如当前可用 GPT-5.4 high | 历史结论、现行边界和新纠偏范围容易混淆 |
| 批次 1 | frontier/high | 需要审计旧实验、官方技能、版本和测试合同 |
| 批次 2 | frontier/high + 原生图像理解/编辑能力 | 分层资产、眼睑对齐、颈部遮挡决定后续上限 |
| 批次 3 | frontier/high | 涉及 GSAP 层级、确定性、关键姿态与视觉迭代 |
| 批次 4 | frontier/high | 需要判断方法能否迁移到真实项目素材 |
| 批次 5 | frontier/high | 匿名材料、公平对照和质量解释不能误导用户 |
| 批次 6 | frontier/high | 需依据用户反馈最小返修并形成最终架构结论 |

---

## 推荐批次划分

| 批次 | 是否与相邻批次合并 | 原因 |
| --- | --- | --- |
| 1. 审计与合同 | 不合并 | 先修正测试问题，避免后续继续验证错误目标 |
| 2. 受控资产 | 不合并 | 静态分层若不成立，动画只会放大瑕疵 |
| 3. 受控实现 | 不合并 | 用统一素材证明 HyperFrames 局部动作上限 |
| 4. 项目迁移 | 不合并 | 独立检验可迁移性，不能被小羊样片替代 |
| 5. 用户门 | 不合并 | 必须冻结匿名候选后等待用户判断 |
| 6. 最终收口 | 不合并 | 依赖用户意见，只做一次有界返修和分类 |

总提示词模式下，执行会话仍应自动从批次 1 连续推进至批次 5；只有计划写明的用户审片、资源越界、外部服务、破坏性操作或真实阻塞才暂停。

---

## 新会话背景交代提示词

本轮只做计划07的背景熟悉和执行前核对，不实施、不修改代码或文档、不创建执行记录、不生成或编辑图片、不安装或升级工具、不下载模型、不写HyperFrames组合、不渲染视频；请完整阅读 /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/07-HyperFrames拆层微动态专项验证计划.md、本文提示词文档、总体规划、计划04与计划06最终执行记录、motion_feasibility_v1.md、director_workflow_v1.md、核心需求与项目交接文档，再只读检查当前git工作树、旧HyperFrames人物方案JSON与HTML、计划04适配器、现有隔离环境和样片证据；必须调用并完整遵循当前HyperFrames入口技能，按需阅读hyperframes-core、hyperframes-animation、hyperframes-keyframes、hyperframes-cli、hyperframes-creative和media-use的本地说明，同时用当前官方文档或Context7核对发生变化的版本/命令，不凭旧记忆；重点确认前次人物实验主动设置no_segmentation、no_independent_body_motion并禁止眨眼/呼吸等动作，故旧结果只能否定整图推近与弱叠层，不能否定拆层微动态；准确复述计划07的两案例、S/W/L同源对照、动作Brief、素材层、关键姿态、资源上限、用户门、禁止修改范围和PASS/CONDITIONAL/FAIL；若文档与当前代码或官方技能冲突，记录差异但本轮不得修复；子代理仅可用于边界明确的只读代码映射或官方资料核对，主执行者必须复核并结束；完成后只报告目标理解、旧测试误区、当前HyperFrames/Node/Chrome/FFmpeg事实、关键文件、预计风险、工作树保护、是否具备进入批次1的条件，不开始任何执行。

---

## 批次 1 提示词：现状复核、错误测试审计与实验合同

把本段视为可独立执行的计划07批次1合同；先完整阅读 /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/07-HyperFrames拆层微动态专项验证计划.md、本文提示词、总体规划、计划04/06最终记录、motion_feasibility_v1.md、旧人物shot plan与HTML、当前HyperFrames相关技能和最新官方命令，再读取 /Users/yuh/Desktop/项目/文本视音屏生成器/短视频V2规划文档/执行记录/07-HyperFrames拆层微动态专项验证执行记录.md，若不存在则先创建简洁标题、背景与批次1章节；本批节奏固定为只读核对现状→列目标/文件/测试/风险/最小改动→建立实验合同与轻量测试→自审→定向验证→更新记录，不生成/编辑图片、不渲染视频、不修改正式pipeline；必须记录git HEAD/status并保护用户已有修改，不reset/clean/checkout/stash，不碰计划04冻结工程；调用HyperFrames入口技能以及core/animation/keyframes/cli/creative/media-use，按技能要求核对旧pin、npm latest、doctor、Node、Chrome、FFmpeg、磁盘和进程，只对新计划07工程运行只读upgrade check，不在旧工程升级；明确写出旧测试哪些证据仍有效、哪些结论不适用于拆层微动态，禁止再次用“保护原图”排除主体动作；在 【包A】视频引擎包/experiments/short_video_v2_phase7/ 下建立README、layered_motion_brief_v1.md、asset_manifest_v1.json、scorecard_v1.json，并建立只约束路径/命令/模板/媒体/动作证明字段的 test_v2_phase7_hyperframes_micro_motion.py，不实现第二套引擎、不新增依赖、不硬编码小羊名称、一次性哈希或评分答案；合同必须区分镜头层、场景层、主体层和局部状态层，定义案例A受控动物、案例B项目迁移、S/W/L同源对照、关键姿态、视觉失败项、1GiB新增上限和用户审片门；如需创建计划07隔离根，只创建空目录与轻量元数据，不下载模型或浏览器；运行phase7定向测试及必要的现有phase4合同测试，失败先修合同而非放宽门槛；子代理只可做旧代码只读审计、官方资料核对或测试审查，结束前必须收束；完成后更新执行记录，写明实际文件、版本、命令、测试、差异、风险与是否允许进入批次2，并在最终报告列改动、验证和保护情况后自动进入批次2。

---

## 批次 2 提示词：受控样片资产与静态姿态证明

把本段视为可独立执行的计划07批次2合同；开始前完整阅读计划07第4–7、9–12节、当前HyperFrames与ImageGen/Image2技能、批次1执行记录和新模板，确认批次1测试通过，再按只读盘点→写动作Brief和资产策略→生成/编辑→静态叠合与关键姿态审查→一次有界修订→冻结manifest→测试→记录的节奏执行；本批只为案例A准备一个原创、轮廓清楚、头颈与眼睛可分层的9:16小羊或等价动物主图，不写HyperFrames动画、不渲染S/W/L视频；必须先明确身份锚点、主图焦点、镜头/主体/局部状态/环境动作、层级、枢轴、遮挡、证明帧与失败项，再使用当前Codex ImageGen/Image2能力生成或选择master，保存完整提示词和生成账；准备background-clean、subject-cutout、body、head、eyes-closed或eyelid、foreground及asset manifest，优先小步Image2编辑和同图切分，可对适合输入试一次HyperFrames官方remove-background候选，但需先记录是否触发官方模型下载并把全部新增限制在 /Users/yuh/Library/Caches/text-video-plan07-hyperframes/ 与1GiB内，自动去背对动物边缘失败时不得连下其他模型；所有层先叠回master，另制作头部动作峰值、闭眼状态、浅/深底alpha边缘和联系表，逐项检查颈部余量、原头残影、双眼/双脸、背景空洞、毛发硬边、闭眼透视和构图安全区；最多允许一次针对性资产修订，若主图先天不适合可换一张更适合分层的原创图，但必须记录原因和旧图，不能以滤镜、强光或缩小画面掩盖缺陷；不把生成式修改结果伪称为HyperFrames动作，不新增云API/密钥，不修改Schema、包A/B、旧样片或正式路线；子代理仅可做独立图像审查、alpha/哈希/manifest核验，不能并行生成另一套不一致主角，主执行者须统一选择并结束；冻结全部资产尺寸、alpha、SHA-256、来源和用途后运行phase7定向测试，更新执行记录的提示词、循环、资产、静态证明、问题、磁盘、测试与批次结论，静态层未通过不得进入批次3，通过后自动进入批次3。

---

## 批次 3 提示词：受控样片 S/W/L 实现与技术验证

把本段视为可独立执行的计划07批次3合同；开始前读取计划07第4、6–9、12–15节、HyperFrames入口/core/animation/keyframes/cli/creative/media-use技能、批次1–2执行记录和冻结asset manifest，确认静态叠合/点头峰值/闭眼姿态通过；本批节奏为核对输入和当前pin→catalog先行→建立新实验工程与hero frame→S/W/L实现→lint/check/keyframes/snapshot→draft视觉审查→最多一次动作参数修订→high render/probe/decode→记录，不修改正式pipeline；先用词面catalog查询camera push zoom、particle burst、drift/parallax等语义并只安装确实适配的组件，记录tier和结果，puppet/eyelid没有合适组件时按hyperframes-keyframes写最小GSAP关键姿态，不启用未授权的on-device目录索引；新工程不得改写计划04 rainy-messenger-motion，先只读upgrade check，若把0.7.106升到执行时最新稳定patch，只修改新工程package pin且upgrade后check必须通过，否则回原pin并记录；S为同图静态，W为同图整图推近/简单叠层，L必须在不同嵌套层实现克制推近、一次头部点动与回稳、一至两次非等间隔眨眼、低幅呼吸和一种前景/粒子运动，眼睑跟随head，camera/subject/head/eyelid/particle不得竞争同一transform；所有渲染关键动画同步建立在一个paused timeline，有限重复、固定种子、无Date.now/performance.now/未种子Math.random/网络fetch/无限循环，末帧有稳定hold且不黑屏/复位；对真实动画目标分别运行lint、strict check、keyframes JSON、focused shot与第一帧/动作前/峰值/闭眼/回稳/final-minus-hold/最终帧snapshot，不能只证明camera-rig，若动作太弱不可感知须调高而非用晃动代替，若木偶感或接缝明显须降低幅度或修层；只以draft迭代，技术和视觉门通过后再high render，S/W/L同为4–6秒、1080×1920、30FPS、H.264/yuv420p、video-only，执行ffprobe和完整解码，记录命令、退出码、哈希、耗时、RSS、磁盘与孤儿进程检查；最多一次有界参数修订，不无限润色，不加BGM/TTS/字幕/强滤镜；子代理只可做独立动画图谱审查、抽帧/媒体核验或测试复核，不能替代主执行者整合；更新执行记录与manifest后运行phase7和受影响phase4测试，最终报告列S/W/L、动作证明、问题、修订、测试、风险和是否允许进入批次4，通过后自动进入批次4。

---

## 批次 4 提示词：当前项目镜头迁移

把本段视为可独立执行的计划07批次4合同；先读取计划07第7.2、7.3、8–15节、批次1–3执行记录、案例A资产/组合/动作证明与当前项目最近一次成功短视频素材，先只读比较候选镜头的主体轮廓、头颈/叶柄、遮挡、背景可补全性和动作语义，再写选择理由与新的motion brief；本批目标是把批次3已经证明的最小方法迁移到一个真实项目相关镜头，优先西瓜幼苗/叶片清楚的植物镜头，其次人物近景或用户近期其他合适素材，不得用信息图、纯粒子或专门新造的第二张测试图替代迁移；植物路线应拆分background-clean、stem/base、若干关键叶片/藤蔓/果实、foreground与光粒，测试不同相位叶片轻摆、克制推近和一种局部光/露珠变化；人物路线只选一至两项点头/眨眼/呼吸并沿用颈部/眼睑/背景遮挡合同，不机械复制小羊的角度和时间；准备资产时保留原图、提示词、编辑循环、哈希与静态叠合证明，最多一次资产修订，自动去背失败不得下载新的大模型；至少输出W与L，资源允许时补S，所有版本同源、同时长、同规格，L必须含真实主体或植物层运动而非只有camera/particles；严格复用单一paused timeline、父子层、固定种子、finite repeat、离线资产和HyperFrames检查链，运行focused keyframes到真实head/leaf/eyelid目标、proof snapshots、draft/high render、ffprobe、完整解码和孤儿进程检查；明确区分“该素材先天不适合”“资产准备方法失败”“HyperFrames编排失败”和“视觉质量不足”，不可用换术语掩盖；不修改Schema、包A/B正式pipeline、旧成片或short-video-director能力声明，不加入音频；子代理仅可做候选素材只读评估、独立视觉审查、媒体/测试核验，主执行者整合并结束；更新执行记录的选择理由、动作Brief、资产、实际复杂度、循环、动作证明、媒体、性能、问题、测试和批次结论，形成可比较候选后自动进入批次5。

---

## 批次 5 提示词：匿名审片材料与用户门

把本段视为可独立执行的计划07批次5合同；先读取计划07第7.3、9、12、14–17节、全部案例A/B的master、manifest、S/W/L视频、proof snapshots、媒体探测和执行记录，确认没有缺失版本或未解释硬失败；本批节奏为冻结候选哈希→统一媒体规格→制作匿名映射/联系表/动作峰值证明→Codex独立评分→技术复杂度简表→展示用户→记录并暂停，不再改变动作、不重渲、不提前下结论；案例A必须提供同源S/W/L，案例B至少W/L，统一为1080×1920、30FPS、同时长、同编码目标，匿名文件名和画面不得暴露工具/版本/“新版更好”等暗示，private mapping单独保存；联系表只覆盖第一帧、点头/叶片峰值、闭眼、回稳、最终帧，另提供简短技术账说明层数、生成/编辑循环、作者时间、渲染时间和新增磁盘，不以复杂度多证明质量好；Codex按主体动作可感知性、自然度、身份稳定、接缝/遮挡、场景层次、镜头舒适度、工程复杂度和整体可用性评分并封存原始结果，不向用户展示可引导的工具映射或结论；随后必须把最小审片集交给用户，只问：哪版最像画面本身会动、局部动作是否自然且看得见、是否有木偶/接缝/闪烁/晕动、值得用于少量还是多数镜头、哪处应减弱/加强/删除；在用户答复前，把状态写为awaiting_user_review，计划最多CONDITIONAL，更新执行记录并暂停，不能继续批次6或宣称HyperFrames拆层微动态通过；不借用户门处理无关代码、Git提交或新工具；子代理只可做匿名性和证据独立核验，主执行者必须收束；最终报告只列审片入口、候选规格/哈希、盲化保护、已知风险、执行记录状态和等待用户回答的五项问题。

---

## 批次 6 提示词：最小返修、最终分类与交接

把本段视为可独立执行的计划07批次6合同；只有用户已完成批次5审片后才能开始，先读取用户逐项反馈、private mapping、封存Codex评分、全部执行记录和计划07最终等级，准确区分相对偏好与不可接受瑕疵；本批节奏为揭盲→定位用户指出的具体动作/时间点→每案例最多一次最小资产或参数返修→只重跑受影响检查和视频→必要时展示最小复核→冻结final manifest→更新现行文档→回归→最终结论；不得因用户偏好某版就忽略其对断颈、眼睑漂移、木偶感、晕动或动作不可感知的明确意见，不得用自动评分覆盖用户判断；返修优先调整动作幅度、相位、时间、枢轴、遮挡或单一局部状态，不能重做整套主图、换工具、加I2V/滤镜/音频或修改正式pipeline；重跑受影响的lint、strict check、focused keyframes、proof snapshots、high render、ffprobe与完整解码，并更新哈希、耗时、问题前后对照；依据两案例和用户意见给HyperFrames拆层微动态formal_candidate/manual_only/research_only/rejected之一，formal_candidate至少要求受控与项目迁移均通过且用户明确认为L优于S/W、基本可用，只有受控通过或适用面很窄应为manual_only/conditional，等待证据不得写PASS；更新 /Users/yuh/Desktop/项目/文本视音屏生成器/【包A】视频引擎包/docs/short_video_v2/motion_feasibility_v1.md、总体规划、phase7 README与final manifest，清楚标注计划04旧结论只覆盖整图/弱叠层，若建议正式接入则另立集成计划而非本批修改Schema或包A Motion Router；运行phase7定向测试和V2核心矩阵，检查旧样片、服务、工作树、磁盘、进程和隔离根，不自动删除缓存、不提交/推送；子代理只可做最终证据复核、回归失败分类或文档一致性审查，主执行者整合并结束；最后把用户反馈、返修、最终视频/哈希、动作证明、性能、资源、许可、测试、保护情况、最终等级、适用镜头和后续是否另立集成计划完整写入执行记录，并报告改动、验证、剩余风险和计划07是否完成。

---

## 每批进入下一批的硬性条件

1. 批次 1：旧测试误区、案例、模板、资源门和测试合同完整，定向测试通过；
2. 批次 2：静态叠合、头部峰值和闭眼姿态无明显穿帮，资产可追溯；
3. 批次 3：受控 L 版主体动作可独立证明，S/W/L 同规格且媒体通过；
4. 批次 4：至少一个本项目镜头含真实局部层运动，复杂度和失败类型有记录；
5. 批次 5：匿名候选冻结并等待用户，用户答复前不得进入批次 6；
6. 批次 6：用户意见已落实、一次最小返修完成、文档与回归通过、最终分类有证据。

若某批硬门失败，应在该批范围内做最小修复；若失败来自素材先天不适合，可以按计划允许的唯一次数更换或修订素材，但不得通过扩张工具、降低门槛或虚构动作证明继续。
