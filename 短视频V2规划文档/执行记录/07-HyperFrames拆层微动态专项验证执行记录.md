# 短视频 V2 计划 07：HyperFrames 拆层微动态专项验证执行记录

> 后续产品决定（2026-08-13）：本记录转为历史证据，第一版不做图片动态化。原有 `complete / CONDITIONAL / manual_only` 是该实验自身判定，不代表 HyperFrames 仍在活跃工作流中。

> 工作区：`/Users/yuh/Desktop/项目/文本视音屏生成器`
> 开始日期：2026-08-12（Asia/Shanghai）
> 当前状态：`complete / CONDITIONAL / manual_only`
> 当前结论：Round 1 的 `FAIL / rejected` 仍为冻结历史；Round 2 仅小鹿“两次眨眼 + 单耳微摆”窄配方获用户接受。植物虽动作明显且像一阵风，但用户确认存在明显重影，最终为 `user_rejected_due_to_ghosting`。普通自然主体生产路由关闭，12 镜广度门不启动

## 0. 任务边界与工作树保护

- 本轮只验证“静态主图 → 干净背景/身体/头部/眼睑或闭眼状态/前景等独立资产 → 父子层+正确枢轴+遮罩+单一可 seek 时间线 → 无声单镜头”。
- 旧实验 `no_segmentation=true`、`no_independent_body_motion=true`，并明确禁止眨眼、呼吸与衣袂形变；因此只能否定整图推近与弱叠层，不能否定本轮拆层微动态。
- 禁止修改 Schema v1、Job Bundle 公共契约、包 A/B 正式管线、旧计划 04 工程、已验收成片与旧审片证据。
- 不启用 MFLUX、DepthFlow、Draw Things 或 I2V；不加 BGM、SFX、环境音、TTS 或字幕。
- 不执行 `reset/clean/checkout/stash`，不自动 stage、commit 或 push；所有新产物只落在计划 07 实验根与证据根。
- 资源门：计划 07 新增下载/缓存默认不超过 `1 GiB`；新模型、第三方 Provider、云/API/费用、破坏性操作须暂停。

### 0.1 起始 Git 现场

- 分支：`main`
- HEAD：`99e3c14835f769a9aa26bfaccf8e8140204b9a96`
- 工作树开始时已脏；已记录并保护 10 项 tracked 变更与两份未跟踪的计划 07 规划/提示词文档。
- 其中包含现行 `motion_feasibility_v1.md`、计划 04 退役 MFLUX 相关修改、`config.ini` 及总体规划等用户已有内容；本轮不覆盖、不回退。

## 1. 批次 1：现状复核、错误测试审计与实验合同

### 1.1 执行目标

1. 冻结旧实验真实范围，不再用“先禁止主体动作”的实验判断主体动作能力。
2. 冻结案例 A/B、S/W/L 公平对照、四层动作、关键姿态、资产/媒体/资源/用户门。
3. 仅新建轻量合同、模板与定向测试；不生成图片、不写动画、不渲染视频。

### 1.2 权威资料与当前事实

- 已完整阅读计划 07 正文与执行提示词，并按序核对总体规划、计划 04/06 最终记录、`motion_feasibility_v1.md`、旧 shot plan/HTML、计划 04 适配器、导演工作流、核心需求与交接文档。
- 已完整读取 HyperFrames 入口、core、animation、keyframes、CLI、creative 与 media-use Skill；并读取本任务所需的 determinism、GSAP、motion principles、init/check/render/doctor/upgrade 及 remove-background 参考。
- Context7 解析 `/heygen-com/hyperframes`，确认项目 pin 只读检查命令为 `npx hyperframes@latest upgrade --project . --check --json`；最终门为 `check`、真实目标 focused keyframes/snapshot 与渲染媒体校验。
- npm 当前 latest：`hyperframes 0.7.107`，`dist.unpackedSize=25,686,311 B`，Apache-2.0。
- 旧项目 pin：`0.7.106`；Node `24.17.0`，npm/npx `11.13.0`，Chrome Headless Shell `152.0.7928.2`，包 A FFmpeg/ffprobe `8.1.2`。
- 旧隔离根约 `1,142,540 KiB`；数据卷可用约 `291.9 GiB`。计划 07 根已只创建空目录，未下载模型、浏览器或 CLI。
- 旧 pin 的 `doctor --json` 必要项（Node/CPU/内存/磁盘/FFmpeg/ffprobe/Chrome）通过；总 `ok=false` 仅因本轮不需要的 Whisper/TTS/BGM/Docker 可选项缺失。离线 doctor 把 0.7.106 视为 latest，版本结论以联网 `npm view` 的 0.7.107 为准。
- 当前无计划 07 HyperFrames/Chrome/FFmpeg 孤儿进程；工作区存在 Codex/CodeGraph/Context7 自身 Node 进程，不属于本计划，不处理。

### 1.3 旧测试证据分类

**仍然有效**

- HyperFrames 0.7.106 + Chrome + FFmpeg 能在本机确定性检查、高质量渲染、取消并输出 1080×1920/30 FPS/H.264/yuv420p 无声单镜头。
- 设计信息镜头可用；整图推近、弱雨层和光罩对自然人物的观感增益不足。
- 旧适配器的 list argv、`shell=False`、有限 timeout、隔离输出与取消收束证据仍可作工程参考。

**不适用于本轮上限判断**

- 旧人物只有一张完整 `<img>`，没有 background-clean/body/head/eyelid/foreground 独立层。
- 旧 HTML 只对整图 `scale 1.000→1.024`、雨层整体位移与光罩位移/透明度变化；无头部枢轴、呼吸、眼睑、衣物或前后景独立动作。
- 因旧 brief 主动禁止拆层与主体动作，“自然人物 HyperFrames 已拒绝”不可外推为拆层微动态失败。

### 1.4 本批计划内改动

- 新建本执行记录。
- 新建 `experiments/short_video_v2_phase7/README.md`。
- 新建 `templates/layered_motion_brief_v1.md`、`asset_manifest_v1.json`、`scorecard_v1.json`。
- 新建 `tests/test_v2_phase7_hyperframes_micro_motion.py`，仅约束路径、命令、模板、媒体、动作证明与用户门，不实现第二套引擎。
- 新建空的计划 07 隔离根与证据根；本批不产生图片或视频。

### 1.5 验证、问题与批次结论

- phase7 定向测试首轮 6 PASS / 1 FAIL；失败仅因测试期待英文 `runtime fetch`，模板实际写为等价且更准确的中文 `运行时 fetch`。仅修正该词面断言后 fresh 7/7 PASS。
- phase4 合同回归 fresh 14/14 PASS；未修改 phase4 源码、计划 04 冻结工程或旧产物。
- `git diff --check` 对本批新文件无报错。
- 已只读筛选案例 B 真实素材：首选 `user-creations/watermelon-growth-20260812/assets/keyframes/shot-003.png`（941×1672），因为主藤、多片掌状叶与叶柄枢轴清楚，适合不同相位叶片轻摆；叶缘茸毛与交叠遮挡为主要风险。
- 计划 07 新工程的 pin 只读 upgrade check 将在批次 3 scaffold 创建后立即执行；本批未创建 HyperFrames 项目，不在旧工程上执行升级。
- **批次 1：PASS。** 错误测试边界、两案例、S/W/L、四层动作、资产/姿态/媒体/资源/用户门与定向测试均已冻结，允许进入批次 2。

## 2. 批次 2：受控样片资产与静态姿态证明

> 状态：`PASS`

- 输入与边界已核对：本批只为案例 A 准备原创 9:16 受控动物主图、干净背景、透明主体、身体、头部、眼睑/闭眼状态与前景；不写 HyperFrames 动画，不渲染 S/W/L。
- 已依 ImageGen Skill 生成 1 张原创小鹿主图，并以同一构图为源制作 clean background、闭眼状态与色键主体源；全部提示词已写入 `case-a-controlled/prompts.md`。
- 确定性资产准备产出 1080×1920 的 `background-clean/body/head/neck-cover/eyes-closed/foreground-left/foreground-right`等独立层；头部以颈根为枢轴，头/身保留重叠区并以 `neck-cover` 处理遮挡缝。
- 首轮浅/深底 alpha 审查发现细窄洋红边；仅执行计划允许的一次有界修订（`edge-contract 1` + `edge-feather 0.25`），复审无硬洋红边。高反差底上仍有纤细暖色自然毛边，列为渲染像素复查风险。
- 静态证明已冻结：hero 重组、主体峰值、闭眼峰值、浅/深底 alpha 与接触表；局部差分框分别为 `[259,446,850,1121]` 与 `[392,662,703,794]`，证明变化发生于主体局部而非整帧。
- 清单校验捕获色键源实际为 941×1671（非预期 941×1672）；已如实修正 manifest，且下游所有层均已确定性归一到 1080×1920。
- phase7 定向测试 fresh 8/8 PASS，包含所有源/分层/证明的实际尺寸、透明性语义与 SHA-256 反查；phase4 回归 fresh 14/14 PASS。`git diff --check` 只报告任务开始前已存在的 `config.ini` 空行，本批新文件无新的空白错误。
- 计划 07 缓存根仍为 0 KiB；未新增模型、第三方 Provider、云/API 或费用。
- **批次 2：PASS。** 静态不成立禁止动画的门已通过，允许进入批次 3。

## 3. 批次 3：受控样片 S/W/L HyperFrames 公平对照

> 状态：`PASS`

- 输入与边界已核对：只使用批次 2 冻结的小鹿同源资产；于计划 07 独立缓存根创建新工程，不修改旧计划 04 工程。
- 以当前实际包 `hyperframes 0.7.107` 核对 `init/catalog/check/keyframes/snapshot/render` 帮助，新工程 pin 为 0.7.107；`upgrade --project . --check --json` 返回 `changed=false`。
- `npx @latest` 首次隔离下载卡在无输出状态，在计划 07 缓存占用约 347 MiB 时终止本轮新建的三个悬挂 npm 进程，保留缓存避免重复下载；随后直接使用已落地的 0.7.107 包入口，未越过 1 GiB 门。
- catalog 词面查询 `camera push zoom` / `particle burst` / `foreground drift parallax` 均为 `tier=words`；结果含 `push-in`、确定性粒子与 parallax 参照，但无匹配动物颈根枢轴+眼睑状态的组件，故未安装 registry 项，依 keyframes 合同手写最小 GSAP。未启用 on-device 索引。
- 工程完全位于 `/Users/yuh/Library/Caches/text-video-plan07-hyperframes/project/short-video-v2-micro-motion`；GSAP 3.14.2 冻结为本地离线资产（SHA-256 `c174bfce…d8280`），运行时无 CDN/fetch。只读复用旧隔离根的 Chrome Headless Shell 152.0.7928.2，旧工程未改动。
- S 为同图静态；W 为同图 1.000→1.035 整图推近+显式光粒；L 以独立 `camera/scene/body/head-rig/eyes-closed/foreground/motes` 完成同幅推近、2.6° 一次点头及回稳、1.30s/3.62s 两次非等间隔眨眼、两段低幅呼吸及前景/显式光粒。所有动作在每组合单一 paused timeline 内，有限 repeat，无随机、时钟或网络依赖。
- strict check 在 69 个时间/转场样本上 0 error / 0 warning / 0 issue；focused keyframes 分别证明 `#head-rig`、`#eyes-closed`、`#body`，且 head 报告明确为 `0°→2.6°→0°`。
- 首轮可寻址抽样在组合边界 5.000s 触发 end-exclusive 黑帧；这不是视频末帧故障。终帧证明改取 30 FPS 实际最后一帧 4.966s/帧 149，S/W/L 均有图且未复位。为消除 CLI 对回稳起点的模糊静态推断，把等值 `to` 重写为显式 `fromTo`；数值未变，不计入动作参数修订。
- draft W/L 经完整解码与接触表自审：L 主体动作可感知，未见断颈、双脸、眼睑漂移、背景空洞或硬毛边；未使用计划允许的一次参数修订。
- high S/W/L 均为 5.000s、1080×1920、30 FPS、H.264/yuv420p、video-only，`ffprobe` 通过且 `ffmpeg -f null -` 完整解码通过。SHA-256：S `4b8b4870…30e98e6d`，W `f9d8399d…6322d2`，L `4284f7ea…b66ec8`。
- high 渲染节点耗时/RSS：S 6.06s / 722,141,184 B，W 9.86s / 737,492,992 B；L 产物于 17:58:48 正常落盘，当次串行命令输出在采集中被截止，故不伪造 L 的独立 time/RSS，以媒体完整性为成功证据。
- 计划 07 隔离根当前 458,944 KiB，低于 1 GiB；无新模型/第三方 Provider/云/API/费用。本计划所属渲染/Chrome 孤儿进程检查为空。
- phase7 定向测试 fresh 8/8 PASS，phase4 回归 fresh 14/14 PASS。
- **批次 3：PASS。** 受控 L 版已对真实主体目标独立证明，S/W/L 同源、同时长、同规格且媒体通过，允许进入批次 4。

## 4. 批次 4：当前项目真实素材迁移

> 状态：`PASS`

- 输入与边界已核对：首选真实项目素材 `watermelon-growth-20260812/assets/keyframes/shot-003.png`（941×1672），主藤、多片掌状叶与叶柄枢轴清楚，适合不同相位轻摆；叶缘茸毛与交叠遮挡为主要风险。
- 该素材来自当前项目近期技术成功的用户创作，任务记录仍待用户验收；本记录不把它误称为“已验收成片”。
- 输入原图 SHA-256 为 `b9b489b0…b8360ec`；仅对这一张原图做 clean plate 与紫红色键主体源各1次编辑，完整提示词与操作账写入 `case-b-project-migration/prompts.md`；未生成第二张替代镜头。
- 静态分层冻结为 `background-clean/subject-cutout/stem-base/leaf-top/leaf-left/leaf-right/foreground/seam-covers`，均已归一到1080×1920；顶叶、左叶与前景各有叶柄或根部枢轴，右叶静态保护西瓜遮挡。
- 首轮宽掩码在峰值姿态露出横切暗缝；依计划仅使用1次有界资产修订，收窄叶簇、改为内部硬分区并加局部 `seam-covers`。hero 重组、叶片峰值、浅/深底 alpha 与接触表复审未见硬缝、背景空洞、双主体或西瓜漂移。此后未再修改资产。
- S 为同图静态；W 为同图旧式整图推近；L 为同组 `camera > scene > background/stem-base/leaf-rigs/seam-covers/dew/motes`：镜头 1.000→1.028，顶叶 `0°→0.7°→-0.25°→0°`，左叶 `0°→-0.28°→0.16°→0°`，前景低幅轻摆，两枚显式露珠只做1次透明度脉冲，3枚光粒为有限显式位移。叶片主体动作不由整图、滤镜或粒子代替。
- 每个组合仅一条 paused GSAP timeline，无 `repeat:-1`、随机、时钟或运行时网络。focused keyframes 分别锁定 `#leaf-top` 与 `#leaf-left`，数值、相位与回稳皆与 brief 一致；未使用动作参数修订配额。
- HyperFrames 0.7.107 strict check：lint 0 error/0 warning，runtime 0 issue，layout 0 issue，53个时间样本，transition sample 丢失0。可寻址 snapshot 覆盖 0/0.7/1.55/2.55/3.45/4.2/4.55/4.966s；末帧取实际帧149，三版均无黑屏或复位。
- draft L 耗时/RSS 为 28.21s / 272,908,288 B；high S/W/L 分别为 6.50s / 728,137,728 B、9.98s / 732,889,088 B、30.12s / 732,119,040 B。
- high S/W/L 均为 5.000s、1080×1920、30 FPS、150帧、H.264/yuv420p、video-only，`ffprobe` 通过且 `ffmpeg -f null -` 全片解码通过。SHA-256：S `4f94b2ea…09c5501`，W `60600972…774d25`，L `470ab757…3594de`。
- 资产清单已冻结为 `frozen_batch_4`，所有源、分层、证明与视频均由测试反查 SHA-256、尺寸与透明性语义。phase7 fresh 9/9 PASS，phase4 回归 fresh 14/14 PASS。
- 计划 07 隔离根当前 514,636 KiB，低于1 GiB；未新增模型、第三方 Provider、云/API或费用，本计划渲染与 Chrome 孤儿进程检查为空。
- 自审结论：真实素材已生成可比的 S/W/L 候选，局部动作方法技术成立；残余风险是亚度叶片转动可能观感过弱，以及稠密遮挡区可能仅在连续播放中显出细线。二者均留待批次 5 匿名审片，不于此先行裁决。
- **批次 4：PASS。** 真实项目迁移、拆层微动、同源 S/W/L 与媒体硬门均已完成，允许进入批次 5。

## 5. 批次 5：匿名对照冻结与用户审片门

> 状态：`awaiting_user_review`

- 输入与边界已核对：只使用批次 3/4 已冻结的两组 S/W/L；不再调整资产、动作或渲染参数，不向用户暴露 S/W/L 映射。
- 已于 `review-batch5/public/case-01` 与 `case-02` 各冻结 3 份同源候选；文件名仅为 `candidate-01/02/03`，画面、文件名和公开指引均不包含工具、S/W/L、新旧或质量暗示。
- 为避免审片哈希与源 manifest 直接对照揭盲，6 份公开 MP4 统一做无转码、无定向元数据的中性重封装；画面码流与帧数不变，未重渲、未调参。
- 候选均为 5.000s、1080×1920、30 FPS、150帧、H.264/yuv420p、video-only；6份审片副本均再次完整解码通过。
- 案例 01 同时点接触表覆盖首帧/眼睑状态/头部峰值/回稳/最后帧；案例 02 覆盖首帧/顶叶峰值/露珠与前景状态/回稳/最后帧。六份接触表已独立查看，无文字或标签泄露映射；其局限已写明：须以连续播放判断微动与暂态接缝。
- 私有映射位于 `review-batch5/private/mapping.json`，Codex 按8项0–3固定量表的原始分数位于 `private/codex-scores.json`；两者均在展示前封存，不以自动分数替代用户判断。
- 简短技术账已按案例记录独立层数、生成/编辑循环、作者落盘时间窗、渲染耗时与磁盘，并明示“复杂度不证明质量”。
- 公开候选 SHA-256：案例 01 依次为 `88a17f87…24b92b83`、`06ddd711…8b9accc5`、`cdfe66d6…69a0bea4`；案例 02 依次为 `37e9b09a…86c7cb30`、`310d4c61…6b87eef5`、`73ce492d…aec8160`。公开视频/接触表/指引/技术账及私有映射/评分的完整哈希均冻结于 `review-manifest.json`，逐项 `shasum -c` 全部通过。
- 首轮冻结校验的 `jq` 流表达式因运算优先级未展开为校验行，命令当即失败且未改文件；改为先显式合并 public/private 数组后重跑，全部哈希通过。
- phase7 合同新增审片冻结、匿名命名、映射/评分封存与实体哈希反查，fresh 10/10 PASS；phase4 回归 fresh 14/14 PASS。
- 最终磁盘：计划 07 隔离缓存 514,636 KiB，实验证据根 147,784 KiB（其中审片副本 29,788 KiB），合计约 646.9 MiB，低于1 GiB。HyperFrames render/Chrome 孤儿进程检查为空。
- `git diff --check` 仍只报告任务开始前已存在的 `【包A】视频引擎包/程序文件/config.ini:7` 文件尾空行；开始时的 tracked 修改状态仍在，未执行 reset/clean/checkout/stash/stage/commit/push。
- **批次 5 当前门状态：`awaiting_user_review`。** 最小审片集已冻结，当前结论严格保持 `CONDITIONAL`；用户答复下列5问前，不进入批次 6：
  1. 哪版最像画面本身会动？
  2. 局部主体或叶片动作是否自然且看得见？
  3. 是否存在不可接受的木偶感、接缝、闪烁或晕动？
  4. 这种方法值得用于少量镜头，还是多数普通镜头？
  5. 哪一处动作应减弱、加强或删除？

## 6. 批次 6：用户反馈、揭盲、最终分类与交接

> 状态：`PASS`（本批的“PASS”仅表示反馈已准确落实、分类与回归已完成；实验路线总结论为 `FAIL / rejected`）

### 6.1 输入与模式

- 输入为用户对批次 5 五问的完整答复；匿名媒体、私有映射与 Codex 评分仍是用户观看时的冻结版，未预先泄露。
- 已重新读取当前 HyperFrames 入口 Skill，并依 `short-video-director` 选择 `Resume` 模式：从第一个未满足硬门（用户意见落实）续接，不重做批次 1–5。
- 导演工作流把“用户认为基础动态整体不可接受”列为强制停止信号。用户认为当前效果不佳，并明确说明无必要给出某一动作应减弱/加强/删除的返修意见。因此本批不臆造参数、不消耗“每案一次”的返修配额、不重渲，保留原媒体作为失败证据。

### 6.2 用户反馈原意归类

1. “最像画面本身会动”的是案例 01 候选 01，但动起来生硬。案例 01 候选 02 只有轻微逐步放大，候选 03 看不出变化。案例 02 候选 01 有放大，候选 02 没有变化，候选 03 也只感觉画面变大。
2. “局部主体或叶片动作看不到”。
3. 仅案例 01 候选 01 有明显动作，但木偶感较明显；未明显感受到接缝、闪烁或晕动。
4. 无论木偶感、放大或不变的版本，均不应用于多数普通镜头；只有当产品明确是“静态图片视频”时，不变的静图才可作为多数镜头。
5. 因当前动作视频整体效果不佳，用户认为没有必要指定哪一处动作应减弱、加强或删除。

### 6.3 揭盲与 Codex 评分校正

- 案例 01：候选 01=`L`，候选 02=`W`，候选 03=`S`。用户正确区分了真拆层局部动作、整图推近和静止；但 L 的木偶感构成计划 07 视觉失败项。
- 案例 02：候选 01=`W`，候选 02=`S`，候选 03=`L`。L 确有 `#leaf-top` / `#leaf-left` focused keyframes，但用户只感知到画面变大，说明技术姿态证明不能代替最终像素的动作可感知性。
- 封存 Codex 评分对案例 A L 的自然度/木偶感与案例 B L 的主体动作可感知性判断过于乐观。用户视觉判断优先，已在 final manifest 中明示覆盖自动分数。

### 6.4 最终失败分类

- **素材先天不适合：否。** 受控动物是为分层选的原创素材，植物是当前项目真实迁移素材；两者静态姿态门均通过。
- **资产准备失败：否。** clean background、透明主体、头部/身体/眼睑或叶片/基座/前景/遮挡补片均可追溯，浅/深底 alpha 与静态重组通过。
- **HyperFrames 编排失败：否（技术层）。** 单一 paused timeline、父子层、枢轴、遮挡、有限动作、strict check、focused keyframes、snapshot、high render、ffprobe 和完整解码均成立。
- **视觉质量与产品价值失败：是。** 受控 L 动作可感知但生硬/木偶；项目 L 局部动作不可感知；用户否定用于多数普通镜头的价值。
- 依计划 07 第 15 节 FAIL 条件（“主体动作不可感知或木偶感明显”），总结论为 `FAIL`；主体拆层微动态分类为 `rejected`，不建立正式 Provider，不另立集成计划。
- HyperFrames 路线/数字/档案状态等信息设计用途仍是 `manual_only`；Image 2 + 包 B + 包 A/FFmpeg 已验收主链不受影响。

### 6.5 产物、性能、资源与验证

- 未返修/未重渲，故最终 S/W/L 就是批次 3/4 冻结媒体，完整哈希见 `phase7-hyperframes-micro-motion/final-manifest.json`（SHA-256 `d63a67e9…43cd342b`）。案例 A/B 六份原媒体哈希逐项复核通过，且六份再次 `ffmpeg -f null -` 全片解码通过。
- 性能不变：案例 A high S/W 为 6.06s/722,141,184 B 与 9.86s/737,492,992 B，L 当次独立 time/RSS 未捕获；案例 B high S/W/L 为 6.50s/728,137,728 B、9.98s/732,889,088 B、30.12s/732,119,040 B。
- 最终资源：计划 07 缓存 513,092 KiB，证据根 146,368 KiB，审片副本 29,788 KiB；缓存+证据约 644.0 MiB，低于1 GiB。未新增模型、第三方 Provider、云/API或费用。
- V2 完整矩阵：`python3 -m unittest discover -s tests -p 'test_v2_*.py' -v` fresh 运行 116 项，114 PASS，2 项仅限计划 05 隔离副本的长故障注入按合同 SKIP，0 FAIL。其中 phase7 11/11 PASS。
- HyperFrames render/Chrome 孤儿进程检查为空。`git diff --check` 只报告任务开始前已存的 `config.ini:7` 文件尾空行。
- 未修改 Schema v1、Job Bundle 公共契约、包 A/B 正式管线、计划 04 冻结工程或已验收成片；未执行 reset/clean/checkout/stash/stage/commit/push。

### 6.6 最终文档交接

- `docs/short_video_v2/motion_feasibility_v1.md`：将主体拆层微动态从 `re-evaluation_pending` 改为 `rejected`，保留信息设计 `manual_only`，写明技术成立与视觉失败并不矛盾。
- `短视频V2总体目标与阶段规划.md`：更新动效路由、工具表、阶段 6 与计划 07 状态，明确不进入集成。
- `experiments/short_video_v2_phase7/README.md`：写入最终 `FAIL / rejected`、用户反馈、不返修理由与安全边界。
- `final-manifest.json`：冻结揭盲、用户意见、自动评分校正、最终媒体/哈希、失败分类、资源和回归证据。
- **批次 6：PASS；计划 07：完成，总结论 `FAIL / rejected`。**

## 7. 用户复核后重开：第二轮有界诊断与返修

> 状态：`reopened_after_user_methodology_feedback`

### 7.1 重开依据

- 用户在首轮结论后继续逐项复核候选与联系表，将最终像素准确归为三类：有动作但木偶、只有整图放大、基本无变化；并进一步提出应检查姿态数量与姿态本身，而不能只看最终视频文件存在与否。
- 这份补充意见构成批次 6 所缺少的明确返修目标，故推翻 6.1 中“不消耗返修配额、不重渲”的当时依据。首轮 `FAIL / rejected` 仍作为 Round 1 历史事实冻结，不再作为尚未测试改良姿态表示与感知门槛后的最终能力上限。
- 本轮仅使用计划 07 既有的“每案一次”有界返修：保留旧 S/W/L、旧匿名映射、旧 manifest 与哈希；新增 Round 2 组合、媒体、诊断和 manifest，不覆盖前证。

### 7.2 首轮方法审计结论

- 批次 5 的五格不是五张生成式关键帧，而是从每条 5 秒、30 FPS、150 帧 MP4 中抽出的五个时点。准确链路是“少量分层 PNG + 单一 paused GSAP 时间线逐帧求值 → 150 帧 MP4 → 五时点抽帧”。
- 用户对证据失效的判断成立：全画面五联帧每格仅 216×384，案例 B 顶叶峰值缩小后约 1.1px，左叶约 0.28px；这类联系表无法证明局部微动，且与 L 同幅的 2.8% 全局推近会把叶片信号完全压住。
- 案例 A 的木偶感并非输出帧率不足。原 L 已有 150 个连续输出帧，但“点头”实为同一张头颈平面作 2.6° Z 轴侧倾；头、身体、静止颈部补片互为平级并在颈根大幅重叠，身体又整卡纵向缩放。增加更多时间采样不能补出真实俯仰、颈部弯曲与耳部跟随。
- 原 strict check 的通过只证明 lint/runtime/layout 等合同成立，不能证明动作在最终像素中可感知或自然；原静态 peak 亦不得替代真实运行时峰值。

### 7.3 Round 2 修订合同

- 案例 A：取消整图推近、粒子证明与整身拉伸；修正父子层、颈根枢轴与非对称动作节奏。优先验证新增的真实低头姿态状态；若其身份、配准或局部编辑边界不合格，则不得强用，并明确记录资产门失败。
- 案例 B：镜头固定，叶片动作以最终交付尺寸的叶尖位移为门槛；顶叶、左叶与前景错相且非对称回稳，露珠须跟随叶片父层，粒子不得作为主体动作证据。
- 两案均须先产出 camera-frozen 的局部动作版本；技术检查之后，以 1×连续播放、局部 ROI 峰值条、实际运行时峰值、首帧差分/运动能量和 seek 重复性共同验证。全画幅五格只作构图辅助，不再承担局部动作证明。
- Round 2 仍不得修改 Schema v1、Job Bundle 公共契约、包 A/B 正式管线、计划 04 工程或已验收成片；不得重启禁用 Provider，不加入音频，不提交或推送。

### 7.4 外部成熟方法输入与本地边界

- 依用户建议，补查 Live2D 父子 deformer、Spine mesh/weights、Rive bones/mesh 与 Adobe Puppet/Mesh Warp 的官方方法。共同原则为：使用同一纹理和同一拓扑，头骨等刚性区与颈部/耳尖等柔性过渡分开，以权重或网格变形，而非多张独立人像直接淡化。
- 本机无 Rive、Spine、Live2D、After Effects 或 Blender 可用作者工具/运行时；本轮不新增下载、付费软件或 Provider。最小本地类比实现选择 macOS SpriteKit `SKWarpGeometryGrid` 离线烘焙同拓扑状态，仍由 HyperFrames/GSAP 单时间线编排。
- 经有界验证后判废的路线：独立生成中间低头姿态（身份/背景漂移）、姿态交叉淡化（双耳/双脸重影）、全分辨率及 1/8 粗尺度双向光流（耳缘/额顶晕边）、九态整头网格压缩（用户指出头骨变扁，且 10Hz 阶梯）。

### 7.5 受控动物最小返修

- 依用户逐帧意见，低头动作整体判废，不以增加关键姿态数量美化错误形变；保留用户认可的两次眨眼。
- 新主体动作为画面左侧耳尖一次低幅摆动：24×40 SpriteKit 网格，耳根为锚点，峰值 2.4°，仅耳轴权重区变形；另一只耳、脸、头骨和颈部的输出像素不变。
- 第一版多 `<img>` 同时 opacity set 产生 0.4s 缺头，判废；第二版逐帧换 `src` 只有约 15 FPS 有效更新，判废。最终改为预解码状态图集 + 单一 canvas 同步绘制；耳部 ROI 在 28 个相邻输出间隔中 26 个有动作，脸/颈 ROI 为 0 个。
- seek 重复验证：`2.2→1.6→2.2→1.6s` 的两组同时点 PNG 分别字节级同哈希；`check --strict --at-transitions` 为 0 errors / 0 warnings。独立视觉复核认为无明显阶梯、闪断、脸颈牵连或眨眼残影，可进入用户复核，但非生产 PASS。
- high 媒体：5.000s、1080×1920、30 FPS、150 帧、H.264/yuv420p、无音轨，整片解码通过；SHA-256 `2a1448e0…a96910ba7`。

### 7.6 真实项目植物返修

- 删除原 L 的 2.8% 全局推近、粒子与整体干扰；顶叶、左叶和前景叶分别使用错相多段姿态，露珠移入顶叶父层。
- 最终实测局部特征位移约为：顶叶 14px、左叶 6–7px、前景 6–8px；背景天空差异 0.435，远低于 Round 1 整体运镜的 5.859，证明没有以推近冒充叶片动作。
- 独立视觉审查未见明显暗缝、重影、错层或全局闪烁，但小尺寸五格仍会将位移压缩到约 1px；故 Round 2 审片同时附原速全画面和同源局部慢放。
- high 媒体：5.000s、1080×1920、30 FPS、150 帧、H.264/yuv420p、无音轨，整片解码通过；SHA-256 `ded3f096…b4047c`。

### 7.7 Round 2 审片门

- 冻结新证据树 `phase7-hyperframes-micro-motion/round2-reopen/`；`round2-manifest.json` 状态为 `awaiting_user_review`，且显式引用未变的 Round 1 manifest SHA-256 `d63a67e9…342b`。
- Round 1 case-A 曾被后续系统 Python 3.9/Pillow 11.3 误重跑覆盖 11 张 PNG；已用原 Python 3.12/Pillow 12.2/12.3 产物精确恢复。恢复后 4 source + 9 layers + 6 proofs + 3 videos = 22/22 哈希匹配，Round 1 asset manifest、final manifest 和六条 S/W/L 媒体均未改。
- Round 1 已经完成同源 S/W/L 公平对照；Round 2 只复核受影响的两条 L2，不重复展示已判为放大/静态的 S/W。局部慢放是同一 high 媒体的裁切时序证明，不计为新候选。
- 用户回复前，最高等级仍为 `CONDITIONAL`，不得进入 Round 2 最终分类或声称主体拆层微动态通过。

### 7.8 用户复核、问题根因与有界返修

- 用户确认两案均比 Round 1 更像画面中的事物在动；小鹿眨眼与耳部动作可见且总体自然，建议耳部略强；植物动作可见，但移动前、移动中和移动后的同源叶片同时存在，形成重影。用户认为若瑕疵解决，此路线可考虑多数普通镜头。
- 植物故障并非 GSAP 残帧或编码拖影，而是资产所有权错误：动态叶片与静态 `leaf-right` / `seam-covers` 共享大量同源 RGB，`leaf-top` 与 `leaf-left` 也有异相重复。旧位层不动，故叶片一移便显出过去姿态。
- 修订严格限于两项：小鹿单耳同拓扑形变峰值由 2.4° 增至 2.7°，不改眨眼、脸颈或节奏；植物动作参数不变，只按 `foreground > leaf-left > leaf-top > leaf-right > stem residual` 重建唯一像素归属，并删除运行时静态 seam cover。
- 植物生成器现将 6 份冻结输入 expected/actual SHA-256 纳入 hard gate，输出保存后重新载入再验；alpha 0–255 全部 256 个阈值均为 0 holes、0 extras、0 pairwise overlap。五层零姿态重组与 canonical `subject-cutout` 的 RGBA 最大误差为 0。此结论只证明层资产恒等，不冒称完整浏览器首帧等于 `master.png`。
- 独立逐帧视觉门：小鹿 high 150/150 帧 PASS，耳尖约抬 5–6px，目标耳峰值 ROI 差 7.457/255，另一耳、脸和颈仅编码噪声；两次眨眼完整，无空头、双头、跳帧或耳根裂缝。植物 150/150 帧 PASS，顶/左/前景叶峰值位移约 13.45/6.96/7.99px，无旧位叶片、洞、断根、黑边、色边或一帧闪缝。
- 小鹿显式 DOM 状态层在乱序序列 `0→1.70→2.20→1.70→0→2.20→1.70s` 下，相同时间的 PNG SHA-256 完全一致；植物以唯一 paused GSAP 时间线求值。HyperFrames 0.7.107 strict check 均为 0 error / 0 warning / 0 layout issue。
- 两条 high 媒体均为 5.000s、1080×1920、30 FPS、150帧、H.264/yuv420p、无音轨并全解码；SHA-256 分别为小鹿 `d301e981…4cea6ba`、植物 `2958770d…02ed02`。

### 7.9 配方冻结、成熟路线与有限可行性门

- 已建立 `docs/short_video_v2/motion_experiment_playbook_v1.md`，配方状态固定为 `draft → technical_candidate → replay_verified → user_accepted → production_recipe/rejected`。每条必须冻结输入/输出哈希、层级/枢轴/所有权、时间线、运行时/argv、验证、成本与失败边界。
- 新增自包含证据包 `round2-reopen/revision-batch8/`：包含两份 composition、本地 GSAP、全部运行资产、SpriteKit 源、唯一所有权生成器、诊断、配方 manifest、high 成片与完整哈希账。离开原缓存后 cold strict check 仍为 0/0，并可独立渲染两条 150 帧 draft；故当前状态为 `replay_verified_awaiting_revision_review`，尚非生产配方。
- 依当前官方资料比较成熟工具：若未来批准新作者工具与费用，Spine Professional 的 weighted mesh 与绝对时间 `Animation.apply(..., time)` 最适合先作有界验证；Rive 技术上顺，但 Editor 为 online-first，与严格无云边界不合；Live2D 的随机 seek 与通用视频生成器许可均需先确认；After Effects Puppet Pin 只适合已有订阅时烘焙少量重点镜头。本轮未下载、安装或付费。
- “多数镜头可用”不由两例推断。后续须一次性执行 `3 个真实视频 × 每个 4 类镜头 = 12 镜` 广度门：至少 9/12、每视频至少 3/4、2D eligible 通过率至少 80%、每种拓扑至少 2/3，且用户无硬瑕疵；每镜时间盒 30 分钟+一次 15 分钟返修，45 分钟即停。
- 走路、转身、手物交互、口型、复杂表情、长发衣物大幅运动、水烟火、完整风场耦合、新视角/新表面列为 `semantic_motion_required`，不得继续在当前 2D 路线逐动作硬做。

### 7.10 Round 2 返修审片门

- `review-batch8` 只含用户点名的两条受影响 high 成片及定位联系表，不重复 Round 1 S/W/L，也不把联系表当作连续动作证明。
- 审片前最高只可称 `narrow replay-verified technical candidate`；现行正式路由与 Round 1 final manifest 均未改。
- 用户只需复核：小鹿耳部略增后是否仍自然；植物旧位重影是否消失，以及是否新增洞、断根、接缝、闪烁或色边。回复前不升级为 `user_accepted`，亦不进入 12 镜广度门。

### 7.11 批次 8 用户复核与植物最终修订边界

- 用户明确回复：小鹿“通过，正常”，故案例 A 升为 `user_accepted`，接受媒体 SHA-256 为 `d301e981…4cea6ba`；批次 9 不改它、不重渲、不重复展示。
- 植物未被否定，而是“幅度偏小，尚无法确认”；用户要求增大摇动并让不止一片叶子同时动。该回复构成明确的有界例外返修，但 `automatic_batch10_forbidden=true`；若此次仍不接受，将停止继续调这一株植物。
- 先作一次大幅刚性整层旋转诊断；虽然 HyperFrames lint/strict 无通用工程错误，可视峰值出现严重斜缝和西瓜纵切缝，故该 L3 当场判废，未渲成 high，也不对用户展示。此事证明：自动 strict 不能代替视觉缝隙门。
- 根因不是关键帧数量，而是批次 8 的叶层虽像素唯一，却含多个语义不连通的残片；整层旋转会将残片一并拉开。故批次 9 必须转为“语义连通独立层 + 根部锁定局部网格”，不再用整层加大角度。

### 7.12 批次 9：植物语义拆层、局部网格与最小审片集

- 新资产将主体分为静态主茎、西瓜/其他残余、右叶，以及语义连通的顶叶、左叶、右下前景株三个活动层。alpha 0–255 共 256 阈值的 holes/extras/pairwise-overlap 均为 0，动层皆语义连通，零姿态 RGBA 误差为 0。
- 三个动层均以本地 SpriteKit 网格烘焙 31 个同拓扑状态，根部锁定误差为 0，相邻叶尖理论步进不超过 1.5px。HyperFrames 仅用一条 paused GSAP 时间线以显式状态切换推进，每层每时刻只有一张可见，无交叉淡化、计时器、随机、网络或运行时补缝。
- 顶叶、左叶、右下前景株峰值位移分别约 21.9/16.0/16.0px；帧 50–65 共16帧有两组主叶同时达约 10px 可见位移，峰值帧 53/59/73 错开，西瓜与相机静止。
- 乱序 seek 同时点截图哈希一致；150帧状态扫描中每层唯一状态、首末回稳。high 成片 150/150 帧视觉门 PASS，未见旧位重影、断根、运动开缝、闪烁、方块或色边；媒体为 5.000s、1080×1920、30fps、150帧、H.264/yuv420p、无音轨，完整解码通过，SHA-256 `94a59bd1…a254822`。
- 已冻结 `revision-batch9/` 自包含工程、配方 manifest、high 成片与完整哈希账；`review-batch9/` 只公开案例 02 这一条成片及定位联系表。小鹿保持 `user_accepted`，植物当前仅为 `replay_verified technical candidate`。
- 独立将冻结工程复制到全新临时根后，cold strict check、双序 seek、150帧状态扫描与 high 重渲均 PASS；冷重渲 MP4 与冻结审片成片逐字节同 SHA-256。五份历史诊断 JSON 仅保留原 cache 绝对路径作 provenance，它们不是 composition、check、seek 或 render 的运行依赖，已列为低级非运行时提示。
- **审片前门状态（历史）：`awaiting_plant_revision_review`。** 当时不将植物升为 `user_accepted`，不进入 12 镜广度门，不修改正式集成结论。

### 7.13 批次 9 用户终审与 Round 2 收口

- 用户对最终植物候选的三点回复为：“动作明显”、“像一阵风”、“明显重影”。因此动作可感知性与多叶风感同步门均记为 PASS，但瑕疵门为 FAIL，案例 B 最终状态是 `user_rejected_due_to_ghosting / rejected`。
- 批次 9 冻结工程仍保留 `replay_verified_technical_candidate`：它证明自包含冷重放、乱序 seek、单时间线、媒体规格与多叶位移均成立；但技术可复现不等于视觉可接受，该状态不得升格为 `user_accepted`。
- Codex 的 high 逐帧视觉门曾记为 PASS，而用户在连续成片中明确看见重影；故该自动视觉门是假阴性。此处以用户视觉门为最终优先级，不以 alpha 所有权、根部锁定、像素哈希或自动帧扫描覆盖人眼审片结论。
- 用户回复后对冻结 high 成片作了解码帧复核，已在 0-based 帧 38–90（约 1.27–3.03s）复现结构性双轮廓，帧 50–66（约 1.67–2.20s）最明显。它不是单纯的 H.264 拖尾：解码单帧本身已有旧/新轮廓，且 HTML 每层每时刻只有一个 state、没有交叉淡化。
- 批次 9 终审后的阶段性取证以中高置信度确认了一项重要贡献机制：`leaf-top`、`leaf-left`、`foreground-plant` 虽各自满足唯一像素所有权、8 连通与零姿态重组，却仍是包含多片叶和枝杈纹理的粗语义簇。它们被独立形变后，会彼此穿插，并与静态主茎或右叶形成结构性错叠，视觉上读作旧/新双轮廓。既有自动门把“连通、互斥”误当成“同一形变语义”，也没有检查活动扫掠区内的动态—动态、动态—静态结构关系；7.14 的最终因果例外进一步限定此机制并非已证明的唯一或完整根因。
- 31 个预烘焙状态的硬切换是次因：全片 149 对相邻帧中有 77 对保持同一组合 state，会加强阶梯与滞留感，但并非双像主因。此取证只说明工程机制；因用户未提供具体注视区域或截图，不断言用户注意的恰是哪一片叶。
- 计划 07 最终等级为 `CONDITIONAL`，分类为 `manual_only`：只保留已被用户接受的小鹿眨眼+单耳窄配方，且不外推至其他动物、人物、植物或多数普通镜头。
- 12 镜广度门保持 `not_run`，最终处置为 `cancelled_due_to_failed_prerequisite`，失败前置是 `case_b_user_visual_gate`。`automatic_batch10_forbidden=true`，不再对同一株植物自动调参；正式集成仍为 `not_reopened_for_production`。

### 7.14 用户授权的最终因果例外与永久终止

- 本次一次性排除试验登记为 `user_authorized_final_causal_exception`；它不是批次 10、Round 3 或新候选，不改变既有 `complete / CONDITIONAL / manual_only`，也不重开普通自然主体生产路由或 12 镜广度门。
- 唯一有效首跑采用 single-owner `36x48` unified mesh：G4 动作门 `PASS`，但 G5 `visible-strain` 为 `HARD FAIL`；量化值为 `sigma_min=0.435627`、`sigma_max=1.622578`、`cond=2.435135`、`area=0.462118–1.552697`、`p99=1.324495`，并记录 `zero-warp drift`。
- `G6 proxy` 无效，不作裁决，亦不得覆盖 G5 硬失败。本例未创建 HF composition/draft，未渲染新审片候选，且未作第二次调参。
- 因果表述据此收窄：批次 9 的多层结构互穿是重影的重要贡献机制，但不是已证明的唯一或完整根因；single-owner 统一网格虽排除了多层互穿，却因可见纹理应变同样不可用。
- 植物单所有者统一网格结论冻结为 `single_owner_unified_mesh_hard_fail`，植物路线最终标记为 `plant_route_permanently_stopped`。小鹿继续保持 `user_accepted / manual_only`；普通人物、动物、植物生产路由、广度门与批次 10 均保持关闭。
