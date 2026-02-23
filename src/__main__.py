"""A2A Server entry point for reusable agent service."""

import os
import logging

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill

# ADK migration: use ADKAgentExecutor wrapper instead of ReusableAgentExecutor
from src.agent_executor import ADKAgentExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    # Initialize the ADK-based executor
    agent_executor = ADKAgentExecutor()
    # The ADK path may not expose legacy service data; fall back to env vars.
    service = getattr(agent_executor, "service", None)

    # Read name/description from registry data if available
    if service is not None and getattr(service, "agent_data", None):
        agent_name = service.agent_data.get("name", "dynamic-agent").lower().replace(" ", "-")
        agent_description = service.agent_data.get("description", "A dynamic agent service")
    else:
        agent_name = os.getenv("AGENT_NAME", "reusable-agent")
        agent_description = os.getenv("AGENT_DESCRIPTION", "A reusable agent")

    port = int(os.getenv("AGENT_PORT", "9100"))

    agent_card = AgentCard(
        name=agent_name,
        description=agent_description,
        url=f"http://0.0.0.0:{port}/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id=f"{agent_name}-skill",
                name=agent_name,
                description=agent_description,
                tags=["agent"],
            )
        ],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    logger.info(
        f"Starting A2A server: {agent_name} on port {port} "
        + (f"[execution_type={getattr(service, 'execution_type', 'single')}, roles: {[a.role for a in getattr(service, 'agents', [])]}]" \
           if service is not None else "")
    )

    uvicorn.run(app.build(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
