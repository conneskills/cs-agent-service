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


class ComplexityAssessor:
    """Assess task complexity using simple heuristics."""

    def assess(self, user_input: str) -> str:
        text = user_input.lower()
        word_count = len(text.split())

        # Simple heuristics for complexity assessment
        is_complex = any(kw in text for kw in ["analyze", "compare", "evaluate", "design", "architect"])
        is_moderate = any(kw in text for kw in ["implement", "debug", "refactor", "create"])

        if word_count > 50 or is_complex:
            return "complex"
        if word_count > 20 or is_moderate:
            return "moderate"
        return "simple"


class HybridOrchestrator(BaseAgent):
    """Orchestrates between SLM and LLM based on task complexity."""

    def __init__(self, name: str, slm_agent: BaseAgent, llm_agent: BaseAgent):
        self.name = name
        self.slm_agent = slm_agent
        self.llm_agent = llm_agent
        self.assessor = ComplexityAssessor()

    async def _run_async_impl(self, ctx):
        user_input = ctx.state.get("current_task", "")
        complexity = self.assessor.assess(user_input)

        if complexity == "simple":
            # Route to SLM (Fast, Low Cost)
            invoke = getattr(self.slm_agent, "invoke", None) or getattr(self.slm_agent, "_run_async_impl", None)
        else:
            # Route to LLM (Powerful, High Cost)
            invoke = getattr(self.llm_agent, "invoke", None) or getattr(self.llm_agent, "_run_async_impl", None)

        if callable(invoke):
            import asyncio
            if asyncio.iscoroutinefunction(invoke):
                return await invoke(ctx)
            return invoke(ctx)
        return ""


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
        if execution_type == "coordinator":
            return self._build_coordinator(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)
        if execution_type == "hub-spoke":
            return self._build_hub_spoke(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)
        if execution_type == "hybrid":
            return self._build_hybrid(self.runtime_config.get("roles", []), self.resolved_prompts, self.runtime_config)

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

    def _build_coordinator(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        coordinator_role = config.get("coordinator_role")
        workers = [_build_llm_agent(r, prompts, self._tools) for r in roles if r.get("name") != coordinator_role]
        
        coord_config = next((r for r in roles if r.get("name") == coordinator_role), roles[0])
        coordinator = _build_llm_agent(coord_config, prompts, self._tools)
        
        # Add workers as tools to the coordinator
        if hasattr(coordinator, "tools"):
            coordinator.tools.extend([agent_tool.AgentTool(agent=w) for w in workers])
        return coordinator

    def _build_hub_spoke(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        hub_role = config.get("hub_role")
        spokes = [_build_llm_agent(r, prompts, self._tools) for r in roles if r.get("name") != hub_role]
        
        hub_config = next((r for r in roles if r.get("name") == hub_role), roles[0])
        hub = _build_llm_agent(hub_config, prompts, self._tools)
        
        # Add spokes as tools to the hub
        if hasattr(hub, "tools"):
            hub.tools.extend([agent_tool.AgentTool(agent=s) for s in spokes])
        return hub

    def _build_hybrid(self, roles: List[dict], prompts: Dict[str, str], config: dict) -> BaseAgent:
        # Expects exactly two roles: the first for SLM, the second for LLM
        if len(roles) < 2:
            return _build_llm_agent(roles[0] if roles else {}, prompts, self._tools)
            
        slm_agent = _build_llm_agent(roles[0], prompts, self._tools)
        llm_agent = _build_llm_agent(roles[1], prompts, self._tools)
        
        return HybridOrchestrator(name="hybrid_orchestrator", slm_agent=slm_agent, llm_agent=llm_agent)
