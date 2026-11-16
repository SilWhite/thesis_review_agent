#!/bin/bash
# start_single_gpu_q8.sh: Start Qwen3.8-27B-Q8_0 on a single GPU using llama-server
set -e

MODEL_FILE="${MODEL_FILE:-/data01/llms/Qwen3.8-27B-Q8_0.gguf}"
PORT="${PORT:-8122}"
HOST="${HOST:-127.0.0.1}"
GPU_ID="${GPU_ID:-2}"

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"

if [ ! -f "$MODEL_FILE" ]; then
    echo "Error: Model file $MODEL_FILE does not exist or download is not finished yet."
    exit 1
fi

echo "=========================================="
echo "Starting Single-GPU Q8_0 Server via llama-server"
echo "Model File : $MODEL_FILE"
echo "GPU ID     : $GPU_ID"
echo "Host:Port  : $HOST:$PORT"
echo "=========================================="

export CUDA_VISIBLE_DEVICES="$GPU_ID"

exec "$LLAMA_SERVER_BIN" \
  -m "$MODEL_FILE" \
  -ngl 99 \
  --port "$PORT" \
  --host "$HOST" \
  -c 65536 \
  --alias "Qwen3.8-27B,Qwen3-8B-IT,default" \
  --reasoning-budget 0
