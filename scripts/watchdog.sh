#!/bin/bash
# watchdog.sh: Auto-heal thesis_review_agent and model inference services
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# 1. Check Inference Model service on port 8122
if ! curl -s --max-time 3 http://127.0.0.1:8122/health > /dev/null 2>&1; then
    # check if process is already starting
    if ! pgrep -f "llama-server.*Qwen3.8-27B" > /dev/null 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Model inference server is down. Restarting on GPU 2..." >> logs/watchdog.log
        nohup ./scripts/start_single_gpu_q8.sh >> logs/model.log 2>&1 &
    fi
fi

# 2. Check Agent Web service on port 8088
if ! curl -s --max-time 3 http://127.0.0.1:8088/api/v1/config > /dev/null 2>&1; then
    if ! pgrep -f "uvicorn.*app.main:create_app" > /dev/null 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Agent web service is down. Restarting..." >> logs/watchdog.log
        nohup ./scripts/start_agent.sh >> logs/agent.log 2>&1 &
    fi
fi
