import pytest
import asyncio
import os
from unittest.mock import MagicMock, patch
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from src.agent_executor import ADKAgentExecutor
from src.mcp_config import MCPConfig

@pytest.mark.asyncio
@patch("src.mcp_tool_loader.list_servers")
@patch("src.utils.secrets.get_user_credential")
async def test_user_credential_propagation(mock_get_secret, mock_list_servers):
    # Setup environment for discovery
    with patch.dict(os.environ, {"DEBUG_MCP_TOOLS": "true", "GOOGLE_CLOUD_PROJECT": "test-project"}):
        # Setup mocks
        mock_get_secret.return_value = "super-secret-token"
        
        # Mock server that requires auth
        mock_list_servers.return_value = [
            MCPConfig(server_name="jira", transport="http", endpoint="http://jira", requires_user_auth=True)
        ]
        
        # Create executor
        executor = ADKAgentExecutor()
        
        # Create RequestContext with user_id
        context = MagicMock(spec=RequestContext)
        context.get_user_input.return_value = "hello"
        context.user_id = "user123"
        context.message = "hello"
        context.current_task = MagicMock()
        context.current_task.context_id = "ctx1"
        context.current_task.id = "task1"
        
        event_queue = MagicMock(spec=EventQueue)
        event_queue.enqueue_event = MagicMock(side_effect=lambda x: asyncio.sleep(0))
        
        # Mock runner behavior
        mock_runner = MagicMock()
        async def mock_run(text, metadata=None):
            return "Done"
        mock_runner.run = mock_run
        executor._runner = mock_runner
        
        # Execute
        await executor.execute(context, event_queue)
        
        # Now verify the tool wrapper works (internal logic)
        from src.mcp_tool_loader import MCPToolLoader
        loader = MCPToolLoader()
        # Force reload to use mocked list_servers
        loader._cache = None
        tools = await loader.load_tools()
        
        assert len(tools) > 0
        auth_tool = tools[0]
        
        # The tool's fn is wrapped. Let's call it and verify get_user_credential was called.
        # In the wrapper, it sets tool.fn = wrapped_fn.
        # If it's the real ADK tool, we might need to check tool.func too.
        wrapped_func = getattr(auth_tool, 'fn', getattr(auth_tool, 'func', None))
        assert wrapped_func is not None
        
        # Invoke the wrapped function
        if asyncio.iscoroutinefunction(wrapped_func):
            await wrapped_func(user_id="user123")
        else:
            # Some wrappers might be sync or use different calling convention
            try:
                await wrapped_func(user_id="user123")
            except TypeError:
                wrapped_func(user_id="user123")
        
        # Verify secret was fetched for user123 and service jira
        mock_get_secret.assert_called_with("user123", "jira")
