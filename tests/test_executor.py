import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from src.agent_executor import ADKAgentExecutor


class DummyContext:
    def __init__(self, message: str = "hello"):
        self.message = message
        self.context_id = "ctx-1"
        self.id = "task-1"
        self.current_task = type("T", (), {"id": self.id, "context_id": self.context_id})()
    def get_user_input(self):
        return self.message


class DummyEventQueue:
    def __init__(self):
        self.enqueued = []
    async def enqueue_event(self, event):
        self.enqueued.append(event)


@pytest.mark.asyncio
async def test_adk_executor_runs_with_runner(monkeypatch):
    # Patch ADK Runner to return a deterministic value
    class FakeRunner:
        async def run(self, input_text):
            return f"ADK_RESULT:{input_text}"

    with patch("google.adk.runners.Runner", return_value=FakeRunner()):
        executor = ADKAgentExecutor()
        ctx = DummyContext("test input")
        ev = DummyEventQueue()
        await executor.execute(ctx, ev)
        # We expect at least a status and an artifact event enqueued
        assert len(ev.enqueued) >= 1
