"""Host → fork resolution (B88) — the last piece of per-request routing.

A fork is an ArangoDB database, and a request names its fork in the **host**:
``daves-game.transversal.app``. This middleware reads that label, looks the fork up
in the registry, and scopes the request with ``use_database()``, so every
``get_db()`` inside it resolves to the right database without any caller knowing
which campaign it is serving.

It is **inert unless ``FORKS_BASE_DOMAIN`` is set**, so today's single-database
behaviour is unchanged until there is a domain for forks to hang off.

Three rules worth stating because each is a failure mode:

- **The tenancy tier is never scoped.** ``/api/v1/accounts`` and ``/api/v1/forks``
  act on the registry, which lives *beside* every campaign — signing in has to work
  on a campaign host, and the switcher has to list forks it is not inside.
- **An unknown label is a 404, never a fallback.** Falling back to the default
  database would serve the owner's own game to a stranger's typo.
- **Only a first-level label counts**, matching the certificate coverage: the slug
  is the whole label, and ``a.b.transversal.app`` is not a fork host.

A pure ASGI middleware rather than ``BaseHTTPMiddleware`` on purpose: the context
variable has to be set in the same task that runs the endpoint, and
``BaseHTTPMiddleware`` runs the downstream app in a child task.
"""

from __future__ import annotations

import os

from starlette.responses import JSONResponse

from transversal.db.arango import use_database
from transversal.db.registry_repository import RegistryRepository

#: Registry-backed routes: they name no campaign because they *choose* one.
TENANCY_PREFIXES = ("/api/v1/accounts", "/api/v1/forks")


def base_domain() -> str:
    """The domain forks hang off. Empty means host resolution is switched off."""
    return (os.getenv("FORKS_BASE_DOMAIN", "") or "").strip().strip(".").lower()


def slug_from_host(host: str, base: str) -> str | None:
    """The campaign label in ``host``, or None when this is not a fork host.

    None covers the apex (``transversal.app``), an unrelated domain, a deeper name
    (``a.b.transversal.app``) and a missing base. All of those mean "no campaign
    named here", which is different from "no such campaign" — one is routed
    normally, the other is a 404.
    """
    host = (host or "").split(":", 1)[0].strip().lower()
    base = (base or "").strip(".").lower()
    if not host or not base or not host.endswith("." + base):
        return None
    label = host[: -(len(base) + 1)]
    if not label or "." in label:
        return None
    return label


def _header(scope, name: bytes) -> str:
    for key, value in scope.get("headers", []) or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


class ForkScopeMiddleware:
    """Scope every request to the fork its host names."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        base = base_domain()
        path = scope.get("path", "")
        if not base or path.startswith(TENANCY_PREFIXES):
            return await self.app(scope, receive, send)

        slug = slug_from_host(_header(scope, b"host"), base)
        if not slug:
            return await self.app(scope, receive, send)

        fork = RegistryRepository().find_fork_by_slug(slug)
        if fork is None:
            response = JSONResponse({"detail": "no such campaign"}, status_code=404)
            return await response(scope, receive, send)

        with use_database(fork.database):
            return await self.app(scope, receive, send)
