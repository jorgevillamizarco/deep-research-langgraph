#!/bin/bash
# Deploy script for deep-research-agent Docker container.
# Reads API key from ~/.hermes/.env (outside Hermes redaction scope).
set -e

source ~/.hermes/.env

docker stop deep-research-agent 2>/dev/null || true
docker rm deep-research-agent 2>/dev/null || true

docker run -d \
  --name deep-research-agent \
  --network research-net \
  -p 8100:8100 \
  -e SEARXNG_URL=http://deep-research-searxng:8080 \
  -e "WORKER_API_KEY=$DEEPSEEK_API_KEY" \
  -e WORKER_API_BASE=https://api.deepseek.com \
  -e WORKER_MODEL=deepseek-v4-flash \
  -e CRITIC_MODEL=deepseek-v4-pro \
  -e MAX_SEARCH_ITERATIONS=3 \
  deep-research-agent

sleep 2
echo "Health: $(curl -s http://localhost:8100/health)"
echo "Key check: $(docker exec deep-research-agent sh -c 'echo $WORKER_API_KEY | cut -c1-6')"
