"""
Lightweight Phoenix client to fetch prompts from the Arize Phoenix API.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

class PhoenixClient:
    """
    Lightweight Phoenix client to fetch prompts and lists of prompts
    from the Phoenix/LiteLLM prompt management API.
    All HTTP operations are asynchronous and errors are gracefully handled.
    """

    def __init__(self, endpoint: str, api_key: Optional[str] = None, timeout: float = 10.0):
        # Ensure endpoint doesn't end with /v1 as we add it in methods
        self.endpoint = endpoint.rstrip("/")
        if self.endpoint.endswith("/v1"):
            self.endpoint = self.endpoint[:-3]
            
        self.api_key = api_key
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # Use a persistent async client
        self.client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def get_prompt(self, prompt_name: str, tag: str = "production") -> Dict[str, Any]:
        """
        Retrieve a single prompt by name and tag from Phoenix API v1.
        
        Returns:
            Dict containing:
            - 'text': The resolved system prompt string.
            - 'model': The model name associated with the prompt in Phoenix.
        """
        # Try tag first
        url = f"{self.endpoint}/v1/prompts/{prompt_name}/tags/{tag}"
        try:
            resp = await self.client.get(url)
            
            # Fallback to latest if tag not found or other client error
            if resp.status_code == 404:
                logger.debug("Prompt tag '%s' not found for '%s', trying /latest", tag, prompt_name)
                url = f"{self.endpoint}/v1/prompts/{prompt_name}/latest"
                resp = await self.client.get(url)
                
            resp.raise_for_status()
            data_wrapper = resp.json()
            data = data_wrapper.get("data", {})
            
            result = {
                "text": "",
                "model": data.get("model_name")
            }
            
            template = data.get("template", {})
            template_type = template.get("type", "string")
            
            if template_type == "chat":
                # Handle Phoenix CHAT template format
                messages = template.get("messages", [])
                for msg in messages:
                    if msg.get("role") == "system":
                        content_list = msg.get("content", [])
                        if content_list and isinstance(content_list, list):
                            result["text"] = content_list[0].get("text", "")
                            break
                # Fallback if no system message found
                if not result["text"] and messages:
                    content_list = messages[0].get("content", [])
                    if content_list and isinstance(content_list, list):
                        result["text"] = content_list[0].get("text", "")
            else:
                # Handle Phoenix string template format
                result["text"] = template.get("template") or str(data_wrapper.get("prompt") or "")
                
            return result
            
        except Exception as e:
            logger.error("Error fetching prompt '%s' from Phoenix (%s): %s", prompt_name, url, str(e))
            if hasattr(e, "response") and e.response:
                logger.error("Response content: %s", e.response.text)
            return {"text": "", "model": None}

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """
        Retrieve a list of available prompts from Phoenix API v1.
        """
        url = f"{self.endpoint}/v1/prompts"
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            # Phoenix v1 returns { "data": [...], "next_cursor": ... }
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error("Error listing prompts from Phoenix: %s", e)
            return []
