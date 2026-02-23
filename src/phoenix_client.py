from __future__ import annotations
from typing import List, Dict
import httpx


class PhoenixClient:
    """
    Lightweight Phoenix client to fetch prompts and lists of prompts
    from the Phoenix/LiteLLM prompt management API.
    All HTTP operations are asynchronous and errors are gracefully handled.
    """

    def __init__(self, endpoint: str, api_key: str, timeout: float = 5.0):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {api_key}"}
        # Use a persistent async client
        self.client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def get_prompt(self, prompt_id: str) -> str:
        """
        Retrieve a single prompt by ID.
        Returns the prompt text as string, or an empty string on error.
        """
        url = f"{self.endpoint}/prompts/{prompt_id}"
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                # Common shapes: { "prompt": "...", "text": "..." }
                return str(data.get("prompt") or data.get("text") or "")
            if isinstance(data, str):
                return data
            return ""
        except httpx.RequestError:
            # Connection issues
            return ""
        except httpx.HTTPStatusError:
            # Non-2xx status
            return ""

    async def list_prompts(self) -> List[Dict]:
        """
        Retrieve a list of available prompts.
        Returns a list of dicts, or an empty list on error.
        """
        url = f"{self.endpoint}/prompts"
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "prompts" in data and isinstance(data["prompts"], list):
                return data["prompts"]
            return []
        except httpx.RequestError:
            return []
        except httpx.HTTPStatusError:
            return []
