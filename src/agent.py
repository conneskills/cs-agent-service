"""Reusable Base Agent - A2A wrapper using OpenAI SDK via LiteLLM proxy.

LiteLLM manages provider keys and routing. The agent only needs
LITELLM_URL + LITELLM_API_KEY — no provider API keys in containers.

Supports two modes:
- Legacy: reads AGENT_ROLE + SYSTEM_PROMPT from env vars, prompts from local files
- Dynamic: reads AGENT_ID from env, loads full config from Registry API

Prompt resolution order:
1. prompt_inline (hardcoded in role config)
2. prompt_ref → LiteLLM Prompt Management API (LITELLM_URL + LITELLM_API_KEY)
3. prompt_ref → Registry API fallback (REGISTRY_URL)
4. Local file (/app/prompts/{role}.txt)
5. Default: "You are a {role} agent."
"""

import os
import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LiteLLM as OpenAI-compatible proxy
_litellm_url = os.getenv("LITELLM_URL", "https://litellm.conneskills.com")
_litellm_key = os.getenv("LITELLM_API_KEY", "")
_default_model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

_client = AsyncOpenAI(
    base_url=_litellm_url,
    api_key=_litellm_key,
)


class BaseAgent:
    """Single-role agent that calls LiteLLM via OpenAI SDK."""

    def __init__(self, role: str = None, system_prompt: str = None,
                 max_turns: int = 10, model: Optional[str] = None):
        self.role = role or os.getenv("AGENT_ROLE", "general")
        self.system_prompt = system_prompt or self._load_prompt()
        self.max_turns = max_turns
        self.model = model or _default_model
        logger.info(f"BaseAgent: role={self.role}, model={self.model}, max_turns={self.max_turns}")

    def _load_prompt(self) -> str:
        """Load system prompt from file or environment."""
        prompt_file = os.getenv("PROMPT_FILE", f"/app/prompts/{self.role}.txt")
        if os.path.exists(prompt_file):
            with open(prompt_file) as f:
                return f.read()
        return os.getenv("SYSTEM_PROMPT", f"You are a {self.role} agent.")

    async def invoke(self, user_message: str) -> str:
        """Execute the agent via LiteLLM (OpenAI-compatible)."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await _client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096,
            )
            result = response.choices[0].message.content or ""
            logger.info(f"Agent '{self.role}' completed: {len(result)} chars")
            return result
        except Exception as e:
            logger.exception("Agent invocation failed")
            return f"Error: {str(e)}"


class AgentService:
    """Dynamic agent service that loads config from Registry API.

    Supports execution types: single, sequential, parallel, coordinator, hub-spoke.
    One container, one image — behavior determined entirely by config.
    """

    def __init__(self):
        self.agent_id = os.getenv("AGENT_ID")
        self.registry_url = os.getenv("REGISTRY_URL", "http://registry-api:9500")
        self.litellm_url = os.getenv("LITELLM_URL", "https://litellm.conneskills.com")
        self.litellm_api_key = os.getenv("LITELLM_API_KEY", "")
        self.agent_data = None
        self.runtime_config = None
        self.execution_type = "single"
        self.agents: list[BaseAgent] = []
        self.roles_by_name: dict[str, BaseAgent] = {}

        if self.agent_id:
            self._load_from_registry()
        else:
            # Legacy mode: single BaseAgent from env vars
            # If PROMPT_REF is set, resolve from LiteLLM first
            prompt_ref = os.getenv("PROMPT_REF")
            system_prompt = None
            if prompt_ref:
                system_prompt = self._fetch_litellm_prompt(prompt_ref, {})
                if system_prompt:
                    logger.info(f"Legacy mode: prompt resolved from LiteLLM via PROMPT_REF={prompt_ref}")
                else:
                    logger.warning(f"Legacy mode: PROMPT_REF={prompt_ref} not found in LiteLLM, falling back to env/file")

            agent = BaseAgent(system_prompt=system_prompt)
            self.agents = [agent]
            self.roles_by_name = {agent.role: agent}
            self.execution_type = "single"

    def _load_from_registry(self):
        """Load agent config from Registry API (sync, called at startup)."""
        import httpx

        headers = {}
        if self.litellm_api_key:
            headers["Authorization"] = f"Bearer {self.litellm_api_key}"

        for attempt in range(3):
            try:
                resp = httpx.get(
                    f"{self.registry_url}/agents/{self.agent_id}",
                    timeout=10.0,
                    headers=headers,
                )
                resp.raise_for_status()
                self.agent_data = resp.json()
                break
            except Exception as e:
                logger.warning(f"Registry attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    import time
                    time.sleep(2)
                else:
                    logger.error("Failed to load from registry, falling back to legacy mode")
                    agent = BaseAgent()
                    self.agents = [agent]
                    self.roles_by_name = {agent.role: agent}
                    return

        self.runtime_config = self.agent_data.get("runtime_config")

        if not self.runtime_config:
            # Agent exists in registry but has no runtime_config — use legacy
            logger.info("Agent has no runtime_config, using legacy mode")
            agent = BaseAgent()
            self.agents = [agent]
            self.roles_by_name = {agent.role: agent}
            return

        self.execution_type = self.runtime_config.get("execution_type", "single")
        roles = self.runtime_config.get("roles", [])

        if not roles:
            logger.warning("No roles in runtime_config, using legacy mode")
            agent = BaseAgent()
            self.agents = [agent]
            self.roles_by_name = {agent.role: agent}
            return

        # Build BaseAgent for each role
        for role_config in roles:
            prompt = self._resolve_prompt(role_config)
            agent = BaseAgent(
                role=role_config.get("name", "agent"),
                system_prompt=prompt,
                max_turns=role_config.get("max_turns", 10),
                model=role_config.get("model"),
            )
            self.agents.append(agent)
            self.roles_by_name[agent.role] = agent

        logger.info(
            f"AgentService loaded: type={self.execution_type}, "
            f"roles={[a.role for a in self.agents]}"
        )

    def _resolve_prompt(self, role_config: dict) -> str:
        """Resolve prompt with fallback chain.

        Order: inline → LiteLLM → Registry API → local file → default.
        """
        # 1. Inline prompt takes priority
        if role_config.get("prompt_inline"):
            return role_config["prompt_inline"]

        prompt_ref = role_config.get("prompt_ref")
        variables = role_config.get("metadata", {})

        if prompt_ref:
            # 2. Try LiteLLM Prompt Management API
            prompt = self._fetch_litellm_prompt(prompt_ref, variables)
            if prompt:
                return prompt

            # 3. Fallback to Registry API
            prompt = self._fetch_registry_prompt(prompt_ref, variables)
            if prompt:
                return prompt

        # 4. Fallback: try local file
        role_name = role_config.get("name", "general")
        prompt_file = f"/app/prompts/{role_name}.txt"
        if os.path.exists(prompt_file):
            with open(prompt_file) as f:
                return f.read()

        # 5. Default
        return f"You are a {role_name} agent."

    def _fetch_litellm_prompt(self, prompt_ref: str, variables: dict) -> Optional[str]:
        """Fetch prompt from LiteLLM Prompt Management API.

        Endpoint: GET /prompts/{prompt_id}/info
        Response: { prompt_spec: { litellm_params: { dotprompt_content: "---\\n...\\n---\\n<body>" } } }
        """
        if not self.litellm_api_key:
            logger.debug("LITELLM_API_KEY not set, skipping LiteLLM prompt fetch")
            return None

        import httpx
        try:
            resp = httpx.get(
                f"{self.litellm_url}/prompts/{prompt_ref}/info",
                headers={"Authorization": f"Bearer {self.litellm_api_key}"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.debug(f"LiteLLM prompt '{prompt_ref}' not found (HTTP {resp.status_code})")
                return None

            data = resp.json()
            dotprompt = (
                data.get("prompt_spec", {})
                .get("litellm_params", {})
                .get("dotprompt_content", "")
            )
            if not dotprompt:
                return None

            # Extract body after YAML frontmatter (---\n...\n---\n)
            template = self._parse_dotprompt_body(dotprompt)

            # Render variables if present
            if variables and "{" in template:
                try:
                    return template.format(**variables)
                except KeyError:
                    return template

            logger.info(f"Prompt '{prompt_ref}' loaded from LiteLLM ({len(template)} chars)")
            return template

        except Exception as e:
            logger.warning(f"Failed to fetch LiteLLM prompt '{prompt_ref}': {e}")
            return None

    def _fetch_registry_prompt(self, prompt_ref: str, variables: dict) -> Optional[str]:
        """Fetch prompt from Registry API (fallback)."""
        import httpx
        try:
            resp = httpx.get(
                f"{self.registry_url}/prompts/{prompt_ref}",
                timeout=10.0,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            template = data.get("template", "")
            if not template:
                return None

            if variables and "{" in template:
                try:
                    return template.format(**variables)
                except KeyError:
                    return template
            return template

        except Exception as e:
            logger.warning(f"Failed to fetch registry prompt '{prompt_ref}': {e}")
            return None

    @staticmethod
    def _parse_dotprompt_body(dotprompt_content: str) -> str:
        """Extract body text from dotprompt format (strip YAML frontmatter)."""
        if not dotprompt_content.startswith("---"):
            return dotprompt_content.strip()

        # Find closing --- after the opening ---
        lines = dotprompt_content.split("\n")
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break

        if end_idx is not None:
            return "\n".join(lines[end_idx + 1:]).strip()

        # No closing ---, return as-is
        return dotprompt_content.strip()

    def _get_role(self, role_name: str) -> Optional[BaseAgent]:
        """Get agent by role name."""
        return self.roles_by_name.get(role_name)

    async def handle_task(self, user_message: str) -> str:
        """Execute based on execution_type."""
        if self.execution_type == "single":
            return await self._run_single(user_message)
        elif self.execution_type == "sequential":
            return await self._run_sequential(user_message)
        elif self.execution_type == "parallel":
            return await self._run_parallel(user_message)
        elif self.execution_type == "coordinator":
            return await self._run_coordinator(user_message)
        elif self.execution_type == "hub-spoke":
            return await self._run_hub_spoke(user_message)
        else:
            logger.warning(f"Unknown execution_type '{self.execution_type}', falling back to single")
            return await self._run_single(user_message)

    async def _run_single(self, user_message: str) -> str:
        """Single role execution."""
        return await self.agents[0].invoke(user_message)

    async def _run_sequential(self, user_message: str) -> str:
        """Sequential pipeline: chain output from one role to the next."""
        chain_output = self.runtime_config.get("chain_output", True) if self.runtime_config else True
        context = user_message
        results = []

        for agent in self.agents:
            logger.info(f"Sequential: running role '{agent.role}'")
            result = await agent.invoke(context)
            results.append({"role": agent.role, "result": result})
            if chain_output:
                context = result

        # Return last result (final output of the pipeline)
        return results[-1]["result"] if results else "No results."

    async def _run_parallel(self, user_message: str) -> str:
        """Parallel execution with optional aggregator."""
        rc = self.runtime_config or {}
        parallel_role_names = rc.get("parallel_roles", [])
        aggregator_name = rc.get("aggregator_role")

        # Determine which agents run in parallel
        if parallel_role_names:
            parallel_agents = [a for a in self.agents if a.role in parallel_role_names]
        else:
            # All agents except aggregator run in parallel
            parallel_agents = [a for a in self.agents if a.role != aggregator_name]

        logger.info(f"Parallel: running {[a.role for a in parallel_agents]}")
        tasks = [a.invoke(user_message) for a in parallel_agents]
        results = await asyncio.gather(*tasks)

        # Build combined output
        combined = "\n\n".join(
            f"=== {agent.role} ===\n{result}"
            for agent, result in zip(parallel_agents, results)
        )

        # If aggregator exists, pass combined results to it
        if aggregator_name:
            aggregator = self._get_role(aggregator_name)
            if aggregator:
                logger.info(f"Parallel: aggregating with role '{aggregator_name}'")
                return await aggregator.invoke(
                    f"Aggregate and synthesize these results:\n\n{combined}"
                )

        return combined

    async def _run_coordinator(self, user_message: str) -> str:
        """Coordinator decides which workers to invoke."""
        rc = self.runtime_config or {}
        coordinator_name = rc.get("coordinator_role")
        worker_names = rc.get("worker_roles", [])

        coordinator = self._get_role(coordinator_name) if coordinator_name else self.agents[0]
        if not coordinator:
            return await self._run_single(user_message)

        # Coordinator decides which workers to use
        worker_list = ", ".join(worker_names) if worker_names else "none defined"
        decision_prompt = (
            f"You are a coordinator. Available workers: [{worker_list}]. "
            f"For this task, decide which worker(s) to use. "
            f"Respond with ONLY the worker name(s), comma-separated.\n\n"
            f"Task: {user_message}"
        )

        logger.info(f"Coordinator: asking '{coordinator.role}' to decide")
        decision = await coordinator.invoke(decision_prompt)

        # Parse decision and invoke selected workers
        selected = [name.strip().lower() for name in decision.split(",")]
        results = []
        for name in selected:
            worker = self._get_role(name)
            if worker:
                logger.info(f"Coordinator: dispatching to worker '{name}'")
                result = await worker.invoke(user_message)
                results.append(f"=== {name} ===\n{result}")

        if not results:
            # Fallback: coordinator handles it directly
            logger.warning("No workers matched, coordinator handles directly")
            return await coordinator.invoke(user_message)

        # Coordinator synthesizes results
        combined = "\n\n".join(results)
        return await coordinator.invoke(
            f"Synthesize these worker results into a final response:\n\n{combined}"
        )

    async def _run_hub_spoke(self, user_message: str) -> str:
        """Hub routes to appropriate spoke(s)."""
        rc = self.runtime_config or {}
        hub_name = rc.get("hub_role")
        spoke_names = rc.get("spoke_roles", [])

        hub = self._get_role(hub_name) if hub_name else self.agents[0]
        if not hub:
            return await self._run_single(user_message)

        # Hub decides which spoke to route to
        spoke_list = ", ".join(spoke_names) if spoke_names else "none defined"
        routing_prompt = (
            f"You are a hub router. Available spokes: [{spoke_list}]. "
            f"Route this request to the best spoke. "
            f"Respond with ONLY the spoke name.\n\n"
            f"Request: {user_message}"
        )

        logger.info(f"Hub-spoke: asking '{hub.role}' to route")
        decision = await hub.invoke(routing_prompt)
        spoke_name = decision.strip().lower()

        spoke = self._get_role(spoke_name)
        if spoke:
            logger.info(f"Hub-spoke: routing to spoke '{spoke_name}'")
            return await spoke.invoke(user_message)

        # Fallback: hub handles directly
        logger.warning(f"Spoke '{spoke_name}' not found, hub handles directly")
        return await hub.invoke(user_message)


class ReusableAgentExecutor(AgentExecutor):
    """A2A Executor that wraps the AgentService."""

    def __init__(self):
        self.service = AgentService()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        user_text = context.get_user_input()
        task = context.current_task

        if not context.message:
            raise ValueError("No message provided")

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        # Working status
        service_desc = (
            f"{self.service.execution_type} "
            f"({', '.join(a.role for a in self.service.agents)})"
        )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        f"Processing [{service_desc}]...",
                        task.context_id,
                        task.id,
                    ),
                ),
                final=False,
                context_id=task.context_id,
                task_id=task.id,
            )
        )

        try:
            result = await self.service.handle_task(user_text)
        except Exception:
            logger.exception("Agent execution failed")
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            "Agent execution failed.",
                            task.context_id,
                            task.id,
                        ),
                    ),
                    final=True,
                    context_id=task.context_id,
                    task_id=task.id,
                )
            )
            return

        # Determine artifact name from service
        name = self.service.agent_data.get("name", "agent") if self.service.agent_data else "agent"

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                append=False,
                context_id=task.context_id,
                task_id=task.id,
                last_chunk=True,
                artifact=new_text_artifact(
                    name=f"{name}_result",
                    description=f"Response from {name} ({self.service.execution_type})",
                    text=result,
                ),
            )
        )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.completed),
                final=True,
                context_id=task.context_id,
                task_id=task.id,
            )
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError("Cancel not supported")
