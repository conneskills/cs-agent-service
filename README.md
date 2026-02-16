# cs-agent-service

Dynamic Agent Runtime — one Docker image, N containers, each configured at startup via Registry API.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Registry API (:9500)                  │
│  POST /agents      → Create agent config                │
│  POST /prompts     → Create reusable prompts            │
│  GET  /agents/{id} → Container reads config at startup  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Container A   │  │ Container B   │  │ Container C   │ │
│  │ AGENT_ID=aaa  │  │ AGENT_ID=bbb  │  │ AGENT_ID=ccc  │ │
│  │ single agent  │  │ sequential    │  │ parallel      │ │
│  │               │  │ pipeline      │  │ + aggregator  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         Same Docker image: agent-service:latest         │
└─────────────────────────────────────────────────────────┘
```

**Key concept:** All containers use the same image. Behavior is determined by `AGENT_ID` → Registry API returns `runtime_config` with execution type, roles, prompts, and tools.

## Execution Types

| Type | Description |
|------|-------------|
| `single` | One role, one agent |
| `sequential` | Pipeline: output of role N → input of role N+1 |
| `parallel` | All roles run concurrently, optional aggregator |
| `coordinator` | Coordinator decides which workers to invoke |
| `hub-spoke` | Hub routes requests to specialized spokes |

## Components

| Component | Port | Description |
|-----------|------|-------------|
| **Registry API** | 9500 | Agent/prompt CRUD, config storage |
| **Agent Service** | 9100 | Generic runtime, loads config from Registry via AGENT_ID |

## Quick Start

```bash
# 1. Start Registry API
cd registry_api && pip install aiohttp httpx && uvicorn main:app --port 9500

# 2. Create a prompt
curl -X POST http://localhost:9500/prompts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "researcher",
    "template": "You are a research agent specialized in {domain}.",
    "version": "1.0"
  }'

# 3. Create an agent with runtime config
curl -X POST http://localhost:9500/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Research Pipeline",
    "description": "Sequential researcher → analyzer",
    "url": "",
    "execution_type": "sequential",
    "roles": [
      {"name": "researcher", "prompt_ref": "researcher", "tools": ["Bash","Read","WebSearch"]},
      {"name": "analyzer", "prompt_inline": "You analyze research results.", "tools": ["Bash","Read"]}
    ]
  }'

# 4. Run agent container (dynamic mode)
cd reusable && AGENT_ID=<id> REGISTRY_URL=http://localhost:9500 python -m src

# 5. Or legacy mode (no registry)
cd reusable && AGENT_ROLE=researcher SYSTEM_PROMPT="You are a researcher." python -m src
```

## Environment Variables

### Agent Container

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_ID` | _(none)_ | Registry agent ID — enables dynamic mode |
| `REGISTRY_URL` | `http://registry-api:9500` | Registry API endpoint |
| `AGENT_PORT` | `9100` | A2A server port |
| `AGENT_ROLE` | `general` | Legacy: role name |
| `SYSTEM_PROMPT` | _(auto)_ | Legacy: inline prompt |
| `ALLOWED_TOOLS` | `Bash,Read,Grep,Glob` | Legacy: comma-separated tools |
| `PERMISSION_MODE` | `bypassPermissions` | Claude Agent SDK permission mode |
| `WORKDIR` | `/app` | Working directory for agent |

### Registry API

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(none)_ | Phoenix/OTLP endpoint (optional) |

## Tracing (Optional)

If `OTEL_EXPORTER_OTLP_ENDPOINT` is set and `opentelemetry` packages are installed, spans are sent to Phoenix/OTLP. Otherwise, tracing degrades gracefully to no-op — no crash, no dependency required.

## Project Structure

```
cs-agent-service/
├── models/
│   └── capabilities.py       # Data models: RuntimeConfig, ExecutionType, AgentCard
├── registry_api/
│   ├── Dockerfile             # Registry API image
│   ├── main.py                # FastAPI: agents, prompts, skills, tools CRUD
│   ├── storage.py             # JSON file storage
│   └── tracing.py             # Optional OpenTelemetry (graceful no-op)
└── reusable/
    ├── docker/
    │   └── Dockerfile         # Agent service image
    ├── prompts/               # Default prompt files (fallback)
    └── src/
        ├── __main__.py        # A2A server entry point
        └── agent.py           # BaseAgent + AgentService (all 5 patterns)
```
