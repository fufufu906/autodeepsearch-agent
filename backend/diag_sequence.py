import traceback

def try_import(name):
    try:
        module = __import__(name)
        print(f"import {name} OK")
        return module
    except Exception:
        print(f"import {name} FAILED")
        traceback.print_exc()
        return None

modules = [
    'fastapi',
    'fastapi.openapi.models',
    'hello_agents',
    'hello_agents.tools',
    'src1.config',
    'src1.agent',
    'src1.main',
]

for m in modules:
    try_import(m)

