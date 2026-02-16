"""Reusable Base Agent - A2A wrapper for Claude Agent SDK."""

import os
import logging
import asyncio
from typing import Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact

from claude_agent_sdk import query, AssistantMessage, ClaudeAgentOptions, TextBlock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseAgent:
    """Reusable agent that loads role and tools from environment."""

    def __init__(self):
        self.role = os.getenv("AGENT_ROLE", "general")
        self.system_prompt = self._load_prompt()
        self.max_turns = int(os.getenv("MAX_TURNS", "10"))
        self.allowed_tools = self._parse_tools()
        logger.info(f"Initialized agent: role={self.role}, tools={self.allowed_tools}")

    def _load_prompt(self) -> str:
        """Load system prompt from file or environment."""
        prompt_file = os.getenv("PROMPT_FILE", f"/app/prompts/{self.role}.txt")
        if os.path.exists(prompt_file):
            with open(prompt_file) as f:
                return f.read()
        return os.getenv("SYSTEM_PROMPT", f"You are a {self.role} agent.")

    def _parse_tools(self) -> list[str]:
        """Parse allowed tools from comma-separated env var."""
        tools_env = os.getenv("ALLOWED_TOOLS", "Bash,Read,Grep,Glob")
        return [t.strip() for t in tools_env.split(",")]

    async def invoke(self, user_message: str) -> str:
        """Execute the agent with user message."""
        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            allowed_tools=self.allowed_tools,
            max_turns=self.max_turns,
            permission_mode=os.getenv("PERMISSION_MODE", "bypassPermissions"),
            cwd=os.getenv("WORKDIR", "/app"),
        )

        result_parts = []
        try:
            async for message in query(prompt=user_message, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_parts.append(block.text)
        except Exception as e:
            logger.exception("Agent invocation failed")
            return f"Error: {str(e)}"

        result = "\n".join(result_parts) if result_parts else "No response generated."
        logger.info(f"Agent '{self.role}' completed: {len(result)} chars")
        return result


class ReusableAgentExecutor(AgentExecutor):
    """A2A Executor that wraps the reusable BaseAgent."""

    def __init__(self):
        self.agent = BaseAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        user_text = context.get_user_input()
        task = context.current_task

        if not context.message:
            raise ValueError("No message provided")

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        f"Processing as {self.agent.role}...",
                        task.context_id,
                        task.id,
                    ),
                ),
                final=False,
                context_id=task.context_id,
                task_id=task.id,
            )
        )

        try:
            result = await self.agent.invoke(user_text)
        except Exception:
            logger.exception("Agent execution failed")
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

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                append=False,
                context_id=task.context_id,
                task_id=task.id,
                last_chunk=True,
                artifact=new_text_artifact(
                    name=f"{self.agent.role}_result",
                    description=f"Response from {self.agent.role} agent",
                    text=result,
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

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError("Cancel not supported")
