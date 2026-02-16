"""
Agent Capabilities Management - Skills, Tools, RAGs, and more.

This module defines the complete agent capability model.
"""

from typing import Optional, list
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


# ============================================================================
# ENUMS
# ============================================================================

class AgentType(str, Enum):
    """Type of agent."""
    GENERAL = "general"
    RESEARCHER = "researcher"
    ANALYZER = "analyzer"
    WRITER = "writer"
    COORDINATOR = "coordinator"
    HUB = "hub"
    SPOKE = "spoke"
    CUSTOM = "custom"


class ToolProvider(str, Enum):
    """Tool provider type."""
    MCP = "mcp"
    OPENAPI = "openapi"
    CUSTOM = "custom"
    BUILTIN = "builtin"


class RAGType(str, Enum):
    """RAG configuration type."""
    VECTOR_STORE = "vector_store"
    KNOWLEDGE_BASE = "knowledge_base"
    WEB_SEARCH = "web_search"
    DOCUMENT = "document"


# ============================================================================
# SKILLS
# ============================================================================

class SkillDefinition(BaseModel):
    """Skill definition for an agent."""
    id: str = Field(..., description="Unique skill ID")
    name: str = Field(..., description="Human-readable skill name")
    description: str = Field(..., description="What the skill does")
    tags: list[str] = Field(default_factory=list, description="Skill tags for discovery")
    examples: list[str] = Field(
        default_factory=list, 
        description="Example queries for this skill"
    )
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


# ============================================================================
# TOOLS
# ============================================================================

class ToolParameter(BaseModel):
    """Tool parameter definition."""
    name: str
    type: str = "string"
    description: str
    required: bool = False
    default: Optional[str] = None
    enum: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """Tool definition for an agent."""
    id: str = Field(..., description="Unique tool ID")
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="What the tool does")
    provider: ToolProvider = Field(default=ToolProvider.BUILTIN, description="Tool provider")
    
    # MCP specific
    mcp_server: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    
    # OpenAPI specific
    openapi_spec: Optional[str] = None
    openapi_operation: Optional[str] = None
    
    # Custom/Builtin
    handler: Optional[str] = None  # Python function path
    
    parameters: list[ToolParameter] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


# ============================================================================
# RAG CONFIGURATION
# ============================================================================

class RAGConfig(BaseModel):
    """RAG (Retrieval-Augmented Generation) configuration."""
    id: str = Field(..., description="Unique RAG config ID")
    name: str = Field(..., description="RAG configuration name")
    rag_type: RAGType = Field(..., description="Type of RAG")
    
    # Vector Store
    vector_store_provider: Optional[str] = None  # pinecone, qdrant, weaviate, pgvector
    vector_store_config: dict = Field(default_factory=dict)
    
    # Knowledge Base
    knowledge_base_id: Optional[str] = None
    knowledge_base_provider: Optional[str] = None  # aws-kb, azure-ai-search, etc.
    
    # Web Search
    web_search_provider: Optional[str] = None  # tavily, brave, serper, etc.
    web_search_config: dict = Field(default_factory=dict)
    
    # Document
    document_sources: list[str] = Field(default_factory=list)  # URLs, paths, etc.
    document_loader: Optional[str] = None  # pdf, markdown, etc.
    
    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_model: str = "text-embedding-ada-002"
    
    # Retrieval
    top_k: int = 5
    similarity_threshold: Optional[float] = None
    
    metadata: dict = Field(default_factory=dict)


# ============================================================================
# CAPABILITIES
# ============================================================================

class Capabilities(BaseModel):
    """Agent capabilities."""
    streaming: bool = False
    push_notifications: bool = False
    state_transition: bool = False
    artifacts: bool = True
    inline_tool_calls: bool = False


# ============================================================================
# AGENT CARD (complete)
# ============================================================================

class CompleteAgentCard(BaseModel):
    """Complete agent card with all capabilities."""
    
    # Identity
    agent_id: Optional[str] = None
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    url: str = Field(..., description="Agent A2A endpoint URL")
    version: str = "1.0.0"
    
    # Type
    agent_type: AgentType = AgentType.GENERAL
    
    # Protocol
    protocol_version: str = "1.0"
    
    # I/O Modes
    default_input_modes: list[str] = ["text"]
    default_output_modes: list[str] = ["text"]
    
    # Capabilities
    capabilities: Capabilities = Field(default_factory=Capabilities)
    
    # Skills (what the agent can do)
    skills: list[SkillDefinition] = Field(default_factory=list)
    
    # Tools (specific tools available)
    tools: list[ToolDefinition] = Field(default_factory=list)
    
    # RAG configurations
    rag_configs: list[RAGConfig] = Field(default_factory=list)
    
    # Metadata
    owner: Optional[str] = None
    team: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Dependencies
    requires_auth: bool = False
    rate_limit: Optional[int] = None
    
    # Discovery
    is_public: bool = False
    is_discoverable: bool = True
    
    metadata: dict = Field(default_factory=dict)


# ============================================================================
# ARCHITECTURE DEFINITION
# ============================================================================

class AgentReference(BaseModel):
    """Reference to an agent in an architecture."""
    agent_id: str
    role: str  # coordinator, worker, spoke, hub, etc.
    config: dict = Field(default_factory=dict)


class ArchitectureDefinition(BaseModel):
    """Complete architecture definition."""
    architecture_id: Optional[str] = None
    name: str
    description: str
    
    # Pattern
    pattern: str  # sequential, parallel, coordinator, hub-spoke, mesh
    
    # Agents in this architecture
    agents: list[AgentReference]
    
    # Connections (for complex architectures)
    connections: list[dict] = Field(default_factory=list)
    
    # Shared resources
    shared_tools: list[str] = Field(default_factory=list)
    shared_rag: list[str] = Field(default_factory=list)
    
    # Execution config
    timeout: int = 300
    retry_count: int = 3
    
    metadata: dict = Field(default_factory=dict)


# ============================================================================
# SKILL MATCHER
# ============================================================================

class SkillMatcher:
    """Match user queries to agent skills."""
    
    @staticmethod
    def match(query: str, skills: list[SkillDefinition]) -> list[SkillDefinition]:
        """Find matching skills for a query."""
        query_lower = query.lower()
        matches = []
        
        for skill in skills:
            score = 0
            
            # Check name
            if skill.name.lower() in query_lower:
                score += 10
            
            # Check description
            if any(word in skill.description.lower() for word in query_lower.split()):
                score += 5
            
            # Check tags
            for tag in skill.tags:
                if tag.lower() in query_lower:
                    score += 3
            
            # Check examples
            for example in skill.examples:
                if any(word in example.lower() for word in query_lower.split()):
                    score += 2
            
            if score > 0:
                matches.append((skill, score))
        
        # Sort by score
        matches.sort(key=lambda x: x[1], reverse=True)
        return [m[0] for m in matches]
    
    @staticmethod
    def find_best_agent(query: str, agents: list[CompleteAgentCard]) -> Optional[CompleteAgentCard]:
        """Find the best agent for a query based on skills."""
        best_agent = None
        best_score = 0
        best_skills = []
        
        for agent in agents:
            if not agent.is_discoverable:
                continue
            
            matches = SkillMatcher.match(query, agent.skills)
            
            if matches:
                # Score based on number of matching skills
                score = len(matches)
                
                if score > best_score:
                    best_score = score
                    best_agent = agent
                    best_skills = matches
        
        return best_agent
