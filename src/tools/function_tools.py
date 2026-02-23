"""Function tool interface for ADK integration (Phase 3).

In Phase 3 this file will be populated with real function tools discovered via MCP.
For now, provide a minimal stub and a NotImplementedError for the factory to consume.
"""

class FunctionTool:
    def __init__(self, tool_id: str, fn=None):
        self.tool_id = tool_id
        self.fn = fn

    def __repr__(self) -> str:
        return f"FunctionTool(tool_id={self.tool_id})"


def get_builtin_tool(tool_id: str) -> FunctionTool:
    """Return a built-in tool by id.

    This is a placeholder until MCP tool discovery is implemented in Phase 3.
    """
    raise NotImplementedError("get_builtin_tool is not implemented yet in Phase 1")
