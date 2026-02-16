"""
Example: Complete Agent Management with Skills, Tools, and RAGs

This script demonstrates the full capabilities of the Agent Registry API v2.
"""

import requests
import json

BASE_URL = "http://localhost:9502"
API_KEY = "sk-1234"

headers = {"Authorization": f"Bearer {API_KEY}"}


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# ============================================================================
# 1. CREATE SKILLS
# ============================================================================
print_section("1. CREATE SKILLS")

skills = [
    {
        "id": "research",
        "name": "Research",
        "description": "Gather information from web and documents",
        "tags": ["search", "information", "facts"],
        "examples": ["Find information about X", "Research topic Y"]
    },
    {
        "id": "analyze",
        "name": "Analyze",
        "description": "Analyze data and identify patterns",
        "tags": ["analysis", "patterns", "insights"],
        "examples": ["Analyze this data", "Find patterns"]
    },
    {
        "id": "write",
        "name": "Write",
        "description": "Create written content",
        "tags": ["writing", "content", "documentation"],
        "examples": ["Write a summary", "Create documentation"]
    },
]

for skill in skills:
    resp = requests.post(f"{BASE_URL}/skills", json=skill, headers=headers)
    print(f"Created skill: {skill['name']} - {resp.json().get('status')}")


# ============================================================================
# 2. CREATE TOOLS
# ============================================================================
print_section("2. CREATE TOOLS")

tools = [
    {
        "id": "web_search",
        "name": "Web Search",
        "description": "Search the web for information",
        "provider": "mcp",
        "mcp_server": "web-search-mcp",
        "mcp_tool_name": "search",
        "parameters": [
            {"name": "query", "type": "string", "description": "Search query", "required": True}
        ]
    },
    {
        "id": "code_executor",
        "name": "Code Executor",
        "description": "Execute Python code",
        "provider": "builtin",
        "handler": "tools.execute_python",
        "parameters": [
            {"name": "code", "type": "string", "description": "Code to execute", "required": True}
        ]
    },
    {
        "id": "file_reader",
        "name": "File Reader",
        "description": "Read files from filesystem",
        "provider": "builtin",
        "handler": "tools.read_file",
        "parameters": [
            {"name": "path", "type": "string", "description": "File path", "required": True}
        ]
    },
]

for tool in tools:
    resp = requests.post(f"{BASE_URL}/tools", json=tool, headers=headers)
    print(f"Created tool: {tool['name']} - {resp.json().get('status')}")


# ============================================================================
# 3. CREATE RAG CONFIG
# ============================================================================
print_section("3. CREATE RAG CONFIG")

rag_configs = [
    {
        "id": "company-docs",
        "name": "Company Documentation",
        "rag_type": "knowledge_base",
        "knowledge_base_provider": "qdrant",
        "knowledge_base_id": "company-docs-v1",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "embedding_model": "text-embedding-3-small",
        "top_k": 3,
    },
    {
        "id": "web-search-rag",
        "name": "Web Search RAG",
        "rag_type": "web_search",
        "web_search_provider": "tavily",
        "web_search_config": {"max_results": 5},
        "top_k": 5,
    },
]

for rag in rag_configs:
    resp = requests.post(f"{BASE_URL}/rag", json=rag, headers=headers)
    print(f"Created RAG: {rag['name']} - {resp.json().get('status')}")


# ============================================================================
# 4. CREATE AGENT WITH CAPABILITIES
# ============================================================================
print_section("4. CREATE AGENT WITH SKILLS, TOOLS, AND RAG")

agent = {
    "name": "Research Analyst Agent",
    "description": "Comprehensive research and analysis agent",
    "url": "http://research-analyst:9100/",
    "agent_type": "researcher",
    "input_modes": ["text"],
    "output_modes": ["text"],
    "streaming": True,
    "artifacts": True,
    "skill_ids": ["research", "analyze"],
    "tool_ids": ["web_search", "file_reader"],
    "rag_ids": ["company-docs", "web-search-rag"],
    "tags": ["research", "analysis", "RAG"],
    "is_public": True,
    "owner": "data-team",
    "team": "analytics",
}

resp = requests.post(f"{BASE_URL}/agents", json=agent, headers=headers)
result = resp.json()
print(f"Created agent: {agent['name']}")
print(f"Agent ID: {result.get('agent_id')}")


# ============================================================================
# 5. CREATE ARCHITECTURE
# ============================================================================
print_section("5. CREATE ARCHITECTURE")

architecture = {
    "name": "Research Pipeline",
    "description": "Sequential research workflow",
    "pattern": "sequential",
    "agents": [
        {"agent_id": result.get("agent_id"), "role": "researcher"},
    ],
    "timeout": 300,
    "retry_count": 3,
}

resp = requests.post(f"{BASE_URL}/architectures", json=architecture, headers=headers)
arch_result = resp.json()
print(f"Created architecture: {architecture['name']}")
print(f"Architecture ID: {arch_result.get('architecture_id')}")


# ============================================================================
# 6. DISCOVER AGENTS
# ============================================================================
print_section("6. DISCOVER AGENTS")

resp = requests.get(
    f"{BASE_URL}/discover?query=I+need+to+research+AI+trends",
    headers=headers
)
discovery = resp.json()
print(f"Query: {discovery.get('query')}")
print(f"Recommended: {discovery.get('recommended_agent', {}).get('name')}")
print(f"Matching skills: {discovery.get('matching_skills')}")


# ============================================================================
# 7. LIST ALL
# ============================================================================
print_section("7. LIST ALL ENTITIES")

resp = requests.get(f"{BASE_URL}/skills", headers=headers)
print(f"Skills: {resp.json().get('count')}")

resp = requests.get(f"{BASE_URL}/tools", headers=headers)
print(f"Tools: {resp.json().get('count')}")

resp = requests.get(f"{BASE_URL}/rag", headers=headers)
print(f"RAG configs: {resp.json().get('count')}")

resp = requests.get(f"{BASE_URL}/agents", headers=headers)
print(f"Agents: {resp.json().get('count')}")


# ============================================================================
# 8. FILTER AGENTS
# ============================================================================
print_section("8. FILTER AGENTS")

resp = requests.get(f"{BASE_URL}/agents?skill=research", headers=headers)
print(f"Agents with 'research' skill: {resp.json().get('count')}")

resp = requests.get(f"{BASE_URL}/agents?tag=analysis", headers=headers)
print(f"Agents with 'analysis' tag: {resp.json().get('count')}")

resp = requests.get(f"{BASE_URL}/agents?agent_type=researcher", headers=headers)
print(f"Agents of type 'researcher': {resp.json().get('count')}")


print("\n✅ Complete example finished!")
