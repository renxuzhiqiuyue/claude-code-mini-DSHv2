#!/usr/bin/env bash
# 先填写本目录 config.py；请在已激活的 conda / .venv 终端中执行
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/.."
exec python -m hiagent2llm
