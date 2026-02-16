"""
Multi-Agent A2A Demo - Client Examples

This script demonstrates how to use each of the 4 patterns.
Run after starting docker-compose.multi-agent.yml
"""

import asyncio
import aiohttp
from a2a.client import A2AClient
from typing import Any


# ============================================================================
# PATTERN 1: Sequential Pipeline
# ============================================================================
async def sequential_pipeline(query: str) -> str:
    """
    Researcher → Analyzer → Writer
    Each agent passes output to the next
    """
    print("\n" + "="*60)
    print("PATTERN 1: SEQUENTIAL PIPELINE")
    print("="*60)
    
    researcher = A2AClient("http://localhost:9101/")
    analyzer = A2AClient("http://localhost:9102/")
    writer = A2AClient("http://localhost:9103/")
    
    print(f"Query: {query}")
    print("\n[1/3] Running Researcher...")
    research = await researcher.send_message({"text": f"Research: {query}"})
    print(f"   → Research completed: {len(str(research))} chars")
    
    print("[2/3] Running Analyzer...")
    analysis = await analyzer.send_message({"text": f"Analyze: {research}"})
    print(f"   → Analysis completed: {len(str(analysis))} chars")
    
    print("[3/3] Running Writer...")
    final = await writer.send_message({"text": f"Write: {analysis}"})
    print(f"   → Final output: {len(str(final))} chars")
    
    return final


# ============================================================================
# PATTERN 2: Parallel Execution
# ============================================================================
async def parallel_execution(query: str) -> str:
    """
    Multiple agents work simultaneously, then aggregate
    """
    print("\n" + "="*60)
    print("PATTERN 2: PARALLEL EXECUTION")
    print("="*60)
    
    searcher = A2AClient("http://localhost:9201/")
    computer = A2AClient("http://localhost:9202/")
    aggregator = A2AClient("http://localhost:9203/")
    
    print(f"Query: {query}")
    print("\n[Running 3 agents in parallel...]")
    
    # Execute all simultaneously
    search_task = searcher.send_message({"text": f"Search: {query}"})
    compute_task = computer.send_message({"text": f"Compute: {query}"})
    
    search_result, compute_result = await asyncio.gather(search_task, compute_task)
    
    print(f"   → Search: {len(str(search_result))} chars")
    print(f"   → Compute: {len(str(compute_result))} chars")
    
    print("\n[Aggregating results...]")
    final = await aggregator.send_message({
        "text": f"Aggregate:\nSearch: {search_result}\n\nCompute: {compute_result}"
    })
    print(f"   → Aggregated: {len(str(final))} chars")
    
    return final


# ============================================================================
# PATTERN 3: Coordinator
# ============================================================================
async def coordinator_pattern(query: str) -> str:
    """
    Coordinator decides which agents to call dynamically
    """
    print("\n" + "="*60)
    print("PATTERN 3: COORDINATOR")
    print("="*60)
    
    coordinator = A2AClient("http://localhost:9301/")
    
    print(f"Query: {query}")
    print("\n[Coordinator analyzing and delegating...]")
    
    # Coordinator decides internally which agents to call
    result = await coordinator.send_message({"text": query})
    print(f"   → Result: {len(str(result))} chars")
    
    return result


# ============================================================================
# PATTERN 4: Hub-and-Spoke
# ============================================================================
async def hub_and_spoke(query: str) -> str:
    """
    Hub routes to appropriate spoke based on keywords
    """
    print("\n" + "="*60)
    print("PATTERN 4: HUB-AND-SPOKE")
    print("="*60)
    
    hub = A2AClient("http://localhost:9401/")
    
    print(f"Query: {query}")
    print("\n[Hub routing to appropriate spoke...]")
    
    # Hub will route based on keywords in query
    result = await hub.send_message({"text": query})
    print(f"   → Result: {len(str(result))} chars")
    
    return result


# ============================================================================
# MAIN DEMO
# ============================================================================
async def run_demo():
    """Run all patterns with the same query"""
    
    query = "What are the best practices for building Python microservices?"
    
    print("\n" + "#"*60)
    print("# MULTI-AGENT A2A DEMO")
    print("#"*60)
    print(f"\nTest Query: {query}")
    
    # Pattern 1: Sequential
    result1 = await sequential_pipeline(query)
    print(f"\n✓ Sequential complete")
    
    # Pattern 2: Parallel
    result2 = await parallel_execution(query)
    print(f"\n✓ Parallel complete")
    
    # Pattern 3: Coordinator
    result3 = await coordinator_pattern(query)
    print(f"\n✓ Coordinator complete")
    
    # Pattern 4: Hub-and-Spoke
    result4 = await hub_and_spoke(query)
    print(f"\n✓ Hub-and-Spoke complete")
    
    print("\n" + "#"*60)
    print("# ALL PATTERNS COMPLETE")
    print("#"*60)


if __name__ == "__main__":
    asyncio.run(run_demo())
