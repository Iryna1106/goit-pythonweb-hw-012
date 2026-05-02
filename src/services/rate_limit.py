"""Shared SlowAPI rate limiter used across all routers.

The single :data:`limiter` instance is reused so the running app has
one coherent state. It is also published as ``app.state.limiter`` in
:mod:`main` so SlowAPI middleware can find it.

Tests can disable enforcement by toggling ``limiter.enabled = False``
(see ``tests/integration/conftest.py``).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
"""Process-wide rate limiter keyed by the client's remote IP."""
