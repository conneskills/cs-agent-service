"""
Agent Registry API v2 - With Skills, Tools, RAGs, and full capabilities.

Provides:
- Skills management
- Tools integration (MCP, OpenAPI, Custom)
- RAG configuration
- Smart agent discovery
- Architecture patterns
- PostgreSQL persistence (via DATABASE_URL)
- OTEL tracing to Phoenix (via OTEL_EXPORTER_OTLP_ENDPOINT)
"""

import os
import uuid
import asyncio
import aiohttp
import json
import logging
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Query, Body, Depends
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from storage import StorageBackend, create_storage
from tracing import init_tracing, get_tracer

# Import models
from models.capabilities import (
    CompleteAgentCard,
    SkillDefinition,
    ToolDefinition,
    RAGConfig,
    Capabilities,
    AgentType,
    ToolProvider,
    RAGType,
    ArchitectureDefinition,
    AgentReference,
    SkillMatcher,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agent Registry API",
    version="2.1.0",
    description="Complete agent management with skills, tools, and RAG"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage backend (initialized on startup)
storage: StorageBackend = None  # type: ignore

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")


@app.on_event("startup")
async def startup():
    global storage
    database_url = os.getenv("DATABASE_URL")
    storage = await create_storage(database_url)
    init_tracing()
    logger.info("Agent Registry API started")


@app.on_event("shutdown")
async def shutdown():
    if storage:
        await storage.close()


# ============================================================================
# MODELS (API)
# ============================================================================

class SkillCreate(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = []
    examples: list[str] = []
    metadata: dict = {}


class ToolCreate(BaseModel):
    id: str
    name: str
    description: str
    provider: str = "builtin"
    mcp_server: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    openapi_spec: Optional[str] = None
    openapi_operation: Optional[str] = None
    handler: Optional[str] = None
    parameters: list[dict] = []
    metadata: dict = {}


class RAGCreate(BaseModel):
    id: str
    name: str
    rag_type: str
    vector_store_provider: Optional[str] = None
    vector_store_config: dict = {}
    knowledge_base_id: Optional[str] = None
    knowledge_base_provider: Optional[str] = None
    web_search_provider: Optional[str] = None
    web_search_config: dict = {}
    document_sources: list[str] = []
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_model: str = "text-embedding-ada-002"
    top_k: int = 5
    metadata: dict = {}


class AgentCreate(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    agent_type: str = "general"

    # I/O
    input_modes: list[str] = ["text"]
    output_modes: list[str] = ["text"]

    # Capabilities
    streaming: bool = False
    push_notifications: bool = False
    state_transition: bool = False
    artifacts: bool = True

    # References
    skill_ids: list[str] = []
    tool_ids: list[str] = []
    rag_ids: list[str] = []

    # Metadata
    tags: list[str] = []
    owner: Optional[str] = None
    team: Optional[str] = None
    is_public: bool = False
    metadata: dict = {}


class ArchitectureCreate(BaseModel):
    name: str
    description: str
    pattern: str  # sequential, parallel, coordinator, hub-spoke, mesh
    agents: list[dict]  # [{"agent_id": "xxx", "role": "coordinator"}]
    connections: list[dict] = []
    shared_tools: list[str] = []
    shared_rag: list[str] = []
    timeout: int = 300
    retry_count: int = 3
    metadata: dict = {}


# ============================================================================
# UTILITIES
# ============================================================================

def get_api_key(authorization: Optional[str] = Header(None)) -> str:
    if not MASTER_KEY:
        return "dev"
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if token == MASTER_KEY or token == "dev":
            return token
    raise HTTPException(status_code=401, detail="Invalid API key")


def to_dict(card: CompleteAgentCard) -> dict:
    """Convert CompleteAgentCard to dictionary for storage."""
    return {
        "agent_id": card.agent_id,
        "name": card.name,
        "description": card.description,
        "url": card.url,
        "version": card.version,
        "agent_type": card.agent_type,
        "protocol_version": card.protocol_version,
        "default_input_modes": card.default_input_modes,
        "default_output_modes": card.default_output_modes,
        "capabilities": card.capabilities.model_dump() if card.capabilities else {},
        "skills": [s.model_dump() for s in card.skills],
        "tools": [t.model_dump() for t in card.tools],
        "rag_configs": [r.model_dump() for r in card.rag_configs],
        "owner": card.owner,
        "team": card.team,
        "tags": card.tags,
        "is_public": card.is_public,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
        "metadata": card.metadata,
    }


def from_dict(data: dict) -> CompleteAgentCard:
    """Convert dictionary to CompleteAgentCard."""
    return CompleteAgentCard(
        agent_id=data.get("agent_id"),
        name=data.get("name", ""),
        description=data.get("description", ""),
        url=data.get("url", ""),
        version=data.get("version", "1.0.0"),
        agent_type=data.get("agent_type", "general"),
        protocol_version=data.get("protocol_version", "1.0"),
        default_input_modes=data.get("default_input_modes", ["text"]),
        default_output_modes=data.get("default_output_modes", ["text"]),
        capabilities=Capabilities(**data.get("capabilities", {})) if data.get("capabilities") else Capabilities(),
        skills=[SkillDefinition(**s) for s in data.get("skills", [])],
        tools=[ToolDefinition(**t) for t in data.get("tools", [])],
        rag_configs=[RAGConfig(**r) for r in data.get("rag_configs", [])],
        owner=data.get("owner"),
        team=data.get("team"),
        tags=data.get("tags", []),
        is_public=data.get("is_public", False),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        metadata=data.get("metadata", {}),
    )


# ============================================================================
# HEALTH
# ============================================================================

@app.get("/health")
async def health_check():
    storage_health = await storage.health() if storage else {"type": "uninitialized", "status": "error"}
    tracing_enabled = bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
    return {
        "status": "healthy",
        "service": "agent-registry-api",
        "version": "2.1.0",
        "storage": storage_health,
        "tracing": {
            "enabled": tracing_enabled,
            "endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        },
    }


# ============================================================================
# SKILLS ENDPOINTS
# ============================================================================

@app.get("/skills")
async def list_skills(api_key: str = Depends(get_api_key)):
    """List all skills."""
    skills = await storage.list_all("skills")
    return {"skills": skills, "count": len(skills)}


@app.post("/skills")
async def create_skill(skill: SkillCreate, api_key: str = Depends(get_api_key)):
    """Create a new skill."""
    if await storage.exists("skills", skill.id):
        raise HTTPException(status_code=400, detail="Skill already exists")

    skill_data = skill.model_dump()
    await storage.put("skills", skill.id, skill_data)

    return {"status": "created", "skill": skill_data}


@app.get("/skills/{skill_id}")
async def get_skill(skill_id: str, api_key: str = Depends(get_api_key)):
    """Get skill details."""
    skill = await storage.get("skills", skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@app.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, api_key: str = Depends(get_api_key)):
    """Delete a skill."""
    if not await storage.delete("skills", skill_id):
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "deleted", "skill_id": skill_id}


# ============================================================================
# TOOLS ENDPOINTS
# ============================================================================

@app.get("/tools")
async def list_tools(api_key: str = Depends(get_api_key)):
    """List all tools."""
    tools = await storage.list_all("tools")
    return {"tools": tools, "count": len(tools)}


@app.post("/tools")
async def create_tool(tool: ToolCreate, api_key: str = Depends(get_api_key)):
    """Create a new tool."""
    if await storage.exists("tools", tool.id):
        raise HTTPException(status_code=400, detail="Tool already exists")

    tool_data = tool.model_dump()
    await storage.put("tools", tool.id, tool_data)

    return {"status": "created", "tool": tool_data}


@app.get("/tools/{tool_id}")
async def get_tool(tool_id: str, api_key: str = Depends(get_api_key)):
    """Get tool details."""
    tool = await storage.get("tools", tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@app.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str, api_key: str = Depends(get_api_key)):
    """Delete a tool."""
    if not await storage.delete("tools", tool_id):
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "tool_id": tool_id}


# ============================================================================
# RAG CONFIG ENDPOINTS
# ============================================================================

@app.get("/rag")
async def list_rag_configs(api_key: str = Depends(get_api_key)):
    """List all RAG configurations."""
    configs = await storage.list_all("rag_configs")
    return {"configs": configs, "count": len(configs)}


@app.post("/rag")
async def create_rag_config(rag: RAGCreate, api_key: str = Depends(get_api_key)):
    """Create a new RAG configuration."""
    if await storage.exists("rag_configs", rag.id):
        raise HTTPException(status_code=400, detail="RAG config already exists")

    rag_data = rag.model_dump()
    await storage.put("rag_configs", rag.id, rag_data)

    return {"status": "created", "rag_config": rag_data}


@app.get("/rag/{rag_id}")
async def get_rag_config(rag_id: str, api_key: str = Depends(get_api_key)):
    """Get RAG config details."""
    config = await storage.get("rag_configs", rag_id)
    if not config:
        raise HTTPException(status_code=404, detail="RAG config not found")
    return config


@app.delete("/rag/{rag_id}")
async def delete_rag_config(rag_id: str, api_key: str = Depends(get_api_key)):
    """Delete a RAG config."""
    if not await storage.delete("rag_configs", rag_id):
        raise HTTPException(status_code=404, detail="RAG config not found")
    return {"status": "deleted", "rag_id": rag_id}


# ============================================================================
# AGENTS ENDPOINTS
# ============================================================================

@app.get("/agents")
async def list_agents(
    skill: Optional[str] = Query(None),
    tool: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    api_key: str = Depends(get_api_key)
):
    """List agents with filters."""
    agents = await storage.list_all("agents")

    # Apply filters
    if skill:
        agents = [a for a in agents if any(
            skill.lower() in s.get("name", "").lower() or
            skill.lower() in s.get("description", "").lower()
            for s in a.get("skills", [])
        )]

    if tool:
        agents = [a for a in agents if any(
            tool.lower() == t.get("id", "").lower()
            for t in a.get("tools", [])
        )]

    if tag:
        agents = [a for a in agents if tag.lower() in [t.lower() for t in a.get("tags", [])]]

    if agent_type:
        agents = [a for a in agents if a.get("agent_type", "").lower() == agent_type.lower()]

    return {"agents": agents, "count": len(agents)}


@app.post("/agents")
async def create_agent(agent: AgentCreate, api_key: str = Depends(get_api_key)):
    """Create a new agent with full capabilities."""
    agent_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Resolve referenced skills/tools/rag_configs from storage
    skills_list = []
    for sid in agent.skill_ids:
        s = await storage.get("skills", sid)
        if s:
            skills_list.append(SkillDefinition(**s))

    tools_list = []
    for tid in agent.tool_ids:
        t = await storage.get("tools", tid)
        if t:
            tools_list.append(ToolDefinition(**t))

    rag_list = []
    for rid in agent.rag_ids:
        r = await storage.get("rag_configs", rid)
        if r:
            rag_list.append(RAGConfig(**r))

    # Build complete agent card
    card = CompleteAgentCard(
        agent_id=agent_id,
        name=agent.name,
        description=agent.description,
        url=agent.url,
        version=agent.version,
        agent_type=agent.agent_type,
        default_input_modes=agent.input_modes,
        default_output_modes=agent.output_modes,
        capabilities=Capabilities(
            streaming=agent.streaming,
            push_notifications=agent.push_notifications,
            state_transition=agent.state_transition,
            artifacts=agent.artifacts,
        ),
        skills=skills_list,
        tools=tools_list,
        rag_configs=rag_list,
        owner=agent.owner,
        team=agent.team,
        tags=agent.tags,
        is_public=agent.is_public,
        created_at=now,
        updated_at=now,
        metadata=agent.metadata,
    )

    await storage.put("agents", agent_id, to_dict(card))

    # Register with LiteLLM if public
    if agent.is_public and MASTER_KEY:
        await register_with_litellm(card)

    return {"status": "created", "agent_id": agent_id, "agent": to_dict(card)}


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str, api_key: str = Depends(get_api_key)):
    """Get agent details with all capabilities."""
    agent = await storage.get("agents", agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    agent: AgentCreate,
    api_key: str = Depends(get_api_key)
):
    """Update an agent."""
    existing_data = await storage.get("agents", agent_id)
    if not existing_data:
        raise HTTPException(status_code=404, detail="Agent not found")

    existing = from_dict(existing_data)
    now = datetime.utcnow()

    # Resolve referenced skills/tools/rag_configs from storage
    skills_list = []
    for sid in agent.skill_ids:
        s = await storage.get("skills", sid)
        if s:
            skills_list.append(SkillDefinition(**s))

    tools_list = []
    for tid in agent.tool_ids:
        t = await storage.get("tools", tid)
        if t:
            tools_list.append(ToolDefinition(**t))

    rag_list = []
    for rid in agent.rag_ids:
        r = await storage.get("rag_configs", rid)
        if r:
            rag_list.append(RAGConfig(**r))

    # Update fields
    existing.name = agent.name
    existing.description = agent.description
    existing.url = agent.url
    existing.version = agent.version
    existing.agent_type = agent.agent_type
    existing.default_input_modes = agent.input_modes
    existing.default_output_modes = agent.output_modes
    existing.capabilities = Capabilities(
        streaming=agent.streaming,
        push_notifications=agent.push_notifications,
        state_transition=agent.state_transition,
        artifacts=agent.artifacts,
    )
    existing.skills = skills_list
    existing.tools = tools_list
    existing.rag_configs = rag_list
    existing.tags = agent.tags
    existing.owner = agent.owner
    existing.team = agent.team
    existing.is_public = agent.is_public
    existing.updated_at = now
    existing.metadata = agent.metadata

    await storage.put("agents", agent_id, to_dict(existing))

    return {"status": "updated", "agent_id": agent_id}


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, api_key: str = Depends(get_api_key)):
    """Delete an agent."""
    if not await storage.delete("agents", agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "agent_id": agent_id}


# ============================================================================
# DISCOVERY ENDPOINTS
# ============================================================================

@app.get("/discover")
async def discover_agent(
    query: str = Query(..., description="Natural language query"),
    api_key: str = Depends(get_api_key)
):
    """Smart agent discovery using skill matching."""
    all_agents = await storage.list_all("agents")
    agents = [from_dict(a) for a in all_agents if a.get("is_discoverable", True)]

    # Use skill matcher
    best_agent = SkillMatcher.find_best_agent(query, agents)

    if best_agent:
        return {
            "query": query,
            "recommended_agent": to_dict(best_agent),
            "matching_skills": [
                {"id": s.id, "name": s.name, "description": s.description}
                for s in best_agent.skills
            ],
        }

    return {"query": query, "message": "No matching agent found"}


# ============================================================================
# ARCHITECTURES ENDPOINTS
# ============================================================================

@app.get("/architectures")
async def list_architectures(api_key: str = Depends(get_api_key)):
    """List all architectures."""
    archs = await storage.list_all("architectures")
    return {"architectures": archs, "count": len(archs)}


@app.post("/architectures")
async def create_architecture(
    arch: ArchitectureCreate,
    api_key: str = Depends(get_api_key)
):
    """Create a new architecture."""
    arch_id = str(uuid.uuid4())

    arch_data = {
        "architecture_id": arch_id,
        "name": arch.name,
        "description": arch.description,
        "pattern": arch.pattern,
        "agents": arch.agents,
        "connections": arch.connections,
        "shared_tools": arch.shared_tools,
        "shared_rag": arch.shared_rag,
        "timeout": arch.timeout,
        "retry_count": arch.retry_count,
        "metadata": arch.metadata,
    }

    await storage.put("architectures", arch_id, arch_data)

    return {"status": "created", "architecture_id": arch_id, "architecture": arch_data}


@app.get("/architectures/{arch_id}")
async def get_architecture(arch_id: str, api_key: str = Depends(get_api_key)):
    """Get architecture details."""
    arch = await storage.get("architectures", arch_id)
    if not arch:
        raise HTTPException(status_code=404, detail="Architecture not found")
    return arch


@app.post("/architectures/{arch_id}/invoke")
async def invoke_architecture_endpoint(
    arch_id: str,
    query: str = Body(..., embed=True),
    api_key: str = Depends(get_api_key)
):
    """Execute an architecture."""
    arch = await storage.get("architectures", arch_id)
    if not arch:
        raise HTTPException(status_code=404, detail="Architecture not found")

    pattern = arch["pattern"]
    tracer = get_tracer()

    with tracer.start_as_current_span(
        "a2a.invoke_architecture",
        attributes={
            "architecture.name": arch["name"],
            "architecture.pattern": pattern,
            "architecture.id": arch_id,
        },
    ) as arch_span:
        results = {}

        if pattern == "sequential":
            context = query
            for agent_ref in arch["agents"]:
                agent = await storage.get("agents", agent_ref.get("agent_id", ""))
                if agent:
                    result = await invoke_agent(agent["url"], context)
                    results[agent["name"]] = result
                    if result.get("status") == "success":
                        context = result.get("result", "")

        elif pattern == "parallel":
            tasks = []
            agent_names = []
            for agent_ref in arch["agents"]:
                agent = await storage.get("agents", agent_ref.get("agent_id", ""))
                if agent:
                    tasks.append(invoke_agent(agent["url"], query))
                    agent_names.append(agent["name"])

            if tasks:
                parallel_results = await asyncio.gather(*tasks)
                for name, result in zip(agent_names, parallel_results):
                    results[name] = result

        arch_span.set_attribute("architecture.agent_count", len(results))

    return {"architecture": arch["name"], "pattern": pattern, "results": results}


# ============================================================================
# UTILITIES
# ============================================================================

async def invoke_agent(agent_url: str, query: str) -> dict:
    """Invoke an agent via A2A with OTEL tracing."""
    if not agent_url.endswith("/"):
        agent_url += "/"

    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tasks/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": query}]
            }
        }
    }

    tracer = get_tracer()

    with tracer.start_as_current_span(
        "a2a.invoke_agent",
        attributes={
            "agent.url": agent_url,
            "a2a.method": "tasks/send",
        },
    ) as span:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    agent_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    span.set_attribute("http.status_code", resp.status)
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("result", {})
                        artifacts = result.get("artifacts", [])
                        if artifacts:
                            parts = artifacts[0].get("parts", [])
                            texts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
                            return {"status": "success", "result": "\n".join(texts)}
                        return {"status": "success", "result": str(result)}
                    return {"status": "error", "error": f"HTTP {resp.status}"}
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            return {"status": "error", "error": str(e)}


async def register_with_litellm(agent_card: CompleteAgentCard):
    """Register agent with LiteLLM."""
    if not MASTER_KEY:
        return

    payload = {
        "agent_name": agent_card.name.lower().replace(" ", "-"),
        "agent_card_params": {
            "name": agent_card.name,
            "description": agent_card.description,
            "url": agent_card.url,
            "version": agent_card.version,
            "defaultInputModes": agent_card.default_input_modes,
            "defaultOutputModes": agent_card.default_output_modes,
            "capabilities": agent_card.capabilities.model_dump() if agent_card.capabilities else {},
            "skills": [{"id": s.id, "name": s.name, "description": s.description} for s in agent_card.skills],
        }
    }

    headers = {"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{LITELLM_URL}/v1/agents", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    agent_id = data.get("agent_id")
                    if agent_id and agent_card.is_public:
                        await session.post(f"{LITELLM_URL}/v1/agents/{agent_id}/make_public", headers=headers)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9500)
