#!/bin/bash
exec bash "$(dirname "$0")/models/start_vllm.sh" "$@"
