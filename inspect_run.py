import inspect
from google.adk.runners import Runner

print("Runner.run signature:")
print(inspect.signature(Runner.run))
