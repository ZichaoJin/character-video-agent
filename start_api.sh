#!/usr/bin/env bash
# ── MovieAgent API 启动脚本 ──────────────────────────────────────────────────
# 用法: bash start_api.sh
#
# API keys 存在 ~/.env_movieagent（不进 git），格式：
#   OPENAI_API_KEY=sk-...
#   GOOGLE_API_KEY=...
#   RUNWAYML_API_SECRET=...
#   S3_BUCKET=zichao-movie-sg-2026
#   CHARACTER_PHOTOS_PATH=/home/ubuntu/MovieAgent-main/dataset/布布一二_PittsburghTrip/character_list
#   API_TOKEN=mzc-secret-2026-xK9pQ
#   AWS_DEFAULT_REGION=ap-southeast-1
# ─────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

ENV_FILE="${HOME}/.env_movieagent"
if [ ! -f "$ENV_FILE" ]; then
  echo "❌  找不到 $ENV_FILE，请先创建并填写 API key。"
  echo "    参考格式见 start_api.sh 顶部注释。"
  exit 1
fi

# 加载环境变量（跳过空行和注释）
set -o allexport
# shellcheck source=/dev/null
source "$ENV_FILE"
set +o allexport

echo "✅  已加载环境变量: $ENV_FILE"

# 停掉旧进程
pkill -f "uvicorn api.main:app" 2>/dev/null && echo "⏹  已停止旧 uvicorn" || true
sleep 1

# 启动
LOG="${HOME}/api.log"
nohup venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 >> "$LOG" 2>&1 &
echo "🚀  MovieAgent API 已启动 PID=$!，日志: $LOG"
