"""Built-in function tools for cs-agent-service.

This module provides the implementation of standard tools that can be
attached to agents (LlmAgent) via the AgentFactory.
"""

import datetime
from typing import Any, Dict, Optional
import logging

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)

def get_date_time() -> str:
    """Returns the current system date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def search_knowledge_base(query: str) -> str:
    """Simulates a search in a local knowledge base."""
    # Mock implementation for Phase 13
    return f"Search result for '{query}': No specific entries found in local KB. Please try a different query or use web search."

async def http_request(url: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> str:
    """Performs a simple HTTP request."""
    if not httpx:
        return "Error: httpx is not installed. HTTP request tool is unavailable."
    
    try:
        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                resp = await client.get(url, timeout=10.0)
            elif method.upper() == "POST":
                resp = await client.post(url, json=data, timeout=10.0)
            else:
                return f"Error: Unsupported HTTP method '{method}'"
            
            resp.raise_for_status()
            return resp.text[:1000] # Return first 1000 chars
    except Exception as e:
        logger.error(f"HTTP request failed: {e}")
        return f"Error: HTTP request to {url} failed: {str(e)}"

def get_builtin_tool(tool_id: str) -> Optional[Any]:
    """Resolves a tool ID to a function or tool object."""
    from src.agent_factory import FunctionTool, HAVE_ADK
    
    registry = {
        "get_date_time": get_date_time,
        "search_knowledge_base": search_knowledge_base,
        "http_request": http_request,
    }
    
    fn = registry.get(tool_id)
    if not fn:
        return None
        
    if HAVE_ADK:
        return FunctionTool(fn)
    else:
        # Fallback stub implementation
        return FunctionTool(tool_id, fn)
