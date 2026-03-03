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
    class FakeRunner:
        async def run(self, user_id=None, session_id=None, new_message=None, run_config=None, metadata=None):
            class DummyMessage:
                parts = []
            class DummyEvent:
                def __init__(self, text):
                    class Part:
                        def __init__(self, text):
                            self.text = text
                    class Msg:
                        def __init__(self, text):
                            self.parts = [Part(text)]
                    self.message = Msg(text)
            
            # Since ADK 1.1.1 run() returns an async generator:
            yield DummyEvent(f"ADK_RESULT:{new_message.parts[0].text if hasattr(new_message, 'parts') else new_message}")
        executor = ADKAgentExecutor()
        ctx = DummyContext("test input")
        ev = DummyEventQueue()
        await executor.execute(ctx, ev)
        # We expect at least a status and an artifact event enqueued
        assert len(ev.enqueued) >= 1
