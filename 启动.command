#!/bin/bash
# 从源码直接启动(首次运行会自动建虚拟环境并装依赖)
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "首次运行:创建虚拟环境并安装依赖…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

exec ./.venv/bin/python -m wlmac.app
