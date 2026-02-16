"""A2A AgentExecutor bridge to Claude Agent SDK."""

import logging

from typing_extensions import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact

from .agent import DevOpsAgent

logger = logging.getLogger(__name__)


class DevOpsAgentExecutor(AgentExecutor):
    """Bridges A2A protocol to the DevOps Claude Agent."""

    def __init__(self) -> None:
        self.agent = DevOpsAgent()

    @override
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

        # Signal that we're working
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        "Processing DevOps request...",
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
            logger.exception("Agent invocation failed")
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            "Agent execution failed. Check logs for details.",
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

        # Send result as artifact
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                append=False,
                context_id=task.context_id,
                task_id=task.id,
                last_chunk=True,
                artifact=new_text_artifact(
                    name="devops_result",
                    description="DevOps agent response",
                    text=result,
                ),
            )
        )

        # Mark completed
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.completed),
                final=True,
                context_id=task.context_id,
                task_id=task.id,
            )
        )

    @override
    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError("Cancel not supported in MVP")
