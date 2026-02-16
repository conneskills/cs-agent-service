# Multi-Agent A2A Demo - 5 Architectures

Este documento muestra 5 arquitecturas de sistemas multiagente usando el protocolo A2A con LiteLLM.

---

## 1. Sequential Pipeline (Pipeline lineal)

**Patrón**: Researcher → Analyzer → Writer  
**Uso**: Tasks que requieren pasos ordered (research → analysis → output)

```
┌────────────┐    ┌────────────┐    ┌────────────┐
│ Researcher │───▶│  Analyzer  │───▶│   Writer   │
└────────────┘    └────────────┘    └────────────┘
```

### Implementación

```python
# sequential_pipeline.py
import asyncio
from a2a.client import A2AClient

class SequentialPipeline:
    def __init__(self, agents: dict[str, str]):
        self.clients = {
            name: A2AClient(agent_url)
            for name, agent_url in agents.items()
        }
    
    async def run(self, query: str) -> str:
        # Step 1: Research
        research_result = await self.clients['researcher'].send_message(
            {"text": f"Research: {query}"}
        )
        
        # Step 2: Analyze
        analysis_result = await self.clients['analyzer'].send_message(
            {"text": f"Analyze: {research_result}"}
        )
        
        # Step 3: Write
        final = await self.clients['writer'].send_message(
            {"text": f"Write: {analysis_result}"}
        )
        
        return final

# Usage
pipeline = SequentialPipeline({
    'researcher': 'http://researcher-agent:9101/',
    'analyzer': 'http://analyzer-agent:9102/',
    'writer': 'http://writer-agent:9103/',
})
result = await pipeline.run("Explain quantum computing")
```

---

## 2. Parallel Execution (Ejecución paralela)

**Patrón**: Un task se divide en subtasks que se ejecutan simultáneamente  
**Uso**: Queries que pueden obtener información de múltiples fuentes en paralelo

```
                    ┌──────────────┐
                    │  Orchestrator │
                    └──────┬───────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
   ┌───────────┐    ┌───────────┐    ┌───────────┐
   │  Search   │    │   Compute │    │  Report   │
   │   Agent   │    │   Agent   │    │   Agent   │
   └───────────┘    └───────────┘    └───────────┘
```

### Implementación

```python
# parallel_execution.py
import asyncio
from a2a.client import A2AClient
from typing import Any

class ParallelExecutor:
    def __init__(self, agents: dict[str, str]):
        self.clients = {
            name: A2AClient(url) 
            for name, url in agents.items()
        }
    
    async def run_parallel(self, query: str) -> dict[str, Any]:
        tasks = [
            self.clients['searcher'].send_message({"text": f"Search: {query}"}),
            self.clients['computer'].send_message({"text": f"Compute: {query}"}),
            self.clients['reporter'].send_message({"text": f"Gather data: {query}"}),
        ]
        
        results = await asyncio.gather(*tasks)
        
        return {
            'search_results': results[0],
            'computation': results[1],
            'report_data': results[2],
        }
    
    async def run_with_aggregation(self, query: str) -> str:
        parallel_results = await self.run_parallel(query)
        
        # Send to aggregator agent
        aggregation = await self.clients['aggregator'].send_message({
            "text": f"Aggregate these results: {parallel_results}"
        })
        
        return aggregation

# Usage
executor = ParallelExecutor({
    'searcher': 'http://searcher-agent:9201/',
    'computer': 'http://computer-agent:9202/',
    'reporter': 'http://reporter-agent:9203/',
    'aggregator': 'http://aggregator-agent:9204/',
})
results = await executor.run_parallel("Analyze market trends for AI")
```

---

## 3. Coordinator/Orchestrator (Coordinador central)

**Patrón**: Un coordinator recibe requests y decide qué agentes llamar  
**Uso**: Complex tasks que requieren decisión dinámica de qué sub-agents usar

```
┌─────────────────┐
│   User Query    │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Coordinator    │ ◄── LLM decides which agents to call
│    Agent        │
└────────┬────────┘
         │
    ┌────┴────┬──────────┬───────┐
    ▼         ▼          ▼       ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│Search │ │Code   │ │Docs   │ │Web    │
│Agent  │ │Agent  │ │Agent  │ │Agent  │
└───────┘ └───────┘ └───────┘ └───────┘
```

### Implementación

```python
# coordinator_pattern.py
from a2a.client import A2AClient
from claude_agent_sdk import query, ClaudeAgentOptions

COORDINATOR_PROMPT = """\
You are a Coordinator Agent. Your job is to:
1. Understand the user's request
2. Break it down into subtasks
3. Decide which specialist agents to call
4. Aggregate their responses

Available agents:
- search: Web search and information retrieval
- code: Code analysis and debugging
- docs: Documentation lookup
- web: Web fetching and scraping

Respond with a JSON plan:
{
  "tasks": [{"agent": "search", "query": "..."}, ...],
  "aggregated_answer": "final response"
}
"""

class CoordinatorAgent:
    def __init__(self, agents: dict[str, str]):
        self.clients = {name: A2AClient(url) for name, url in agents.items()}
        self.plan = None
    
    async def decide(self, query: str) -> dict:
        """Use LLM to decide which agents to call."""
        options = ClaudeAgentOptions(
            system_prompt=COORDINATOR_PROMPT,
            max_turns=3,
        )
        
        response = []
        async for msg in query(
            prompt=f"Decide which agents to use for: {query}",
            options=options
        ):
            response.append(msg)
        
        # Parse the plan from LLM response
        # In production, use proper JSON parsing
        return self._parse_plan(response)
    
    async def execute(self, query: str) -> str:
        plan = await self.decide(query)
        
        # Execute tasks in parallel
        tasks = []
        for task in plan['tasks']:
            agent = task['agent']
            task_query = task['query']
            tasks.append(
                self.clients[agent].send_message({"text": task_query})
            )
        
        results = await asyncio.gather(*tasks)
        
        # Aggregate results
        aggregated = await self.clients['aggregator'].send_message({
            "text": f"Synthesize: {dict(zip([t['agent'] for t in plan['tasks']], results))}"
        })
        
        return aggregated

# Usage
coordinator = CoordinatorAgent({
    'search': 'http://search-agent:9301/',
    'code': 'http://code-agent:9302/',
    'docs': 'http://docs-agent:9303/',
    'web': 'http://web-agent:9304/',
    'aggregator': 'http://aggregator-agent:9305/',
})
result = await coordinator.execute("How do I implement auth in FastAPI?")
```

---

## 4. Hub-and-Spoke (Centro-radio)

**Patrón**: Un hub agent central conecta a spokes (agentes especializados)  
**Diferencia con Coordinator**: El hub NO decide - simplemente enruta basada en metadata

```
        ┌──────────────┐
        │     Hub      │
        │  (Router)    │
        └──────┬───────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌───────┐ ┌───────┐ ┌───────┐
│ Spoke │ │ Spoke │ │ Spoke │
│  A    │ │  B    │ │  C    │
└───────┘ └───────┘ └───────┘
```

### Implementación

```python
# hub_and_spoke.py
from a2a.types import AgentCard
from a2a.client import A2AClient
import aiohttp

class HubAgent:
    """Central hub that routes to spoke agents based on capabilities."""
    
    def __init__(self, registry_url: str):
        self.registry_url = registry_url
        self.spokes: dict[str, A2AClient] = {}
    
    async def discover_spokes(self):
        """Discover available spokes from registry."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.registry_url}/agents") as resp:
                agents = await resp.json()
        
        for agent in agents:
            card = AgentCard(**agent)
            self.spokes[card.name] = A2AClient(card.url)
    
    async def route(self, query: str) -> str:
        """Route query to appropriate spoke based on skills."""
        query_lower = query.lower()
        
        # Simple keyword-based routing
        if any(kw in query_lower for kw in ['search', 'find', 'lookup']):
            return await self.spokes['search-spoke'].send_message({"text": query})
        elif any(kw in query_lower for kw in ['code', 'debug', 'implement']):
            return await self.spokes['code-spoke'].send_message({"text": query})
        elif any(kw in query_lower for kw in ['docs', 'document', 'guide']):
            return await self.spokes['docs-spoke'].send_message({"text": query})
        else:
            # Default: fan-out to all spokes
            return await self.fan_out(query)
    
    async def fan_out(self, query: str) -> str:
        """Send to all spokes and aggregate."""
        tasks = [client.send_message({"text": query}) 
                 for client in self.spokes.values()]
        results = await asyncio.gather(*tasks)
        
        # Simple aggregation
        return "\n\n---\n\n".join(results)

# Usage
hub = HubAgent(registry_url="http://litellm-gateway:4000")
await hub.discover_spokes()
result = await hub.route("Find information about Python async")
```

---

## 5. Mesh/P2P (Peer-to-Peer con Discovery)

**Patrón**: Agentes se descubren y colaboran directamente sin coordinator  
**Uso**: Sistemas adaptivos donde los agentes negocian entre sí

```
    ┌─────────┐         ┌─────────┐
    │ Agent A │◄───────►│ Agent B │
    └────┬────┘         └────┬────┘
         │                   │
         ▼                   ▼
    ┌─────────┐         ┌─────────┐
    │ Agent C │◄───────►│ Agent D │
    └─────────┘         └─────────┘
```

### Implementación

```python
# mesh_p2p.py
import asyncio
import aiohttp
from a2a.client import A2AClient
from a2a.types import AgentCard
from typing import Optional

class MeshAgent:
    """P2P agent that discovers peers and collaborates."""
    
    def __init__(self, agent_url: str, registry_url: str):
        self.agent_url = agent_url
        self.registry_url = registry_url
        self.client = A2AClient(agent_url)
        self.peers: dict[str, AgentCard] = {}
    
    async def register(self, agent_card: AgentCard):
        """Register this agent with the registry."""
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{self.registry_url}/agents",
                json=agent_card.model_dump()
            )
    
    async def discover_peers(self, skill_filter: Optional[str] = None):
        """Discover available peers from registry."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.registry_url}/agents") as resp:
                agents = await resp.json()
        
        for agent_data in agents:
            card = AgentCard(**agent_data)
            if skill_filter:
                # Filter by required skill
                if any(skill.id == skill_filter for skill in (card.skills or [])):
                    self.peers[card.name] = card
            else:
                self.peers[card.name] = card
    
    async def consult_peer(self, peer_name: str, query: str) -> str:
        """Ask a specific peer for help."""
        peer_url = self.peers[peer_name].url
        peer_client = A2AClient(peer_url)
        result = await peer_client.send_message({"text": query})
        return result
    
    async def broadcast_query(self, query: str, min_responses: int = 2) -> str:
        """Broadcast query to multiple peers and synthesize."""
        # Select random peers
        peer_names = list(self.peers.keys())[:min_responses]
        
        tasks = [
            A2AClient(self.peers[name].url).send_message({"text": query})
            for name in peer_names
        ]
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors
        valid_responses = [r for r in responses if isinstance(r, str)]
        
        # Synthesize (simple concatenation - use LLM in production)
        return "\n\n---\n\n".join(valid_responses)
    
    async def negotiate(self, problem: str) -> str:
        """Collaborative problem solving with peers."""
        await self.discover_peers()
        
        # Phase 1: Initial perspectives from peers
        perspectives = await self.broadcast_query(
            f"Give your perspective on: {problem}"
        )
        
        # Phase 2: Ask peers to refine based on others' views
        refinement = await self.broadcast_query(
            f"Refine this: {perspectives}"
        )
        
        return refinement


# Example: Research Agent that consults domain experts
class ResearchMeshAgent(MeshAgent):
    """Specialized research agent using P2P collaboration."""
    
    async def research(self, topic: str) -> str:
        await self.discover_peers()
        
        # Get different perspectives
        code_perspective = await self.consult_peer("code-expert", topic)
        docs_perspective = await self.consult_peer("docs-expert", topic)
        web_perspective = await self.consult_peer("web-expert", topic)
        
        return f"""
# Research: {topic}

## Technical Perspective
{code_perspective}

## Documentation
{docs_perspective}

## Web Sources
{web_perspective}
"""

# Usage
researcher = ResearchMeshAgent(
    agent_url="http://researcher-mesh:9401/",
    registry_url="http://litellm-gateway:4000"
)

# Register with skills
from a2a.types import AgentSkill
await researcher.register(AgentCard(
    name="researcher-mesh",
    url="http://researcher-mesh:9401/",
    skills=[
        AgentSkill(id="research", name="Research", description="Research topics")
    ]
))

result = await researcher.research("How to scale a Python web app?")
```

---

## Docker Compose Setup

```yaml
# docker-compose.yml - add these services

services:
  # === Sequential Pipeline Agents ===
  sequential-researcher:
    build: ./agents/sequential/researcher
    ports:
      - "9101:9100"
    environment:
      - AGENT_NAME=sequential-researcher
      - AGENT_PORT=9100
      - MAX_TURNS=10

  sequential-analyzer:
    build: ./agents/sequential/analyzer
    ports:
      - "9102:9100"
    environment:
      - AGENT_NAME=sequential-analyzer
      - AGENT_PORT=9100

  sequential-writer:
    build: ./agents/sequential/writer
    ports:
      - "9103:9100"
    environment:
      - AGENT_NAME=sequential-writer
      - AGENT_PORT=9100

  # === Parallel Execution Agents ===
  parallel-searcher:
    build: ./agents/parallel/searcher
    ports:
      - "9201:9100"

  parallel-computer:
    build: ./agents/parallel/computer
    ports:
      - "9202:9100"

  # === Coordinator Agent ===
  coordinator-agent:
    build: ./agents/coordinator
    ports:
      - "9301:9100"
    environment:
      - LITELLM_GATEWAY=http://litellm:4000

  # === Hub Agent ===
  hub-agent:
    build: ./agents/hub
    ports:
      - "9401:9100"
    environment:
      - REGISTRY_URL=http://litellm:4000

  # === Mesh Agent ===
  mesh-agent:
    build: ./agents/mesh
    ports:
      - "9501:9100"
    environment:
      - REGISTRY_URL=http://litellm:4000
```

---

## Registering Agents with LiteLLM

```bash
# Register sequential pipeline agents
curl -X POST 'http://localhost:4000/v1/agents' \
  -H 'Authorization: Bearer YOUR_MASTER_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_name": "sequential-researcher",
    "agent_card_params": {
      "name": "Sequential Researcher",
      "description": "Research agent - first step in pipeline",
      "url": "http://sequential-researcher:9100/",
      "version": "1.0.0",
      "skills": [
        {"id": "research", "name": "Research", "description": "Gather information"}
      ]
    }
  }'

# Make public for discovery
curl -X POST 'http://localhost:4000/v1/agents/AGENT_ID/make_public' \
  -H 'Authorization: Bearer YOUR_MASTER_KEY'

# List available agents
curl -X GET 'http://localhost:4000/public/agent_hub' \
  -H 'Authorization: Bearer USER_API_KEY'
```

---

## Summary: When to Use Each Architecture

| Architecture | Best For | Complexity |
|-------------|----------|------------|
| **Sequential** | Research → Analysis → Write workflows | Low |
| **Parallel** | Independent subtasks that can run simultaneously | Low-Medium |
| **Coordinator** | Complex tasks requiring dynamic agent selection | Medium |
| **Hub-and-Spoke** | Central routing based on agent capabilities | Medium |
| **Mesh/P2P** | Adaptive collaboration, peer consultation | High |
