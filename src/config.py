from typing import Optional, Dict, List, Union
import os

# Phoenix integration configuration (optional)
PHOENIX_ENDPOINT: Optional[str] = None
PHOENIX_API_KEY: Optional[str] = None
PHOENIX_ENABLED: bool = False
REGISTRY_API_URL: str = os.getenv("REGISTRY_API_URL", "")
BUILTIN_TOOLS: List[str] = []

def _load_builtin_tools_from_registry() -> Union[List[str], None]:
    """Load builtin tool IDs from the Registry service if available."""
    if not REGISTRY_API_URL:
        return None
    try:
        import httpx  # type: ignore
        resp = httpx.get(f"{REGISTRY_API_URL}/builtin-tools", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            tools = data.get("tools") or data.get("builtin_tools")
            if isinstance(tools, list):
                ids: List[str] = []
                for t in tools:
                    if isinstance(t, dict):
                        ids.append(str(t.get("id") or t.get("tool_id") or t.get("name")))
                    elif isinstance(t, str):
                        ids.append(t)
                return [x for x in ids if x]
    except Exception:
        pass
    return None

def _init_builtin_tools_config():
    """Initialize builtin tools, preferring registry configuration if available."""
    global BUILTIN_TOOLS
    reg_tools = _load_builtin_tools_from_registry()
    if reg_tools:
        BUILTIN_TOOLS = reg_tools
    else:
        # Fallback default builtin tools
        BUILTIN_TOOLS = ["code_search", "get_file_summary"]

def get_builtin_tools() -> List[str]:
    """Return the list of builtin tool IDs to expose to agents."""
    global BUILTIN_TOOLS
    if not BUILTIN_TOOLS:
        _init_builtin_tools_config()
    return BUILTIN_TOOLS


def _load_phoenix_from_env() -> Optional[Dict[str, str]]:
    endpoint = os.getenv("PHOENIX_ENDPOINT")
    api_key = os.getenv("PHOENIX_API_KEY")
    if endpoint and api_key:
        return {"endpoint": endpoint, "api_key": api_key}
    return None


def _load_phoenix_from_registry() -> Optional[Dict[str, str]]:
    if not REGISTRY_API_URL:
        return None
    try:
        # Optional dependency; if unavailable, skip registry config load
        import httpx  # type: ignore
        resp = httpx.get(f"{REGISTRY_API_URL}/phoenix-config", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            ep = data.get("endpoint")
            key = data.get("api_key")
            if ep and key:
                return {"endpoint": ep, "api_key": key}
    except Exception:
        pass
    return None


def _init_phoenix_config():
    global PHOENIX_ENDPOINT, PHOENIX_API_KEY, PHOENIX_ENABLED
    phoenix = _load_phoenix_from_env() or _load_phoenix_from_registry()
    if phoenix:
        PHOENIX_ENDPOINT = phoenix["endpoint"]
        PHOENIX_API_KEY = phoenix["api_key"]
        PHOENIX_ENABLED = True
    else:
        PHOENIX_ENDPOINT = None
        PHOENIX_API_KEY = None
        PHOENIX_ENABLED = False


def get_phoenix_config() -> Optional[Dict[str, str]]:
    """Return Phoenix config if configured, else None."""
    if PHOENIX_ENABLED and PHOENIX_ENDPOINT and PHOENIX_API_KEY:
        return {"endpoint": PHOENIX_ENDPOINT, "api_key": PHOENIX_API_KEY}
    return None


# Initialize at import time (best-effort, does not block startup)
try:
    _init_phoenix_config()
except Exception:
    PHOENIX_ENDPOINT = None
    PHOENIX_API_KEY = None
    PHOENIX_ENABLED = False
# Initialize builtin tools config after attempting Phoenix config
try:
    _init_builtin_tools_config()
except Exception:
    BUILTIN_TOOLS = ["code_search", "get_file_summary"]
