import pkgutil
import inspect
import google.adk

print("Modules in google.adk:")
for importer, modname, ispkg in pkgutil.walk_packages(path=google.adk.__path__, prefix=google.adk.__name__+'.'):
    if 'session' in modname or 'memory' in modname or 'service' in modname:
        print(modname)
        try:
            mod = __import__(modname, fromlist=["*"])
            for sub_name, obj in inspect.getmembers(mod):
                if inspect.isclass(obj) and ('Session' in sub_name or 'Service' in sub_name):
                    print(f"  Class: {sub_name}")
        except Exception:
            pass
