FROM python:3.11-slim

WORKDIR /app

# System deps: curl for health checks, git for Claude Agent SDK tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python deps
# - claude-agent-sdk: bundles Claude CLI, provides query() + ClaudeAgentOptions
# - a2a-sdk[http-server]: A2A protocol server (FastAPI/Starlette)
# - httpx: sync HTTP client for registry/LiteLLM calls at startup
RUN pip install --no-cache-dir \
    "claude-agent-sdk>=0.1.30" \
    "a2a-sdk[http-server]>=0.3.0" \
    httpx

# Copy application code
COPY src/ /app/src/
COPY prompts/ /app/prompts/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# ── LiteLLM as provider gateway ──
# Claude Agent SDK routes through LiteLLM (manages provider keys)
# ENV ANTHROPIC_BASE_URL=https://litellm.conneskills.com
# ENV ANTHROPIC_API_KEY=sk-...  (LiteLLM virtual key)

# ── LiteLLM prompt management ──
# ENV LITELLM_URL=https://litellm.conneskills.com
# ENV LITELLM_API_KEY=sk-...

# ── Dynamic mode (set AGENT_ID to load config from registry) ──
# ENV AGENT_ID=
# ENV REGISTRY_URL=http://registry-api:9500

# ── Agent defaults ──
ENV AGENT_PORT=9100
ENV PERMISSION_MODE=bypassPermissions

EXPOSE 9100

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9100/ || exit 1

CMD ["python", "-m", "src"]
