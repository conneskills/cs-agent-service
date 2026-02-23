import os
import pytest
from unittest.mock import patch
from src.config import get_builtin_tools, get_phoenix_config

def test_get_builtin_tools_defaults(monkeypatch):
    """Test that default tools are returned when no registry is available."""
    # Ensure REGISTRY_API_URL is empty
    monkeypatch.setenv("REGISTRY_API_URL", "")
    
    # Reloading the module state for test isolation is tricky without re-importing,
    # but we can patch the internal variable if needed.
    # For now, we test the public interface.
    tools = get_builtin_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0
    assert "code_search" in tools

def test_get_phoenix_config_from_env(monkeypatch):
    """Test that Phoenix config is correctly loaded from environment variables."""
    monkeypatch.setenv("PHOENIX_ENDPOINT", "http://localhost:6006")
    monkeypatch.setenv("PHOENIX_API_KEY", "test-key")
    
    # We need to trigger the init logic again since it runs at import time
    from src.config import _init_phoenix_config
    _init_phoenix_config()
    
    config = get_phoenix_config()
    assert config is not None
    assert config["endpoint"] == "http://localhost:6006"
    assert config["api_key"] == "test-key"

def test_get_phoenix_config_disabled_by_default(monkeypatch):
    """Test that Phoenix is disabled if environment variables are missing."""
    monkeypatch.delenv("PHOENIX_ENDPOINT", raising=False)
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.setenv("REGISTRY_API_URL", "")
    
    from src.config import _init_phoenix_config
    _init_phoenix_config()
    
    config = get_phoenix_config()
    assert config is None
