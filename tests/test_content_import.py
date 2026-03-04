import sys
import traceback

print("Trying to find Content...")
try:
    from google.genai.types import Content
    print("Found in google.genai.types!")
except ImportError:
    pass

try:
    from google.adk.flows.llm_flows.types import Content
    print("Found in google.adk.flows.llm_flows.types")
except ImportError:
    pass

try:
    # Just inspect what google.adk exports!
    import google.adk
    for key in dir(google.adk):
        if key == 'types':
            print("google.adk has types attribute!")
except Exception as e:
    traceback.print_exc()

sys.exit(0)
