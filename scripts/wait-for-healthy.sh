#!/usr/bin/env bash
# FlowForge — Wait for service healthy script
set -euo pipefail

SERVICE="${1:-api}"
TIMEOUT="${2:-60}"
URL="${3:-http://localhost:8000/health}"

echo "Waiting for ${SERVICE} at ${URL} to report healthy (timeout ${TIMEOUT}s)..."

START_TIME=$(date +%s)
while true; do
    if curl -sf "${URL}" > /dev/null 2>&1; then
        echo "${SERVICE} is healthy!"
        exit 0
    fi
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    if [ "${ELAPSED}" -ge "${TIMEOUT}" ]; then
        echo "Timed out waiting for ${SERVICE} to become healthy."
        exit 1
    fi
    sleep 2
done
