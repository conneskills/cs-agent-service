from src.agent_factory import AgentFactory

rc = {
    "execution_type": "single",
    "roles": [{"name": "test_agent", "instruction": "You are a test agent", "model": "gpt-4o-mini"}]
}
factory = AgentFactory(rc, {})
agent = factory.build()

print("Agent attributes:")
print(dir(agent))

if hasattr(agent, "invoke"):
    print("\nHas invoke method!")
else:
    print("\nDoes NOT have invoke method!")
