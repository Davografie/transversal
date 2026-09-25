"""Tests for the generalised image owner (`B200`).

An image belongs to an **owner** — an entity or a trait — and optionally to the
tier below it (``variant_id``: a projection for an entity, a traitsetting for a
trait). These exercise the resolution ladder and the owner/legacy field
invariant. The repository tests run against live ArangoDB with namespaced
fixture ids and skip when it is unavailable; stubbing the ladder would only test
the stub.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from transversal.db.repository import EntityRepository
from transversal.main import app
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    ImageType,
    MediaImage,
    Projection,
    RatingType,
    Trait,
    TraitSet,
    TraitSetting,
    TransversalType,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

requires_db = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

TRAIT = "test-imgowner-trait"
TRAITSET = "test-imgowner-ts"
ENTITY = "test-imgowner-entity"
PROJ = "test-imgowner-proj"
SETTING = "test-imgowner-setting"

DEF_ID = "test-imgowner-def"
NEWER_ID = "test-imgowner-newer"
VAR_ID = "test-imgowner-var"
ENT_ID = "test-imgowner-ent"

EARLY = "2026-01-01T00:00:00+00:00"
LATE = "2026-02-01T00:00:00+00:00"


# ── The model invariant (no database) ─────────────────


def test_owner_fields_and_legacy_pair_stay_in_sync():
    """Both representations of "whose image is this" must agree, whichever the
    caller wrote. A raw dict merge that updates one and not the other is how
    resolution silently reads a stale owner."""
    # A row written the old way derives the owner.
    legacy = MediaImage(
        id="x1", entity_id="character-kael", projection_id="proj-1",
        universe="earth", image_type=ImageType.UPLOADED,
    )
    assert (legacy.owner_kind, legacy.owner_id, legacy.variant_id) == (
        "entity", "character-kael", "proj-1",
    )

    # A trait row has no entity at all, and must not invent one.
    trait = MediaImage(
        id="x2", owner_kind="trait", owner_id=TRAIT,
        universe="three_realms", image_type=ImageType.IMAGEN,
    )
    assert trait.entity_id == "" and trait.projection_id is None
    assert trait.variant_id is None  # owner-level = the definition image

    # A row written the new way fills the legacy pair for the older code still
    # reading the shared database.
    new = MediaImage(
        id="x3", owner_kind="entity", owner_id="loc-abc", variant_id="proj-2",
        universe="earth", image_type=ImageType.IMAGEN,
    )
    assert (new.entity_id, new.projection_id) == ("loc-abc", "proj-2")


# ── Fixtures ──────────────────────────────────────────


def _cleanup(repo):
    """Idempotent teardown, safe on a partial run.

    Guarded on existence throughout: `delete_image` raises on a missing key (it
    has no ignore-missing branch), and a teardown that explodes on a clean
    database hides the failure it was running to report.
    """
    for iid in (DEF_ID, NEWER_ID, VAR_ID, ENT_ID):
        if repo.get_image(iid) is not None:
            repo.delete_image(iid)
    # A traitset cascades its traits, and a trait now cascades its own images.
    if repo.get_traitset_by_id(TRAITSET) is not None:
        repo.delete_traitset(TRAITSET)
    if repo.get_entity(ENTITY) is not None:
        repo.delete_entity(ENTITY, rmtree=True)  # cascades projection + images


def _fixtures(repo):
    _cleanup(repo)
    repo.create_traitset(TraitSet(
        id=TRAITSET, name="ImgOwnerProbe", universes=["three_realms", "earth"],
    ))
    # One trait spanning two universes: the case that motivates one picture per
    # trait rather than one per (trait, universe).
    repo.create_trait(Trait(
        id=TRAIT, name="ImgOwnerSpiritHerb", universes=["three_realms", "earth"],
        traitset_id=TRAITSET, explanation="a faintly glowing herb",
    ))
    repo.create_entity(Entity(
        id=ENTITY, type=EntityType.GMC, name="ImgOwnerProbe",
        current_universe="earth",
    ))
    repo.create_projection(Projection(
        id=PROJ, entity_id=ENTITY, origin_universe="earth", universe="earth",
        transversal_type=TransversalType.NATIVE,
    ))
    repo.create_traitsetting(TraitSetting(
        id=SETTING, entity_id=ENTITY, trait_id=TRAIT,
        from_type="projection", projection_id=PROJ,
        rating_type=RatingType.STATIC, dice=[DieType.D8],
    ))


def _trait_image(image_id, *, universe="three_realms", roles=("sheet",),
                 variant_id=None, created_at=EARLY, filename=None):
    return MediaImage(
        id=image_id, owner_kind="trait", owner_id=TRAIT, variant_id=variant_id,
        universe=universe, image_type=ImageType.IMAGEN, roles=list(roles),
        filename=filename or f"probe_{image_id}", extension="webp",
        created_at=created_at,
    )


# ── Trait-owned images ────────────────────────────────


@requires_db
def test_trait_definition_image_resolves_by_role():
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))

    url = repo.resolve_role_image(TRAIT, "sheet")
    assert url == f"/media/imagen/{TRAIT}/three_realms/probe_{DEF_ID}_Large.webp"

    entry = repo.resolve_role_image_entry(TRAIT, "sheet")
    assert entry is not None
    assert (entry.owner_kind, entry.owner_id, entry.variant_id) == ("trait", TRAIT, None)
    # A role the image does not carry resolves to nothing, not to the image.
    assert repo.resolve_role_image(TRAIT, "navdot") is None
    _cleanup(repo)


@requires_db
def test_one_trait_image_serves_every_universe():
    """The picture is stored in one universe but the trait spans two, and no
    projection supplies a universe to match — so the owner-level rung answers,
    which is what makes a single canonical image enough (663 of 802 live traits
    span more than one universe)."""
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID, universe="three_realms"))
    assert repo.resolve_role_image(TRAIT, "sheet") is not None

    # And it still answers when the request carries a variant that has no image
    # of its own: the traitsetting tier is empty, so it falls through.
    assert repo.resolve_role_image(TRAIT, "sheet", SETTING) is not None
    _cleanup(repo)


@requires_db
def test_newest_trait_image_wins():
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID, created_at=EARLY))
    repo.create_image(_trait_image(NEWER_ID, created_at=LATE))

    url = repo.resolve_role_image(TRAIT, "sheet")
    assert NEWER_ID in url and DEF_ID not in url
    _cleanup(repo)


@requires_db
def test_traitsetting_override_wins_and_falls_back():
    """The instance tier beats the definition, and the definition catches a role
    the override does not carry — the ladder slice 2 will lean on."""
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID, roles=("sheet",)))
    repo.create_image(_trait_image(
        VAR_ID, roles=("sheet",), variant_id=SETTING, created_at=LATE,
    ))

    assert VAR_ID in repo.resolve_role_image(TRAIT, "sheet", SETTING)

    # The override carries background only, so a sheet request falls back to the
    # definition rather than returning the wrong picture.
    repo.update_image(VAR_ID, {"roles": ["background"]})
    assert DEF_ID in repo.resolve_role_image(TRAIT, "sheet", SETTING)
    assert VAR_ID in repo.resolve_role_image(TRAIT, "background", SETTING)
    _cleanup(repo)


@requires_db
def test_get_images_for_owner_separates_the_tiers():
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))
    repo.create_image(_trait_image(VAR_ID, variant_id=SETTING))

    definition = repo.get_images_for_owner(TRAIT)
    assert [i.id for i in definition] == [DEF_ID]
    assert [i.id for i in repo.get_images_for_owner(TRAIT, SETTING)] == [VAR_ID]
    _cleanup(repo)


@requires_db
def test_delete_trait_cascades_its_images():
    """A trait is an owner now, so deleting it must take its images with it —
    otherwise it seeds exactly the orphan class already known to exist."""
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))
    assert repo.get_image(DEF_ID) is not None

    assert repo.delete_trait(TRAIT) is True
    assert repo.get_image(DEF_ID) is None
    _cleanup(repo)


@requires_db
async def test_deleting_a_trait_image_removes_its_files(tmp_path, monkeypatch):
    """The variants must go with the record.

    This is the bug the generalisation introduced and the suite could not see:
    `delete_image` built the directory from the legacy `entity_id`, which is
    empty for a trait, so it looked in the wrong place, deleted the row and left
    the files behind. Asserting the row alone passes either way.
    """
    import transversal.imagen.orchestrator as orch

    repo = _repo
    _fixtures(repo)

    monkeypatch.setattr(orch, "IMAGEN_DIR", tmp_path / "imagen")
    monkeypatch.setattr(orch, "ANIMATED_DIR", tmp_path / "animated")
    image_dir = tmp_path / "imagen" / TRAIT / "three_realms"
    image_dir.mkdir(parents=True)
    variant = image_dir / f"probe_{DEF_ID}_Large.webp"
    variant.write_bytes(b"not really a webp")

    repo.create_image(_trait_image(DEF_ID))
    assert variant.exists()

    orchestrator = orch.ImagenOrchestrator(repository=repo)
    # `delete_image` returns the deleted document (truthy), not a bool.
    assert await orchestrator.delete_image(DEF_ID)

    assert not variant.exists()
    # And the empty tree it lived in goes too, rather than leaving a bare
    # owner/universe pair behind for every deleted image.
    assert not image_dir.exists()
    assert repo.get_image(DEF_ID) is None
    _cleanup(repo)


# ── Entity behaviour, unchanged by the generalisation ─

@requires_db
def test_entity_projection_falls_back_to_the_entity_image():
    """Regression guard for the ladder rewrite: a projection with no image of its
    own still resolves the entity-level one."""
    repo = _repo
    _fixtures(repo)
    repo.create_image(MediaImage(
        id=ENT_ID, owner_kind="entity", owner_id=ENTITY, universe="earth",
        image_type=ImageType.IMAGEN, roles=["sheet"],
        filename=f"probe_{ENT_ID}", extension="webp", created_at=EARLY,
    ))

    assert ENT_ID in repo.resolve_role_image(ENTITY, "sheet", PROJ)
    assert ENT_ID in repo.resolve_role_image(ENTITY, "sheet", None)
    _cleanup(repo)


@requires_db
def test_projection_image_still_wins_for_its_body():
    repo = _repo
    _fixtures(repo)
    repo.create_image(MediaImage(
        id=ENT_ID, owner_kind="entity", owner_id=ENTITY, universe="earth",
        image_type=ImageType.IMAGEN, roles=["sheet"],
        filename=f"probe_{ENT_ID}", extension="webp", created_at=EARLY,
    ))
    repo.create_image(MediaImage(
        id=VAR_ID, owner_kind="entity", owner_id=ENTITY, variant_id=PROJ,
        universe="earth", image_type=ImageType.IMAGEN, roles=["sheet"],
        filename=f"probe_{VAR_ID}", extension="webp", created_at=EARLY,
    ))

    assert VAR_ID in repo.resolve_role_image(ENTITY, "sheet", PROJ)
    # With no projection named, only the definition tier is considered.
    assert ENT_ID in repo.resolve_role_image(ENTITY, "sheet", None)
    _cleanup(repo)


# ── Uploading to a trait owner ────────────────────────


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 200, 90)).save(buf, format="PNG")
    return buf.getvalue()


@requires_db
def test_upload_registers_an_image_for_a_trait_owner():
    """The upload endpoint speaks owners, and a trait's first image takes all
    three roles by the sole-image rule — so one upload renders everywhere."""
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    r = client.post(
        f"/api/v1/media/upload?owner_kind=trait&owner_id={TRAIT}&universe=three_realms",
        files={"file": ("spirit-herb.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 200, r.text
    image_id = r.json()["image_id"]
    assert image_id

    try:
        img = repo.get_image(image_id)
        assert img is not None
        assert (img.owner_kind, img.owner_id, img.variant_id) == ("trait", TRAIT, None)
        assert img.roles == ["background", "sheet", "navdot"]
        assert img.universe == "three_realms"
        # It answers for every role surface, and for a traitsetting tier that has
        # no image of its own.
        for role in ("sheet", "background", "navdot"):
            assert image_id in repo.resolve_role_image(TRAIT, role)
        assert image_id in repo.resolve_role_image(TRAIT, "sheet", SETTING)

        # The GM trait editor reads the picture back over this same list — the
        # endpoint an entity gallery uses, now keyed by any owner id, with the
        # URL built from owner_id rather than the legacy entity_id.
        listing = client.get(f"/api/v1/imagen/{TRAIT}").json()
        row = next(i for i in listing["images"] if i["id"] == image_id)
        assert row["path_large"] == f"/media/imagen/{TRAIT}/three_realms/upload_{image_id}_Large.webp"
        assert row["variant_id"] is None and row["projection_id"] is None
    finally:
        if repo.get_image(image_id) is not None:
            repo.delete_image(image_id)
    _cleanup(repo)


@requires_db
def test_upload_still_accepts_the_legacy_entity_id_parameter():
    """Two frontend callers still send `entity_id`; the alias has to carry them
    across the rename."""
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    r = client.post(
        f"/api/v1/media/upload?entity_id={ENTITY}&universe=earth",
        files={"file": ("portrait.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 200, r.text
    image_id = r.json()["image_id"]

    try:
        img = repo.get_image(image_id)
        assert img is not None
        assert (img.owner_kind, img.owner_id) == ("entity", ENTITY)
    finally:
        if repo.get_image(image_id) is not None:
            repo.delete_image(image_id)
    _cleanup(repo)


def test_upload_rejects_an_unknown_owner_kind():
    client = TestClient(app)
    r = client.post(
        "/api/v1/media/upload?owner_kind=projection&owner_id=whatever",
        files={"file": ("x.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 400


# ── Cutting out a trait image ─────────────────────────
#
# The BiRefNet pass itself needs the GPU and is not exercised here — the
# orchestrator's cutout is `test_imagen_auto_cutout`'s subject. What these pin is
# the *wiring*: that the endpoint accepts a trait owner, resolves it, validates
# ownership, and hands the owner id and display name to the job.


def _stub_cutout_job(monkeypatch):
    """Replace the queued background task; return the list it records calls in."""
    import transversal.api.rest.imagen as imagen_mod

    calls = []
    monkeypatch.setattr(imagen_mod, "_run_remove_bg_bg", lambda *a, **k: calls.append(a))
    return imagen_mod, calls


def _drain_job(imagen_mod, owner_id):
    """A stubbed job never reports completion, so clear its queue entry."""
    imagen_mod.active_jobs.pop(owner_id, None)
    if owner_id in imagen_mod._job_order:
        imagen_mod._job_order.remove(owner_id)


@requires_db
def test_remove_background_accepts_a_trait_owner(monkeypatch):
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))
    imagen_mod, calls = _stub_cutout_job(monkeypatch)
    client = TestClient(app)

    try:
        r = client.post(
            f"/api/v1/remove-background/{TRAIT}?owner_kind=trait",
            json={"image_id": DEF_ID},
        )
        assert r.status_code == 200, r.text
        assert r.json()["accepted"] is True
        # owner id, image id, display name — the job reports under the trait's id
        # and names the file after the trait.
        assert calls == [(TRAIT, DEF_ID, "ImgOwnerSpiritHerb")]
    finally:
        _drain_job(imagen_mod, TRAIT)
        _cleanup(repo)


@requires_db
def test_remove_background_still_defaults_to_an_entity_owner(monkeypatch):
    """The image viewer sends no owner_kind; the default must stay entity."""
    repo = _repo
    _fixtures(repo)
    repo.create_image(MediaImage(
        id=ENT_ID, owner_kind="entity", owner_id=ENTITY, universe="earth",
        image_type=ImageType.IMAGEN, roles=["sheet"],
        filename=f"probe_{ENT_ID}", extension="webp", created_at=EARLY,
    ))
    imagen_mod, calls = _stub_cutout_job(monkeypatch)
    client = TestClient(app)

    try:
        r = client.post(f"/api/v1/remove-background/{ENTITY}", json={"image_id": ENT_ID})
        assert r.status_code == 200, r.text
        assert calls and calls[0][0] == ENTITY
    finally:
        _drain_job(imagen_mod, ENTITY)
        _cleanup(repo)


@requires_db
def test_remove_background_rejects_a_cross_owner_image(monkeypatch):
    """A trait image must not be cut out through an entity's id, or vice versa."""
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))
    imagen_mod, _ = _stub_cutout_job(monkeypatch)
    client = TestClient(app)

    try:
        r = client.post(f"/api/v1/remove-background/{ENTITY}", json={"image_id": DEF_ID})
        assert r.status_code == 400
        assert "does not belong" in r.json()["detail"]
    finally:
        _drain_job(imagen_mod, ENTITY)
        _cleanup(repo)


@requires_db
def test_remove_background_rejects_an_unknown_trait_and_kind(monkeypatch):
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))
    imagen_mod, _ = _stub_cutout_job(monkeypatch)
    client = TestClient(app)

    try:
        missing = client.post(
            "/api/v1/remove-background/test-imgowner-absent?owner_kind=trait",
            json={"image_id": DEF_ID},
        )
        assert missing.status_code == 404

        bad_kind = client.post(
            f"/api/v1/remove-background/{TRAIT}?owner_kind=projection",
            json={"image_id": DEF_ID},
        )
        assert bad_kind.status_code == 400
    finally:
        _drain_job(imagen_mod, TRAIT)
        _cleanup(repo)


# ── Provenance flags: [AI], [AI-generated], [AI-animated] ──
#
# Labels, not roles. They live in their own field precisely because `roles` is
# unique per (owner, role) and strips siblings — so putting `ai` in `roles` would
# make flagging one image silently untag every other image of the same owner.
# `test_flags_do_not_strip_siblings_the_way_roles_do` pins both halves of that.


@requires_db
def test_upload_carries_the_manual_ai_flag():
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    r = client.post(
        f"/api/v1/media/upload?owner_kind=trait&owner_id={TRAIT}"
        "&universe=three_realms&flags=ai",
        files={"file": ("ai-art.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 200, r.text
    image_id = r.json()["image_id"]

    try:
        assert repo.get_image(image_id).flags == ["ai"]
    finally:
        if repo.get_image(image_id) is not None:
            repo.delete_image(image_id)
        _cleanup(repo)


@requires_db
def test_flags_do_not_strip_siblings_the_way_roles_do():
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID, roles=("sheet",)))
    repo.create_image(_trait_image(NEWER_ID, roles=("background",), created_at=LATE))
    client = TestClient(app)

    try:
        for image_id in (DEF_ID, NEWER_ID):
            r = client.patch(f"/api/v1/imagen/{image_id}", json={"flags": ["ai"]})
            assert r.status_code == 200, r.text

        assert repo.get_image(DEF_ID).flags == ["ai"]
        assert repo.get_image(NEWER_ID).flags == ["ai"], (
            "a provenance label is not unique per owner — both images keep it"
        )

        # The contrast, pinned in the same test: a ROLE does move.
        r = client.patch(f"/api/v1/imagen/{NEWER_ID}", json={"roles": ["background", "sheet"]})
        assert r.status_code == 200, r.text
        assert repo.get_image(DEF_ID).roles == []
        assert sorted(repo.get_image(NEWER_ID).roles) == ["background", "sheet"]
    finally:
        _cleanup(repo)


@requires_db
def test_an_unknown_flag_is_rejected_everywhere():
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))
    client = TestClient(app)

    try:
        up = client.post(
            f"/api/v1/media/upload?owner_kind=trait&owner_id={TRAIT}"
            "&universe=three_realms&flags=ai,definitely_not_a_flag",
            files={"file": ("x.png", _png_bytes(), "image/png")},
        )
        assert up.status_code == 400
        assert "Unknown image flag" in up.json()["detail"]

        patch = client.patch(f"/api/v1/imagen/{DEF_ID}", json={"flags": ["nope"]})
        assert patch.status_code == 400
        assert repo.get_image(DEF_ID).flags == [], "a rejected write leaves the row alone"
    finally:
        _cleanup(repo)


@requires_db
def test_patch_clears_the_ai_flag():
    repo = _repo
    _fixtures(repo)
    repo.create_image(_trait_image(DEF_ID))
    client = TestClient(app)

    try:
        assert client.patch(f"/api/v1/imagen/{DEF_ID}", json={"flags": ["ai"]}).status_code == 200
        assert repo.get_image(DEF_ID).flags == ["ai"]

        assert client.patch(f"/api/v1/imagen/{DEF_ID}", json={"flags": []}).status_code == 200
        assert repo.get_image(DEF_ID).flags == []
    finally:
        _cleanup(repo)
