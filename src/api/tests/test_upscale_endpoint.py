"""The per-image upscale endpoint and the signals the UI reads (`B207`).

The pipeline itself (model, cap, backup, tiers) lives in
`ImagenOrchestrator.run_upscale` and needs the GPU; these cover the wiring —
what is refused, what is queued, and what the gallery is told.
"""

import pytest
from fastapi.testclient import TestClient

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType, ImageType, MediaImage
from transversal.imagen.orchestrator import UPSCALE_MASTER_CAP
from transversal.main import app

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

requires_db = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

ENTITY = "test-upscale-entity"
SMALL = "test-upscale-small"
BIG = "test-upscale-big"
LOOP = "test-upscale-loop"
EARLY = "2026-01-01T00:00:00+00:00"
UNIVERSE = "earth"


def _cleanup(repo):
    for image_id in (SMALL, BIG, LOOP):
        if repo.get_image(image_id) is not None:
            repo.delete_image(image_id)
    if repo.get_entity(ENTITY) is not None:
        repo.delete_entity(ENTITY, rmtree=True)


def _image(image_id, width, height, renders=(), roles=("background",)):
    return MediaImage(
        id=image_id, owner_kind="entity", owner_id=ENTITY, universe=UNIVERSE,
        image_type=ImageType.IMAGEN, renders=list(renders), roles=list(roles),
        width=width, height=height, filename=image_id, extension="webp", created_at=EARLY,
    )


def _fixtures(repo):
    _cleanup(repo)
    repo.create_entity(Entity(
        id=ENTITY, type=EntityType.LOCATION, name="Upscale Probe", current_universe=UNIVERSE,
    ))
    repo.create_image(_image(SMALL, 832, 1216))
    repo.create_image(_image(BIG, UPSCALE_MASTER_CAP, UPSCALE_MASTER_CAP))
    # A loop is a picture with an animated render now, not an `animated` type.
    repo.create_image(_image(LOOP, 832, 1216, renders=("animated",), roles=()))


def _stub_job(monkeypatch):
    """Replace the queued background task; return (module, calls)."""
    import transversal.api.rest.imagen as imagen_mod
    calls = []
    monkeypatch.setattr(imagen_mod, "_run_upscale_bg", lambda *a, **k: calls.append(a))
    return imagen_mod, calls


def _drain(imagen_mod, owner_id):
    """Drop the tracker entry for an owner, whatever campaign filed it (B305)."""
    for key in [
        k for k in list(imagen_mod.active_jobs)
        if k == owner_id or (isinstance(k, tuple) and k[-1] == owner_id)
    ]:
        imagen_mod.active_jobs.pop(key, None)
    for order in imagen_mod._job_order.values():
        if owner_id in order:
            order.remove(owner_id)


@requires_db
def test_upscale_queues_a_job_keyed_by_the_owner(monkeypatch):
    repo = _repo
    _fixtures(repo)
    imagen_mod, calls = _stub_job(monkeypatch)
    client = TestClient(app)

    try:
        r = client.post(f"/api/v1/upscale/{SMALL}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["accepted"] is True
        assert body["owner_id"] == ENTITY
        # The gallery that offered the button polls jobs[owner_id], so the key
        # matters as much as the call.
        assert calls == [(ENTITY, SMALL)]
        # Asserted through the surface the gallery actually polls: the tracker is keyed
        # by (campaign, owner) now, and this read is what has to keep working (B305).
        jobs = client.get("/api/v1/imagen/jobs").json()["jobs"]
        assert jobs[ENTITY]["type"] == "upscale"
    finally:
        _drain(imagen_mod, ENTITY)
        _cleanup(repo)


@requires_db
def test_upscale_refuses_an_image_already_at_the_ceiling(monkeypatch):
    """Nothing to gain: a master at the cap cannot get bigger than what is served."""
    repo = _repo
    _fixtures(repo)
    imagen_mod, calls = _stub_job(monkeypatch)
    client = TestClient(app)

    try:
        r = client.post(f"/api/v1/upscale/{BIG}")
        assert r.status_code == 400
        assert "ceiling" in r.json()["detail"]
        assert calls == [], "nothing may be queued"
    finally:
        _drain(imagen_mod, ENTITY)
        _cleanup(repo)


@requires_db
def test_upscale_refuses_a_loop(monkeypatch):
    repo = _repo
    _fixtures(repo)
    imagen_mod, calls = _stub_job(monkeypatch)
    client = TestClient(app)

    try:
        r = client.post(f"/api/v1/upscale/{LOOP}")
        assert r.status_code == 400
        assert "still images" in r.json()["detail"]
        assert calls == []
    finally:
        _drain(imagen_mod, ENTITY)
        _cleanup(repo)


def test_upscale_unknown_image_is_404():
    client = TestClient(app)
    assert client.post("/api/v1/upscale/test-upscale-absent").status_code == 404


@requires_db
def test_the_list_offers_upscale_only_below_the_ceiling():
    """This is what decides whether the button appears and whether the XL tag does."""
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    try:
        listing = client.get(f"/api/v1/imagen/{ENTITY}").json()["images"]
        rows = {i["id"]: i for i in listing}
        assert rows[SMALL]["can_upscale"] is True
        assert rows[BIG]["can_upscale"] is False
        # Untouched images have no backup, so `upscaled` is false for both.
        assert rows[SMALL]["upscaled"] is False

        # The backup file is what marks an image as already through the pass.
        import os
        backup_dir = f"/app/media/imagen/{ENTITY}/{UNIVERSE}"
        os.makedirs(backup_dir, exist_ok=True)
        with open(f"{backup_dir}/{SMALL}_PreUpscale.webp", "wb") as fh:
            fh.write(b"x")
        listing = client.get(f"/api/v1/imagen/{ENTITY}").json()["images"]
        rows = {i["id"]: i for i in listing}
        assert rows[SMALL]["upscaled"] is True
    finally:
        _cleanup(repo)
