"""SEC-4 — request values must never become filesystem path components.

Rejection cases need no database; the stored-value case stubs the repository.
"""

import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from transversal.api.rest import media as media_mod
from transversal.services import media_store

#: The campaign an upload belongs to. Media is written under
#: ``<MEDIA_ROOT>/<campaign>/…`` (B88), so these tests read it from where the code
#: writes it rather than naming a root of their own — the constants they used to
#: patch are gone, and a patch that no longer reaches the code is worse than none.
CAMPAIGN = "test-campaign"


@pytest.fixture(autouse=True)
def _media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(media_store, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(media_store, "campaign_name", lambda: CAMPAIGN)


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    return buf.getvalue()


def _upload(filename="a.png", data=None) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data if data is not None else _png_bytes()),
        filename=filename,
    )


class _Tasks:
    """Stands in for FastAPI's BackgroundTasks."""

    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


class _FakeRepo:
    def __init__(self, universe: str, entity_type: str = "character"):
        self._universe = universe
        self._entity_type = entity_type

    def get_entity(self, entity_id):
        return SimpleNamespace(
            current_universe=self._universe, universes=[self._universe],
            type=self._entity_type, name="Probe",
        )


@pytest.mark.parametrize(
    "bad", ["../../etc/passwd", "..", "../evil", "a/b", ".hidden", "a\\b", "a\x00b"]
)
async def test_traversal_entity_id_is_rejected(bad):
    with pytest.raises(HTTPException) as exc:
        await media_mod.upload_media(_Tasks(), entity_id=bad, universe="", file=_upload())
    assert exc.value.status_code == 400


@pytest.mark.parametrize("bad", ["../../etc", "..", "a/b", ".hidden"])
async def test_traversal_universe_is_rejected(bad):
    with pytest.raises(HTTPException) as exc:
        await media_mod.upload_media(_Tasks(), entity_id="", universe=bad, file=_upload())
    assert exc.value.status_code == 400


async def test_svg_upload_is_refused():
    """SVG is stored verbatim and served same-origin — stored XSS."""
    with pytest.raises(HTTPException) as exc:
        await media_mod.upload_media(_Tasks(), 
            entity_id="", universe="", file=_upload("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        )
    assert exc.value.status_code == 400


def test_svg_is_not_an_allowed_upload_extension():
    assert ".svg" not in media_mod.ALLOWED_EXTENSIONS


async def test_valid_upload_lands_inside_the_media_dir(tmp_path, monkeypatch):

    res = await media_mod.upload_media(_Tasks(), entity_id="", universe="", file=_upload())

    written = tmp_path / CAMPAIGN / res["filename"]
    assert written.exists()
    assert written.parent == tmp_path / CAMPAIGN
    assert res["path"] == f"/media/{res['filename']}"


async def test_bad_stored_universe_cannot_traverse(tmp_path, monkeypatch):
    """A malicious universe already in the data must not escape either."""
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: _FakeRepo("../../evil"))

    res = await media_mod.upload_media(_Tasks(), entity_id="loc-1", universe="", file=_upload())

    assert res["image_id"] is None  # registration skipped, not written
    assert not (tmp_path.parent / "evil").exists()


class _RecordingRepo:
    """Captures what the upload registers, so the rung it lands on can be read."""

    def __init__(self, universe="earth"):
        self._universe = universe
        self.created = []
        self.updated = {}

    def get_entity(self, entity_id):
        return SimpleNamespace(
            current_universe=self._universe, universes=[self._universe],
            type="character", name="Probe",
        )

    def get_trait(self, trait_id):
        return SimpleNamespace(universes=[self._universe])

    def get_images_for_owner(self, owner_id, variant_id=None):
        # After `create_image`, so this is the sole-image rule's view.
        return [i for i in self.created if (i.variant_id or None) == variant_id]

    def create_image(self, image):
        self.created.append(image)
        return image

    def update_image(self, image_id, updates):
        self.updated.setdefault(image_id, {}).update(updates)
        return next((i for i in self.created if i.id == image_id), None)


async def test_a_colon_bearing_variant_id_is_accepted(tmp_path, monkeypatch):
    """The per-instance override is addressed by a **traitsetting id**, and every
    live one contains a colon (`faction-44351398:trait-description`). Validating it
    with the path pattern made every one of them a 400, which put the whole
    override out of reach — the file has never named the variant.
    """
    repo = _RecordingRepo()
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: repo)

    setting = "faction-44351398:trait-description"
    res = await media_mod.upload_media(_Tasks(), 
        owner_kind="trait", owner_id="trait-probe", variant_id=setting,
        universe="", file=_upload(),
    )

    assert res["image_id"], "the upload registered"
    assert repo.created[0].variant_id == setting, "the rung is the setting"
    # The file names the owner, never the variant: the variant is metadata.
    assert (tmp_path / CAMPAIGN / "imagen" / "trait-probe" / "earth").is_dir()
    # And the sole-image rule fires on that rung, so the first instance picture
    # overrides the definition for every role without a tagging step.
    assert repo.updated[res["image_id"]]["roles"] == ["background", "sheet", "navdot"]


async def test_a_variant_id_cannot_reach_the_filesystem(tmp_path, monkeypatch):
    """It is an id, not a path, so traversal in it is inert — the file lands under
    the owner's directory whatever it says."""
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: _RecordingRepo())

    res = await media_mod.upload_media(_Tasks(), 
        owner_kind="trait", owner_id="trait-probe", variant_id="../../evil",
        universe="", file=_upload(),
    )

    assert res["image_id"]
    written = [p for p in (tmp_path / CAMPAIGN / "imagen").rglob("*") if p.is_file()]
    assert written and all("trait-probe" in str(p) for p in written)
    assert not (tmp_path.parent / "evil").exists()


async def test_a_control_character_in_a_variant_id_is_refused(tmp_path, monkeypatch):
    """Bounded rather than path-checked — it is stored and echoed in the list."""
    with pytest.raises(HTTPException) as exc:
        await media_mod.upload_media(_Tasks(), 
            owner_kind="trait", owner_id="trait-probe", variant_id="a\nb",
            universe="", file=_upload(),
        )
    assert exc.value.status_code == 400


# ── An occupant's or a trait's picture gets a matte on its own ([[B214]]) ──


async def test_an_occupant_upload_queues_a_matte(tmp_path, monkeypatch):
    """A character's picture is a subject, so the matte is part of the upload —
    queued, because the response must not wait on the GPU."""
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: _RecordingRepo())
    tasks = _Tasks()

    res = await media_mod.upload_media(
        tasks, owner_kind="entity", owner_id="char-1", universe="", file=_upload(),
    )

    assert res["image_id"]
    assert len(tasks.tasks) == 1, "exactly one job queued"
    fn, args, _ = tasks.tasks[0]
    assert fn.__name__ == "_run_remove_bg_bg"
    assert args[:2] == ("char-1", res["image_id"])


async def test_a_trait_upload_queues_a_matte(tmp_path, monkeypatch):
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: _RecordingRepo())
    tasks = _Tasks()

    await media_mod.upload_media(
        tasks, owner_kind="trait", owner_id="trait-1", universe="", file=_upload(),
    )

    assert len(tasks.tasks) == 1


async def test_a_location_upload_queues_nothing(tmp_path, monkeypatch):
    """A room is a scene: there is nothing to cut out of it, and the GPU pass
    would be wasted."""
    monkeypatch.setattr(
        media_mod, "EntityRepository", lambda: _FakeRepo("earth", entity_type="location")
    )
    tasks = _Tasks()

    res = await media_mod.upload_media(
        tasks, owner_kind="entity", owner_id="loc-1", universe="", file=_upload(),
    )

    assert res["image_id"], "it still uploads"
    assert tasks.tasks == [], "but nothing is cut out"
