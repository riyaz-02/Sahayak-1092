"""ASGI application entrypoint.

Production deployments can target `backend.app:app`. The existing
`backend.main:app` entrypoint remains supported for local development and
backward compatibility.
"""

from backend.main import app

__all__ = ["app"]
