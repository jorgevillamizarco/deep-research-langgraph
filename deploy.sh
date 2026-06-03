#!/usr/bin/env bash
# Deploy the deep research stack: agent + SearXNG.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

AGENT_CONTAINER=deep-research-agent
AGENT_IMAGE=deep-research-agent
ENV_FILE="$SCRIPT_DIR/.docker.env"
SEARXNG_PORT=8080
AGENT_PORT=8100

# Colors
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${G}[OK]${NC} $1"; }
warn()  { echo -e "${Y}[..]${NC} $1"; }
error() { echo -e "${R}[!!]${NC} $1"; }

searxng_alive() {
  curl -sf --max-time 3 "http://localhost:${SEARXNG_PORT}/search?q=health&format=json" > /dev/null 2>&1
}

do_start() {
  echo "=== Deploying Deep Research Stack ==="

  # Build image if needed
  if ! docker image inspect "$AGENT_IMAGE" > /dev/null 2>&1; then
    info "Building agent image..."
    docker build -t "$AGENT_IMAGE" .
  fi

  # Check env file
  if [ ! -f "$ENV_FILE" ]; then
    warn "Missing $ENV_FILE - create from .docker.env.template"
  fi

  # Check SearXNG
  local net_mode searxng_url
  if searxng_alive; then
    info "Using existing SearXNG on localhost:${SEARXNG_PORT}"
    net_mode="host"
    searxng_url="http://localhost:${SEARXNG_PORT}"
  else
    info "Starting new SearXNG container..."
    docker network create research-net 2>/dev/null || true
    docker rm -f deep-research-searxng 2>/dev/null || true
    docker run -d \
      --name deep-research-searxng \
      --network research-net \
      --restart unless-stopped \
      -v "$SCRIPT_DIR/searxng-config:/etc/searxng:rw" \
      searxng/searxng:2026.6.2-e964708c0

    for i in $(seq 1 15); do
      docker run --rm --network research-net alpine sh -c \
        "wget -q -O- http://deep-research-searxng:8080/search?q=health&format=json" > /dev/null 2>&1 && break
      sleep 2
    done
    info "SearXNG ready"
    net_mode="bridge"
    searxng_url="http://deep-research-searxng:8080"
  fi

  # Remove old agent
  docker rm -f "$AGENT_CONTAINER" 2>/dev/null || true

  # Build args
  local net_args=""
  if [ "$net_mode" = "host" ]; then
    net_args="--network host"
  else
    net_args="--network research-net -p ${AGENT_PORT}:${AGENT_PORT}"
  fi

  # Start agent
  #shellcheck disable=SC2086
  docker run -d \
    --name "$AGENT_CONTAINER" \
    $net_args \
    --restart unless-stopped \
    ${ENV_FILE:+--env-file "$ENV_FILE"} \
    -e "SEARXNG_URL=$searxng_url" \
    -e "RESEARCH_OUTPUT_DIR=/data" \
    -e "CHECKPOINT_DB_PATH=/app/checkpoints/checkpoints.db" \
    -v ~/research:/data \
    -v research_checkpoints:/app/checkpoints \
    "$AGENT_IMAGE"

  # Wait for agent
  for i in $(seq 1 10); do
    if curl -sf "http://localhost:${AGENT_PORT}/health" > /dev/null 2>&1; then
      info "Agent ready on http://localhost:${AGENT_PORT}/mcp"
      echo ""
      info "Stack deployed"
      echo "  MCP:    http://localhost:${AGENT_PORT}/mcp"
      echo "  Test:   curl -s http://localhost:${AGENT_PORT}/health"
      echo "  Hermes: hermes mcp add research --url http://localhost:${AGENT_PORT}/mcp"
      return 0
    fi
    sleep 2
  done

  error "Agent failed to start"
  docker logs "$AGENT_CONTAINER" --tail 20
  return 1
}

do_stop() {
  docker stop "$AGENT_CONTAINER" 2>/dev/null || true
  info "Agent stopped"
}

do_restart() { do_stop; sleep 1; do_start; }

do_status() {
  echo ""
  echo "  Agent:   $(docker ps --filter name=$AGENT_CONTAINER --format '{{.Status}}' 2>/dev/null || echo 'not running')"
  if searxng_alive; then
    echo "  SearXNG: running on port ${SEARXNG_PORT} (external)"
  else
    echo "  SearXNG: $(docker ps --filter name=deep-research-searxng --format '{{.Status}}' 2>/dev/null || echo 'not running')"
  fi
  echo ""
  if curl -sf "http://localhost:${AGENT_PORT}/health" > /dev/null 2>&1; then
    info "Agent healthy"
  else
    warn "Agent not reachable"
  fi
  echo ""
}

do_logs() {
  docker logs -f "$AGENT_CONTAINER" 2>/dev/null || error "Agent not running"
}

do_rm() {
  do_stop
  docker rm "$AGENT_CONTAINER" 2>/dev/null || true
  docker rm deep-research-searxng 2>/dev/null || true
  docker network rm research-net 2>/dev/null || true
  info "Stack removed"
}

case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_restart ;;
  status)  do_status ;;
  logs)    do_logs ;;
  rm)      do_rm ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|rm}"
    exit 1
    ;;
esac
