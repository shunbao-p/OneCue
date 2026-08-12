# 短视频 V2 图片动态化可行性与计划 05 交接（v1）

## 1. 当前决定

- 默认路线始终是包 A 既有 FFmpeg 预设；它负责低复杂度动态、统一标准化与最终合成。
- 用户匿名审片已完成。四组虽都相对选择了高级版本，但用户明确认为自然场景候选仍只是微放大、平移或晃动，缺少真正的场景内/主体内运动；因此正式高级候选为零。
- HyperFrames 只保留信息设计型人工选项；DepthFlow 与 HyperFrames 自然场景构图不进入计划 05 正式路线。
- MFLUX 因冷模型下载耗时失控归为 `research_only`；Draw Things / 本地 I2V 因未获授权归为 `research_only`。
- 高级工具不得写 Schema v1、不得进入 Job Bundle 公共输入、不得接管时间线、字幕、TTS、缓存或 final。

## 2. 镜头路由

| 镜头意图 | 默认 | 可选候选 | 当前状态 |
| --- | --- | --- | --- |
| 普通人物、建筑、风景图 | FFmpeg `slow_push_in` / `gentle_drift` | 无需高级工具 | 正式默认；优先微放大，避免无叙事依据的左右晃动 |
| 有明显前中后景、轮廓清楚的环境 hero 镜头 | FFmpeg | DepthFlow 外部 2.5D | `rejected`；不能产生雨落、旗动、人物动作等语义运动 |
| 路线、警灯、档案状态、信息图或可寻址 DOM 动画 | FFmpeg 静态推拉兜底 | HyperFrames 设计型单镜头 | `manual_only`；用户认为动态更明显，可用于少量特殊镜头 |
| 普通人物氛围层或环境分层 | FFmpeg | HyperFrames 手工构图 | `rejected`；当前雨层/摆动没有形成足够可感知的真实动态 |
| 本地静态生成后备 | Image 2 仍是主路径 | MFLUX | `research_only` |
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
- 未来缓存键最少包含：输入图 SHA-256、route/version、时长/尺寸/FPS、运动参数；HyperFrames 另含 composition 源 SHA-256，DepthFlow 另含模型 revision。
- FFmpeg 对照不得删除；高级路线失败、超时、取消或媒体校验失败时，应回落默认路线并保护旧产物。
- 中央实验根为 `/Users/yuh/Library/Caches/text-video-plan04-feasibility/`，其 `mflux/`、`depthflow/`、`hyperframes/` 可逐路线单独移除；不得笼统清理其他用户缓存。

## 5. 许可与分发

- HyperFrames：Apache-2.0；当前仅中央实验项目与浏览器运行时，不打入包 A 发布物。
- DepthFlow：AGPL-3.0；仅作为独立外部人工工具继续评估，不复制或链接其代码进包 A。
- MFLUX：代码 MIT，所选模型 Apache-2.0；当前模型未完整取得。
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
| 人物整体轻摆 | 有条件支持 | 先把人物与背景、躯干/头部等拆成透明层，再以枢轴做 2D puppet；人工准备较重，容易出现纸片感，只适合少量风格化镜头 |
| 衣发、表情、肢体、雨水与环境自然联动 | 当前未支持 | 需要 I2V/视频扩散或专门的角色动画模型。FFmpeg、DepthFlow、当前 HyperFrames 构图都不能自动完成 |
| 本地 I2V | 技术上可能，尚未验证 | M1 Pro 32GB 理论可试小型量化模型，但预计约 9.344 GiB 模型、较长推理、身份漂移与许可风险；用户当前未授权，计划 04 未下载 |
| 云端 I2V | 未评估/未接入 | 当前项目没有经授权、经验证的视频生成 Provider；若未来评估，仍须保持包 A 时间线、字幕、缓存与最终 FFmpeg 合成职责 |

计划 05 应先采用“FFmpeg 微放大默认 + HyperFrames 信息设计人工可选”的保守交接。若产品必须达到雨落、人物呼吸/摆动、旗帜与烟雾等自然运动，应另立有界 I2V 可行性批次；在新的下载/API/费用授权前，不以二维晃动冒充真正动态。
