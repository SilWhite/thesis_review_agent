#!/bin/bash
# status.sh: Check status of Thesis Review Agent & Model Inference Service
echo "=== Model Inference Service (8122) ==="
if curl -s --max-time 2 http://127.0.0.1:8122/health > /dev/null 2>&1; then
    echo "[ONLINE] Model Service is responding on 8122"
else
    echo "[OFFLINE] Model Service is NOT responding on 8122"
fi
pgrep -a -f "llama-server.*Qwen3.8-27B|vllm serve" || echo "No model process found"

echo ""
echo "=== Thesis Review Agent (8088) ==="
if curl -s --max-time 2 http://127.0.0.1:8088/api/v1/config > /dev/null 2>&1; then
    echo "[ONLINE] Agent is responding on 8088"
else
    echo "[OFFLINE] Agent is NOT responding on 8088"
fi
pgrep -a -f "uvicorn.*app.main:create_app" || echo "No agent process found"
