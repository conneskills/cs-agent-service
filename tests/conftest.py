import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure the repository root is on PYTHONPATH for tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

@pytest.fixture(autouse=True)
def mock_registry_api():
    """Mock Registry API to avoid real HTTP calls during tests."""
    with patch("httpx.get") as mock_get:
        # Default mock response for builtin-tools
        mock_get.return_value = MagicMock()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"tools": ["code_search", "get_file_summary"]}
        yield mock_get

@pytest.fixture
def agent_factory():
    """Fixture for AgentFactory with a mock prompt resolver."""
    from src.agent_factory import AgentFactory
    
    def _create_factory(runtime_config=None, resolved_prompts=None):
        runtime_config = runtime_config or {"execution_type": "single", "name": "test_agent"}
        resolved_prompts = resolved_prompts or {"test_agent": "Test instruction"}
        return AgentFactory(runtime_config, resolved_prompts)
    
    return _create_factory

@pytest.fixture
def temp_logs_dir(tmp_path):
    """Fixture for a temporary directory for test logs."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir
