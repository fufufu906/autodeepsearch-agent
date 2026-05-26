import traceback
import pydantic
import pydantic_core
import fastapi

print('pydantic', pydantic.__version__)
print('pydantic_core', pydantic_core.__version__)
print('fastapi', fastapi.__version__)
try:
    from fastapi.openapi import models
    print('imported fastapi.openapi.models OK')
except Exception:
    traceback.print_exc()

