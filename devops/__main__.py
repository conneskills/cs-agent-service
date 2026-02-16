"""Entry point for the DevOps Helper A2A Agent."""

import logging

import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from .agent_card import build_agent_card
from .config import settings
from .executor import DevOpsAgentExecutor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    agent_card = build_agent_card()
    host = settings.get("agent_host", "0.0.0.0")
    port = settings.get("agent_port", 9100)

    request_handler = DefaultRequestHandler(
        agent_executor=DevOpsAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    logger.info("Starting DevOps Helper Agent on %s:%s", host, port)
    logger.info("Agent card: http://%s:%s/.well-known/agent.json", host, port)

    uvicorn.run(app.build(), host=host, port=port)


if __name__ == "__main__":
    main()
