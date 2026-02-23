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

# Exposed so tests can monkeypatch/adapt behavior without importing the real client
PHX_CLIENT_CLASS = _PHXClient

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
        return await client.get_prompt(str(prompt_id))  # type: ignore
    except Exception as exc:  # pragma: no cover - robust against many Phoenix errors
        logger.debug("Phoenix prompt retrieval failed: %s", exc)
        return None


def _read_from_registry(role_name: str) -> Optional[str]:
    reg_url = os.getenv("REGISTRY_API_URL", "")
    if not reg_url:
        return None
    try:
        import requests
        url = f"{reg_url}/prompts/{role_name}"
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
    for fname in (f"{role_name}.txt", f"{role_name}.md"):
        path = os.path.join(base, fname)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception:
                pass
    # Fallback to generic default prompt
    default_path = os.path.join(base, "default.txt")
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    return None


def resolve_prompt(role_config: Dict[str, Any], prompts: Dict[str, str]) -> str:
    """Resolve the prompt text for a given role using the resolution chain.

    Priority: Phoenix (primary) -> LiteLLM -> Registry -> Local file -> Default.
    - role_config may contain a phoenix_prompt_id to fetch via Phoenix.
    - prompts mapping is used for LiteLLM fallback (role_name -> prompt).
    """
    tracer = TracerManager.get_tracer()
    span_cm = tracer.start_as_current_span("resolve_prompt") if tracer else contextlib.nullcontext()
    
    with span_cm as span:
        role_name = role_config.get("name")
        if span:
            span.set_attribute("role.name", role_name or "unknown")

        # 1) Try Phoenix (async client, called from sync context)
        try:
            prompt = _run_async(_try_phoenix_prompt(role_config))
            if prompt:
                source = f"Phoenix ({role_config.get('phoenix_prompt_id', role_name)})"
                logger.info("Prompt source: %s", source)
                if span:
                    span.set_attribute("prompt.source", "Phoenix")
                return prompt
        except Exception:
            # If anything goes wrong, fall back to next source
            pass

        # 2) LiteLLM fallback using role mapping (if provided by runtime)
        if isinstance(prompts, dict) and role_name in prompts:
            prompt = prompts[role_name]
            logger.info("Prompt source: LiteLLM (runtime prompts mapping) for %s", role_name)
            if span:
                span.set_attribute("prompt.source", "LiteLLM-Mapping")
            return prompt
        if isinstance(role_config, dict) and "instruction" in role_config and isinstance(role_config.get("instruction"), str) and role_config.get("instruction"):
            logger.info("Prompt source: LiteLLM (explicit instruction) for %s", role_name)
            if span:
                span.set_attribute("prompt.source", "LiteLLM-Explicit")
            return role_config.get("instruction")  # type: ignore

        # 3) Registry API
        if role_name:
            reg_prompt = _read_from_registry(role_name)
            if reg_prompt:
                logger.info("Prompt source: Registry for %s", role_name)
                if span:
                    span.set_attribute("prompt.source", "Registry")
                return reg_prompt

        # 4) Local file prompts
        if role_name:
            file_prompt = _read_from_file(role_name)
            if file_prompt:
                logger.info("Prompt source: Local file for %s", role_name)
                if span:
                    span.set_attribute("prompt.source", "LocalFile")
                return file_prompt

        # 5) Default system prompt
        logger.info("Prompt source: Default system prompt for %s", role_name)
        if span:
            span.set_attribute("prompt.source", "Default")
        return _default_prompt(role_config)
