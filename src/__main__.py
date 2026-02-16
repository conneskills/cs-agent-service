"""A2A Server entry point for reusable agent service."""

import os
import logging

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill

from src.agent import ReusableAgentExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    agent_executor = ReusableAgentExecutor()
    service = agent_executor.service

    # Read name/description from registry data if available
    if service.agent_data:
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
        f"[{service.execution_type}, roles: {[a.role for a in service.agents]}]"
    )

    uvicorn.run(app.build(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
