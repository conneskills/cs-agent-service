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
    HAVE_ADK = True
except Exception:
    HAVE_ADK = False

    class BaseAgent:
        async def _run_async_impl(self, ctx):
            return ""

    class LlmAgent(BaseAgent):
        def __init__(self, name: str, model: str, instruction: str, tools: Optional[List[Any]] = None):
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


def _load_tools(role_config: dict) -> List[FunctionTool]:
    tools: List[FunctionTool] = []
    tool_configs = role_config.get("tools", []) if isinstance(role_config, dict) else []
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
            tools.append(FunctionTool(tool_id or "unknown"))
            
    if not tool_configs:
        try:
            for bid in get_builtin_tools():
                if bid:
                    tools.append(FunctionTool(bid))
        except Exception:
            pass
            
    try:
        from src.mcp_tool_loader import MCPToolLoader
        loader = MCPToolLoader()
        mcp_tools = loader.load_tools_sync()
        for t in mcp_tools:
            tool_id = getattr(t, "tool_id", None) or getattr(t, "id", None) or str(t)
            tools.append(FunctionTool(tool_id, t))
    except Exception:
        pass
    return tools


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

    # 2. Determine model (Priority: Phoenix -> Registry -> Default)
    model_name = prompt_model or role_config.get("model", "gpt-4o-mini")
    model = f"litellm/{model_name}"
    
    logger.info("Building agent %s with model %s", role_name, model)
    return LlmAgent(name=role_name, model=model, instruction=instruction, tools=tools)


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
