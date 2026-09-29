"""SEC-7 — CORS must be an allowlist, not a wildcard.

Nothing in a supported deployment needs CORS (the app is same-origin: both the
Vite dev server and the nginx edge proxy ``/api``), so the assertion that matters
is simply that no page anywhere can read API responses by default. Importing
``transversal.main`` builds the real middleware stack; the rest are direct unit
tests of the origin resolver.
"""

from fastapi.middleware.cors import CORSMiddleware

from transversal import main


def _cors_kwargs() -> dict:
    for middleware in main.app.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware.kwargs
    raise AssertionError("CORSMiddleware is not installed on the app")


def test_middleware_does_not_allow_every_origin():
    origins = _cors_kwargs()["allow_origins"]
    assert "*" not in origins, "the CORS wildcard is back"


def test_defaults_are_specific_origins(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    origins = main._cors_origins()
    assert origins, "an empty allowlist silently disables CORS entirely"
    assert "*" not in origins
    assert all(o.startswith("http://") for o in origins)


def test_env_override_is_honoured_and_trimmed(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS", "https://a.example, https://b.example ,"
    )
    assert main._cors_origins() == ["https://a.example", "https://b.example"]


def test_blank_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "   ")
    assert "*" not in main._cors_origins()
