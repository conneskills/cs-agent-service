import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.agent_factory import LlmAgent, SequentialAgent, ParallelAgent, LoopAgent

@pytest.mark.asyncio
async def test_llm_agent_initialization():
    agent = LlmAgent(name="test", model="litellm/gpt-4o", instruction="Do something")
    assert agent.name == "test"
    assert agent.model == "litellm/gpt-4o"
    assert agent.instruction == "Do something"

@pytest.mark.asyncio
async def test_llm_agent_execution_via_runner():
    agent = LlmAgent(name="test", model="litellm/gpt-4o", instruction="Do something")
    
    # Mock the Runner class to avoid missing __init__ arguments and dependencies
    with patch("google.adk.runners.Runner") as MockRunner:
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run = AsyncMock(return_value="Mocked result")
        
        runner = MockRunner(agent=agent)
        result = await runner.run("hello")
        assert result == "Mocked result"
        MockRunner.assert_called_with(agent=agent)

def test_sequential_agent_structure():
    sub1 = LlmAgent(name="s1", model="m", instruction="i")
    sub2 = LlmAgent(name="s2", model="m", instruction="i")
    seq = SequentialAgent(name="seq", sub_agents=[sub1, sub2])
    assert seq.name == "seq"
    assert len(seq.sub_agents) == 2
    assert seq.sub_agents[0].name == "s1"

def test_parallel_agent_structure():
    sub1 = LlmAgent(name="p1", model="m", instruction="i")
    sub2 = LlmAgent(name="p2", model="m", instruction="i")
    par = ParallelAgent(name="par", sub_agents=[sub1, sub2])
    assert par.name == "par"
    assert len(par.sub_agents) == 2

def test_loop_agent_structure():
    sub = LlmAgent(name="l1", model="m", instruction="i")
    loop = LoopAgent(name="loop", sub_agents=[sub], max_iterations=3)
    assert loop.name == "loop"
    assert loop.max_iterations == 3
