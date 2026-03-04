import asyncio
from a2a.client import A2AClient
from a2a.types import Message, TextPart

async def main():
    url = "http://localhost:9100"
    print(f"Connecting to {url} via A2AClient...")
    
    async with A2AClient(url) as client:
        try:
            # El cliente maneja el protocolo JSON-RPC internamente
            response = await client.send_message(
                message=Message(
                    role="user",
                    parts=[TextPart(text="Hola, preséntate brevemente.")]
                ),
                context_id="test-session-123"
            )
            print("\n--- Agent Response ---")
            print(response)
            print("----------------------")
        except Exception as e:
            print(f"A2A Request failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
