import asyncio
import types
import os
import sys

# Ensure repository root is on PYTHONPATH for tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _make_mock_phx_client(prompts_return=None):
    class MockPhoenixClient:
        def __init__(self, endpoint, api_key):
            self.endpoint = endpoint
            self.api_key = api_key
            self.last_prompt_id = None

        async def get_prompt(self, prompt_id):
            self.last_prompt_id = prompt_id
            return prompts_return if prompts_return is not None else f"PROMPT-{prompt_id}"

    return MockPhoenixClient


def test_phoenix_priority(monkeypatch):
    # Patch Phoenix config to simulate Phoenix availability and patch client class
    import src.prompt_resolver as pr

    class MockClient:
        def __init__(self, endpoint, api_key):
            self.endpoint = endpoint
            self.api_key = api_key
            self.called_id = None

        async def get_prompt(self, prompt_id):
            self.called_id = prompt_id
            return f"PHOENIX-PROMPT-{prompt_id}"

    monkeypatch.setattr(pr, "PHX_CLIENT_CLASS", MockClient, raising=False)
    monkeypatch.setattr(pr, "_get_phoenix_config", lambda: {"endpoint": "http://phx", "api_key": "k"})

    role_config = {"name": "role1", "phoenix_prompt_id": "rp1"}
    prompts = {"role1": "Lite prompt"}

    prompt_text = pr.resolve_prompt(role_config, prompts)
    assert isinstance(prompt_text, str) and prompt_text.startswith("PHOENIX-PROMPT-")


def test_fallback_to_lite_llm_when_phoenix_fails(monkeypatch):
    import src.prompt_resolver as pr

    class MockClient:
        def __init__(self, endpoint, api_key):
            pass
        async def get_prompt(self, prompt_id):
            return ""

    monkeypatch.setattr(pr, "PHX_CLIENT_CLASS", MockClient, raising=False)
    monkeypatch.setattr(pr, "_get_phoenix_config", lambda: {"endpoint": "http://phx", "api_key": "k"})

    role_config = {"name": "role1", "phoenix_prompt_id": "rp1"}
    prompts = {"role1": "LiteLLM instruction"}
    prompt_text = pr.resolve_prompt(role_config, prompts)
    assert prompt_text == "LiteLLM instruction"


def test_full_chain_default_when_all_fail(monkeypatch):
    import src.prompt_resolver as pr

    class MockClient:
        def __init__(self, endpoint, api_key):
            pass
        async def get_prompt(self, prompt_id):
            return ""

    monkeypatch.setattr(pr, "PHX_CLIENT_CLASS", MockClient, raising=False)
    monkeypatch.setattr(pr, "_get_phoenix_config", lambda: {"endpoint": "http://phx", "api_key": "k"})

    # No LiteLLM prompts provided
    role_config = {"name": "role1", "phoenix_prompt_id": "rp1"}
    prompts = {}

    # Patch registry/file read to always fail by ensuring environment has no registry URL and no files
    monkeypatch.delenv("REGISTRY_API_URL", raising=False)
    prompt_text = pr.resolve_prompt(role_config, prompts)
    assert prompt_text == "You are an AI assistant."
