"""A2A Server entry point for reusable agent service."""

import os
import logging
from a2a.server import A2AServer
from agent import ReusableAgentExecutor

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

    server = A2AServer(
        agent_executor=agent_executor,
        agent_name=agent_name,
        agent_description=agent_description,
        port=port,
        host="0.0.0.0",
    )

    logger.info(
        f"Starting A2A server: {agent_name} on port {port} "
        f"[{service.execution_type}, roles: {[a.role for a in service.agents]}]"
    )
    server.start()


if __name__ == "__main__":
    main()
