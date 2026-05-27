# Deep Research Agent — Docker image
#
# Build:
#   docker build -t deep-research-agent .
#
# Run (MCP SSE server):
#   docker run -p 8100:8100 \
#     -e WORKER_API_KEY=sk-... \
#     -e WORKER_API_BASE=https://api.deepseek.com \
#     -e WORKER_MODEL=deepseek-v4-flash \
#     -e CRITIC_API_KEY=sk-... \
#     -e CRITIC_API_BASE=https://api.deepseek.com \
#     -e CRITIC_MODEL=deepseek-v4-flash \
#     -e MAX_SEARCH_ITERATIONS=3 \
#     -e RESEARCH_OUTPUT_DIR=/data \
#     -v research_data:/data \
#     deep-research-agent
#
# Or via docker-compose (includes SearXNG): docker compose up -d

FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir build && \
    python -m build --wheel --no-isolation 2>/dev/null || \
    pip install --no-cache-dir --prefix=/install . 2>/dev/null || true

# ─────────────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# Install runtime deps (no build tools needed)
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    langgraph>=0.4.0 \
    langchain-community>=0.3.0 \
    langchain-openai>=0.2.0 \
    pydantic>=2.0.0 \
    duckduckgo_search>=8.0.0 \
    httpx>=0.28.0 \
    mcp>=1.0.0 \
    uvicorn>=0.48.0 \
    && rm -rf /root/.cache

# Copy application code
COPY app/ /app/app/
COPY tests/ /app/tests/
COPY pyproject.toml /app/

# Expose MCP SSE port
EXPOSE 8100

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8100/health', timeout=30);" || exit 1

# Default: run MCP SSE server
ENTRYPOINT ["python", "-m", "app.mcp_server", "--transport", "sse", "--port", "8100"]
