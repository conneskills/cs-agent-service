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

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your LiteLLM credentials and preferred model
```

### 2. Build and run with Docker

```bash
# Build the image
docker build -t cs-agent-service .

# Run (legacy mode — no registry needed)
docker run -d \
  --name cs-agent-service \
  --env-file .env \
  -p 9100:9100 \
  cs-agent-service

# Run (dynamic mode — reads config from Registry API)
docker run -d \
  --name cs-agent-service \
  --env-file .env \
  -e AGENT_ID=<uuid-from-registry> \
  -e REGISTRY_URL=http://registry-api:9500 \
  -p 9100:9100 \
  cs-agent-service
```

### 3. Run locally (without Docker)

```bash
pip install openai "a2a-sdk[http-server]>=0.3.0" httpx uvicorn

# Legacy mode
LITELLM_URL=https://litellm.conneskills.com \
LITELLM_API_KEY=sk-... \
DEFAULT_MODEL=cs-claude-sonnet-4 \
python -m src
```

### 4. Verify it's running

```bash
curl http://localhost:9100/.well-known/agent.json
```

## A2A API Reference

The service exposes the [A2A (Agent-to-Agent) protocol](https://github.com/google/A2A) over JSON-RPC 2.0.

### Agent Card

```bash
# GET /.well-known/agent.json — Returns agent capabilities and metadata
curl http://localhost:9100/.well-known/agent.json
```

```json
{
  "name": "reusable-agent",
  "description": "A reusable agent",
  "protocolVersion": "0.3.0",
  "capabilities": { "streaming": false },
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    {
      "id": "reusable-agent-skill",
      "name": "reusable-agent",
      "description": "A reusable agent",
      "tags": ["agent"]
    }
  ],
  "url": "http://0.0.0.0:9100/",
  "version": "1.0.0"
}
```

### Send a message

```bash
# POST / — method: message/send
curl -X POST http://localhost:9100/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [
          {"kind": "text", "text": "Hello, what can you do?"}
        ],
        "messageId": "msg-001"
      }
    }
  }'
```

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "id": "task-uuid",
    "kind": "task",
    "status": { "state": "completed" },
    "artifacts": [
      {
        "artifactId": "artifact-uuid",
        "name": "agent_result",
        "parts": [
          { "kind": "text", "text": "Agent response here" }
        ]
      }
    ]
  }
}
```

### Get a task

```bash
# POST / — method: tasks/get
curl -X POST http://localhost:9100/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "tasks/get",
    "params": {
      "id": "<task-id-from-message-send>"
    }
  }'
```

### Error responses

| Code | Message | Description |
|------|---------|-------------|
| `-32601` | Method not found | Invalid JSON-RPC method |
| `-32001` | Task not found | Task ID does not exist |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LITELLM_URL` | `https://litellm.conneskills.com` | LiteLLM proxy URL (OpenAI-compatible) |
| `LITELLM_API_KEY` | _(none)_ | LiteLLM API key |
| `DEFAULT_MODEL` | `gpt-4o-mini` | Model to use via LiteLLM proxy |
| `AGENT_PORT` | `9100` | A2A server port |
| `AGENT_ID` | _(none)_ | Registry agent ID — enables dynamic mode |
| `REGISTRY_URL` | `http://registry-api:9500` | Registry API endpoint |
| `AGENT_NAME` | `reusable-agent` | Agent name (legacy mode) |
| `AGENT_DESCRIPTION` | `A reusable agent` | Agent description (legacy mode) |
| `AGENT_ROLE` | `general` | Role name (legacy mode) |
| `SYSTEM_PROMPT` | _(auto)_ | Inline system prompt (legacy mode) |

## Roadmap

- [ ] **Auto-Registration** — On startup, agent PATCHes its Cloud Run URL to Registry API and registers with LiteLLM `/v1/agents` endpoint. Public agents discoverable via `/v1/agents/{id}/make_public`. Works in both Cloud Run (`K_SERVICE` detection) and local Docker.

## Project Structure

```
cs-agent-service/
├── Dockerfile          # Docker image
├── .env.example        # Environment variables reference
├── src/
│   ├── __init__.py
│   ├── __main__.py     # A2A server entry point (uvicorn + Starlette)
│   └── agent.py        # BaseAgent + AgentService (all 5 execution patterns)
└── prompts/            # Default prompt files (fallback)
```
