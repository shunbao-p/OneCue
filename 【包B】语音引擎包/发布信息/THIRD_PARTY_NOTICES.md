# 第三方组件与发布说明

- Python 3.12 arm64 来自锁定的 python-build-standalone 原始资产。
- Python 依赖由 88 个逐文件 SHA-256 校验的 wheel 离线安装；许可证随各 dist-info 保留在运行时中。
- ffmpeg/ffprobe 来自包 A 同批离线源码构建，启用 GPL/libx264/libass，明确未启用 nonfree。
- 精确工具构建报告和源码归档位于本目录。
- 产品包未签名、未公证；公开分发前需要独立完成 Developer ID 与公证流程。
