#!/bin/zsh
set -u

SCRIPT_DIR="${0:A:h}"
PYTHON_RUNTIME="$SCRIPT_DIR/runtime/python/bin/python3.12"
LAUNCHER="$SCRIPT_DIR/_internal/macos_launcher.py"

if [[ ! -x "$PYTHON_RUNTIME" ]]; then
  print -u2 "[启动失败] 缺少包内 Apple Silicon Python 3.12：$PYTHON_RUNTIME"
  print -u2 "恢复方法：重新解压完整的 Apple Silicon macOS 包。"
  read -k 1 "?按任意键关闭窗口..."
  print
  exit 1
fi

cd "$SCRIPT_DIR" || exit 1
"$PYTHON_RUNTIME" -B "$LAUNCHER" start \
  --model dots-tts-soar --device auto --precision auto --port 7860 \
  --log-file "$SCRIPT_DIR/logs/gradio.log"
STATUS=$?
if (( STATUS != 0 )); then
  print -u2 ""
  print -u2 "质量版需要完整包内 dots-tts-soar；模型不完整时请使用“启动-快速版.command”。"
  read -k 1 "?按任意键关闭窗口..."
  print
fi
exit $STATUS
