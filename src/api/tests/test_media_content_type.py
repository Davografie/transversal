"""SEC-10 — media must declare its real content type, and only then send nosniff.

python:3.12-slim's ``mimetypes`` database has no ``.webp``, so ``StaticFiles``
declared generated images ``application/octet-stream``. Browsers sniffed them
back into place, which is why it went unnoticed; the declared type was wrong and
it made ``X-Content-Type-Options: nosniff`` unsafe (it would have blanked every
image in the game).

Both halves are asserted here together because they are only correct together: a
registered type with no header loses the hardening, and the header without the
type breaks images.
"""

import mimetypes

from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.main import CachedStaticFiles


def _client(tmp_path) -> TestClient:
    app = FastAPI()
    app.mount("/media", CachedStaticFiles(directory=str(tmp_path)))
    return TestClient(app)


def test_webp_registration_survives_import():
    """Importing the app is what registers the type — the mount depends on it."""
    assert mimetypes.guess_type("image.webp")[0] == "image/webp"


def test_webm_registration_survives_import():
    assert mimetypes.guess_type("loop.webm")[0] == "video/webm"


def test_webp_is_served_with_the_right_type_and_nosniff(tmp_path):
    (tmp_path / "a.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    response = _client(tmp_path).get("/media/a.webp")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_webm_is_served_with_the_right_type_and_nosniff(tmp_path):
    (tmp_path / "a.webm").write_bytes(b"\x1a\x45\xdf\xa3")
    response = _client(tmp_path).get("/media/a.webm")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/webm"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_long_lived_caching_is_retained(tmp_path):
    (tmp_path / "a.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    response = _client(tmp_path).get("/media/a.webp")
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
