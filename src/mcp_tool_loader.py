import asyncio
import time
import os
import logging
from typing import List, Any, Optional, Dict
from src.utils.secrets import get_user_credential
from src.mcp_config import list_servers, MCPConfig

logger = logging.getLogger(__name__)

"""
MCP Tool Loader

- Provides an integration point to load MCP tools from the discovered MCP servers.
- Supports user-specific credential resolution via Secret Manager for servers marked with requires_user_auth.
- When google-adk is available, it uses adk.MCPToolset.
"""


class MCPToolLoader:
    """MCP Tool Loader with async discovery and TTL caching.

    This loader attempts to discover available MCP tools from configured MCP
    servers. It handles user context injection for tools that require it.
    """

    # Class-wide cache so multiple loader instances share the same discovery
    _cache: List[Any] | None = None
    _cache_ts: float = 0.0
    _ttl: int = 300  # seconds
    _lock: asyncio.Lock | None = None

    def __init__(self, ttl: int = 300):
        # Allow per-instance TTL override while keeping a shared cache
        self._ttl = ttl
        if MCPToolLoader._lock is None:
            MCPToolLoader._lock = asyncio.Lock()

        # Optional: an internal signal to force refresh if needed
        self._force_reload: bool = False

    # Async API: perform discovery and return a list of discovered tool descriptors
    async def load_tools(self) -> List[Any]:
        # Fast path: return cached tools if still valid
        now = time.time()
        if MCPToolLoader._cache is not None and (now - MCPToolLoader._cache_ts) < self._ttl:
            return MCPToolLoader._cache  # type: ignore[return-value]

        async with MCPToolLoader._lock:  # type: ignore[arg-type]
            # Re-check after acquiring the lock
            now = time.time()
            if MCPToolLoader._cache is not None and (now - MCPToolLoader._cache_ts) < self._ttl:
                return MCPToolLoader._cache  # type: ignore[return-value]

            tools = await self._discover_tools()
            MCPToolLoader._cache = tools
            MCPToolLoader._cache_ts = time.time()
            return tools

    # Optional sync wrapper for environments that call sync code paths
    def load_tools_sync(self) -> List[Any]:
        """Synchronous wrapper around async discovery for simple call sites."""
        try:
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None

            if loop is None or loop.is_running() is False:
                if loop is None:
                    # Create a new loop if none exists
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                return loop.run_until_complete(self.load_tools())
            # If an event loop is already running (common in async apps), return cached
            # value to avoid blocking the loop.
            return MCPToolLoader._cache or []
        except Exception:
            return MCPToolLoader._cache or []

    async def _discover_tools(self) -> List[Any]:
        """Internal discovery implementation.

        Tries to use a Google ADK-like MCPToolset if available; falls back to
        an empty list if discovery is not possible.
        """
        all_tools = []
        
        # Load servers from config
        registry_url = os.getenv("REGISTRY_API_URL")
        servers = list_servers(registry_url)
        
        # Attempt discovery via an external ADK-like package if present
        try:
            if _HAS_GOOGLE_ADK and hasattr(adk, "MCPToolset"):
                # Group servers by auth requirement
                auth_servers = [s for s in servers if s.requires_user_auth]
                no_auth_servers = [s for s in servers if not s.requires_user_auth]
                
                # Load regular tools
                if no_auth_servers:
                    toolset = adk.MCPToolset(servers=no_auth_servers)  # type: ignore
                    tools = toolset.load_tools()
                    if tools:
                        all_tools.extend(list(tools))
                
                # Load auth-required tools with a wrapper
                for s in auth_servers:
                    toolset = adk.MCPToolset(servers=[s])
                    tools = toolset.load_tools()
                    if tools:
                        # Wrap these tools to inject user credentials at call time
                        for t in tools:
                            all_tools.append(self._wrap_tool_with_auth(t, s.server_name))
            
            # Mock discovery for testing/dev if enabled
            if os.getenv("DEBUG_MCP_TOOLS") == "true":
                all_tools.extend(self._get_mock_tools(servers))

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            # If we are in debug mode, we still want the mock tools even if ADK failed
            if os.getenv("DEBUG_MCP_TOOLS") == "true" and not all_tools:
                all_tools.extend(self._get_mock_tools(servers))

        return all_tools

    def _wrap_tool_with_auth(self, tool: Any, server_name: str) -> Any:
        """
        Wraps an ADK tool to intercept calls and inject user-specific credentials.
        This assumes the tool supports a 'user_id' in its call context.
        """
        # Handle both stub (fn) and real ADK (func)
        attr_name = "fn" if hasattr(tool, "fn") else "func"
        original_fn = getattr(tool, attr_name, None)
        
        if not original_fn:
            return tool

        async def wrapped_fn(*args, **kwargs):
            user_id = kwargs.get("user_id")
            if user_id:
                # Resolve credential from Secret Manager
                credential = get_user_credential(user_id, server_name)
                if credential:
                    # Inject credential into the call (e.g. as an auth token)
                    kwargs["auth_token"] = credential
            
            if asyncio.iscoroutinefunction(original_fn):
                return await original_fn(*args, **kwargs)
            return original_fn(*args, **kwargs)
        
        setattr(tool, attr_name, wrapped_fn)
        return tool

    def _get_mock_tools(self, servers: List[MCPConfig]) -> List[Any]:
        """Provides mock tools for development purposes."""
        from src.agent_factory import FunctionTool, HAVE_ADK
        mock_tools = []
        for s in servers:
            # Create a dummy function for the mock tool
            async def jira_auth_tool(*args, **kwargs):
                return f"Mock result from {s.server_name}"

            try:
                if HAVE_ADK:
                    # Real ADK takes just the function
                    t = FunctionTool(jira_auth_tool)
                else:
                    # Stub takes name and function
                    t = FunctionTool(f"{s.server_name}_auth_tool", jira_auth_tool)
                
                if s.requires_user_auth:
                    mock_tools.append(self._wrap_tool_with_auth(t, s.server_name))
                else:
                    mock_tools.append(t)
            except Exception as e:
                logger.error(f"Failed to create mock tool: {e}")
                
        return mock_tools

# Placeholder for integration point
try:
    # Example hypothetical integration with google-adk if present
    from google import adk  # type: ignore
    _HAS_GOOGLE_ADK = True
except Exception:
    adk = None  # type: ignore
    _HAS_GOOGLE_ADK = False

__all__ = ["MCPToolLoader"]

# Placeholder for integration point
try:
    # Example hypothetical integration with google-adk if present
    from google import adk  # type: ignore
    _HAS_GOOGLE_ADK = True
except Exception:
    adk = None  # type: ignore
    _HAS_GOOGLE_ADK = False


def _integrate_with_google_adk(loader: MCPToolLoader) -> List[object]:
    if not _HAS_GOOGLE_ADK:
        return []
    # This is a placeholder demonstrating how integration would look
    # tools = adk.MCPToolset().load_tools(servers=...)
    # return tools
    return []


__all__ = ["MCPToolLoader"]
