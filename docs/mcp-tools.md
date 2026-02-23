MCP Tools Configuration

Overview
- The MCP tool system discovers and assigns tools to agents at build time.
- Builtin tools can be provided by a Registry service or fallback to defaults.
- Role configurations can specify tools; builtins are merged when not specified.

Registry config format
- Env var REGISTRY_API_URL points to the registry service.
- The registry may expose an endpoint /builtin-tools returning:
  { "tools": [ {"id": "code_search"}, {"id": "get_file_summary"} ] }
- Alternatively a plain list of tool IDs may be returned.

Builtin tools
- Default builtin tool IDs:
  - code_search
  - get_file_summary
- Registry override allows listing additional tools or replacing defaults.
- The list is consumed by get_builtin_tools() in src/config.py.

Role configuration examples
- Minimal example (only builtin tools via config):
  {
    "name": "default",
    "tools": ["code_search", "get_file_summary"]
  }
- Example with MCP tools to be merged:
  {
    "name": "dev",
    "tools": [
      {"id": "code_search", "provider": "builtin"},
      {"id": "get_file_summary", "provider": "builtin"}
    ]
  }
- With MCP-provided tools (merged automatically by loader):
  {
    "name": "ci",
    "tools": [{"id": "mcp-tool-a", "provider": "mcp"}]
  }

Examples
- See src/agent_factory.py for how tools are loaded and mapped to FunctionTool instances.
- See src/config.py for builtin tool loading logic.
