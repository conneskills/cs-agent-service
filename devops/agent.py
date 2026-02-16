"""DevOps Helper Agent - Claude Agent SDK wrapper."""

import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from .config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a DevOps helper agent for the litellm-central platform.
Your environment is a Docker Compose stack with these services:
- LiteLLM Gateway (litellm-gateway, port 4000)
- PostgreSQL (litellm-postgres, port 5432)
- Redis (litellm-redis, port 6379)
- Arize Phoenix (litellm-phoenix, port 6006)

You can:
- Check Docker container status with `docker ps`, `docker stats`, `docker inspect`
- View service logs with `docker logs <container>`
- Check service health via curl (LiteLLM: http://litellm-gateway:4000/health, Phoenix: http://litellm-phoenix:6006)
- Read config files in /app (config.yaml, docker-compose.yml, etc.)
- Analyze logs for errors and patterns
- Check disk, memory, and network usage

Guidelines:
- Be concise and direct in your answers.
- Use tables or structured output when listing multiple items.
- When checking health, always report the HTTP status code.
- For log analysis, focus on errors and warnings from the last hour unless asked otherwise.
- Never modify running containers or config files unless explicitly asked.
- Never expose secrets or API keys in your output.
"""


class DevOpsAgent:
    """Wraps Claude Agent SDK for DevOps tasks."""

    def __init__(self) -> None:
        self.max_turns = settings.get("max_turns", 15)

    async def invoke(self, user_message: str) -> str:
        """Execute a DevOps query and return the text response."""
        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Bash", "Read", "Grep", "Glob"],
            max_turns=self.max_turns,
            permission_mode="bypassPermissions",
            cwd="/app",
            stderr=lambda line: logger.debug("claude-cli: %s", line),
        )

        text_parts: list[str] = []
        async for message in query(prompt=user_message, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)

        return "\n".join(text_parts) if text_parts else "No response generated."
