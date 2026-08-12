# 第三方组件与分发说明

此本地验收构建包含独立 FFmpeg/ffprobe 可执行文件。因启用 GPL 的 libx264，
该 FFmpeg 构建按 GPL-2.0-or-later 处理；未启用 `--enable-nonfree` 或 libfdk-aac。
精确源码归档、SHA-256、版本和构建参数位于同构建 ID 的 sources.zip 与 manifest.json。
这不是法律意见；正式分发前应由发布方完成许可证与专利合规复核。

Python 运行时来自 astral-sh/python-build-standalone；运行时内保留 CPython 与 vendored 组件许可证。
包内 jieba 0.42.1 使用 MIT 许可证（Copyright 2013 Sun Junyi）。

## 锁定组件

- astral-sh/python-build-standalone 3.13.13 — MPL-2.0 build project; runtime component licenses are contained in the archive — `1ad1ed518447005d4b6dfa16d4f847d45790e17e94e30164a0a6e6c79a99730f`
- ffmpeg 8.1.2 — GPL-2.0-or-later when built with libx264 — `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`
- x264 b35605ace3ddf7c1a5d67a2eb553f034aef41d55 — GPL-2.0-or-later — `cd71a7515b0e9a012e1ac9b1f8415bebcaf6fc97d4db32286642ac4c0fbe24f9`
- libass 0.17.5 — ISC — `2dca25c0e0c837ddf00b52011b3f82cac1e4ddd3ad018227806b0c2288864acc`
- freetype 2.14.1 — FTL or GPL-2.0-or-later — `32427e8c471ac095853212a37aef816c60b42052d4d9e48230bab3bdf2936ccc`
- fribidi 1.0.16 — LGPL-2.1-or-later — `1b1cde5b235d40479e91be2f0e88a309e3214c8ab470ec8a2744d82a5a9ea05c`
- harfbuzz 14.3.0 — MIT — `16070d77cfc4ba1f1e7327e83bf9b3f55898081cabdb94e56a33e04fc8874eae`
- pkgconf 3.0.5 — ISC — `3acd3a8a3cce65a8d620321855d92fb602e026cbe8e13ee36bdec58483b59ace`
