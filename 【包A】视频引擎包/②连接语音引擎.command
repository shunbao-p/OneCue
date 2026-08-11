#!/bin/bash
set -u
PACKAGE_ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$PACKAGE_ROOT/程序文件/runtime/bin/python3" \
  "$PACKAGE_ROOT/程序文件/connect_dots.py" "$@"
