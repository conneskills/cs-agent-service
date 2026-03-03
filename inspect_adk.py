import inspect
from google.adk.runners import Runner
import google.adk

print("Runner init signature:")
print(inspect.signature(Runner.__init__))

try:
    import google.adk.services
    print("\nServices available in ADK:")
    for name in dir(google.adk.services):
        if not name.startswith("_"):
            print(name)
except ImportError:
    print("\ngoogle.adk.services module not found")

try:
    from google.adk.services.session import InMemorySessionService
    print("\nInMemorySessionService available!")
except Exception:
    pass
