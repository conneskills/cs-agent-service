from src.agent_factory import AgentFactory

rc = {
    "execution_type": "single",
    "roles": [{"name": "test_agent", "instruction": "You are a test agent", "model": "gpt-4o-mini"}]
}
factory = AgentFactory(rc, {})
agent = factory.build()

import sys
methods = [m for m in dir(agent) if callable(getattr(agent, m)) and not m.startswith("__")]
print("Callable methods:")
for m in methods:
    print(f"- {m}")

print("\nAll attributes:")
print(dir(agent))
sys.exit(0)
