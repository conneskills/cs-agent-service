"""Dynaconf settings for the DevOps agent."""

from pathlib import Path

from dynaconf import Dynaconf

_agent_dir = Path(__file__).parent

settings = Dynaconf(
    settings_files=[str(_agent_dir / "settings.toml")],
    environments=True,
    env_switcher="MCPGW_ENV",
    load_dotenv=True,
    dotenv_path=".env",
    envvar_prefix="MCPGW",
)
