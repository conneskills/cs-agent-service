import sys
import asyncio
import os
import json
from src.agent_factory import AgentFactory

async def main():
    rc = {
        "execution_type": "single",
        "roles": [{"name": "researcher", "instruction": "You are a research agent.", "model": "litellm/gemini-3.1-pro"}]
    }
    factory = AgentFactory(rc, {})
    agent = factory.build()

    print(f"Agent built: {agent.name}")
    print("Calling agent.run_async()...")
    
    try:
        from google.genai.types import Content, Part
        
        msg = Content(parts=[Part.from_text(text="Hola, ¿quién eres?")], role="user")
        
        # Iniciar ejecución
        events = agent.run_async(user_id="user1", session_id="sess1", new_message=msg)
        
        final_text = ""
        async for event in events:
            # En ADK 2.x los eventos suelen tener el atributo message
            if hasattr(event, "message") and event.message and event.message.parts:
                for p in event.message.parts:
                    if hasattr(p, "text") and p.text:
                        final_text += p.text
            
        if not final_text:
            print("No output received from agent events.")
        else:
            print(f"\n--- Result ---\n{final_text}\n--------------")
            
    except Exception as e:
        print(f"Run failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
