"""A2A Server entry point for Discovery Agent."""

import os
import logging
from a2a.server import A2AServer
from discovery_agent import DiscoveryAgentExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    agent_name = os.getenv("AGENT_NAME", "discovery-agent")
    agent_description = os.getenv("AGENT_DESCRIPTION", "Discovers agents from LiteLLM Registry")
    port = int(os.getenv("AGENT_PORT", "9100"))

    agent_executor = DiscoveryAgentExecutor()

    server = A2AServer(
        agent_executor=agent_executor,
        agent_name=agent_name,
        agent_description=agent_description,
        port=port,
        host="0.0.0.0",
    )

    logger.info(f"Starting Discovery A2A server: {agent_name} on port {port}")
    server.start()


if __name__ == "__main__":
    main()
