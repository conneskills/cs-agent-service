import sys
import traceback
from src.agent_factory import AgentFactory

print("Testing Agent builder and Runner...")

rc = {
    "execution_type": "single",
    "roles": [{"name": "test_agent", "instruction": "You are a test agent", "model": "gpt-4o-mini"}]
}
try:
    factory = AgentFactory(rc, {})
    agent = factory.build()
    print(f"Agent built: {agent}")
except Exception as e:
    print("Agent build failed!")
    traceback.print_exc()
    sys.exit(1)

try:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="cs-agent-service",
        agent=agent,
        session_service=session_service
    )
    print("Runner initialized successfully")
except Exception as e:
    print("Runner initialization failed!")
    traceback.print_exc()

sys.exit(0)
