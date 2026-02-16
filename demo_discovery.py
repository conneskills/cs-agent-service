"""
Demo: Using the Discovery Agent

This script demonstrates how to use the Discovery Agent
to find and invoke agents from the LiteLLM Registry.

Usage:
    python demo_discovery.py
"""

import asyncio
import json


async def call_discovery_agent(query: str) -> str:
    """Call discovery agent via HTTP."""
    import uuid
    import aiohttp
    
    url = "http://localhost:9501/"
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
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            result = data.get("result", {})
            artifacts = result.get("artifacts", [])
            if artifacts:
                parts = artifacts[0].get("parts", [])
                texts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
                return "\n".join(texts)
            return str(result)


async def main():
    print("=" * 60)
    print("DISCOVERY AGENT DEMO")
    print("=" * 60)
    
    # Demo queries - Discovery
    discovery_queries = [
        "List all available agents",
        "Find agents that can do research",
        "What agents can help with coding?",
    ]
    
    for query in discovery_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print("=" * 60)
        
        result = await call_discovery_agent(query)
        
        print(f"\nResult:\n{result}")
        print()

    # Demo: Invoke an agent directly
    print("\n" + "=" * 60)
    print("INVOKE DEMO - Calling another agent directly")
    print("=" * 60)
    
    invoke_queries = [
        "invoke sequential-researcher with What is quantum computing?",
    ]
    
    for query in invoke_queries:
        print(f"\nQuery: {query}")
        print("-" * 40)
        
        result = await call_discovery_agent(query)
        
        # Show first 500 chars
        print(f"Result: {result[:500]}...")
        print()

    # Demo: Streaming invoke
    print("\n" + "=" * 60)
    print("STREAMING DEMO - Streaming from another agent")
    print("=" * 60)
    
    stream_query = "invoke sequential-researcher with Explain AI in 2 sentences stream"
    
    print(f"\nQuery: {stream_query}")
    print("-" * 40)
    print("Streaming response:")
    
    # Call with streaming
    result = await call_discovery_agent(stream_query)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
