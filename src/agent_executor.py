"""ADK-based AgentExecutor wrapper for A2A server.

This module provides ADKAgentExecutor which uses google"s ADK Runner when
available. It falls back to the existing single-agent invocation path when
ADK is not present. The executor implements the A2A AgentExecutor interface
so it can be plugged into the DefaultRequestHandler used by the A2A server.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
import contextlib
import uuid

import asyncio

try:
    from opentelemetry import trace
except ImportError:
    trace = None

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
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
        # module import in environments where ADK isn"t installed.
        self._runner = None  # type: ignore
        self._agent = None
        self.factory = None  # type: ignore
        self.agent_data = None
        self.runtime_config = {}

        # Attempt to build the ADK-backed agent using the existing runtime
        # configuration if available.
        agent_id = os.getenv("AGENT_ID")
        if agent_id:
            try:
                from src.utils.registry import fetch_agent_config, fetch_runtime_config
                self.agent_data = fetch_agent_config(agent_id)
                self.runtime_config = fetch_runtime_config(agent_id) or {}
            except Exception as e:
                logger.warning(f"Failed to fetch config from registry: {e}")

        # Build agent using factory
        self.factory = AgentFactory(self.runtime_config, {})
        self._agent = self.factory.build()

        # Try to initialize ADK Runner if the package is available
        try:
            from google.adk.runners import Runner as ADKRunner  # type: ignore
            from google.adk.sessions import InMemorySessionService

            self._runner_class = ADKRunner
            self._session_service = InMemorySessionService()

            # Instantiate runner with the built ADK agent
            self._runner = ADKRunner(
                app_name="cs-agent-service",
                agent=self._agent,
                session_service=self._session_service
            )  # type: ignore
        except Exception as e:
            logger.warning(f"Failed to initialize ADK runner, falling back. Error: {e}")
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
        session_id = context.context_id

        with span_cm as span:
            if span:
                span.set_attribute("agent.name", getattr(self._agent, "name", "unknown"))
                span.set_attribute("agent.model", getattr(self._agent, "model", "unknown"))
                span.set_attribute("execution.type", "ADK Runner" if self._runner else "Direct Invoke")
                if user_id:
                    span.set_attribute("user_id", str(user_id))
                if session_id:
                    span.set_attribute("session_id", str(session_id))

            try:
                if self._runner is not None:
                    # ADK Runner handles user_id and session_id
                    from google.genai.types import Content, Part
                    
                    user_id_str = str(user_id) if user_id else "default"
                    session_id_str = str(session_id) if session_id else str(uuid.uuid4())
                    
                    # Ensure session exists in the service
                    try:
                        await self._session_service.get_session(user_id=user_id_str, session_id=session_id_str)
                    except Exception:
                        await self._session_service.create_session(
                            app_name="cs-agent-service",
                            user_id=user_id_str,
                            session_id=session_id_str
                        )

                    msg = Content(parts=[Part.from_text(text=user_text)], role="user")
                    
                    # ADR-001: Execution via ADK Runner
                    events = self._runner.run(
                        user_id=user_id_str,
                        session_id=session_id_str,
                        new_message=msg
                    )
                    
                    final_text = ""
                    # handle both async and sync generator
                    if hasattr(events, "__aiter__"):
                        async for event in events:
                            content = getattr(event, "content", None)
                            if content and hasattr(content, "parts"):
                                for p in content.parts:
                                    if hasattr(p, "text") and p.text:
                                        final_text += p.text
                    else:
                        for event in events:
                            content = getattr(event, "content", None)
                            if content and hasattr(content, "parts"):
                                for p in content.parts:
                                    if hasattr(p, "text") and p.text:
                                        final_text += p.text
                                        
                    result = final_text
                else:
                    # Fallback to direct invocation on the built agent using proper context
                    from google.adk.types import InvocationContext
                    from google.genai.types import Content, Part
                    
                    ctx = InvocationContext(
                        user_id=str(user_id) if user_id else "default",
                        new_message=Content(parts=[Part.from_text(text=user_text)], role="user")
                    )
                    
                    events = self._agent.run_async(parent_context=ctx)
                    final_text = ""
                    async for event in events:
                        content = getattr(event, "content", None)
                        if content and hasattr(content, "parts"):
                            for p in content.parts:
                                if hasattr(p, "text") and p.text:
                                    final_text += p.text
                    result = final_text
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
                                f"Agent execution failed: {str(e)}",
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

        name = self.agent_data.get("name", "agent") if self.agent_data else "agent"

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
