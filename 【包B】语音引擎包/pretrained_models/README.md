# 模型目录

模型权重不纳入 Git 仓库。请在仓库根目录执行：

```bash
python3 scripts/download_macos_models.py --model mf
```

脚本会从 Hugging Face 下载 `rednote-hilab/dots.tts-mf`，并根据
`manifests/macos-mf-model.json` 对文件大小和 SHA-256 逐项校验。
质量版使用 `--model soar`。不要手动改名、替换或混用模型目录。
