"""ADK-based AgentExecutor wrapper for A2A server.

This module provides ADKAgentExecutor which uses google's ADK Runner when
available. It falls back to the existing single-agent invocation path when
ADK is not present. The executor implements the A2A AgentExecutor interface
so it can be plugged into the DefaultRequestHandler used by the A2A server.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import contextlib

import asyncio

try:
    from opentelemetry import trace
except ImportError:
    trace = None

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_text_artifact, new_task
from .agent_factory import AgentFactory
from .tracing import TracerManager

logger = logging.getLogger(__name__)


class ADKAgentExecutor(AgentExecutor):
    """ADK-backed executor.

    It builds the ADK agent using AgentFactory and executes it via the ADK
    Runner when available. If ADK is not installed, it gracefully falls back
    to invoking the generated agent directly.
    """

    def __init__(self):
        # Runtime config is discovered lazily to avoid importing ADK during
        # module import in environments where ADK isn't installed.
        self._runner = None  # type: ignore
        self._agent = None
        self.factory = None  # type: ignore
        self.service = None  # optional legacy service for backward-compat

        # Attempt to build the ADK-backed agent using the existing runtime
        # configuration if available. We avoid hard dependencies during import.
        try:
            # Lightweight: reuse legacy AgentService to fetch config if available
            from src.agent import AgentService  # type: ignore

            self.service = AgentService()
            runtime_config = self.service.runtime_config or {}
            # Prompts are resolved by the runtime config itself; empty mapping is fine
            self.factory = AgentFactory(runtime_config, {})
            self._agent = self.factory.build()
        except Exception:
            # Fallback: build a minimal single-agent using runtime_config from env
            self.factory = AgentFactory({}, {})
            self._agent = self.factory.build()

        # Try to initialize ADK Runner if the package is available
        try:
            from google.adk.runners import Runner as ADKRunner  # type: ignore

            self._runner_class = ADKRunner
            # Instantiate runner with the built ADK agent
            self._runner = ADKRunner(agent=self._agent)  # type: ignore
        except Exception:
            self._runner = None
            self._runner_class = None  # type: ignore

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Core execution path with working status, artifact emission and completion
        user_text = context.get_user_input()
        task = context.current_task if hasattr(context, "current_task") else None

        if not context.message:
            # Fallback to the user_text if message is not populated
            context.message = user_text

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        service_desc = (
            f"ADK {'Runner' if self._runner else 'fallback'}" 
        )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        f"Processing [{service_desc}]...",
                        task.context_id,
                        task.id,
                    ),
                ),
                final=False,
                context_id=task.context_id,
                task_id=task.id,
            )
        )

        tracer = TracerManager.get_tracer()
        span_cm = tracer.start_as_current_span("agent_execute") if tracer else contextlib.nullcontext()
        
        # Extract user_id from context metadata or attributes
        user_id = getattr(context, "user_id", None) or getattr(context, "metadata", {}).get("user_id")

        with span_cm as span:
            if span:
                span.set_attribute("agent.name", getattr(self._agent, "name", "unknown"))
                span.set_attribute("agent.model", getattr(self._agent, "model", "unknown"))
                span.set_attribute("execution.type", "ADK Runner" if self._runner else "Direct Invoke")
                if user_id:
                    span.set_attribute("user_id", user_id)

            try:
                if self._runner is not None:
                    # ADK Runner is available; pass user_id in metadata
                    result = await self._runner.run(user_text, metadata={"user_id": user_id} if user_id else {})  # type: ignore
                else:
                    # Fallback to direct invocation on the built agent
                    invoke = getattr(self._agent, "invoke", None)
                    kwargs = {"user_id": user_id} if user_id else {}
                    if asyncio.iscoroutinefunction(invoke):
                        result = await invoke(user_text, **kwargs)  # type: ignore
                    elif callable(invoke):
                        result = invoke(user_text, **kwargs)  # type: ignore
                        if asyncio.isfuture(result):
                            result = await result  # type: ignore
                    else:
                        result = ""
            except Exception as e:
                if span:
                    span.record_exception(e)
                    if trace:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                logger.exception("ADK Agent execution failed")
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.failed,
                            message=new_agent_text_message(
                                "Agent execution failed.",
                                task.context_id,
                                task.id,
                            ),
                        ),
                        final=True,
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )
                return

        name = getattr(self.service.agent_data, "get", lambda *a, **k: None)("name", "agent") if self.service and getattr(self.service, "agent_data", None) else "agent"

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                append=False,
                context_id=task.context_id,
                task_id=task.id,
                last_chunk=True,
                artifact=new_text_artifact(
                    name=f"{name}_result",
                    description=f"Response from {name} (ADK)",
                    text=result if isinstance(result, str) else str(result),
                ),
            )
        )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.completed),
                final=True,
                context_id=task.context_id,
                task_id=task.id,
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancel not supported")
