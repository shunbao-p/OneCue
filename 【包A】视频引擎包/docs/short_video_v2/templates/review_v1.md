# 短视频 V2 Review 模板 v1

本模板统一记录技术审计、逐镜质检、用户反馈与最小返修。它是可裁剪的人类/Codex 审查辅助，不替代 Schema、render report、cache manifest 或用户终审。

## 任务与保护快照

- 项目/模式：
- Job Bundle：
- 执行记录：
- 检查或渲染 run id：
- 旧 final/report SHA-256：
- 工作树与正式产物保护范围：

## 合同与生产事实

- `validate --json` 退出码/`ok`/镜头数：
- 契约错误或警告：
- 包 A/B 状态与 API 版本：
- render 状态、warnings/errors：
- cache：audio hit/rebuilt；shot hit/rebuilt；final hit/rebuilt
- 是否触发 Image 2 或真实 TTS 新生成：

## 媒体审计

- final 路径、SHA-256、大小：
- 视频：codec / 1080×1920 / 30 FPS / yuv420p
- 音频：codec / 48 kHz / 双声道
- 时长、音视频差、报告误差：
- 完整解码退出码：
- 黑帧、静音、响度等需解释的信号：
- 播放/人工视觉复核：

## 逐镜审查

| shot_id/时间点 | 内容/事实 | 静态画面/角色 | 人声 | 字幕 | 画面保持/硬切 | 问题级别 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| shot-001 |  |  |  |  |  |  |  |

第一版应逐镜保持静态，并在镜间硬切。审查时确认没有非预期推拉、平移、漂移、拆层动作或叠化；不以任何二维晃动冒充自然动态。

## 用户反馈

- 用户是否已观看：待审 / 已审
- 用户原话：
- 输入是否自然：
- 暂停点是否合适：
- 镜头返修方式是否清楚：
- 是否仍需大量底层操作：
- 是否接受当前静态叙事方向与 UI 延期：
- 判定：accepted / revision_requested / rejected / awaiting

## 最小返修

- 用户指出的镜头/时间点：
- 根因与影响层：文本 / 字幕 / 音频 / 关键帧 / focus-crop / final 时间线
- 最小改动：
- 需重建：audio / shot / final
- 不应重建：
- 预计命令：先 validate；必要时以 `render --shot <shot-id> --json` 限定允许重建范围；仅在必须强制所选缓存失效时追加 `--force`
- 旧 final 保护与隔离策略：
- 返修后缓存/哈希/解码证据：
- 是否返回用户再次审片：

## 结论与续接

- 技术：PASS / CONDITIONAL / FAIL
- 内容/视觉/人声/字幕：PASS / CONDITIONAL / FAIL
- 用户质量：PASS / awaiting_user_review / revision_requested / FAIL
- 已知边界：
- 首个未满足硬门：
- 下一步：
