# Image 2 关键帧提示词模板

```text
Use case: stylized-concept
Asset type: 9:16 short-video keyframe
Primary request: <镜头叙事动作与唯一主体>
Input images: Image 1: character reference; Image 2: style reference
Scene/backdrop: <时代、地点、天气、前中后景>
Subject: <年龄、面部、发型、服装、配件；只写本镜所需动作>
Style/medium: cinematic semi-realistic Chinese narrative illustration
Composition/framing: 9:16; <景别与机位>; keep lower caption-safe area readable; leave motion overscan
Lighting/mood: rainy night; cool indigo ambience; restrained warm lantern accents
Color palette: indigo, charcoal, wet stone, warm amber highlights
Materials/textures: wet cloth, worn leather, rain-darkened stone, subtle brush texture
Constraints: preserve character identity, hair, indigo clothing and brown satchel; period-correct; natural face and hands
Avoid: text, letters, watermark, logo, modern objects, extra fingers, duplicated limbs, cropped face/hands
```

每次迭代只改一个明确问题，并重复不变量。生成账须记录镜头 ID、提示词版本、参考图顺序与职责、生成/编辑次数、拒绝原因、最终尺寸/哈希及是否可进入 Job Bundle。
