#!/bin/bash
# 在项目根目录创建虚拟环境并安装 requirements.txt
# 用法：在项目根目录执行  bash scripts/setup_venv.sh
# 若系统提示 Xcode 许可，请先在终端执行：sudo xcodebuild -license

set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"

if [ -d "$ROOT/.venv" ]; then
  echo ".venv 已存在，跳过创建。若要重装依赖，请先删除 .venv 目录。"
else
  echo "创建虚拟环境: $ROOT/.venv"
  python3 -m venv "$ROOT/.venv"
fi

echo "激活虚拟环境并安装 requirements.txt ..."
# shellcheck disable=SC1090
source "$ROOT/.venv/bin/activate"
pip install --upgrade pip
pip install -r "$ROOT/requirements.txt"

echo "完成。以后使用前请先激活环境："
echo "  source $ROOT/.venv/bin/activate"
echo "或 (Windows)  $ROOT/.venv/Scripts/activate"
