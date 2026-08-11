#!/bin/zsh
set -u

SCRIPT_DIR="${0:A:h}"
PYTHON_RUNTIME="$SCRIPT_DIR/程序文件/runtime/bin/python3"
LAUNCHER="$SCRIPT_DIR/程序文件/mac_launcher.py"

if [[ ! -x "$PYTHON_RUNTIME" ]]; then
  print -u2 "[启动失败] 缺少包内 Apple Silicon Python："
  print -u2 "  $PYTHON_RUNTIME"
  print -u2 "检测到的包目录：$SCRIPT_DIR"
  print -u2 "恢复方法：重新解压完整的 macOS arm64 发布包。开发者请按《macOS使用与构建说明.md》使用 development 模式。"
  print -u2 ""
  read -k 1 "?按任意键关闭窗口..."
  print
  exit 1
fi

"$PYTHON_RUNTIME" -B "$LAUNCHER" start --mode release
STATUS=$?
if (( STATUS != 0 )); then
  print -u2 ""
  print -u2 "启动未完成。诊断报告位于：程序文件/日志/macOS诊断报告.txt"
  read -k 1 "?按任意键关闭窗口..."
  print
fi
exit $STATUS
