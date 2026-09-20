#!/usr/bin/env bash
# 在离线 Linux x86_64 机器上还原 conda 环境 claude-code-mini。
# 用法：
#   bash restore-conda-env.sh
#   bash restore-conda-env.sh /opt/claude-code-mini
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="${ARCHIVE:-$SCRIPT_DIR/../dist/claude-code-mini-linux-x86_64.tar.gz}"
if [[ ! -f "$ARCHIVE" && -f "$SCRIPT_DIR/claude-code-mini-linux-x86_64.tar.gz" ]]; then
  ARCHIVE="$SCRIPT_DIR/claude-code-mini-linux-x86_64.tar.gz"
fi
PREFIX="${1:-${HOME}/envs/claude-code-mini}"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "找不到离线包: $ARCHIVE" >&2
  exit 1
fi

mkdir -p "$PREFIX"
echo "解压到 $PREFIX ..."
tar -xzf "$ARCHIVE" -C "$PREFIX"
# shellcheck disable=SC1091
source "$PREFIX/bin/activate"
if [[ -x "$PREFIX/bin/conda-unpack" ]]; then
  echo "执行 conda-unpack ..."
  conda-unpack
fi
echo
echo "还原完成。"
echo "激活:  source $PREFIX/bin/activate"
echo "验证:  python -c 'import langchain, fastapi, matplotlib; print(\"ok\")'"
echo "退出:  conda deactivate  或  source deactivate"
