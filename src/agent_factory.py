"""AgentFactory for Google ADK migration.

This factory builds ADK LlmAgent instances from a runtime configuration.
It provides a minimal, test-friendly implementation with a safe fallback
if the google-adk package is not available in the execution environment.
"""

from typing import Any, List, Optional, Dict
from src.config import get_builtin_tools
import warnings

# Attempt to import real ADK classes; fall back to lightweight stubs if unavailable
try:
    from google.adk.agents import LlmAgent, BaseAgent, SequentialAgent, ParallelAgent, LoopAgent  # type: ignore
    from google.adk.tools import FunctionTool  # type: ignore
    HAVE_ADK = True
except Exception:
    HAVE_ADK = False

    class BaseAgent:
        pass

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

    # Expose a consistent interface for downstream code/tests

    # Lightweight agent placeholders used when ADK is unavailable
    class SequentialAgent(BaseAgent):
        def __init__(self, name: str, sub_agents: List[BaseAgent]):
            self.name = name
            self.sub_agents = sub_agents

        def __repr__(self) -> str:
            return f"SequentialAgent(name={self.name}, sub_agents={len(self.sub_agents)})"

    class ParallelAgent(BaseAgent):
        def __init__(self, name: str, sub_agents: List[BaseAgent]):
            self.name = name
            self.sub_agents = sub_agents

        def __repr__(self) -> str:
            return f"ParallelAgent(name={self.name}, sub_agents={len(self.sub_agents)})"

    class LoopAgent(BaseAgent):
        def __init__(self, name: str, sub_agents: List[BaseAgent], max_iterations: int = 5):
            self.name = name
            self.sub_agents = sub_agents
            self.max_iterations = max_iterations

        def __repr__(self) -> str:
            return f"LoopAgent(name={self.name}, iterations={self.max_iterations})"


def _load_tools(role_config: dict) -> List[FunctionTool]:
    # Phase 1: return lightweight placeholders for configured built-in tools
    tools: List[FunctionTool] = []
    tool_configs = role_config.get("tools", []) if isinstance(role_config, dict) else []
    for cfg in tool_configs:
        # Support both string shorthand and dict config
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
        if provider == "mcp":
            # skip MCP-provided tools in this phase (we'll merge MCP tools later)
            continue
        if provider == "builtin":
            tools.append(FunctionTool(tool_id or "unknown"))
    # If no explicit role tools configured, fall back to builtin tools from config
    if not tool_configs:
        try:
            for bid in get_builtin_tools():
                if bid:
                    tools.append(FunctionTool(bid))
        except Exception:
            pass
    # Task 2: Integrate MCP-discovered tools if available
    try:
        from src.mcp_tool_loader import MCPToolLoader
        loader = MCPToolLoader()
        mcp_tools = loader.load_tools_sync()
        for t in mcp_tools:
            tool_id = getattr(t, "tool_id", None) or getattr(t, "id", None) or str(t)
            tools.append(FunctionTool(tool_id, t))
    except Exception:
        # Graceful degradation if MCP loader is unavailable or discovery failed
        pass
    return tools


def _build_llm_agent(role_config: dict, prompts: Dict[str, str], tools: List[FunctionTool]) -> LlmAgent:
    # Role name drives prompts; default to 'agent' if not provided
    role_name = role_config.get("name", "agent")
    # Resolve instruction/prompt using the prompt resolver (Phoenix-first, then fallbacks)
    instruction = ""
    try:
        from src.prompt_resolver import resolve_prompt  # type: ignore
        instruction = resolve_prompt(role_config, prompts)
    except Exception:
        # Fallback to existing behavior if prompt_resolver is unavailable
        if isinstance(prompts, dict) and role_name in prompts:
            instruction = prompts[role_name]
        else:
            instruction = role_config.get("instruction", "")
    # Model string for LiteLLM proxy
    model_name = role_config.get("model", "gpt-4o-mini")
    model = f"litellm/{model_name}"
    return LlmAgent(name=role_name, model=model, instruction=instruction, tools=tools)


class AgentFactory:
    """Factory to build ADK agents from runtime configuration."""

    def __init__(self, runtime_config: dict, resolved_prompts: Any):
        self.runtime_config = runtime_config or {}
        self.resolved_prompts = resolved_prompts
        self._tools: List[FunctionTool] = []

    def build(self) -> BaseAgent:
        # Load tools for the chosen path
        execution_type = self.runtime_config.get("execution_type", "single")
        self._tools = _load_tools(self.runtime_config)

        # Support multiple execution patterns introduced by ADK migration plan
        if execution_type == "single":
            return _build_llm_agent(self.runtime_config, self.resolved_prompts, self._tools)
        if execution_type == "sequential":
            return self._build_sequential(self.runtime_config.get("roles", []), self.resolved_prompts)
        if execution_type == "parallel":
            return self._build_parallel(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)
        if execution_type == "loop":
            return self._build_loop(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)

        # Fallback to single execution for any other mode in this phase
        return _build_llm_agent(self.runtime_config, self.resolved_prompts, self._tools)

    # --------- New builder helpers for multi-agent patterns ---------
    def _build_sequential(self, roles: List[dict], prompts: Dict[str, str]) -> "SequentialAgent":
        sub_agents = [_build_llm_agent(r, prompts, self._tools) for r in roles]
        return SequentialAgent(name="pipeline", sub_agents=sub_agents)

    def _build_parallel(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        aggregator_name = config.get("aggregator_role")

        # Build parallel agents (excluding aggregator)
        parallel_agents = [_build_llm_agent(r, prompts, self._tools) for r in roles if r.get("name") != aggregator_name]

        parallel = ParallelAgent(name="fan_out", sub_agents=parallel_agents)

        # If aggregator exists, wrap in SequentialAgent
        if aggregator_name:
            agg_config = next((r for r in roles if r.get("name") == aggregator_name), None)
            if agg_config:
                aggregator = _build_llm_agent(agg_config, prompts, self._tools)
                return SequentialAgent(name="parallel_gather", sub_agents=[parallel, aggregator])
        return parallel

    def _build_loop(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        sub_agents = [_build_llm_agent(r, prompts, self._tools) for r in roles]
        max_iters = config.get("max_iterations", 5)
        return LoopAgent(name="refiner", sub_agents=sub_agents, max_iterations=max_iters)
