# cs-agent-service Memory

**Last Updated:** 2026-02-21

## Overview

Dynamic agent runtime service for ConneSkills platform. Single Docker image, multiple containers with different configurations.

## Quick Reference

| Aspect | Value |
|--------|-------|
| **Language** | Python 3.11 |
| **Framework** | A2A SDK + Starlette |
| **Deployment** | Google Cloud Run |
| **Port** | 9100 |
| **Protocol** | A2A (JSON-RPC 2.0) |

## Architecture

```
┌─────────────────────────────────────────────┐
│                 Cloud Run                    │
├─────────────────────────────────────────────┤
│  src/__main__.py  →  A2A Server (uvicorn)   │
│         ↓                                    │
│  ReusableAgentExecutor (A2A adapter)        │
│         ↓                                    │
│  AgentService (orchestrator)                │
│         ↓                                    │
│  BaseAgent (LLM wrapper)                    │
│         ↓                                    │
│  LiteLLM Proxy → LLM Provider               │
└─────────────────────────────────────────────┘
```

## Execution Types

| Type | Behavior |
|------|----------|
| `single` | One role, one LLM call |
| `sequential` | Chain of agents, output passes to next |
| `parallel` | Multiple agents run concurrently |
| `coordinator` | Coordinator dispatches to workers |
| `hub-spoke` | Hub routes to spokes |

## Key Files

- `src/agent.py` - All classes (BaseAgent, AgentService, ReusableAgentExecutor)
- `src/__main__.py` - A2A server entry point
- `prompts/{role}.txt` - Fallback prompt templates
- `docs/ADR-001-arquitectura-agentes.md` - Architecture decisions

## External Dependencies

| Service | Purpose |
|---------|---------|
| LiteLLM | LLM proxy + prompt management |
| Registry API | Agent configuration storage |
| Cloud Run | Serverless hosting |

## Environment Variables

```bash
LITELLM_URL=https://litellm.conneskills.com
LITELLM_API_KEY=<key>
AGENT_ID=<uuid>              # Dynamic mode
REGISTRY_URL=http://registry-api:9500
DEFAULT_MODEL=gpt-4o-mini
```

## Known Issues

1. **No tests** - Zero automated test coverage
2. **No requirements.txt** - Dependencies only in Dockerfile
3. **Sync HTTP in __init__** - Blocks container startup
4. **InMemoryTaskStore** - Tasks lost on restart

## ADR Reference

See `docs/ADR-001-arquitectura-agentes.md` for:
- Google ADK migration plan
- Phoenix integration
- MCP tool strategy
- Multi-agent patterns

---

*Memory for cs-agent-service - 2026-02-21*
