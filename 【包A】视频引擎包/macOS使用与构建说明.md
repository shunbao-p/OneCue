# 包 A：Apple Silicon macOS 使用与构建说明

本说明覆盖【包 A】视频引擎及其调用同目录【包 B】语音引擎的本机链路。包 A 可独立使用现有 WAV 生成视频；需要文字合成语音时，先启动包 B，再通过包 A 的连接入口写入本机服务地址。

支持目标：Apple Silicon（arm64）macOS。当前实机为 M1 Pro / macOS 26.5.1。Intel Mac 不在本阶段支持范围。

## 最终用户启动

正式的 macOS 发布包内含受控 arm64 Python、FFmpeg、ffprobe 和字体，最终用户不需要 Homebrew，也不依赖 macOS 自带的 Python。

1. 将整个“【包A】视频引擎包”解压到当前用户有写权限的位置。中文、空格路径受到支持。
2. Finder 双击 `①开始使用.command`。
3. 启动器先检查系统架构、包内 Python、FFmpeg/ffprobe 架构和能力、字体、目录写权限与至少 2 GiB 可用空间。
4. 预检通过后，浏览器打开实际监听端口。默认从 8787 开始；若被占用，服务顺延端口，启动器读取 `.port` 后打开正确地址。
5. 再次双击会复用已经健康运行的包 A 服务，不会产生不可控多实例。

## 连接包 B 语音引擎

1. 将完整的“【包A】视频引擎包”和“【包B】语音引擎包”放在同一目录中；中文和空格路径受到支持。
2. 双击包 B 的 `启动-快速版.command`，等待浏览器打开并确认服务可用。快速版 MF 是默认生产路径。
3. 双击包 A 的 `②连接语音引擎.command`。连接器只访问本机 `127.0.0.1`，不会上传音色或文本。
4. 双击包 A 的 `①开始使用.command`，在网页中生成配音和视频。

包 B 的质量版 SOAR 可以正确生成，但在 M1 Pro 上明显慢于音频时长，仅作为可选非实时模式；A+B 日常链路使用快速版 MF。

服务停止命令（在“【包A】视频引擎包”目录执行）：

```text
程序文件/runtime/bin/python3 -B 程序文件/mac_launcher.py stop
```

任务渲染中的停止仍使用网页里的“停止”操作；它会终止当前 FFmpeg 并保留明确终态。

## 首次运行

本地验收构建会明确带有 `unsigned-unnotarized` 标记，不能冒充正式外发包。若从网络下载，Gatekeeper 可能阻止直接双击；本地验证时可在 Finder 中按住 Control 点按该 `.command`，选择“打开”并确认。不要为绕过 Gatekeeper 对整个磁盘执行递归 `xattr` 或关闭系统安全功能。

面向普通用户正式分发前，发布方必须使用 Developer ID、Hardened Runtime 和 Apple `notarytool` 完成签名/公证。缺少证书或凭据时，只能交付本地验收构建与构建证据。

## 开发启动

开发模式可以使用开发机上已经安装或单独缓存的原生工具，但必须显式指定路径；这不会改变最终用户包的受控运行时策略。

```text
/usr/bin/python3 -B "程序文件/mac_launcher.py" preflight --mode development \
  --ffmpeg "/path/to/arm64/ffmpeg" \
  --ffprobe "/path/to/arm64/ffprobe"

/usr/bin/python3 -B "程序文件/mac_launcher.py" start --mode development \
  --ffmpeg "/path/to/arm64/ffmpeg" \
  --ffprobe "/path/to/arm64/ffprobe"
```

开发 FFmpeg 若含 `--enable-nonfree`，预检会发出警告并允许本机验证，但构建脚本绝不会把它复制进发布包。

## 构建发布包

构建必须在 Apple Silicon Mac 上执行。脚本只使用 `scripts/macos-runtime-lock.json` 中的固定 URL 和 SHA-256；下载后先校验再解包。FFmpeg 8.1.2 官方源码还应以锁文件中的 FFmpeg 发布签名指纹复核。构建不需要 Homebrew。

```text
/usr/bin/python3 scripts/build_macos_release.py \
  --work-dir "$HOME/Library/Caches/文本视音屏生成器/phase4-build" \
  --cache-dir "$HOME/Library/Caches/文本视音屏生成器/phase4-sources" \
  --output-dir "$HOME/Desktop/包A-Phase4-产物"
```

产物包括：

- `*-unsigned-unnotarized.zip`：包内 Python、FFmpeg/ffprobe、业务文件、启动器、许可证与 manifest；仅用于本地验收。
- `*-sources.zip`：对应 FFmpeg/x264/libass 及依赖的精确源码归档、lock 与构建脚本。
- `*-build-report.json`：产物哈希、版本、架构、能力与签名/公证状态。

FFmpeg 构建启用 `--enable-gpl --enable-libx264 --enable-libass`，使用 FFmpeg 内建 AAC；禁止 `--enable-nonfree` 和 libfdk-aac。因为包含 libx264，随包 FFmpeg 按 GPL-2.0-or-later 处理，并同时归档对应源码和许可证。正式商业分发还需要发布方自行完成法律与专利合规复核。

## 诊断

发布模式：

```text
程序文件/runtime/bin/python3 -B 程序文件/mac_launcher.py diagnose --mode release
```

开发模式可改为 `/usr/bin/python3 -B` 并附带 `--ffmpeg/--ffprobe`。`-B` 避免把运行时字节码写回发布目录，便于启动前后复核 manifest。诊断会生成：

- `程序文件/日志/macOS诊断报告.json`
- `程序文件/日志/macOS诊断报告.txt`

内容包括系统、架构、版本、工具路径与能力、实际端口、字体、目录写入状态、磁盘、最近 40 行服务日志和包 B 连接状态。日志与路径中的用户主目录会显示为 `~`；不会输出密码、令牌、Cookie、SSH 配置或完整 `config.ini` 内容。

## 故障排除

- “缺少包内 Python”：拿到的是源码/开发目录，不是完整发布包；重新构建或重新解压 `*-unsigned-unnotarized.zip`。
- “需要 Apple Silicon arm64”：当前机器或工具为 Intel/x86_64，本阶段不支持。
- “ffmpeg 缺少 subtitles/libx264/aac”：不要继续运行；用 lock 文件重新构建完整工具链。
- “检测到 `--enable-nonfree`”：该 FFmpeg 仅可做开发验证，不能进入发布包。
- “目录不可写”：把整个包移动到当前用户可写目录，保持文件夹结构完整。
- “磁盘空间不足”：释放空间后重新运行；启动阶段最低要求为 2 GiB，实际长视频应预留更多。
- “浏览器没有打开”：查看诊断报告中的实际端口，手动访问 `http://127.0.0.1:<实际端口>/`。
- “重复启动打开旧页面”：先运行 stop 命令；若报告显示无可验证进程，不会按不可信 PID 强杀其它程序。
- “包 B 未连接”：先启动同目录包 B 的快速版，再双击 `②连接语音引擎.command`；不需要配音时也可直接上传现有 WAV 与 UTF-8 TXT 生成视频。

## 已知限制

- 本阶段只支持 Apple Silicon，不支持 Intel Mac。
- 未取得 Developer ID 与公证凭据时，产物只能标记为未签名/未公证本地验收构建。
- `.command` 不是 `.app`；首次从网络下载时仍可能出现 Gatekeeper 交互。
- Phase 2 的 FFmpeg 6.0 开发缓存含 `--enable-nonfree`，不会复用到发布产物。
- 包 B 快速版在 M1 Pro 上属于可用但非实时级速度；质量版更慢，不作为默认生产路径。
- 超过 200 字的分段长文可能出现局部音量突然变小。该问题不影响文件生成或 A+B 视频链路，当前作为低优先级已知限制保留。
