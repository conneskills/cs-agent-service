"""AgentFactory for Google ADK migration.

This factory builds ADK LlmAgent instances from a runtime configuration.
It provides a minimal, test-friendly implementation with a safe fallback
if the google-adk package is not available in the execution environment.
"""

from typing import Any, List, Optional, Dict
from src.config import get_builtin_tools
import logging

logger = logging.getLogger(__name__)

# Attempt to import real ADK classes; fall back to lightweight stubs if unavailable
try:
    from google.adk.agents import LlmAgent, BaseAgent, SequentialAgent, ParallelAgent, LoopAgent  # type: ignore
    from google.adk.tools import FunctionTool, agent_tool  # type: ignore
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types
    from openai import AsyncOpenAI
    HAVE_ADK = True
except Exception:
    HAVE_ADK = False

    class BaseAgent:
        async def _run_async_impl(self, ctx):
            return ""

    class LlmAgent(BaseAgent):
        def __init__(self, name: str, model: Any, instruction: str, tools: Optional[List[Any]] = None):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools or []

        def __repr__(self) -> str:
            return f"LlmAgent(name={self.name}, model={self.model})"

    class FunctionTool:
        def __init__(self, name: str, fn: Any = None):
            self.name = name
            self.fn = fn

    class agent_tool:
        class AgentTool:
            def __init__(self, agent: BaseAgent):
                self.agent = agent
                self.name = getattr(agent, "name", "agent_tool")

class LiteLlmProxyLlm(BaseLlm):
    """
    Truly agnostic LLM implementation that uses the 'openai' library 
    to call the LiteLLM proxy URL. This bypasses ADK's internal 
    registry and eliminates the dependency on the 'litellm' python package.
    """
    base_url: str
    api_key: str

    async def generate_content_async(self, llm_request: Any, stream: bool = False):
        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        
        messages = []
        # Handle system instruction from ADK config
        system_instr = getattr(llm_request.config, "system_instruction", None)
        if system_instr:
            messages.append({"role": "system", "content": str(system_instr)})
            
        # Convert ADK contents to OpenAI messages
        for content in llm_request.contents:
            role = "assistant" if content.role == "model" else content.role
            text = ""
            for p in content.parts:
                if hasattr(p, "text") and p.text:
                    text += p.text
            if text:
                messages.append({"role": role, "content": text})

        # Call the proxy
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=stream
        )

        if not stream:
            text = response.choices[0].message.content or ""
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)]),
                partial=False,
                model_version=response.model
            )
        else:
            full_text = ""
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    full_text += delta
                    yield LlmResponse(
                        content=types.Content(role="model", parts=[types.Part(text=delta)]),
                        partial=True,
                        model_version=chunk.model
                    )
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=full_text)]),
                partial=False
            )


def _load_tools(role_config: dict) -> List[FunctionTool]:
    tools: List[FunctionTool] = []
    tool_configs = role_config.get("tools", []) if isinstance(role_config, dict) else []
    
    from src.tools.function_tools import get_builtin_tool
    
    for cfg in tool_configs:
        if isinstance(cfg, str):
            tool_id = cfg
            provider = "builtin"
            active = True
        elif isinstance(cfg, dict):
            tool_id = cfg.get("id") or cfg.get("tool_id") or cfg.get("name")
            provider = cfg.get("provider", "builtin")
            active = cfg.get("active", True)
        else:
            continue

        if not active:
            continue
            
        if provider == "builtin":
            t = get_builtin_tool(tool_id or "")
            if t:
                tools.append(t)
            
    if not tool_configs:
        try:
            for bid in get_builtin_tools():
                if bid:
                    t = get_builtin_tool(bid)
                    if t:
                        tools.append(t)
        except Exception:
            pass
            
    try:
        from src.mcp_tool_loader import MCPToolLoader
        loader = MCPToolLoader()
        mcp_tools = loader.load_tools_sync()
        for t in mcp_tools:
            # MCP tools from loader are usually already FunctionTool-compatible or 
            # objects that ADK knows how to handle.
            if hasattr(t, "name"):
                tools.append(t)
    except Exception:
        pass
    return tools


def _probe_model(model: str, base_url: str, api_key: str) -> bool:
    """Check if the model is reachable via a minimal sync request."""
    import httpx
    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
            timeout=5.0,
        )
        return resp.status_code != 404
    except Exception:
        return False


def _build_llm_agent(role_config: dict, prompts: Dict[str, str], tools: List[FunctionTool]) -> LlmAgent:
    role_name = role_config.get("name", "agent")

    # 1. Resolve instruction and model from Phoenix (priority) or fallbacks
    instruction = ""
    prompt_model = None

    try:
        from src.prompt_resolver import resolve_prompt  # type: ignore
        res = resolve_prompt(role_config, prompts)
        instruction = res.get("instruction", "")
        prompt_model = res.get("model")
    except Exception as e:
        logger.warning("Failed to resolve prompt for %s: %s", role_name, e)
        instruction = role_config.get("instruction", "")

    # 2. Determine model: prompt takes priority, registry is fallback
    import os
    litellm_url = os.getenv("LITELLM_URL", "https://litellm.conneskills.com").rstrip("/")
    if not litellm_url.endswith("/v1"):
        litellm_url = f"{litellm_url}/v1"
    litellm_api_key = os.getenv("LITELLM_API_KEY", "")

    registry_model = role_config.get("model", "gpt-4o-mini")
    if prompt_model and prompt_model != registry_model:
        if _probe_model(prompt_model, litellm_url, litellm_api_key):
            model_name = prompt_model
        else:
            logger.warning(
                "Model '%s' from prompt is unavailable, falling back to registry model '%s'",
                prompt_model, registry_model,
            )
            model_name = registry_model
    else:
        model_name = prompt_model or registry_model

    # Create the agnostic proxy LLM instance that uses 'openai' library
    proxy_llm = LiteLlmProxyLlm(
        model=model_name,
        base_url=litellm_url,
        api_key=litellm_api_key,
    )
    
    logger.info("Building agent %s with model %s via agnostic proxy %s", role_name, model_name, litellm_url)
    
    return LlmAgent(name=role_name, model=proxy_llm, instruction=instruction, tools=tools)


class AgentFactory:
    """Factory to build ADK agents from runtime configuration."""

    def __init__(self, runtime_config: dict, resolved_prompts: Any):
        self.runtime_config = runtime_config or {}
        self.resolved_prompts = resolved_prompts or {}
        self._tools: List[FunctionTool] = []

    def build(self) -> BaseAgent:
        execution_type = self.runtime_config.get("execution_type", "single")
        self._tools = _load_tools(self.runtime_config)

        if execution_type == "single":
            roles = self.runtime_config.get("roles", [])
            role_cfg = roles[0] if roles else self.runtime_config
            return _build_llm_agent(role_cfg, self.resolved_prompts, self._tools)
            
        if execution_type == "sequential":
            return self._build_sequential(self.runtime_config.get("roles", []), self.resolved_prompts)
            
        if execution_type == "parallel":
            return self._build_parallel(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)
            
        if execution_type == "loop":
            return self._build_loop(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)
            
        if execution_type == "coordinator":
            return self._build_coordinator(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)
            
        if execution_type == "hub-spoke":
            return self._build_hub_spoke(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)

        return _build_llm_agent(self.runtime_config, self.resolved_prompts, self._tools)

    def _build_sequential(self, roles: List[dict], prompts: Dict[str, str]) -> "SequentialAgent":
        sub_agents = [_build_llm_agent(r, prompts, _load_tools(r)) for r in roles]
        return SequentialAgent(name="pipeline", sub_agents=sub_agents)

    def _build_parallel(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        aggregator_name = config.get("aggregator_role")
        parallel_agents = [_build_llm_agent(r, prompts, _load_tools(r)) for r in roles if r.get("name") != aggregator_name]
        parallel = ParallelAgent(name="fan_out", sub_agents=parallel_agents)

        if aggregator_name:
            agg_config = next((r for r in roles if r.get("name") == aggregator_name), None)
            if agg_config:
                aggregator = _build_llm_agent(agg_config, prompts, _load_tools(agg_config))
                return SequentialAgent(name="parallel_gather", sub_agents=[parallel, aggregator])
        return parallel

    def _build_loop(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        sub_agents = [_build_llm_agent(r, prompts, _load_tools(r)) for r in roles]
        max_iters = config.get("max_iterations", 5)
        return LoopAgent(name="refiner", sub_agents=sub_agents, max_iterations=max_iters)

    def _build_coordinator(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        coordinator_role = config.get("coordinator_role")
        workers = [_build_llm_agent(r, prompts, _load_tools(r)) for r in roles if r.get("name") != coordinator_role]
        coord_config = next((r for r in roles if r.get("name") == coordinator_role), roles[0] if roles else {})
        coordinator = _build_llm_agent(coord_config, prompts, _load_tools(coord_config))
        
        if HAVE_ADK and hasattr(coordinator, "tools"):
            coordinator.tools.extend([agent_tool.AgentTool(agent=w) for w in workers])
        return coordinator

    def _build_hub_spoke(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        hub_role = config.get("hub_role")
        spokes = [_build_llm_agent(r, prompts, _load_tools(r)) for r in roles if r.get("name") != hub_role]
        hub_config = next((r for r in roles if r.get("name") == hub_role), roles[0] if roles else {})
        hub = _build_llm_agent(hub_config, prompts, _load_tools(hub_config))
        
        if HAVE_ADK and hasattr(hub, "tools"):
            hub.tools.extend([agent_tool.AgentTool(agent=s) for s in spokes])
        return hub
