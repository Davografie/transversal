"""SEC-4 — request values must never become filesystem path components.

Rejection cases need no database; the stored-value case stubs the repository.
"""

import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from transversal.api.rest import media as media_mod


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    return buf.getvalue()


def _upload(filename="a.png", data=None) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data if data is not None else _png_bytes()),
        filename=filename,
    )


class _FakeRepo:
    def __init__(self, universe: str):
        self._universe = universe

    def get_entity(self, entity_id):
        return SimpleNamespace(current_universe=self._universe)


@pytest.mark.parametrize(
    "bad", ["../../etc/passwd", "..", "../evil", "a/b", ".hidden", "a\\b", "a\x00b"]
)
async def test_traversal_entity_id_is_rejected(bad):
    with pytest.raises(HTTPException) as exc:
        await media_mod.upload_media(entity_id=bad, universe="", file=_upload())
    assert exc.value.status_code == 400


@pytest.mark.parametrize("bad", ["../../etc", "..", "a/b", ".hidden"])
async def test_traversal_universe_is_rejected(bad):
    with pytest.raises(HTTPException) as exc:
        await media_mod.upload_media(entity_id="", universe=bad, file=_upload())
    assert exc.value.status_code == 400


async def test_svg_upload_is_refused():
    """SVG is stored verbatim and served same-origin — stored XSS."""
    with pytest.raises(HTTPException) as exc:
        await media_mod.upload_media(
            entity_id="", universe="", file=_upload("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        )
    assert exc.value.status_code == 400


def test_svg_is_not_an_allowed_upload_extension():
    assert ".svg" not in media_mod.ALLOWED_EXTENSIONS


async def test_valid_upload_lands_inside_the_media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(media_mod, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(media_mod, "IMAGEN_DIR", tmp_path / "imagen")

    res = await media_mod.upload_media(entity_id="", universe="", file=_upload())

    written = tmp_path / res["filename"]
    assert written.exists()
    assert written.parent == tmp_path
    assert res["path"] == f"/media/{res['filename']}"


async def test_bad_stored_universe_cannot_traverse(tmp_path, monkeypatch):
    """A malicious universe already in the data must not escape either."""
    monkeypatch.setattr(media_mod, "MEDIA_DIR", tmp_path)
    monkeypatch.setattr(media_mod, "IMAGEN_DIR", tmp_path / "imagen")
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: _FakeRepo("../../evil"))

    res = await media_mod.upload_media(entity_id="loc-1", universe="", file=_upload())

    assert res["image_id"] is None  # registration skipped, not written
    assert not (tmp_path.parent / "evil").exists()
