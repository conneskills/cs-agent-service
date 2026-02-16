"""
Register agents with LiteLLM Agent Hub on startup.

This script registers all demo agents with the LiteLLM Agent Hub,
making them discoverable via /public/agent_hub
"""

import os
import asyncio
import aiohttp
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000")
MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-1234")

AGENTS = [
    # Sequential Pipeline
    {
        "name": "sequential-researcher",
        "display": "Sequential Researcher",
        "description": "Research agent - first step in sequential pipeline",
        "url": "http://seq-researcher:9100/",
        "port": 9101,
        "skills": [
            {"id": "research", "name": "Research", "description": "Gather information"}
        ]
    },
    {
        "name": "sequential-analyzer",
        "display": "Sequential Analyzer",
        "description": "Analyze information from researcher",
        "url": "http://seq-analyzer:9100/",
        "port": 9102,
        "skills": [
            {"id": "analyze", "name": "Analyze", "description": "Analyze data and patterns"}
        ]
    },
    {
        "name": "sequential-writer",
        "display": "Sequential Writer",
        "description": "Create final output from research and analysis",
        "url": "http://seq-writer:9100/",
        "port": 9103,
        "skills": [
            {"id": "write", "name": "Write", "description": "Write final output"}
        ]
    },
    # Parallel Execution
    {
        "name": "parallel-searcher",
        "display": "Parallel Searcher",
        "description": "Search agent for parallel execution",
        "url": "http://par-searcher:9100/",
        "port": 9201,
        "skills": [
            {"id": "search", "name": "Search", "description": "Web search"}
        ]
    },
    {
        "name": "parallel-computer",
        "display": "Parallel Computer",
        "description": "Compute agent for parallel execution",
        "url": "http://par-computer:9100/",
        "port": 9202,
        "skills": [
            {"id": "compute", "name": "Compute", "description": "Perform computations"}
        ]
    },
    {
        "name": "parallel-aggregator",
        "display": "Parallel Aggregator",
        "description": "Aggregator for parallel results",
        "url": "http://par-aggregator:9100/",
        "port": 9203,
        "skills": [
            {"id": "aggregate", "name": "Aggregate", "description": "Combine results"}
        ]
    },
    # Coordinator
    {
        "name": "coordinator-agent",
        "display": "Coordinator Agent",
        "description": "Orchestrates other agents dynamically",
        "url": "http://coord-coordinator:9100/",
        "port": 9301,
        "skills": [
            {"id": "orchestrate", "name": "Orchestrate", "description": "Coordinate agents"}
        ]
    },
    # Hub-and-Spoke
    {
        "name": "hub-agent",
        "display": "Hub Agent",
        "description": "Central hub that routes to spokes",
        "url": "http://hub-hub:9100/",
        "port": 9401,
        "skills": [
            {"id": "route", "name": "Route", "description": "Route to appropriate spoke"}
        ]
    },
    {
        "name": "hub-spoke-code",
        "display": "Hub Spoke - Code",
        "description": "Code handling spoke for hub",
        "url": "http://hub-spoke-code:9100/",
        "port": 9411,
        "skills": [
            {"id": "code", "name": "Code", "description": "Handle code questions"}
        ]
    },
    {
        "name": "hub-spoke-docs",
        "display": "Hub Spoke - Docs",
        "description": "Docs handling spoke for hub",
        "url": "http://hub-spoke-docs:9100/",
        "port": 9412,
        "skills": [
            {"id": "docs", "name": "Docs", "description": "Handle documentation"}
        ]
    },
    # Discovery Agent
    {
        "name": "discovery-agent",
        "display": "Discovery Agent",
        "description": "Discovers and queries agents from LiteLLM Agent Hub",
        "url": "http://discovery-agent:9100/",
        "port": 9501,
        "skills": [
            {"id": "discover", "name": "Discover", "description": "Discover available agents"},
            {"id": "search", "name": "Search", "description": "Search agents by capability"},
            {"id": "recommend", "name": "Recommend", "description": "Recommend best agent for task"}
        ]
    },
]


async def register_agent(session: aiohttp.ClientSession, agent: dict) -> str:
    """Register a single agent with LiteLLM."""
    
    payload = {
        "agent_name": agent["name"],
        "agent_card_params": {
            "name": agent["display"],
            "description": agent["description"],
            "url": agent["url"],
            "version": "1.0.0",
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "capabilities": {
                "streaming": False
            },
            "skills": agent["skills"]
        }
    }
    
    headers = {
        "Authorization": f"Bearer {MASTER_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with session.post(
            f"{LITELLM_URL}/v1/agents",
            json=payload,
            headers=headers
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                agent_id = data.get("agent_id", "unknown")
                logger.info(f"✓ Registered: {agent['name']} (ID: {agent_id})")
                return agent_id
            else:
                text = await resp.text()
                logger.warning(f"✗ Failed to register {agent['name']}: {resp.status} - {text}")
                return None
    except Exception as e:
        logger.error(f"✗ Error registering {agent['name']}: {e}")
        return None


async def make_public(session: aiohttp.ClientSession, agent_id: str) -> bool:
    """Make an agent public for discovery."""
    
    headers = {
        "Authorization": f"Bearer {MASTER_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with session.post(
            f"{LITELLM_URL}/v1/agents/{agent_id}/make_public",
            headers=headers
        ) as resp:
            if resp.status == 200:
                logger.info(f"  → Made public")
                return True
            else:
                logger.warning(f"  → Failed to make public: {resp.status}")
                return False
    except Exception as e:
        logger.error(f"  → Error making public: {e}")
        return False


async def list_public_agents(session: aiohttp.ClientSession) -> list:
    """List public agents from the hub."""
    
    headers = {
        "Authorization": f"Bearer {MASTER_KEY}",
    }
    
    try:
        async with session.get(
            f"{LITELLM_URL}/public/agent_hub",
            headers=headers
        ) as resp:
            if resp.status == 200:
                agents = await resp.json()
                logger.info(f"\n📋 Public agents in hub: {len(agents)}")
                for agent in agents:
                    logger.info(f"  - {agent.get('name')}: {agent.get('description')}")
                return agents
            else:
                logger.warning(f"Failed to list agents: {resp.status}")
                return []
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        return []


async def main():
    """Register all agents with LiteLLM."""
    
    logger.info(f"Connecting to LiteLLM at {LITELLM_URL}")
    
    async with aiohttp.ClientSession() as session:
        # Wait for LiteLLM to be ready
        for i in range(10):
            try:
                async with session.get(f"{LITELLM_URL}/health") as resp:
                    if resp.status == 200:
                        logger.info("✓ LiteLLM is ready")
                        break
            except:
                pass
            logger.info(f"Waiting for LiteLLM... ({i+1}/10)")
            await asyncio.sleep(2)
        else:
            logger.error("LiteLLM not available")
            return
        
        logger.info(f"\n{'='*60}")
        logger.info("REGISTERING AGENTS WITH LITELLM AGENT HUB")
        logger.info(f"{'='*60}")
        
        registered_ids = {}
        
        # Register all agents
        for agent in AGENTS:
            agent_id = await register_agent(session, agent)
            if agent_id:
                registered_ids[agent["name"]] = agent_id
                # Make public immediately
                await make_public(session, agent_id)
        
        logger.info(f"\n✓ Registered {len(registered_ids)}/{len(AGENTS)} agents")
        
        # List public agents
        await list_public_agents(session)
        
        logger.info("\n✅ Agent registration complete!")
        logger.info(f"Access agent hub at: {LITELLM_URL}/ui/?login=success&page=agent-hub")


if __name__ == "__main__":
    asyncio.run(main())
