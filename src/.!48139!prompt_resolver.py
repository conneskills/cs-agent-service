from typing import Any, Dict, Optional
import os
import asyncio
import logging
import contextlib
import concurrent.futures
from .tracing import TracerManager

# Public API surface for tests and runtime
logger = logging.getLogger(__name__)

# Phoenix client integration (optional at runtime)
try:
    from src.phoenix_client import PhoenixClient as _PHXClient  # type: ignore
except Exception:
    _PHXClient = None  # type: ignore

# Exposed so tests can monkeypatch/adapt behavior without importing the real clientPHX_CLIENT_CLASS = _PHXClient

# Phoenix config loader (from existing config module)
try:
    from src.config import get_phoenix_config as _get_phoenix_config  # type: ignore
except Exception:  # pragma: no cover
    _get_phoenix_config = lambda: None  # type: ignore


def _run_async(coro):
    """Run an async coroutine from sync code, handling an already-running loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        # No loop running — safe to use asyncio.run()
        return asyncio.run(coro)

    # A loop is already running (e.g. FastAPI/uvicorn).
    # Execute the coroutine in a separate thread with its own event loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=5)


def _default_prompt(role_config: Dict[str, Any]) -> str:
    return "You are an AI assistant."


async def _try_phoenix_prompt(role_config: Dict[str, Any]) -> Optional[str]:
    phoenix_cfg = _get_phoenix_config()
    if not phoenix_cfg or PHX_CLIENT_CLASS is None:
        return None
    prompt_id = role_config.get("phoenix_prompt_id") or role_config.get("name")
    if not prompt_id:
        return None
    try:
        client = PHX_CLIENT_CLASS(phoenix_cfg["endpoint"], phoenix_cfg["api_key"])  # type: ignore
        tag = os.getenv("PHOENIX_PROJECT_NAME", "prod")
        return await client.get_prompt(str(prompt_id), tag=tag)  # type: ignore
    except Exception as exc:  # pragma: no cover - robust against many Phoenix errors
        logger.debug("Phoenix prompt retrieval failed: %s", exc)
        return None


def _read_from_registry(role_name: str) -> Optional[str]:
    reg_url = os.getenv("REGISTRY_URL", "")
    if not reg_url:
        return None
    try:
        import requests
        url = f{reg_url}/prompts/{role_name}
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                p = data.get("prompt") or data.get("text")
                if isinstance(p, str) and p:
                    return p
    except Exception:
        pass
    return None


def _read_from_file(role_name: str) -> Optional[str]:
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    # Try role-specific file
    for fname in (f"{role_name}.txt", f{role_name}.md"):
        path = os.path.join(base, fname)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as z:
