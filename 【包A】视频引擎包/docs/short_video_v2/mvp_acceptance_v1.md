# 短视频 V2 MVP 验收 V1

> 完成日期：2026-08-12（Asia/Shanghai）  
> 计划：05—端到端质量验证与 MVP 验收  
> 最终结论：`PASS`

## 1. 验收范围与正式路线

本次以两个不同内容的严格 Schema v1 Job Bundle 验证从独立关键帧、真实人声、逐镜渲染到 final、缓存、有限返修与人工终审的完整链路。正式路线仅为 Image 2 独立 9:16 关键帧、包 B Dots.tts 人声、包 A V2 管线与 FFmpeg。

本计划未修改 Schema v1，未接入图片/视频 API，未加入 BGM、SFX 或环境音，未下载或重新启用 MFLUX、DepthFlow、自然场景 HyperFrames、Draw Things 或本地/云端 I2V，也未实施计划 06。

## 2. 最终成片

| 案例 | 类型 | 镜头 | 时长 | final SHA-256 | 用户终审 |
| --- | --- | ---: | ---: | --- | --- |
| 《暴雪前的最后一班山村邮车》 | 人物叙事 | 8 | 35.882s | `ab08594f8150e8b89103c49a31654b04c6fb092866f9d8d8668770ab24bbe43c` | 通过 |
| 《一滴雨水如何穿过海绵城市》 | 知识解释 | 8 | 36.133333s | `58e2170063390ad30bc628dd16f97746ed52807ef88eab71739e895c87ac702d` | 通过 |

A 含且仅含一个 dialogue/speaker_id 镜头；B 含且仅含一个 custom 字幕镜头，并保存住建部技术指南与国务院办公厅指导意见来源。两条均使用 8 张互相独立的 9:16 图片与 8 段真实包 B 音频。

## 3. 技术与媒体结果

- 两片均为 H.264 1080×1920、30fps、yuv420p + AAC 48kHz stereo，时长落在 30–45 秒。
- 每包 8 WAV、8 shot、1 final，共 17 个媒体均通过 ffprobe 与完整解码；blackdetect 无黑段。
- A 音视频流差 0.015333s、报告时长误差 0.041s；B 为 0.017333s、0.000651s。
- A 为 -16.7 LUFS、LRA 4.2 LU、真峰值 -3.0 dBFS；B 为 -16.7 LUFS、LRA 3.7 LU、真峰值 -3.6 dBFS。
- QuickTime Player 已对返修后两片从 0 完整播放至末尾，无播放器错误。

## 4. 缓存、故障与保护结果

- 两片第二次相同渲染均为 audio 8/8、shot 8/8、final 1/1 全缓存命中，final 哈希稳定。
- 隔离副本证明 `--shot` 只重建指定镜头和 final；错误图片哈希、越界路径与未知字段在 TTS/FFmpeg 前拒绝。
- 损坏缓存只重建必要层；TTS unavailable、motion static 回退、双失败、取消均具有稳定错误分类并保护旧 final。
- 最终两个正式缓存清单各 17 个实体哈希逐项与磁盘文件一致。
- 工作树原有修改、包 A/B 服务、Schema v1、V1 文档及计划 03–04 产物均受保护；无孤儿渲染/TTS/FFmpeg 进程与 `.part-*`。

## 5. 有限返修与评分

A 使用一次内部返修，仅改 shot-001 与 shot-004 文案/字幕；B 使用一次内部返修，仅改 shot-005。两片均未重生图片。返修前版本和证据保存在各包 `evidence/iterations/batch5-before-internal-revision/`。

Codex 量表得分：A 20/24，B 19/24。此分数只作提交用户审片前的定位证据。用户随后明确裁定 A、B 均通过，未提出有限返修，故两片用户返修次数均为 0。

## 6. 最终回归

- Plan01–05 定向矩阵共发现 106 项：104 项通过、2 项真实 FFmpeg opt-in 按设计跳过；退出码 0。
- static 回退和双失败两个 opt-in 场景分别显式 fresh 运行，各 1/1 通过。
- 两包 fresh validate：8 shots、0 warning、0 error；fresh final audit 均 `ok=true`。
- Schema v1 哈希：project `5eda9ab5bf6b577dd0ea64ff2dcffd273a6844c989041a300a28c40f8e25eeb0`，storyboard `0ddf9a57546e579d1177000121699ef3bb3ada0ebc78332d12fa5b5190769a49`。
- 计划 03 final/report/contact sheet 哈希仍为 `1a93f1c6…1754`、`d919e3f2…9b9d`、`e95fea29…376c`；计划 04 最终 PASS 及“正式高级 Provider 为零”的结论保持不变。

## 7. 已知动态边界

真正自然语义动态尚未实现。当前 FFmpeg 只提供虚拟摄影机推拉、平移与轻漂移；雨落、流水、车辆行驶、人物呼吸或摆动等对象/场景内运动不在 V1 能力内。计划 04 的可行性决策虽为 PASS，正式高级 Provider 仍为零。

用户已在知悉所呈现成片及该能力边界后接受两片为本次 MVP。此接受不把能力缺口改写成已解决，也不授权后续绕过许可、资源或质量门。

## 8. 最终判定与计划 06 交接

| 层级 | 判定 |
| --- | --- |
| 技术 | PASS |
| 可靠性 | PASS |
| 用户质量 | PASS |
| 总判定 | PASS |

两片均获用户接受且全部硬门通过，故允许进入计划 06。计划 06 应继续复用冻结的 Schema v1、Image 2 + 包 B + 包 A + FFmpeg 正式路线，并把“自然语义动态未实现、正式高级 Provider 为零”作为显式产品边界；本文件不实施计划 06。

机器可读总账位于 `成片/短视频V2样片/phase5-mvp-acceptance/final-review/manifest.json`，完整过程证据见计划 05 执行记录。
