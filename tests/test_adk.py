import traceback
import sys

print("Testing ADK Imports...")

try:
    import google.adk.agents
    print("Successfully imported google.adk.agents")
except Exception as e:
    print("Failed to import google.adk.agents!")
    traceback.print_exc()

try:
    from google.adk.runners import Runner
    print("Successfully imported google.adk.runners.Runner")
except Exception as e:
    print("Failed to import google.adk.runners.Runner!")
    traceback.print_exc()

sys.exit(0)
