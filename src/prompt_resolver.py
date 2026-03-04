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
        # No loop running - safe to use asyncio.run()
        return asyncio.run(coro)

    # A loop is already running (e.g. FastAPI/uvicorn).
    # Execute the coroutine in a separate thread with its own event loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=10)


def _default_prompt(role_config: Dict[str, Any]) -> str:
    return "You are an AI assistant."


async def _try_phoenix_prompt(role_config: Dict[str, Any]) -> Dict[str, Any]:
    phoenix_cfg = _get_phoenix_config()
    if not phoenix_cfg or PHX_CLIENT_CLASS is None:
        return {"text": "", "model": None}
        
    # ADR-001 Alignment: Use global PHOENIX_PROMPT_NAME as directed
    prompt_name = os.getenv("PHOENIX_PROMPT_NAME") or role_config.get("phoenix_prompt_name") or role_config.get("name")
    if not prompt_name:
        return {"text": "", "model": None}
        
    try:
        client = PHX_CLIENT_CLASS(phoenix_cfg["endpoint"], phoenix_cfg.get("api_key"))  # type: ignore
        # Priority tag: production -> latest
        tag = os.getenv("PHOENIX_PROMPT_TAG", "production")
        return await client.get_prompt(str(prompt_name), tag=tag)  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.debug("Phoenix prompt retrieval failed for '%s': %s", prompt_name, exc)
        return {"text": "", "model": None}


def _read_from_registry(role_name: str) -> Optional[str]:
    reg_url = os.getenv("REGISTRY_URL", "")
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


def resolve_prompt(role_config: Dict[str, Any], prompts: Dict[str, str]) -> Dict[str, Any]:
    """Resolve the prompt text and model for a given role using the resolution chain.

    Priority: Phoenix (primary) -> LiteLLM -> Registry -> Local file -> Default.
    Returns a dict with 'instruction' and 'model'.
    """
    tracer = TracerManager.get_tracer()
    span_cm = tracer.start_as_current_span("resolve_prompt") if tracer else contextlib.nullcontext()
    
    with span_cm as span:
        role_name = role_config.get("name")
        if span:
            span.set_attribute("role.name", role_name or "unknown")

        # 1) Try Phoenix (async client, called from sync context)
        try:
            res = _run_async(_try_phoenix_prompt(role_config))
            if res.get("text"):
                source = f"Phoenix ({role_config.get('phoenix_prompt_name', role_name)})"
                logger.info("Prompt source: %s", source)
                if span:
                    span.set_attribute("prompt.source", "Phoenix")
                    if res.get("model"):
                        span.set_attribute("prompt.model", res["model"])
                return {"instruction": res["text"], "model": res.get("model")}
        except Exception:
            pass

        # 2) LiteLLM fallback using role mapping
        instruction = ""
        source = ""
        
        if isinstance(prompts, dict) and role_name in prompts:
            instruction = prompts[role_name]
            source = "LiteLLM-Mapping"
        elif isinstance(role_config, dict) and role_config.get("instruction"):
            instruction = role_config.get("instruction")
            source = "LiteLLM-Explicit"
        elif role_name:
            # 3) Registry API
            instruction = _read_from_registry(role_name)
            if instruction:
                source = "Registry"
            else:
                # 4) Local file prompts
                instruction = _read_from_file(role_name)
                if instruction:
                    source = "LocalFile"

        if not instruction:
            # 5) Default system prompt
            instruction = _default_prompt(role_config)
            source = "Default"

        logger.info("Prompt source: %s for %s", source, role_name)
        if span:
            span.set_attribute("prompt.source", source)
            
        return {"instruction": instruction, "model": None}
