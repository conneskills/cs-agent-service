"""AgentCard definition for the DevOps Helper Agent."""

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .config import settings


def build_agent_card() -> AgentCard:
    """Build the A2A AgentCard with DevOps skills."""
    public_url = settings.get("agent_public_url", None)
    port = settings.get("agent_port", 9100)

    skills = [
        AgentSkill(
            id="docker_status",
            name="Docker Status",
            description="Check the status of Docker containers, images, networks, and volumes",
            tags=["docker", "containers", "status"],
            examples=[
                "Show running containers",
                "What containers are using the most memory?",
                "List all Docker networks",
            ],
        ),
        AgentSkill(
            id="service_health",
            name="Service Health Check",
            description="Check health of platform services: LiteLLM, PostgreSQL, Redis, Phoenix",
            tags=["health", "monitoring", "services"],
            examples=[
                "Are all services healthy?",
                "Check if LiteLLM is responding",
                "Is the database accepting connections?",
            ],
        ),
        AgentSkill(
            id="log_analysis",
            name="Log Analysis",
            description="Analyze Docker container logs for errors, warnings, and patterns",
            tags=["logs", "errors", "debugging"],
            examples=[
                "Show recent errors from LiteLLM",
                "Any warnings in the last hour?",
                "Show PostgreSQL slow queries",
            ],
        ),
        AgentSkill(
            id="litellm_status",
            name="LiteLLM Gateway Status",
            description="Check LiteLLM gateway status: models, keys, spend, and configuration",
            tags=["litellm", "gateway", "api"],
            examples=[
                "Is LiteLLM healthy?",
                "What models are configured?",
                "Show LiteLLM gateway health details",
            ],
        ),
    ]

    return AgentCard(
        name=settings.get("agent_name", "devops-helper"),
        description=settings.get(
            "agent_description",
            "DevOps helper agent for Docker, service health, logs, and LiteLLM status",
        ),
        url=public_url or f"http://localhost:{port}/",
        version=settings.get("agent_version", "1.0.0"),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=skills,
    )
