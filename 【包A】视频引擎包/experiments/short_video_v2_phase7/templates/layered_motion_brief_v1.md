# Layered Motion Brief v1

> 本模板是计划 07 实验制作说明，不是 Job Bundle Schema，不得复制到正式公共契约。

## 项目与目标

- case_id：`<case-a|case-b>`
- source_image：`<absolute regular file inside approved roots>`
- 目标：把同一张主图制作为 4–6 秒、9:16、30 FPS、无声的 S/W/L 受控对照。
- 成片感受：`<安静|温暖|克制|生动|...>`
- 身份锚点：`<脸/眼睛/毛发/服装/叶缘/果实等不得改变的内容>`
- 主图焦点：`<normalized x,y and/or pixel x,y>`

## 四层动作

- 镜头层：`<camera-rig 的起点/终点/焦点/持续时间>`
- 场景层：`<前中后景/草叶/光粒/局部光线及相位>`
- 主体层：`<body/head/leaf 的动作、枢轴、峰值与回稳>`
- 局部状态层：`<eyelid/eyes-closed/highlight 的时间与持续帧数>`

## 层级、枢轴与遮挡

- 层级：`background-clean / camera-rig / subject-root / body|base / head-pivot|leaf-pivot / eyelid|state / foreground / particle`
- 枢轴：`<颈部、叶柄或身体重心的像素/百分比坐标>`
- 遮挡顺序：`<谁在谁之前>`
- 重叠余量：`<颈部/叶柄/边缘的像素量>`
- 空洞/残影控制：`<clean plate、mask、counter-transform 或 overlap 策略>`

## 单一 seek-safe 时间线

- composition_id：`<stable-id>`
- timeline key：`window.__timelines["<same-stable-id>"]`
- 时间线：`0.0s 建立；... 主动作；... 状态变化；... 回稳；末尾 hold`
- 确定性：固定种子或显式常量表，有限 repeat，无运行时网络、时钟或计时器。

## 姿态与证明帧

1. `first_frame`
2. `pre_action_hold`
3. `subject_peak`
4. `local_state_peak`
5. `return_to_rest`
6. `final_minus_hold`
7. `final_frame`

每一项填写秒数/帧号、真实动画选择器、期望姿态和 snapshot/focused-shot 路径。

## 视觉失败项

- 断颈、漂浮、关节错位、叶柄断裂。
- 原头残影、双眼/双脸、背景空洞或重复纹理。
- 眼睑/局部状态漂移、颜色不匹配、闪烁。
- alpha 白边、毛发/叶缘硬切、前景遮挡眼睛或主体锚点。
- 整图晃动、木偶循环、晕动，或动作小到 30 FPS/H.264 成片不可感知。
- 以滤镜、锐化、强光、粒子、字幕或缩小画面掩盖问题。

## 验证链

- 静态 hero 叠合、峰值姿态、局部状态、浅/深底 alpha 边缘先通过。
- `hyperframes lint`
- `hyperframes check --strict --snapshots`
- `hyperframes keyframes --selector <real-subject> --shot <proof>`
- `hyperframes snapshot --at <proof-times>`
- draft 视觉自审，最多一次有界动作参数修订。
- high render，再做 ffprobe、完整解码、SHA-256、资源/磁盘/孤儿进程检查。

## 禁止

- 整图左右晃动、滤镜或粒子冒充主体动作。
- 同一元素的同一 transform 属性被并发 tween 重复写入。
- `repeat:-1`、`Date.now`、`performance.now`、未种子 `Math.random`、运行时 fetch、未注册 rAF、计时器。
- 身份变化、遮罩白边、断裂、重影、末帧黑屏或复位。
