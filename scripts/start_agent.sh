#!/bin/bash
# start_agent.sh: Start thesis_review_agent Web service
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${AGENT_PORT:-8088}"
HOST="${AGENT_HOST:-0.0.0.0}"

export MODEL_BASE_URL="${MODEL_BASE_URL:-http://127.0.0.1:8122/v1}"
export MODEL_NAME="${MODEL_NAME:-Qwen3.8-27B}"
export MODEL_API_KEY="${MODEL_API_KEY:-none}"
export DATA_ROOT="${DATA_ROOT:-$DIR/data}"
export MAX_REVIEW_CHARS="${MAX_REVIEW_CHARS:-500000}"
export MODEL_TIMEOUT="${MODEL_TIMEOUT:-600}"

UVICORN_BIN="/home/amax/anaconda3/envs/qwen3/bin/uvicorn"

echo "=========================================="
echo "Starting Thesis Review Agent Service"
echo "Working Dir    : $DIR"
echo "Binding Address: $HOST:$PORT"
echo "Model URL      : $MODEL_BASE_URL"
echo "Model Name     : $MODEL_NAME"
echo "Data Storage   : $DATA_ROOT"
echo "=========================================="

cd "$DIR"
exec "$UVICORN_BIN" app.main:create_app --factory --host "$HOST" --port "$PORT" --workers 1
