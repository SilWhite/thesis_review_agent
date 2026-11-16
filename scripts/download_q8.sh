#!/bin/bash
# download_q8.sh: Resilient auto-retry download for Qwen3.8-27B-Q8_0.gguf
set -u

DEST_DIR="/data01/llms"
TARGET_FILE="$DEST_DIR/Qwen3.8-27B-Q8_0.gguf"
URL="https://hf-mirror.com/ggml-org/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-Q8_0.gguf"

mkdir -p "$DEST_DIR"
echo "=== Starting Resilient Auto-Retry Download ==="
echo "Target: $TARGET_FILE"
echo "URL   : $URL"

while true; do
    # Auto-detect local proxy
    if curl -s -I --connect-timeout 3 -x http://127.0.0.1:1080 https://hf-mirror.com >/dev/null 2>&1; then
        PROXY="http://127.0.0.1:1080"
    elif curl -s -I --connect-timeout 3 -x http://127.0.0.1:7890 https://hf-mirror.com >/dev/null 2>&1; then
        PROXY="http://127.0.0.1:7890"
    else
        PROXY=""
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading / resuming using proxy: ${PROXY:-none}..."
    if [ -n "$PROXY" ]; then
        curl -C - -L -x "$PROXY" --retry 10 --retry-delay 5 -o "$TARGET_FILE" "$URL"
    else
        curl -C - -L --retry 10 --retry-delay 5 -o "$TARGET_FILE" "$URL"
    fi

    ret=$?
    if [ $ret -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Download completed successfully!"
        break
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Curl exited with code $ret. Retrying in 5 seconds..."
        sleep 5
    fi
done
