from typing import List, Optional, Dict, Any
import os
import json
import requests

"""
MCP Configuration module

- Represent MCP server configuration
- Load configuration from a central Registry API
- Load configuration from environment variables
- Validate required fields
"""

class MCPConfig:
    """
    MCP server configuration data class.
    """
    def __init__(self, server_name: str, transport: str, endpoint: str, auth_token: Optional[str] = None, requires_user_auth: bool = False):
        self.server_name = server_name
        self.transport = transport
        self.endpoint = endpoint
        self.auth_token = auth_token
        self.requires_user_auth = requires_user_auth

    def validate(self) -> None:
        """
        Validate required fields. Raises ValueError if invalid.
        """
        if not isinstance(self.server_name, str) or not self.server_name:
            raise ValueError("MCPConfig.server_name is required and must be a string")
        if not isinstance(self.transport, str) or not self.transport:
            raise ValueError("MCPConfig.transport is required and must be a string")
        if not isinstance(self.endpoint, str) or not self.endpoint:
            raise ValueError("MCPConfig.endpoint is required and must be a string")
        if self.auth_token is not None and not isinstance(self.auth_token, str):
            raise ValueError("MCPConfig.auth_token must be a string if provided")
        if not isinstance(self.requires_user_auth, bool):
            raise ValueError("MCPConfig.requires_user_auth must be a boolean")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        """
        Construct MCPConfig from a dictionary. Accepts multiple key naming variants.
        """
        if not isinstance(data, dict):
            raise ValueError("data must be a dict")
        server_name = data.get("server_name") or data.get("name")
        transport = data.get("transport")
        endpoint = data.get("endpoint") or data.get("url") or data.get("uri")
        auth_token = data.get("auth_token") or data.get("token")
        requires_user_auth = data.get("requires_user_auth") or data.get("user_auth") or False
        cfg = cls(
            server_name=server_name, 
            transport=transport, 
            endpoint=endpoint, 
            auth_token=auth_token,
            requires_user_auth=bool(requires_user_auth)
        )
        cfg.validate()
        return cfg

    @classmethod
    def load_from_registry(cls, registry_url: str) -> List["MCPConfig"]:
        """
        Load MCP configurations from a Registry API endpoint.
        The API is expected to return JSON with a list of server entries under a
        key such as "servers" or "MCP_SERVERS".
        Example response:
        {
          "servers": [
            {"server_name": "server-a", "transport": "http", "endpoint": "https://example.com/api", "auth_token": "..."},
            {"server_name": "server-b", "transport": "http", "endpoint": "https://example.org/api"}
          ]
        }
        """
        if not registry_url:
            raise ValueError("registry_url must be provided")
        try:
            resp = requests.get(registry_url, timeout=5)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch MCP registry from {registry_url}: {exc}") from exc

        servers: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            if "servers" in payload:
                servers = payload.get("servers") or []
            elif "MCP_SERVERS" in payload:
                servers = payload.get("MCP_SERVERS") or []
        elif isinstance(payload, list):
            servers = payload

        configs: List[MCPConfig] = []
        for entry in servers:
            try:
                if isinstance(entry, MCPConfig):
                    cfg = entry
                elif isinstance(entry, dict):
                    cfg = cls.from_dict(entry)
                else:
                    continue
                configs.append(cfg)
            except Exception:
                continue
        return configs

    @classmethod
    def load_from_env(cls) -> List["MCPConfig"]:
        """
        Load MCP configurations from environment variables.
        Supported formats:
        - MCP_SERVERS as JSON array of dicts
        - MCP_SERVER_{INDEX}_* individual vars, e.g. MCP_SERVER_0_NAME, MCP_SERVER_0_TRANSPORT, ...
        This function gracefully returns an empty list if nothing is defined.
        """
        # Try JSON array first
        env_raw = os.environ.get("MCP_SERVERS")
        if env_raw:
            try:
                data = json.loads(env_raw)
                if isinstance(data, list):
                    return [cls.from_dict(item) for item in data if isinstance(item, dict)]
            except Exception:
                pass

        # Legacy style: MCP_SERVER_0_NAME etc.
        i = 0
        configs: List[MCPConfig] = []
        while True:
            prefix = f"MCP_SERVER_{i}_"
            name = os.environ.get(prefix + "NAME")
            transport = os.environ.get(prefix + "TRANSPORT")
            endpoint = os.environ.get(prefix + "ENDPOINT") or os.environ.get(prefix + "URL")
            token = os.environ.get(prefix + "TOKEN")
            if not any([name, transport, endpoint]):
                break
            if not (name and transport and endpoint):
                i += 1
                continue
            entry = {
                "server_name": name,
                "transport": transport,
                "endpoint": endpoint,
                "auth_token": token
            }
            try:
                configs.append(cls.from_dict(entry))
            except Exception:
                pass
            i += 1
        return configs

def list_servers(registry_url: Optional[str] = None) -> List[MCPConfig]:
    """
    Discover available MCP servers from registry or environment.
    - If registry_url is provided, fetch from registry first.
    - If registry fetch fails or not provided, fall back to load_from_env().
    """
    servers: List[MCPConfig] = []
    if registry_url:
        try:
            servers = MCPConfig.load_from_registry(registry_url)
        except Exception:
            servers = []
    if not servers:
        try:
            servers = MCPConfig.load_from_env()
        except Exception:
            servers = []
    return servers

def _default_headers(auth_token: Optional[str]) -> Dict[str, str]:
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return {}

__all__ = ["MCPConfig", "list_servers"]
