# 短视频 V2 计划 01 执行记录

> 计划：Mac 基线与三镜头技术样片  
> 工作区：`/Users/yuh/Desktop/项目/文本视音屏生成器`  
> 开始日期：2026-08-11（Asia/Shanghai）  
> 当前状态：批次 1–5 已完成；最终等级 PASS；允许制定并执行计划 02，但本记录未进入计划 02

## 0. 执行边界与现场保护

- 已完整阅读总体规划、计划 01、五批执行提示词、核心需求与完整方案、项目交接文档及根目录 README。
- 工作区及父目录未发现实体 `AGENTS.md`；本会话已注入完整工作区 AGENTS 约束，并据此执行。
- 严格限制在计划 01：不建设正式 V2 Schema/API/UI，不接入高级动态化工具，不使用 BGM、环境音或 SFX，不运行 SOAR、完整耐久或发布验收，不处理签名公证，不改正式 V1 视频入口，不新增非计划依赖。
- 健康服务优先复用；不为形式完整而停止、重启或重复安装。

### 开始时 Git 现场

- 分支：`main`
- HEAD：`eaa3bf37e82be8822c70dc5dcad129cbbba08f7d`
- 已修改且必须保护：
  - `【包A】视频引擎包/程序文件/config.ini`
  - `【包B】语音引擎包/apps/gradio/service.py`
  - `【包B】语音引擎包/macOS使用说明.md`
  - `【包B】语音引擎包/tests/test_phase3_api_contract.py`
- 开始时未跟踪且必须保护：包 A/B 发布信息与运行状态文件、`短视频V2核心需求与完整方案.md`、`项目交接文档.md`、`短视频V2规划文档/`。
- 已跟踪文件 diff 摘要：4 个文件，84 行新增、40 行删除；本计划不回退、不覆盖这些既有修改。

## 1. 批次 1：现场保护与最小基线

### 目标

确认当前 Mac、包 A/B 服务、测试与真实 A+B V1 链路可信；不修改 V2 代码。

### 已确认事实

- 设备：Apple Silicon `arm64`；macOS 26.5.1（25F80）；内存 32 GiB；项目卷可用约 304 GiB。
- 包 A Python：3.13.13；包 B Python：3.12.13。
- 包 A 随包 FFmpeg/ffprobe：8.1.2 arm64，包含 libx264、libass 与所需静态能力。
- 包 B 模型约 9.7 GiB，包 B 运行时约 1.1 GiB，包 A 运行时约 106 MiB。
- 包 A 状态：release 模式，PID 9534，端口 8787，工作脚本为 `程序文件/网站/kt_web.py`；`/api/health` 返回 `status=ok`。
- 包 B 状态：MF 模型，PID 6297，端口 7860，状态 `ready`；API 为 `dots-tts.synthesize.v1`，与包 A 期望版本兼容；根页面 HTTP 200。
- PID、命令、工作目录与监听端口相互吻合，服务保持复用，未停止或重启。
- 包 A 有 7 个 `test_*.py`，包 B 有 6 个 `test_*.py`；现有真实回归脚本为 `tests/run_phase4_ab_e2e.py`。

### 实际命令与结果

1. 包 A 全量纯测试：
   - 命令：`【包A】视频引擎包/程序文件/runtime/bin/python3 -B -m unittest discover -s 【包A】视频引擎包/tests -p 'test_*.py'`
   - 结果：运行 99 项，96 项通过，2 项失败、1 项错误。
   - 分类：三项均属于旧 Windows 边界断言在 macOS 上仍硬编码 `ffmpeg.exe`、`python.exe` 与 `C:/Windows/Fonts`；当前 Mac 实际路径、字幕和 V1 视频均由后续真实回归证明正常。此为相关但非阻塞的测试可移植性问题，按计划低影响规则仅记录，不在本批修改。
2. 包 B 全量纯测试：
   - 命令：`runtime/python/bin/python3.12 -B -m unittest discover -s tests -p 'test_*.py'`
   - 结果：51 项全部通过，耗时约 1.62 秒；出现 `ResourceWarning: unclosed event loop` 警告，不影响退出码和服务使用，记录为低影响事项。
3. 真实 A+B V1 回归：
   - 命令：`【包A】视频引擎包/程序文件/runtime/bin/python3 -B 【包A】视频引擎包/tests/run_phase4_ab_e2e.py --port 8787 --ffprobe 【包A】视频引擎包/程序文件/bin/ffprobe --evidence-dir 【包A】视频引擎包/成片/短视频V2样片/phase1-three-shot/evidence/baseline/ab-e2e --num-steps 4`
   - 结果：PASS。
   - MF TTS：32.57 秒完成；WAV 6.832 秒、48 kHz、单声道、PCM16、无削波；SHA-256 `358aeb968b9dc7b1906fb6b0c4901ac266b93ac1af70044554b38ee1691069e3`。
   - V1 视频：1.31 秒完成；H.264、1080x1920、25 FPS、AAC 48 kHz、时长 6.84 秒；SHA-256 `40a1beac30217266b7453e69713ecc606a7d8514032c81d82ca3e658902b5c0a`。
4. V1 成片完整解码：
   - 命令：`【包A】视频引擎包/程序文件/bin/ffmpeg -v error -i .../package-a-b-mf-1080x1920.mp4 -f null -`
   - 结果：退出码 0，无错误输出。

### 证据

- `【包A】视频引擎包/成片/短视频V2样片/phase1-three-shot/evidence/baseline/ab-e2e/phase4-ab-e2e-report.json`
- `【包A】视频引擎包/成片/短视频V2样片/phase1-three-shot/evidence/baseline/ab-e2e/package-a-calls-b-mf.wav`
- `【包A】视频引擎包/成片/短视频V2样片/phase1-three-shot/evidence/baseline/ab-e2e/package-a-b-mf-1080x1920.mp4`

### 批次 1 退出结论

- 包 A/B 健康、API 兼容、真实 MF TTS 成功、V1 MP4 成功且完整解码通过。
- 未修改 V2 代码，未停止或重启服务，未触碰既有修改。
- 旧 Windows 边界测试的 3 项失败不影响真实 TTS、V1 MP4、样片生成、正常观看、数据安全或计划 02 设计，故批次 1 判定 **PASS**，允许进入批次 2。

## 2. 批次 2：Brief、临时任务包与关键帧

### 实际完成

- 创建原创样片 Brief：`【包A】视频引擎包/成片/短视频V2样片/phase1-three-shot/brief.md`。
- 创建薄版临时实验契约：`storyboard.sample.json`，明确标记 `sample_version=phase1-experimental-1`，只含本批必要字段。
- 按 `imagegen` 技能使用内置生成路径，未使用 CLI、API 密钥、本地图片工具或新增依赖。
- 先生成角色/风格参考表，再以其为共同参考分别生成三个镜头；四张图均首轮选用，无修订，未消耗每镜一次修订预算。
- 完整提示词、选择依据、尺寸、哈希和修订结论记录于 `references/image-generation-record.md`。

### 图片与哈希

| 产物 | 尺寸 | SHA-256 | 结论 |
| --- | --- | --- | --- |
| `references/character-style-sheet.png` | 1024x1536 | `286b61275bac49d072879c1411b261e968b9fa74199cacabe2a4b7a9c6d268eb` | 身份、服装与道具清楚，选用初稿 |
| `assets/keyframes/shot-001.png` | 941x1672 | `a69a953ae6fc428ed55f31ad4b4ea86d908ae22647484ed5a6500d406e32a659` | 古城山雨广景与主体安全区成立 |
| `assets/keyframes/shot-002.png` | 941x1672 | `ddc298c9a9c8e80e904f29ff12999359134033a48ca1b23f39651f38c2b9429d` | 同一人物近景、双手与红蜡密信成立 |
| `assets/keyframes/shot-003.png` | 941x1672 | `2402cc7e27475a8df15386397ff6346cee7e9bfbabfade4f8ef7a538c0dfde48` | 同一人物、青铜信物、守军与警灯成立 |

### 验证与视觉结论

- 命令：对三张关键帧分别运行 `file`、`shasum -a 256` 及包 A 随包 `ffmpeg -v error -i <image> -frames:v 1 -f null -`。
- 结果：三张 PNG 均为 RGB、941x1672，FFmpeg 解码退出码 0、无错误输出。
- 人物一致性：三个镜头中的面部轮廓、束发、靛青服装和棕色斜挎包均基本一致，`shot-002` 与参考表尤为接近；达到“至少两张基本可辨为同一人物与服装”的门槛。
- 未见文字、水印、Logo、现代物件、严重脸手畸形或主体被边缘裁切。
- 低影响差异：`shot-003` 的信物更接近古币牌造型，参考表中则为圆形青铜信物；仍属同类古代小型青铜凭证，不影响叙事与后续动态验证，故不修订。

### 批次 2 退出结论

- 角色表与三张关键帧均已保存到项目工作区、可解码、构图安全且一致性达到计划门槛。
- 批次 2 判定 **PASS**，允许进入批次 3。

## 3. 批次 3：实验渲染器与自动测试

### 测试先行

- 先新增 `【包A】视频引擎包/tests/test_v2_phase1_sample.py`，首次运行因 `render_sample.py` 尚不存在而按预期失败（1 个导入错误）。
- 随后实现实验代码并重跑：9 项测试全部通过，耗时约 0.01 秒。
- 测试覆盖：三镜头数量与 ID、顶层/镜头未知字段、任务目录外路径/绝对路径/符号链接逃逸、空旁白、预设白名单、focus 边界、固定运镜 filter、ASS 转义与时间、报告必需追踪字段、禁止 `shell=True`/`os.system`。

### 新增文件

- `【包A】视频引擎包/experiments/short_video_v2_phase1/render_sample.py`
- `【包A】视频引擎包/experiments/short_video_v2_phase1/README.md`
- `【包A】视频引擎包/experiments/short_video_v2_phase1/sample_storyboard.template.json`
- `【包A】视频引擎包/tests/test_v2_phase1_sample.py`

### 实现边界

- Python 标准库 HTTP 客户端调用包 A `/api/tts`、轮询 `/api/status/<job>`、下载 `/api/tts_file/<job>`；单段失败最多重试一次。
- 用 ffprobe 读取真实 WAV 时长，并按 `WAV + 头留白 + 尾留白` 计算镜头时长。
- 只实现 `static`、`slow_push_in`、`gentle_drift`、`slow_pull_out` 四个固定预设；JSON 不接受任意 filtergraph。
- 使用随包 `simhei.ttf` 生成镜头级与合并 ASS；在临时 staging 目录中以固定安全文件名交给 libass。
- 标准镜头统一为 H.264、1080x1920、30 FPS、yuv420p、AAC 48 kHz 双声道；最终片以 FFmpeg concat filter 硬切合成。
- 增量写入 `render_report.json`，仅在输入与既有报告哈希一致时复用已完成的音频/镜头/最终片；其余既有文件默认拒绝覆盖，`--overwrite` 仅供明确重做本实验受管产物。
- 自动生成代表帧、联系表与 `ffprobe-report.json`。
- 未修改 `kt_web.py`、`kt_video.py`、包 B 源码、正式 `/api/generate` 或 UI；正式 V1 入口未导入实验目录。

### 验证命令与结果

1. 新增测试：`...python3 -B -m unittest discover -s 【包A】视频引擎包/tests -p 'test_v2_phase1_sample.py'` → 9/9 通过。
2. 既有渲染契约：`-p 'test_phase2_render_contracts.py'` → 10/10 通过。
3. 既有 Web 契约：`-p 'test_phase3_web_contracts.py'` → 22/22 通过。
4. 既有包 B 契约：`-p 'test_phase3_package_b_contract.py'` → 7/7 通过。
5. FFmpeg 语法冒烟：用 `shot-001.png`、基线真实 WAV、生成的 ASS 和 `slow_push_in` 渲染 1.0 秒临时镜头；ffprobe 确认 H.264、1080x1920、30 FPS、yuv420p、AAC 48 kHz，成功后临时目录自动清理。
6. 源码检索确认 `short_video_v2_phase1` 只出现在实验 README 与新增测试中；正式 `程序文件/` 无导入。

### 批次 3 退出结论

- 新增与受影响测试全部通过，真实 FFmpeg filter/字幕语法已冒烟验证，无新增依赖、无 shell 执行、无正式入口侵入。
- 批次 3 判定 **PASS**，允许进入批次 4。

## 4. 批次 4：真实三镜头渲染

### 运行与现场

- 运行前再次确认包 A PID 9534/端口 8787 健康、包 B PID 6297/端口 7860 为 MF ready 且 API 兼容，未重启服务。
- 受影响的既有 Web 契约测试会清理真实运行目录中的 `.port` 与 `.package-a-server.json`；测试后进程与监听仍健康。本轮依据批次 1 留存的确切值恢复这两个运行状态文件，并再次核验 PID/端口/mode。此为本轮造成并已修复的测试隔离副作用，未停止服务。
- 实际命令：`.../runtime/bin/python3 -B .../experiments/short_video_v2_phase1/render_sample.py --job-dir .../phase1-three-shot --storyboard .../storyboard.sample.json --package-a-url http://127.0.0.1:8787 --ffmpeg .../bin/ffmpeg --ffprobe .../bin/ffprobe`。
- 总运行区间：17:40:28–17:41:33，约 65 秒；三段 TTS 均首试成功，无重试。

### 三段真实 TTS 与镜头

| 镜头 | 文本 | WAV 时长 | TTS 墙钟 | WAV SHA-256 | 预设 | 目标/实际镜头时长 | 渲染墙钟 | 镜头 SHA-256 |
| --- | --- | ---: | ---: | --- | --- | --- | ---: | --- |
| `shot-001` | 暮色压向古城时，一名浑身湿透的信使赶到了城门。 | 4.730s | 18.78s | `043af0378a75cbf45bd245ab00d70822b76bdb3ef2dc4ef118341f2f9b06029d` | `slow_push_in` | 5.130/5.133s | 1.98s | `49af9994aef4c08b4f26c200fa587e4b7a4f2bd8ba2d96fb0368cb40771895a8` |
| `shot-002` | 他怀里的密信，只写着一句话：山洪会在今夜抵达。 | 5.034s | 16.28s | `29e85e8cc20974ccb219d2ad919447bdf901b4512c9e326b768f33a7487b47fa` | `gentle_drift` | 5.434/5.434s | 1.48s | `2c302104d00f9f35cbb5c87904094cde0b937330ea07dac0509ec06a0a9b8a75` |
| `shot-003` | 城门闭合前，守军认出了信物，第一盏警灯终于亮起。 | 5.077s | 18.31s | `76588e7e46a6a944dfcd789d91a1c77e37dd308b030f293d1cab5a8ef418f845` | `slow_pull_out` | 5.477/5.477s | 2.04s | `bf3711d2bb30c22b766fe72ef0d00b9806c2742b82be3d91922a537bd3bb2d6e` |

### 最终产物

- 三段 WAV：`audio/shot-001.wav` 至 `shot-003.wav`。
- 三个标准镜头：`shots/shot-001.mp4` 至 `shot-003.mp4`。
- 镜头级 ASS 与合并字幕：`captions/`。
- 硬切最终片：`output/final.mp4`；H.264、1080x1920、30 FPS、yuv420p、AAC 48 kHz 双声道，时长 16.064 秒，大小 4,631,862 字节，SHA-256 `35de92e897eb56fcbdccd5c3b00b2d1bafcc9b52f9d7edb471bbd988aa809f9c`；最终合成墙钟 3.38 秒。
- 报告：`output/render_report.json` 与 `evidence/ffprobe-report.json`。
- 代表帧：`evidence/representative-frames/shot-001-mid.png` 至 `shot-003-mid.png`。
- 联系表：`evidence/contact-sheet.jpg`。
- 未生成短叠化 preview；硬切主片已经完成，计划未要求为形式完整额外重编码。

### 最小复核

- 新增测试再次运行 9/9 通过。
- `ffmpeg -v error -i output/final.mp4 -f null -` 退出码 0、无错误输出。
- 三个镜头、三段语音与字幕顺序正确，运镜可感知，主体未被运镜裁出画面。
- 代表帧暴露一项阻塞观感问题：libass 未按中文字符自动换行，三句字幕以单行横向溢出并被画面边缘裁切。此问题不影响批次 4 的真实 TTS、镜头、硬切合成和产物完整性，但违反批次 5 字幕观感门；已停止扩大修改，留给批次 5 唯一一次最小修复循环处理。

### 批次 4 退出结论

- 三段真实 TTS、三个标准镜头与 `final.mp4` 均已生成，无失败或重试；报告、代表帧和联系表齐全。
- 批次 4 判定 **PASS**，允许进入批次 5；字幕溢出必须在批次 5 修复并重验后方可给出最终等级。

## 5. 批次 5：质量门、一次修复循环与收官

### 开始前复核

- 已重新读取本执行记录，并以批次 4 留下的唯一阻塞观感问题——中文长句字幕横向溢出——作为本批修复边界。
- 包 A 仍为 PID 9534、端口 8787；包 B 仍为 PID 6297、端口 7860，两个监听均在，未停止或重启服务。
- 未扩大到正式 V2 Schema/API/UI、BGM、环境音、SFX、高级动态化工具、SOAR、完整耐久、发布验收、签名或公证。

### 唯一一次修复循环

1. 先为较长中文旁白新增回归测试；首次运行按预期失败，原因是 `render_sample.py` 尚无 `wrap_caption`。
2. 在实验渲染器中新增确定性的中文两行换行：优先在标点处分行，每行不超过 16 个中文字符；同时将 `RENDERER_VERSION` 提升为 `phase1-renderer-2`，把渲染器版本及 ASS 哈希纳入镜头复用键，避免字幕逻辑变化后误复用旧镜头。
3. 修正 TTS 复用报告：复用时保留首次真实合成墙钟，不把复用检查时间冒充模型合成时间。
4. 新增测试由失败转为 10/10 通过。
5. 使用原命令加 `--overwrite` 重渲染；三段真实 WAV 全部按哈希复用，未再次调用模型，仅重编码三个镜头及 `final.mp4`。

### 最终三段 TTS

| 镜头 | WAV 时长 | WAV 规格 | WAV SHA-256 | 首次合成墙钟 | 本轮复用 |
| --- | ---: | --- | --- | ---: | --- |
| `shot-001` | 4.730s | PCM s16le、48 kHz、单声道 | `043af0378a75cbf45bd245ab00d70822b76bdb3ef2dc4ef118341f2f9b06029d` | 18.78s | 是 |
| `shot-002` | 5.033979s | PCM s16le、48 kHz、单声道 | `29e85e8cc20974ccb219d2ad919447bdf901b4512c9e326b768f33a7487b47fa` | 16.28s | 是 |
| `shot-003` | 5.077167s | PCM s16le、48 kHz、单声道 | `76588e7e46a6a944dfcd789d91a1c77e37dd308b030f293d1cab5a8ef418f845` | 18.31s | 是 |

- 三段均为首次请求成功，无重试；未见削波。原始 WAV 平均音量约 -17.2/-18.3/-18.0 dB，峰值约 -0.8/-0.7/-0.4 dB。

### 最终三个镜头与合并片

| 产物 | 目标/实际时长 | SHA-256 | 字节数 | 完整解码 |
| --- | --- | --- | ---: | --- |
| `shots/shot-001.mp4` | 5.130/5.133333s | `1bbb0643c3f90c71a9a02fd0fd4714e76a0a4030200fdf35c959f03349585c3e` | 1,938,768 | PASS |
| `shots/shot-002.mp4` | 5.433979/5.434s | `a4b1adc9c44619de8a008880886b506c31d22bbe44e633b299019087df3bc74f` | 659,227 | PASS |
| `shots/shot-003.mp4` | 5.477167/5.477s | `04abd3582de67f860fbeb03cdd20da1e38fb60bc58c1e739b605bfd61d8fd565` | 1,846,787 | PASS |
| `output/final.mp4` | 16.064s | `3b18b368fa990d21a1f8bdb19c7436132fd465a7aa5945e0e752499518f063b7` | 4,678,735 | PASS |

- 三个镜头与最终片均为 H.264、1080x1920、30 FPS、yuv420p，音频均为 AAC 48 kHz 双声道。
- 三镜头容器时长之和 16.044333 秒，最终片 16.064 秒，差 0.019667 秒，小于 0.25 秒门槛；视频流 16.033333 秒、音频流 16.064 秒，差 0.030667 秒。
- 四个 MP4 的 ffprobe 退出码均为 0，`ffmpeg -v error -i <file> -f null -` 均退出 0、无错误输出；blackdetect 未发现黑场段。
- 成片平均/峰值音量约 -21.3/-3.6 dB；三个镜头平均音量差约 1.0 dB，峰值差约 0.7 dB，未见明显忽高忽低。

### 实际观看与观感结论

- 在解锁后的 macOS QuickTime Player 中用临时 ASCII 路径打开正式成片的只读副本，完整播放 00:00 至 00:16；播放器无中断、无解码警告，结束时自行停止。
- 在 QuickTime 内逐点检查三句字幕：第一句约 2.32 秒、第二句约 7.51 秒、第三句约 10.92 秒，均已分成不超过两行，位于画面下方安全区，白字黑边清楚，无横向裁切。
- `slow_push_in`、`gentle_drift`、`slow_pull_out` 均属克制的轻运镜，人物主体未越出安全画面；三镜头硬切顺序清楚，角色面貌、束发、靛青服装与棕色挎包维持一致。
- QuickTime 尾端约 0.03 秒显示黑屏，恰对应视频流比音频流短 0.030667 秒；低于计划时长差门槛且不可感知为实质黑场，blackdetect 亦无发现，故不构成阻塞。
- 视觉佐证包括中点代表帧、六张边界帧、2 FPS 时间轴联系表；与实时播放相互印证。

### 证据与报告

- `output/render_report.json`：已写入 `quality_gate.status=PASS`、修复次数、实时播放结论与计划 02 准入。
- `evidence/quality-check-report.json`：批次 5 的结构化技术/观感门报告。
- `evidence/ffprobe-report.json`：镜头及最终片媒体探测报告。
- `evidence/contact-sheet.jpg`：三镜头代表帧联系表。
- `evidence/boundary-contact-sheet.jpg`：六张镜头起止帧联系表，SHA-256 `a73ed0a00fdc01c3b65e67b7d0e47b73ff3726033bd771292e3ea65a07adae8f`。
- `evidence/timeline-contact-sheet.jpg`：全片 2 FPS 时间轴联系表，SHA-256 `bfa269f63ca2ade862d61bf3071c207a156b15ec2fe08af8b55becc89f2f92c6`。

### 未处理低影响事项

- 包 A 全量测试仍有 2 个失败、1 个错误，均为旧 Windows 边界测试硬编码 `ffmpeg.exe`、`python.exe` 或 `C:/Windows/Fonts`，不影响当前 Mac 真实链路；本计划不修改。
- 包 B 全量测试仍会出现一次未关闭 event loop 的 `ResourceWarning`，51 项测试均通过；本计划不修改。
- TTS 自然尾音静默叠加配置留白，使镜头末尾/切点出现约 0.69–0.93 秒静音；旁白完整，三段音量均衡，当前样片观感可接受。可在计划 02 把“有效发声区测量与尾静音裁剪”列为设计输入，而非计划 01 阻塞项。
- `shot-003` 信物造型较参考表更像古币牌，但仍为同类古代青铜凭证，叙事清楚，不消耗修订预算。

### 批次 5 退出结论

- 字幕阻塞已在唯一一次修复循环中解决；新增测试、真实重渲染、规格探测、完整解码、静音/音量/黑场检测、联系表与 QuickTime 实时播放均已通过。
- 最终等级：**PASS**。
- 计划 01 至此完成，不进入计划 02。依据本阶段证据，**允许制定并执行计划 02**；建议先把有效发声区/尾静音策略纳入其设计，而不回改计划 01 样片。
