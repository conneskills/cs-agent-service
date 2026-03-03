import sys
import traceback
import asyncio
from src.agent_factory import AgentFactory

async def main():
    rc = {
        "execution_type": "single",
        "roles": [{"name": "test_agent", "instruction": "You are a test agent", "model": "gpt-4o-mini"}]
    }
    factory = AgentFactory(rc, {})
    agent = factory.build()

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk import types
    
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="cs-agent-service",
        agent=agent,
        session_service=session_service
    )
    print("Runner initialized. Now calling run...")
    try:
        content = types.Content(parts=[types.Part.from_text("Hello!")], role="user")
        events = runner.run(user_id="user1", session_id="sess1", new_message=content)
        
        final_text = ""
        # events could be async generator or sync generator
        if hasattr(events, "__aiter__"):
            async for event in events:
                if isinstance(event, types.events.ModelOutput):
                    if event.message and event.message.parts:
                        for p in event.message.parts:
                            if p.text: final_text += p.text
        else:
            for event in events:
                if isinstance(event, types.events.ModelOutput):
                    if event.message and event.message.parts:
                        for p in event.message.parts:
                            if p.text: final_text += p.text
                            
        print(f"Final response: {final_text}")
    except Exception as e:
        print("Run failed!")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
