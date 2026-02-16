"""
Discovery Agent - Discovers and queries agents from LiteLLM Registry.

This agent can:
- List all public agents in the hub
- Search agents by capabilities
- Provide recommendations
"""

import os
import json
import logging
import aiohttp
from typing import Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact

from claude_agent_sdk import query as claude_query, AssistantMessage, ClaudeAgentOptions, TextBlock
from claude_agent_sdk import query as claude_query, AssistantMessage, ClaudeAgentOptions, TextBlock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiscoveryAgent:
    """Agent that discovers other agents from LiteLLM Registry."""

    def __init__(self):
        self.role = "discovery"
        self.litellm_url = os.getenv("LITELLM_URL", "http://litellm:4000")
        self.api_key = os.getenv("LITELLM_API_KEY", os.getenv("MASTER_KEY", ""))
        self.max_turns = int(os.getenv("MAX_TURNS", "10"))
        self.allowed_tools = ["Bash", "Read", "Grep", "Glob", "WebSearch", "WebFetch"]
        logger.info("Initialized Discovery Agent")

    async def discover_agents(self) -> list[dict]:
        """Get all public agents from the registry."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.litellm_url}/public/agent_hub",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        agents = await resp.json()
                        logger.info(f"Discovered {len(agents)} agents")
                        return agents
                    else:
                        logger.warning(f"Failed to discover agents: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Error discovering agents: {e}")
            return []

    async def search_agents(self, query: str) -> list[dict]:
        """Search agents by keyword in name, description, or skills."""
        all_agents = await self.discover_agents()
        
        query_lower = query.lower()
        matching_agents = []
        
        for agent in all_agents:
            # Check name
            if query_lower in agent.get("name", "").lower():
                matching_agents.append(agent)
                continue
            
            # Check description
            if query_lower in agent.get("description", "").lower():
                matching_agents.append(agent)
                continue
            
            # Check skills
            skills = agent.get("skills", [])
            for skill in skills:
                skill_name = skill.get("name", "").lower()
                skill_desc = skill.get("description", "").lower()
                if query_lower in skill_name or query_lower in skill_desc:
                    matching_agents.append(agent)
                    break
        
        return matching_agents

    async def get_agent_details(self, agent_name: str) -> Optional[dict]:
        """Get details for a specific agent."""
        all_agents = await self.discover_agents()
        
        for agent in all_agents:
            if agent.get("name", "").lower() == agent_name.lower():
                return agent
        
        return None

    def format_agent_list(self, agents: list[dict]) -> str:
        """Format agent list for display."""
        if not agents:
            return "No agents found."
        
        lines = ["# Available Agents\n"]
        
        for i, agent in enumerate(agents, 1):
            lines.append(f"## {i}. {agent.get('name', 'Unknown')}")
            lines.append(f"   **Description:** {agent.get('description', 'N/A')}")
            lines.append(f"   **URL:** {agent.get('url', 'N/A')}")
            
            skills = agent.get("skills", [])
            if skills:
                skill_names = [s.get("name", "unnamed") for s in skills]
                lines.append(f"   **Skills:** {', '.join(skill_names)}")
            
            lines.append("")
        
        return "\n".join(lines)

    async def invoke_agent(self, agent_url: str, query: str, agent_name: str = "agent") -> str:
        """Invoke another agent and return its response using HTTP."""
        import uuid
        
        try:
            # Ensure URL ends with /
            if not agent_url.endswith("/"):
                agent_url += "/"
            
            payload = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tasks/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": query}]
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    agent_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Extract text from response
                        result = data.get("result", {})
                        artifacts = result.get("artifacts", [])
                        if artifacts:
                            parts = artifacts[0].get("parts", [])
                            texts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
                            return "\n".join(texts)
                        return str(result)
                    else:
                        return f"Error: HTTP {resp.status}"
        except Exception as e:
            logger.error(f"Error invoking agent {agent_name}: {e}")
            return f"Error invoking {agent_name}: {str(e)}"

    async def invoke_agent_streaming(self, agent_url: str, query: str, agent_name: str = "agent"):
        """Invoke another agent with streaming and yield chunks.
        
        Yields: text chunks as they arrive
        """
        import uuid
        
        try:
            if not agent_url.endswith("/"):
                agent_url += "/"
            
            # Use tasks/sendSubscribe for streaming
            payload = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tasks/sendSubscribe",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": query}]
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    agent_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        yield f"Error: HTTP {resp.status}"
                        return
                    
                    # Read SSE stream
                    async for line in resp.content:
                        if not line:
                            continue
                        
                        decoded = line.decode('utf-8').strip()
                        if not decoded:
                            continue
                        
                        # SSE format: "data: {...}"
                        if decoded.startswith("data: "):
                            json_str = decoded[6:]  # Remove "data: "
                            try:
                                data = json.loads(json_str)
                                # Extract text from delta
                                result = data.get("result", {})
                                if "delta" in result:
                                    delta = result["delta"]
                                    parts = delta.get("parts", [])
                                    for part in parts:
                                        if part.get("kind") == "text":
                                            yield part.get("text", "")
                            except json.JSONDecodeError:
                                continue
                            
        except Exception as e:
            logger.error(f"Error streaming from agent {agent_name}: {e}")
            yield f"Error: {str(e)}"

    async def extract_agent_from_query(self, user_message: str) -> tuple[Optional[str], Optional[str]]:
        """Extract agent name and task from an invoke/call query.
        
        Returns: (agent_name, task_query) or (None, None)
        """
        message_lower = user_message.lower()
        
        # Patterns like "invoke researcher with..." or "call analyzer to..."
        invoke_patterns = [
            "invoke ",
            "call ",
            "run ",
            "execute ",
            "ask ",
        ]
        
        for pattern in invoke_patterns:
            if pattern in message_lower:
                # Extract the part after the pattern
                after_keyword = user_message[user_message.lower().find(pattern) + len(pattern):]
                
                # Find the "with" or "to" that separates agent name from task
                for sep in [" with ", " to ", " to do ", " asking "]:
                    if sep in after_keyword.lower():
                        parts = after_keyword.lower().split(sep, 1)
                        agent_part = parts[0].strip()
                        task_part = parts[1].strip() if len(parts) > 1 else ""
                        
                        # Clean up agent name
                        agent_name = agent_part.strip().strip("'\"")
                        
                        # Get the actual task
                        if task_part:
                            task_query = user_message[user_message.lower().find(sep) + len(sep):]
                        else:
                            # Try to find task after agent name
                            task_query = after_keyword[len(agent_part):].strip()
                            if not task_query or len(task_query) < 3:
                                task_query = "Please help with this task."
                        
                        return agent_name, task_query
        
        return None, None

    async def find_agent_by_name(self, agent_name: str) -> Optional[dict]:
        """Find an agent by name in the registry."""
        all_agents = await self.discover_agents()
        
        # Exact match first
        for agent in all_agents:
            if agent.get("name", "").lower() == agent_name.lower():
                return agent
        
        # Partial match
        name_lower = agent_name.lower()
        for agent in all_agents:
            if name_lower in agent.get("name", "").lower():
                return agent
        
        return None

    async def parse_streaming_marker(self, marker: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse [STREAMING:url:task:agent_name] marker."""
        # Format: [STREAMING:url:task:agent_name]
        if marker.startswith("[STREAMING:") and marker.endswith("]"):
            inner = marker[11:-1]  # Remove [STREAMING: and ]
            parts = inner.split(":", 3)
            if len(parts) >= 3:
                agent_url = parts[0]
                task = parts[1]
                agent_name = parts[2] if len(parts) > 2 else "agent"
                return agent_url, task, agent_name
        return None, None, None

    async def invoke_streaming(self, user_message: str):
        """Generator that yields streaming chunks for SSE response."""
        message_lower = user_message.lower()
        
        if "invoke" in message_lower or "call" in message_lower:
            agent_name, task_query = await self.extract_agent_from_query(user_message)
            
            if agent_name:
                agent = await self.find_agent_by_name(agent_name)
                
                if agent:
                    agent_url = agent.get("url", "")
                    agent_display = agent.get("name", agent_name)
                    task = task_query or "Please help with this task."
                    
                    # Yield header
                    yield f"# Streaming from: {agent_display}\n\n"
                    yield f"## Task: {task}\n\n---\n\n"
                    
                    # Stream the response
                    async for chunk in self.invoke_agent_streaming(agent_url, task, agent_display):
                        yield chunk
                    
                    yield "\n\n---\n\n✅ Streaming complete."
                    return
        
        yield "No streaming request detected. Use 'invoke [agent] with [task] stream'"
    
    async def invoke(self, user_message: str) -> str:
        """Execute discovery based on user request."""
        
        # Check if this is a discovery query
        message_lower = user_message.lower()
        
        # Handle specific discovery commands
        if any(kw in message_lower for kw in ["list", "show", "what agents", "available"]):
            if "what agents" in message_lower and "do" in message_lower:
                # Asking what agents can do something
                agents = await self.discover_agents()
                return self.format_agent_list(agents)
            else:
                # Just list all agents
                agents = await self.discover_agents()
                return self.format_agent_list(agents)
        
        elif any(kw in message_lower for kw in ["find", "search", "look for", "need"]):
            # Extract search terms
            search_terms = user_message
            for prefix in ["find ", "search ", "look for ", "need "]:
                if prefix in search_terms:
                    search_terms = search_terms.split(prefix, 1)[1]
                    break
            
            agents = await self.search_agents(search_terms)
            
            if agents:
                return f"# Matching Agents for '{search_terms}'\n\n" + self.format_agent_list(agents)
            else:
                return f"No agents found matching '{search_terms}'. Try listing all agents."
        
        elif "invoke" in message_lower or "call" in message_lower or "run " in message_lower:
            # User wants to invoke a specific agent
            agent_name, task_query = await self.extract_agent_from_query(user_message)
            
            if agent_name:
                # Find the agent in registry
                agent = await self.find_agent_by_name(agent_name)
                
                if agent:
                    agent_url = agent.get("url", "")
                    agent_display = agent.get("name", agent_name)
                    
                    task = task_query or "Please help with this task."
                    
                    # Check if streaming requested
                    is_streaming = "stream" in message_lower
                    
                    if is_streaming:
                        # For streaming, we return a marker that the executor will handle
                        # The actual streaming happens in execute_streaming
                        return f"[STREAMING:{agent_url}:{task}:{agent_display}]"
                    else:
                        result = await self.invoke_agent(agent_url, task, agent_display)
                    
                        return f"""# Invoked: {agent_display}

## Task: {task}

## Result:
{result}
"""
                else:
                    return f"Agent '{agent_name}' not found. Use 'list agents' to see available agents."
            else:
                # Show available agents and how to invoke
                agents = await self.discover_agents()
                return f"""To invoke an agent, use: "invoke [agent-name] with [your task]"

To stream results: "invoke [agent-name] with [task] stream"

Available agents:
{self.format_agent_list(agents)}"""
        
        else:
            # General query - use LLM to decide
            agents = await self.discover_agents()
            agent_info = json.dumps(agents, indent=2)
            
            system_prompt = f"""\
You are a helpful agent that helps users find the right agent from the LiteLLM registry.

Available agents:
{agent_info}

User asked: {user_message}

Provide a helpful response about which agent(s) would be best suited for their needs.
If no agents match, suggest what they might need.
"""
            
            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                allowed_tools=self.allowed_tools,
                max_turns=self.max_turns,
                permission_mode="bypassPermissions",
            )

            result_parts = []
            async for message in claude_query(prompt=user_message, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_parts.append(block.text)

            return "\n".join(result_parts) if result_parts else "No response"


class DiscoveryAgentExecutor(AgentExecutor):
    """A2A Executor for Discovery Agent."""

    def __init__(self):
        self.agent = DiscoveryAgent()

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

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        "Discovering agents from registry...",
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
            result = await self.agent.invoke(user_text)
        except Exception:
            logger.exception("Agent execution failed")
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            "Discovery failed.",
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

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                append=False,
                context_id=task.context_id,
                task_id=task.id,
                last_chunk=True,
                artifact=new_text_artifact(
                    name="discovery_result",
                    description="Discovery results",
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

    async def execute_streaming(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Streaming version of execute for SSE responses."""
        user_text = context.get_user_input()
        task = context.current_task

        if not context.message:
            raise ValueError("No message provided")

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        "Streaming from agent...",
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
            # Check if this is a streaming request
            message_lower = user_text.lower()
            
            if "invoke" in message_lower and "stream" in message_lower:
                # Handle streaming invoke
                chunk_count = 0
                async for chunk in self.agent.invoke_streaming(user_text):
                    chunk_count += 1
                    
                    # Send each chunk as an artifact update
                    await event_queue.enqueue_event(
                        TaskArtifactUpdateEvent(
                            append=True,
                            context_id=task.context_id,
                            task_id=task.id,
                            last_chunk=False,
                            artifact=new_text_artifact(
                                name="stream_result",
                                description=f"Stream chunk {chunk_count}",
                                text=chunk,
                            ),
                        )
                    )
                
                # Mark complete
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(state=TaskState.completed),
                        final=True,
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )
                return
            
            # Regular (non-streaming) execution
            result = await self.agent.invoke(user_text)
            
            # Check for streaming marker
            if "[STREAMING:" in result:
                url, task_query, agent_name = await self.agent.parse_streaming_marker(result)
                if url and task_query:
                    # Do streaming
                    agent_name_str = agent_name or "agent"
                    chunk_count = 0
                    async for chunk in self.agent.invoke_agent_streaming(url, task_query, agent_name_str):
                        chunk_count += 1
                        await event_queue.enqueue_event(
                            TaskArtifactUpdateEvent(
                                append=True,
                                context_id=task.context_id,
                                task_id=task.id,
                                last_chunk=False,
                                artifact=new_text_artifact(
                                    name="stream_result",
                                    description=f"Stream chunk {chunk_count}",
                                    text=chunk,
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
                    return
            
            # Regular response
            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    append=False,
                    context_id=task.context_id,
                    task_id=task.id,
                    last_chunk=True,
                    artifact=new_text_artifact(
                        name="discovery_result",
                        description="Discovery results",
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
            
        except Exception:
            logger.exception("Streaming execution failed")
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            "Streaming failed.",
                            task.context_id,
                            task.id,
                        ),
                    ),
                    final=True,
                    context_id=task.context_id,
                    task_id=task.id,
                )
            )

