#!/bin/bash
# stop_all.sh: Safely stop Agent and Model Inference service
echo "Stopping Thesis Review Agent..."
pkill -f "uvicorn.*app.main:create_app" || true

echo "Stopping Model Inference service..."
pkill -f "llama-server.*Qwen3.8-27B" || true
pkill -f "vllm serve" || true

echo "All services stopped."
