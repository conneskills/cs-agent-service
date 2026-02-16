# cs-agent-service

Dynamic Agent Runtime for AI agents with Registry API, A2A protocol, and Cloud Run scale-to-zero deployment.

## Architecture

```
POST /agents {name, prompt, tools}  →  Registry API saves config
POST /agents/{id}/deploy            →  Registry API calls ai-platform-api
ai-platform-api deploys Cloud Run   →  Generic image + AGENT_ID env var
Container starts → GET /agents/{id} →  Loads prompt/tools from Registry API
Agent live + auto-registered        →  Scale to zero when idle
```

## Components

| Component | Port | Description |
|-----------|------|-------------|
| **Registry API** | 9500 | Agent CRUD, skills, tools, RAG configs, deploy orchestration |
| **Reusable Agent** | 9100 | Generic runtime that loads config from Registry API |
| **DevOps Agent** | 9100 | Example custom agent for infrastructure monitoring |
| **Discovery Agent** | 9501 | Finds and invokes agents via LiteLLM Agent Hub |

## Quick Start

```bash
# Start all services
docker compose up -d

# Create an agent
curl -X POST http://localhost:9500/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Researcher",
    "description": "Research and gather information",
    "url": "",
    "system_prompt": "You are a research agent...",
    "allowed_tools": ["Bash", "Read", "Grep", "Glob", "WebSearch"],
    "max_turns": 10,
    "tags": ["research"],
    "is_public": true
  }'

# Deploy to Cloud Run
curl -X POST http://localhost:9500/agents/{agent_id}/deploy
```

## Multi-Agent Patterns

- **Sequential Pipeline**: Researcher → Analyzer → Writer
- **Parallel Execution**: Multiple agents run simultaneously
- **Coordinator**: Dynamic routing to worker agents
- **Hub-and-Spoke**: Central hub with specialized spokes
- **Discovery**: Natural language agent discovery and invocation

See [multi-agent-architectures.md](multi-agent-architectures.md) for details.

## Development

```bash
# Registry API
cd registry_api && pip install -r requirements.txt && uvicorn main:app --port 9500

# Reusable Agent (legacy mode)
cd reusable && AGENT_ROLE=researcher python -m src

# Reusable Agent (dynamic mode)
cd reusable && AGENT_ID=abc-123 REGISTRY_URL=http://localhost:9500 python -m src
```
