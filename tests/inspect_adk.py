import httpx
import asyncio
import json

async def main():
    url = "http://localhost:9100/"
    
    # Estructura típica de JSON-RPC para A2A task.execute
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "task.execute",
        "params": {
            "task": {
                "id": "task-1",
                "context_id": "ctx-1",
                "message": {
                    "role": "user",
                    "parts": [{"text": "Hola, ¿cuál es tu rol?"}]
                }
            }
        }
    }
    
    print(f"Sending request to {url}...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=30.0)
            print(f"Status: {resp.status_code}")
            print("Response:")
            print(json.dumps(resp.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
