# cs-agent-service

Dynamic Agent Runtime — one Docker image, N containers, each configured at startup via Registry API.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│          cs-agent-registry-api (:9500)                  │
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

## Related Repos

- **[cs-agent-registry-api](https://github.com/conneskills/cs-agent-registry-api)** — Agent/prompt/skill CRUD and config storage

## Execution Types

| Type | Description |
|------|-------------|
| `single` | One role, one agent |
| `sequential` | Pipeline: output of role N → input of role N+1 |
| `parallel` | All roles run concurrently, optional aggregator |
| `coordinator` | Coordinator decides which workers to invoke |
| `hub-spoke` | Hub routes requests to specialized spokes |

## Quick Start

```bash
# 1. Start Registry API (separate repo)
# See: https://github.com/conneskills/cs-agent-registry-api

# 2. Run agent container (dynamic mode)
AGENT_ID=<id> REGISTRY_URL=http://localhost:9500 python -m src

# 3. Or legacy mode (no registry needed)
AGENT_ROLE=researcher SYSTEM_PROMPT="You are a researcher." python -m src
```

## Environment Variables

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

## Project Structure

```
cs-agent-service/
└── reusable/
    ├── docker/
    │   └── Dockerfile         # Agent service image
    ├── prompts/               # Default prompt files (fallback)
    └── src/
        ├── __main__.py        # A2A server entry point
        └── agent.py           # BaseAgent + AgentService (all 5 patterns)
```
