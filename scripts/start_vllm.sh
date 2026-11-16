#!/bin/bash
# start_vllm.sh: Start vLLM OpenAI-compatible server for Qwen3-8B-IT on Single GPU
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_PATH="${MODEL_PATH:-/data01/llms/Qwen3-8B-IT}"
PORT="${PORT:-8122}"
HOST="${HOST:-127.0.0.1}"
GPU_ID="${CUDA_VISIBLE_DEVICES:-1}"

VLLM_BIN="/home/amax/anaconda3/envs/qwen3/bin/vllm"

echo "=========================================="
echo "Starting vLLM Server for Qwen3-8B-IT"
echo "Model Path : $MODEL_PATH"
echo "GPU ID     : $GPU_ID"
echo "Host:Port  : $HOST:$PORT"
echo "=========================================="

export CUDA_VISIBLE_DEVICES="$GPU_ID"
export VLLM_USE_V1=0

exec "$VLLM_BIN" serve "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  --served-model-name "Qwen3-8B-IT" \
  --trust-remote-code \
  --gpu-memory-utilization 0.85 \
  --max-model-len 32768
