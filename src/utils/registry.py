import os
import logging
import httpx
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def fetch_agent_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """Fetch agent configuration from the Registry API."""
    registry_url = os.getenv("REGISTRY_URL", "http://registry-api:9500")
    litellm_api_key = os.getenv("LITELLM_API_KEY", "")
    
    headers = {}
    if litellm_api_key:
        headers["Authorization"] = f"Bearer {litellm_api_key}"

    for attempt in range(3):
        try:
            resp = httpx.get(
                f"{registry_url}/agents/{agent_id}",
                timeout=httpx.Timeout(10.0, connect=3.0),
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Registry attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                import time
                time.sleep(2)
    
    return None

def fetch_runtime_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """Fetch ONLY the runtime configuration for the agent service.
    
    More token-efficient than downloading the full agent card.
    """
    registry_url = os.getenv("REGISTRY_URL", "http://registry-api:9500")
    litellm_api_key = os.getenv("LITELLM_API_KEY", "")
    
    headers = {}
    if litellm_api_key:
        headers["Authorization"] = f"Bearer {litellm_api_key}"

    try:
        resp = httpx.get(
            f"{registry_url}/agents/{agent_id}/runtime-config",
            timeout=httpx.Timeout(10.0, connect=3.0),
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch runtime config: {e}")
        return None
