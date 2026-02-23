import os
import sys
import pytest
from unittest.mock import patch

def test_agent_factory_single_execution_builds_llm_agent():
    # Minimal runtime config to exercise the factory path
    runtime_config = {
        "execution_type": "single",
        "name": "adk_main",
        "model": "gpt-4o",
        "instruction": "Execute ADK migration tasks",
        "tools": ["tool-a", "tool-b"],
    }
    from src.agent_factory import AgentFactory, _load_tools, _build_llm_agent
    # resolved_prompts supplied to resolve instruction
    factory = AgentFactory(runtime_config, resolved_prompts={"adk_main": "Execute ADK migration tasks"})
    agent = factory.build()
    # The agent should be an LlmAgent (or a compatible stub)
    assert agent is not None
    assert hasattr(agent, "name") and agent.name == "adk_main"
    # model should be wrapped as litellm/{model}
    assert getattr(agent, "model", "").startswith("litellm/")
    assert agent.model == "litellm/gpt-4o"
    # instruction should be propagated
    assert getattr(agent, "instruction", "") == "Execute ADK migration tasks"

def test_load_tools_empty_config_returns_empty(monkeypatch):
    from src.agent_factory import _load_tools
    with patch("src.agent_factory.get_builtin_tools", return_value=[]):
        tools = _load_tools({"tools": []})
        assert isinstance(tools, list) and len(tools) == 0

def test_build_llm_agent_private_builder_with_prompts():
    from src.agent_factory import _build_llm_agent
    role_config = {"name": "role1", "model": "gpt-4o"}
    prompts = {"role1": "Role1 instruction"}
    tools = []
    agent = _build_llm_agent(role_config, prompts, tools)
    assert agent.name == "role1"
    assert agent.model == "litellm/gpt-4o"
    assert agent.instruction == "Role1 instruction"


def test_sequential_agent_builds_from_roles():
    from src.agent_factory import AgentFactory, SequentialAgent
    runtime_config = {
        "execution_type": "sequential",
        "roles": [
            {"name": "role1", "model": "gpt-4o"},
            {"name": "role2", "model": "gpt-4o"},
        ],
    }
    factory = AgentFactory(runtime_config, resolved_prompts={"role1": "Role1", "role2": "Role2"})
    agent = factory.build()
    assert isinstance(agent, SequentialAgent)
    assert len(agent.sub_agents) == 2


def test_parallel_agent_builds_without_aggregator():
    from src.agent_factory import AgentFactory, ParallelAgent
    runtime_config = {
        "execution_type": "parallel",
        "roles": [
            {"name": "r1", "model": "gpt-4o"},
            {"name": "r2", "model": "gpt-4o"},
            {"name": "r3", "model": "gpt-4o"},
        ],
    }
    factory = AgentFactory(runtime_config, resolved_prompts={})
    agent = factory.build()
    assert isinstance(agent, ParallelAgent)
    assert len(agent.sub_agents) == 3


def test_parallel_agent_with_aggregator_wraps_in_sequential():
    from src.agent_factory import AgentFactory, SequentialAgent, ParallelAgent
    runtime_config = {
        "execution_type": "parallel",
        "roles": [
            {"name": "worker1", "model": "gpt-4o"},
            {"name": "agg", "model": "gpt-4o"},
        ],
        "aggregator_role": "agg",
    }
    factory = AgentFactory(runtime_config, resolved_prompts={})
    agent = factory.build()
    # The aggregator should wrap the parallel into a SequentialAgent
    assert isinstance(agent, SequentialAgent)
    assert isinstance(agent.sub_agents[0], ParallelAgent)


def test_loop_agent_builds_with_max_iterations():
    from src.agent_factory import AgentFactory, LoopAgent
    runtime_config = {
        "execution_type": "loop",
        "roles": [
            {"name": "step", "model": "gpt-4o"},
        ],
        "max_iterations": 7,
    }
    factory = AgentFactory(runtime_config, resolved_prompts={"step": "Step prompt"})
    agent = factory.build()
    assert isinstance(agent, LoopAgent)
    assert agent.max_iterations == 7

def test_agent_factory_invalid_execution_type_falls_back_to_single():
    from src.agent_factory import AgentFactory, LlmAgent
    runtime_config = {
        "execution_type": "unsupported_type",
        "name": "fallback_agent",
        "model": "gpt-4o",
    }
    factory = AgentFactory(runtime_config, {})
    agent = factory.build()
    # Should fallback to building an LlmAgent for single execution
    assert isinstance(agent, LlmAgent)
    assert agent.name == "fallback_agent"

def test_agent_factory_none_config_graceful_handling():
    from src.agent_factory import AgentFactory, LlmAgent
    # Passing None should not crash; it should use empty defaults
    factory = AgentFactory(None, None)
    agent = factory.build()
    assert agent is not None
    assert isinstance(agent, LlmAgent)

def test_load_tools_invalid_item_skips_gracefully():
    from src.agent_factory import _load_tools
    # tools list contains an invalid non-dict/non-string item
    role_config = {"tools": [123, {"id": "tool1"}, "tool2", None]}
    tools = _load_tools(role_config)
    # 123 and None are skipped; tool1 and tool2 remain
    assert len(tools) == 2
    # Just verify we have tools, the names might vary based on ADK version
    assert tools[0] is not None
    assert tools[1] is not None
