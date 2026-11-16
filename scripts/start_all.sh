#!/bin/bash
# start_all.sh: Launch both Model Inference and Agent in background with log redirection
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$DIR/logs"

echo "1. Checking/Starting Model Inference service (Qwen3.8-27B-Q8_0)..."
if curl -s --max-time 2 http://127.0.0.1:8122/health > /dev/null 2>&1; then
    echo "Model service is already running on port 8122."
else
    nohup "$DIR/scripts/start_single_gpu_q8.sh" > "$DIR/logs/model.log" 2>&1 &
    echo "Model server started with PID $! (logs: $DIR/logs/model.log)"
fi

echo "2. Starting Thesis Review Agent..."
if curl -s --max-time 2 http://127.0.0.1:8088/api/v1/config > /dev/null 2>&1; then
    echo "Thesis Review Agent is already running on port 8088."
else
    nohup "$DIR/scripts/start_agent.sh" > "$DIR/logs/agent.log" 2>&1 &
    echo "Agent started with PID $! (logs: $DIR/logs/agent.log)"
fi

echo "All services initiated. Use ./scripts/status.sh to check status."
