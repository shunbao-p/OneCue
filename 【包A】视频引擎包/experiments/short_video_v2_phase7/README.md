# 短视频 V2 Phase 7：HyperFrames 拆层微动态实验合同

> 状态（2026-08-13）：历史实验目录，第一版不调用。保留合同、测试与证据以便复盘；不得由新建、续接、渲染或返修任务自动运行。

本目录只保存计划 07 的轻量、可追溯实验合同。HyperFrames 工程、npm 缓存、Chrome、可再生 draft 和中间帧位于 `/Users/yuh/Library/Caches/text-video-plan07-hyperframes/`；最终审片证据位于本项目 `成片/短视频V2样片/phase7-hyperframes-micro-motion/`。

## 最终状态

- 计划等级：`CONDITIONAL`；最终分类：`manual_only`。Round 1 的 `FAIL / rejected` 作为冻结历史保留，不被 Round 2 覆盖。
- 只保留一条已获用户接受的窄配方：小鹿两次眨眼 + 单耳加权网格微摆。它不外推为其他动物、人物或多数普通镜头的能力。
- 植物批次 9 的动作被用户确认为“明显”且“像一阵风”，但同时存在“明显重影”，故用户门最终为 `user_rejected_due_to_ghosting / rejected`。
- 工程、冷重放、seek 和自动 high 逐帧门的 PASS 仅保留为 `replay_verified_technical_candidate`证据。自动门未发现用户看到的重影，属假阴性；用户视觉门优先。
- 普通自然主体生产路由关闭；12 镜广度门 `not_run / cancelled_due_to_failed_prerequisite`，失败前置为 `case_b_user_visual_gate`；不启动批次 10。HyperFrames 信息设计仍保持 `manual_only`，Image 2 + 包 B + 包 A/FFmpeg 主链不受影响。

## 实验问题

不使用生成式 I2V 时，一张静态图经真实拆层后，HyperFrames 能否以父子层、正确枢轴、遮罩和单一 seek-safe 时间线实现可感知局部动作，且优于静态与旧式整图运动？

## 两个案例与公平对照

- 案例 A：原创、轮廓清楚、头颈/眼睛可拆的受控动物或角色。
- 案例 B：当前项目真实素材，优先叶片轮廓清楚的西瓜幼苗/植物镜头，其次为头颈与背景较清楚的人物近景。
- S：同源静态主图，无动作。
- W：同源主图，仅整图推近/平移与简单叠层。
- L：同源主图，含镜头层、主体局部动作、局部状态与环境/前景层。

对照必须同尺寸、同时长、同 FPS、同编码目标、无音轨，画面不暴露工具或“新版更好”暗示。

## 四层动作合同

1. 镜头层：camera rig 的克制推近，不与主体 scale 争用同一元素。
2. 场景层：前中后景、草叶、光粒或局部光线，固定种子且有限循环。
3. 主体层：body/subject 低幅呼吸，head 围绕颈部枢轴点动，或 leaf 围绕叶柄不同相位摆动。
4. 局部状态层：眼睑/闭眼状态、露珠/局部高光等，必须与其父层同步。

案例 A 必须覆盖镜头层、主体层、局部状态层，并有一种环境/前景动作。不得以整图晃动、滤镜、粒子或光效冒充主体动态。

## 资产与静态姿态门

- 动物/人物：`master`、`background-clean`、`subject-cutout`、`body`、`head`、`eyes-closed|eyelid`、`foreground`。
- 植物：`master`、`background-clean`、`stem|base`、`leaf-01..N`、可选 `fruit`、`foreground`、`light|particle`。
- 所有资产须有来源、提示词或操作、尺寸、alpha、SHA-256、用途和版本。
- 先把各层静态叠回 master，再审查动作峰值、闭眼/局部状态、浅/深底 alpha 边缘；静态不成立禁止进入动画。

## HyperFrames 实现合同

- 每个 composition 只有一个同步创建的 `gsap.timeline({ paused: true })`，以根 `data-composition-id` 为 `window.__timelines` 键。
- camera/subject/head|leaf/eyelid|state/foreground/particle 使用稳定选择器与父子层；同一元素的同一 transform 属性不并发竞争。
- 无 `Date.now`、`performance.now`、未种子 `Math.random`、运行时 fetch、计时器、未注册 rAF 或 `repeat:-1`。
- 关键姿态：第一帧、动作前稳定、主动作峰值、局部状态峰值、回稳、final-minus-hold、最终帧。
- 证据链：`lint`、`check --strict --snapshots`、真实主体 focused `keyframes --shot`、定点 `snapshot`、draft 自审、high render、ffprobe、完整解码、孤儿进程检查。

## 安全、资源与用户门

- 实验命令仅用 list argv、`shell=false`、有限 timeout，且输出路径必须在计划 07 根内。
- 计划 07 新增下载/缓存上限 `1 GiB`；新模型、第三方 Provider、云/API/费用、破坏性操作须暂停。
- 批次 5 冻结匿名审片材料后曾合法停于 `awaiting_user_review / CONDITIONAL`；映射与 Codex 评分均在用户观看前封存。
- 用户已答复五问，批次 6 只做揭盲、失败分类、文档与回归；未改动作或重渲。最终不宣称 PASS 或正式候选。

## Round 2 重开状态（已收口）

- Round 1 的 `FAIL / rejected`、原始媒体、匿名映射与 `final-manifest.json` 均为冻结历史，不得覆盖、改写或以 Round 2 产物替代。
- 用户后续提出了可验证的姿态表示与局部动作感知问题；这只撤销当时“没有可执行的有界返修目标”这一停止依据，不撤销 Round 1 的用户视觉失败证据，也不恢复生产路由。
- Round 2 已依用户终审收口为 `complete / CONDITIONAL / manual_only`。新媒体、历史审片集、私有映射和 `round2-manifest.json` 仍位于独立 `round2-reopen/` 证据树，冻结批次文件保留当时的 waiting 状态，最终结论只写在聚合 manifest 与现行文档。
- 本轮仍不得修改 Schema v1、Job Bundle 公共契约、包 A/B 正式管线、计划 04 工程或已验收成片；不新增 Provider、模型、云 API、费用或音频。

Round 2 首次复核后，用户已确认两案均为真实对象运动：鹿总体自然，植物则因静态层保留同源叶片而出现重影。批次 8 以唯一像素所有权消除重影后，用户已明确接受小鹿；植物则因幅度偏小、同时动叶不足而要求最后一次有界返修。

批次 9 未继续放大整个不连通叶层；该路径已由斜缝压力试验判废。冻结候选将顶叶、左叶、右下前景株重建为三个语义连通层，每层以根部锁定的 31 状态局部网格在单一 paused 时间线上错峰摆动。三组峰值位移约 21.9/16.0/16.0px，有16帧至少两组主叶同时可见。自动 high 逐帧门当时报 PASS，但用户终审报告“明显重影”，故自动门为假阴性。最终状态为 `case_a=user_accepted / case_b=user_rejected_due_to_ghosting`；技术候选证据保留，但不获生产准入。

终审后的解码帧复核在约 1.27–3.03s 复现结构性双轮廓。它不是 crossfade、背景旧主体残留或单纯编码拖尾；现有门只证明每层唯一可见、alpha 互斥、8 连通与零姿态等价，却未证明活动层内的多叶/枝杈纹理具有同一形变语义，也未检查独立形变后的动态—动态及动态—静态结构错叠。31 态硬切及较高持帧率会加重滞留感，但列为次因。此问题仅作失败取证，不据此生成批次 10。

跨会话配方、失败边界与原预注册的 `3 视频 × 4 镜头` 有限广度门见 `docs/short_video_v2/motion_experiment_playbook_v1.md`。该门因案例 B 用户视觉前置失败而取消；不宣称多数普通镜头可自动动态化。走路、转身、手物交互、口型、复杂衣发、水烟火、完整风场耦合与新视角归为 `semantic_motion_required`。

## 用户授权的最终因果例外（永久收口）

`user_authorized_final_causal_exception` 不是批次 10、Round 3 或新候选。唯一有效首跑以 single-owner `36x48` unified mesh 获 G4 动作门 `PASS`，但 G5 `visible-strain` `HARD FAIL`（`sigma_min=0.435627`、`sigma_max=1.622578`、`cond=2.435135`、`area=0.462118–1.552697`、`p99=1.324495`），并记录 `zero-warp drift`；`G6 proxy` 无效，不作裁决。试验未建 HF composition/draft、未二次调参。故批次 9 多层结构互穿只认定为重要贡献机制，而非唯一或完整根因；统一网格补救亦因可见纹理应变不可用，冻结为 `single_owner_unified_mesh_hard_fail / plant_route_permanently_stopped`。既有 `complete / CONDITIONAL / manual_only`、小鹿 `user_accepted`、普通自然主体生产路由关闭、广度门取消与不启动批次 10 均不变。
