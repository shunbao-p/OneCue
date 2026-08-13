# 短视频 V2 图片动态化可行性与计划 05 交接（v1）

> 状态：历史研究记录，非第一版活跃工作流。自 2026-08-13 起，第一版统一采用多张静态分镜图、逐镜人声、字幕与硬切；新任务不读取本文件作默认路由，也不调用其中的动态工具。只有用户明确重开图片动态化专项时，才以本文件作为既往证据复核，且不得据此绕过新的授权、质量与工程评估。

## 1. 当前决定

- 默认路线始终是包 A 既有 FFmpeg 预设；它负责低复杂度动态、统一标准化与最终合成。
- 用户匿名审片已完成。四组虽都相对选择了高级版本，但用户明确认为自然场景候选仍只是微放大、平移或晃动，缺少真正的场景内/主体内运动；因此计划 05 当时的正式高级候选为零。
- HyperFrames 信息设计型人工选项继续保留为 `manual_only`。计划 07 Round 1 匿名审片的 `FAIL / rejected` 仍是冻结历史；Round 2 最终为 `CONDITIONAL / manual_only`：仅小鹿眨眼+单耳局部网格窄配方获用户接受。植物动作虽明显且像一阵风，但用户确认明显重影，故为 `user_rejected_due_to_ghosting / rejected`。普通人物/动物/植物生产路由关闭，12 镜广度门不启动。
- 本地静态图后备路线已退役；Image 2 仍是唯一经实际成片验证的图片生成主路。Draw Things / 本地 I2V 因未获授权归为 `research_only`。
- 高级工具不得写 Schema v1、不得进入 Job Bundle 公共输入、不得接管时间线、字幕、TTS、缓存或 final。

## 2. 镜头路由

| 镜头意图 | 默认 | 可选候选 | 当前状态 |
| --- | --- | --- | --- |
| 普通人物、建筑、风景图 | FFmpeg `slow_push_in` / `gentle_drift` | 无需高级工具 | 正式默认；优先微放大，避免无叙事依据的左右晃动 |
| 有明显前中后景、轮廓清楚的环境 hero 镜头 | FFmpeg | DepthFlow 外部 2.5D | `rejected`；不能产生雨落、旗动、人物动作等语义运动 |
| 路线、警灯、档案状态、信息图或可寻址 DOM 动画 | FFmpeg 静态推拉兜底 | HyperFrames 设计型单镜头 | `manual_only`；用户认为动态更明显，可用于少量特殊镜头 |
| 普通人物/动物/植物拆层微动作 | 明确要求静态时用静帧；否则仅用 FFmpeg 克制推近 | 仅保留小鹿眨眼+单耳窄配方作人工参考 | 普通自然主体生产路由关闭；植物 `user_rejected_due_to_ghosting / rejected`；不启动广度门 |
| 静态图生成 | Image 2 | 用户提供关键帧 | 无另一本地生成后备 |
| 本地 I2V | 不进入 MVP | Draw Things / SkyReels | `research_only` |

## 3. 计划 05 最小接口

计划 05 只需在包 A 内部保留下列实验适配信息；不得把命令、URL、模型路径或 Provider 私参加入 Schema：

```text
request:
  route: ffmpeg | hyperframes_design_manual
  source_image: absolute regular-file path
  duration_sec: finite positive number
  width: 1080
  height: 1920
  fps: 30
  focus_x/focus_y: 0..1
  preset/strength: package-A owned values
  experiment_work_dir: isolated absolute path
  cancel_event: package-A runtime cancellation source

result:
  visual_clip: absolute regular-file path
  media: H.264 / yuv420p / 1080x1920 / 30 FPS / video-only
  source_sha256
  route_version
  model_or_composition_sha256
  normalized_sha256
  render_elapsed_sec
  normalize_elapsed_sec
  peak_rss_bytes
  warnings/errors
```

## 4. 适配与缓存边界

- 所有命令必须由 `CommandRunner` 以 `list[str]`、`shell=False`、有限超时和统一取消执行。
- 外部工具先写隔离 raw；包 A 再标准化到无声 H.264/yuv420p。DepthFlow 不进入计划 05 正式适配，因此其 raw 原子暂存缺口不扩展为正式工程工作。
- 未来缓存键最少包含：输入图 SHA-256、route/version、时长/尺寸/FPS、运动参数；HyperFrames 另含 composition 源 SHA-256。
- FFmpeg 对照不得删除；高级路线失败、超时、取消或媒体校验失败时，应回落默认路线并保护旧产物。
- 中央实验根为 `/Users/yuh/Library/Caches/text-video-plan04-feasibility/`；退役的本地静态图路线已清理，余下路线仍必须按精确子目录单独处理，不得笼统清理其他用户缓存。

## 5. 许可与分发

- HyperFrames：Apache-2.0；当前仅中央实验项目与浏览器运行时，不打入包 A 发布物。
- DepthFlow：AGPL-3.0；仅作为独立外部人工工具继续评估，不复制或链接其代码进包 A。
- Draw Things：社区 CLI GPL-3.0；SkyReels 为 Skywork Community License；未下载，生产前仍需许可复核。

## 6. 用户审片与最终判定

- 用户选择：人物 B、风景 A、建筑 A、信息设计 B；揭盲后分别对应 HyperFrames 人物、HyperFrames 环境、DepthFlow 建筑、HyperFrames 信息设计。
- 这些选择只是同组相对偏好。用户同时把“没有真正动态镜头”列为不可接受瑕疵，并指出自然场景主要仍是微放大、左右移动或左右晃动。
- 用户认为微放大在现有自然场景方案中勉强可用；信息设计 B 动态更明显，值得少量特殊镜头。
- 显式质量意见优先于 4/4 相对票数。计划 04 最终正式高级候选为零；HyperFrames 信息设计降为 `manual_only`，不因票数降低硬门。

## 7. “真正动态”在当前条件下的客观边界

| 能力 | 当前工具是否支持 | 客观说明 |
| --- | --- | --- |
| 镜头微放大、推拉、平移 | 是 | FFmpeg 已足够；属于虚拟摄影机运动，不是画面对象自身运动 |
| 深度视差、轻微换视点 | 是 | DepthFlow 可做，但本质仍是估深后的摄影机运动，不能让雨、人物、旗帜真正运动 |
| 程序化雨线、雾、灯光闪烁、信息图动画 | 有条件支持 | HyperFrames 可生成真实随时间变化的 2D 叠层；当前样片雨层过弱，用户未感知到有效增益。加强后仍是合成层，不是原图中物体的生成式运动 |
| 人物/动物 2D 拆层枢轴动作 | 窄配方成立，广度未证明 | 小鹿以 clean background、身体、头部、眼睑、遮挡补片、单耳同拓扑局部网格与单一可 seek 时间线实现真局部动作，批次 8 已获用户接受；但仅此一例，不外推为普通镜头能力 |
| 植物叶片 2D 拆层微动 | 用户门失败 / `rejected` | 批次 9 的根部锁定网格峰值约 16–22px，用户确认动作明显、多叶像同一阵风，但同时报告明显重影。自动高质视觉门的 PASS 是假阴性，用户视觉门优先 |
| 衣发、表情、肢体、雨水与环境自然联动 | 当前未支持 | 需要 I2V/视频扩散或专门的角色动画模型。FFmpeg、DepthFlow、当前 HyperFrames 构图都不能自动完成 |
| 本地 I2V | 技术上可能，尚未验证 | M1 Pro 32GB 理论可试小型量化模型，但预计约 9.344 GiB 模型、较长推理、身份漂移与许可风险；用户当前未授权，计划 04 未下载 |
| 云端 I2V | 未评估/未接入 | 当前项目没有经授权、经验证的视频生成 Provider；若未来评估，仍须保持包 A 时间线、字幕、缓存与最终 FFmpeg 合成职责 |

计划 05 已采用“FFmpeg 微放大默认 + HyperFrames 信息设计人工可选”的保守交接。计划 07 完成透明层、枢轴、遮罩与局部状态的正确复测后，仍未过用户视觉门，故不建立主体微动态正式或人工生产路由。若未来产品仍需走路、转身、表情、衣发或环境语义联动，必须另立有界 I2V/角色动画可行性计划，且需新的下载/API/费用授权。本轮不以整图晃动冒充主体动态。

## 8. 计划 07 纠偏状态

- 计划 04 的 HyperFrames CLI、Chrome、确定性渲染、信息设计和弱环境叠层证据继续有效；
- “自然人物已拒绝”的旧结论只适用于当时的整图推近、雨层和光罩方案，不适用于从未实施的头部、眼睑、身体、衣物或植物分层动作；
- 计划 07 已完成同源 S/W/L、受控动物和真实项目植物迁移；静态分层、枢轴、遮挡、单一可 seek 时间线、focused keyframes 与媒体硬门均成立；
- 匿名揭盲：案例 01 候选 01=L、02=W、03=S；案例 02 候选 01=W、02=S、03=L。
- 用户认为案例 01 L 最像会动，但动作生硬且木偶感明显；案例 02 L 仅被感知为画面变大，局部叶片动作不可见。用户未见明显接缝、闪烁或晕动，但认为所有候选均不适合多数普通镜头，且当前效果差到无必要指定减弱/加强/删除某一动作。
- 因用户否定整体基本边界且未给出有价值的有界返修目标，批次 6 不臆造参数调整、不重渲。计划 07 最终为 `FAIL`，HyperFrames 自然主体拆层微动态分类为 `rejected`。
- 该拒绝不否定 HyperFrames `manual_only` 的信息设计用途，也不改变 Image 2 + 包 B + 包 A/FFmpeg 主链已通过的事实；不新建主体微动态 Provider，不修改 Schema v1、包 B 或包 A 正式管线。

## 9. Round 2 有界重开最终状态

- Round 1 的 `FAIL / rejected` 是已归档的用户审片结论，旧媒体、匿名审片、映射、评分与 `final-manifest.json` 均保持原状，不能被第二轮覆盖或改写。
- 用户后续反馈已给出可执行的姿态表示与局部动作感知诊断，故仅撤销“没有有价值的有界返修目标”这一停止依据；它不推翻 Round 1 的视觉失败事实，也不表示主体微动态已获生产准入。
- Round 2 已在批次 9 用户终审后收口为 `complete / CONDITIONAL / manual_only`。独立证据树保留全部历史门状态；普通人物、动物、植物的正式生产路由关闭，信息设计用途仍为 `manual_only`。
- Round 2 不得修改 Schema v1、Job Bundle 公共输入、包 A/B 正式管线或计划 04 冻结工程；不得新增模型、Provider、云 API、费用或音频。
- 第二轮已依成熟 2D 绑定原则（同纹理/同拓扑、刚性与权重形变分离）作最小本地验证。独立姿态生成、交叉淡化、双向光流与整头网格压缩皆因身份漂移、重影/晕边或头骨变扁而判废。
- Round 2 小鹿最终为单耳 2.7° 加权网格微摆+两次眨眼，脸和颈部像素不变，已获用户接受。植物批次 9 的约 21.9/16.0/16.0px 错峰局部网格位移保留 `replay_verified_technical_candidate`，但用户因明显重影将其拒绝。工程门通过不能替代用户视觉门；正式生产路由不变。

### 9.1 用户复核后的证据更新

- 用户现已确认 Round 2 两案都读作“画面中的事物在动”，鹿的眨眼/耳部与植物叶片均可见；鹿总体自然，植物的主要失败是旧位同源叶片仍在，形成重影。用户主观上认为若修复，此路线可考虑多数普通镜头。
- 此处记录的是批次 8 前的阶段性诊断：当时已确认植物层所有权重复是旧位双像的一项直接机制，而非时间线残帧；尚不能据此把它外推为整条植物路线的唯一根因。受影响修订只做两件事：鹿耳峰值由 2.4° 微增至 2.7°；植物改为每个主体像素唯一归一层，删除静态 seam cover，动作时序不变。
- 植物新资产在 alpha 0–255 全阈值均为 0 holes / 0 extras / 0 pairwise overlap，层零姿态与 canonical subject RGBA 误差为 0；逐帧视频门未见旧位叶片、断根、洞、黑边或色边。鹿逐帧门未见跳变、双头、耳根裂缝或脸颈牵连，乱序 seek 同时点哈希一致。
- 两案已冻结为 `replay_verified_awaiting_revision_review`，而非 `production_recipe`；用户返修审片前，现行 `rejected` 正式路由不变。

### 9.2 何时才能判断“视频多数镜头可动态化”

- 两个正例只能证明窄能力，不能证明多数镜头。已建立 `motion_experiment_playbook_v1.md`，后续用一次性 `3 个真实视频 × 每个 4 类镜头 = 12 镜` 广度门收束，不再围绕单一耳朵或叶片无限调参。
- 通过线为：至少 9/12、每视频至少 3/4、2D eligible 镜头通过率至少 80%、每种拓扑至少 2/3，且用户无木偶、重影、断缝、闪烁或明显语义错误。每镜最多 30 分钟首次作者工作 + 15 分钟唯一返修；45 分钟即止。
- 走路、转身、手物交互、口型、复杂表情、长发衣物大幅运动、水烟火、完整风场联动、新视角/新表面不再逐项塞入当前 2D 路线，而归入 `semantic_motion_required`。
- 若未来批准新作者工具与费用，优先有界评估 Spine weighted mesh 作为上游形变作者工具，HyperFrames/GSAP 仍掌唯一主时间与最终 MP4；Rive、Live2D 与 After Effects 分别受云、seek/许可或安装/订阅边界限制，本轮未接入。

### 9.3 批次 9 植物最终有界返修

- 批次 8 用户复核已将小鹿标为 `user_accepted`，对植物则给出“幅度太小、应让不止一片叶子同时摇动”的明确修订目标。这是对植物的最后一次自动有界调整，`automatic_batch10_forbidden=true`。
- 直接增大批次 8 刚性整层角度的诊断稿露出严重斜缝和西瓜纵切缝，已判废且未对用户展示。根因是这些层含语义不连通残片；因此正式返修将顶叶、左叶、右下前景株重建为三个语义连通层，西瓜与其他残余回归静态所有者。
- 每个活动层使用根部锁定的局部 SpriteKit 网格烘焙 31 个状态，由 HyperFrames/GSAP 单一 paused 时间线以绝对时间错峰切换，无交叉淡化、整图摇动、滤镜或粒子代替。顶/左/右下前景株峰值约 21.9/16.0/16.0px，两组主叶同时可见窗口为16帧。
- 256 个 alpha 阈值的 holes/extras/pairwise-overlap 均为 0，零姿态与根部锁定 RGBA 误差均为 0，乱序 seek 同时点像素哈希一致。高质成片 150/150 帧视觉门未见重影、断根、运动开缝、闪烁、方块或色边，西瓜与相机保持静止。
- 植物的技术状态保留为 `replay_verified technical candidate`，用户状态则是 `user_rejected_due_to_ghosting / rejected`。自动高质视觉门未发现用户看到的重影，故此次为自动视觉门假阴性，用户门优先。12 镜广度门保持 `not_run / cancelled_due_to_failed_prerequisite`，失败前置为 `case_b_user_visual_gate`；不启动批次 10，不重开正式集成。
- 用户回复后的解码帧复核在约 1.27–3.03s 复现结构性双轮廓，1.53–2.00s 最明显。交叉淡化与纯编码拖尾已被排除；粗语义簇独立形变造成的动态—动态及动态—静态结构错叠，被确认为重要贡献机制，但最终因果例外已表明它不是已证明的唯一或完整根因。31 态硬切带来的状态持帧会加重滞留感，但只列为次因。

### 9.4 用户授权的最终因果例外与路线终止

- 一次性 single-owner `36x48` unified mesh 排除试验登记为 `user_authorized_final_causal_exception`，不属于批次 10、Round 3 或新候选；既有 `complete / CONDITIONAL / manual_only`、小鹿 `user_accepted`、普通自然主体生产路由关闭及广度门取消均不变。
- 唯一有效首跑的 G4 动作门 `PASS`；G5 `visible-strain` 为 `HARD FAIL`，指标为 `sigma_min=0.435627`、`sigma_max=1.622578`、`cond=2.435135`、`area=0.462118–1.552697`、`p99=1.324495`，另记录 `zero-warp drift`。`G6 proxy` 无效，不作裁决。
- 本例未创建 HF composition/draft、未形成用户审片媒体，也未作第二次调参。批次 9 多层结构互穿只可表述为重要贡献机制，不能再写成唯一或完整根因；single-owner 统一网格又因可见纹理应变而不可用。
- 最终技术标记为 `single_owner_unified_mesh_hard_fail`，路线标记为 `plant_route_permanently_stopped`；不启动批次 10，不恢复 12 镜广度门或正式 Provider 集成。
