#!/bin/bash
# Simple deployment script for API server with optimal settings

set -e

# Determine if debug mode and set environment
if [[ "$*" == *"--debug"* ]]; then
    export DEBUG_MODE=1
    echo "🧪 Starting API server in DEBUG mode"
else
    echo "🚀 Starting API server in PRODUCTION mode"
fi

# Check for --no-generation flag (only effective with --debug)
if [[ "$*" == *"--no-generation"* ]]; then
    export NO_GENERATION=1
    echo "🚫 Card generation DISABLED for spin wins"
fi

# Run with gunicorn + uvloop + httptools for maximum performance (5 workers)
# --preload ensures logging is configured before workers fork
# Access/error logs stay on stdout to align with our centralized logging
exec gunicorn api.server:app \
    --workers 5 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --preload \
    --log-level info \
    --access-logfile - \
    --error-logfile -
