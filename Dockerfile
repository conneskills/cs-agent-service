FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
# - openai: OpenAI SDK, calls LiteLLM as proxy (no provider keys needed)
# - a2a-sdk[http-server]: A2A protocol server (FastAPI/Starlette)
# - httpx: sync HTTP client for registry/LiteLLM calls at startup
RUN pip install --no-cache-dir \
    openai \
    "a2a-sdk[http-server]>=0.3.0" \
    httpx

COPY src/ /app/src/
COPY prompts/ /app/prompts/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# ── LiteLLM proxy (manages all provider keys) ──
# ENV LITELLM_URL=https://litellm.conneskills.com
# ENV LITELLM_API_KEY=sk-...
# ENV DEFAULT_MODEL=gpt-4o-mini

# ── Dynamic mode ──
# ENV AGENT_ID=
# ENV REGISTRY_URL=http://registry-api:9500

ENV AGENT_PORT=9100

EXPOSE 9100

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9100/ || exit 1

CMD ["python", "-m", "src"]
