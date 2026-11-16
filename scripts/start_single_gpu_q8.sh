#!/bin/bash
exec bash "$(dirname "$0")/models/start_single_gpu_q8.sh" "$@"
