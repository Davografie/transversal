"""The tier migration: a matte and a loop fold into the picture (B210).

Driven against a fake `images` collection and a temporary media tree, because the
script's job is file-and-row surgery. The live dry-run is what proves the shape of
the real library; these tests prove the surgery is right and repeatable.
"""

import pytest
from PIL import Image

from transversal import migrate_image_tiers as mig


# ── fakes ────────────────────────────────────────────


class _FakeCollection:
    def __init__(self, docs):
        self.docs = {d["_key"]: dict(d) for d in docs}

    def update(self, doc):
        key = doc["_key"]
        self.docs[key] = {**self.docs.get(key, {}), **doc}

    def delete(self, key):
        self.docs.pop(key, None)


class _FakeAQL:
    def __init__(self, collection):
        self.collection = collection

    def execute(self, query, bind_vars=None):
        return [dict(d) for d in self.collection.docs.values()]


class _FakeDB:
    def __init__(self, docs):
        self.collection_handle = _FakeCollection(docs)
        self.aql = _FakeAQL(self.collection_handle)

    def has_collection(self, name):
        return True

    def collection(self, name):
        return self.collection_handle


def _doc(key, image_type, filename, *, owner="loc-1", universe="three_realms", **fields):
    base = dict(
        _key=key, id=key, owner_kind="entity", owner_id=owner, universe=universe,
        image_type=image_type, filename=filename, extension="webp",
        roles=[], flags=[], renders=[], credits=[], created_at="2026-01-01T00:00:00+00:00",
    )
    base.update(fields)
    return base


def _picture(path, colour):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), colour).save(path)


def _video(path):
    """A placeholder loop file — Pillow cannot write one, and the script only moves it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-webm")


def _ladder(directory, filename, colour=(120, 80, 40), tiers=("Original", "Large", "Small", "Mini")):
    for tier in tiers:
        _picture(directory / f"{filename}_{tier}.webp", colour)


@pytest.fixture
def media(monkeypatch, tmp_path):
    imagen = tmp_path / "imagen"
    animated = tmp_path / "animated"
    monkeypatch.setattr(mig, "IMAGEN_DIR", imagen)
    monkeypatch.setattr(mig, "ANIMATED_DIR", animated)
    return imagen, animated


def _run(monkeypatch, docs, apply=True):
    db = _FakeDB(docs)
    monkeypatch.setattr(mig, "get_db", lambda: db)
    assert mig.migrate(apply=apply) == 0
    return db.collection_handle.docs


# ── cutouts ──────────────────────────────────────────


def test_a_cutout_folds_into_its_picture(media, monkeypatch):
    imagen, _ = media
    _ladder(imagen / "loc-1" / "three_realms", "scene", (200, 100, 50))
    _ladder(imagen / "loc-1" / "three_realms", "scene_cut_ab12", (200, 100, 50),
            tiers=("Original", "Large", "Small", "Mini"))  # no XLarge, as two live ones
    _picture(imagen / "loc-1" / "three_realms" / "scene_cut_ab12_Large.webp", (200, 100, 50))

    docs = [
        _doc("src", "imagen", "scene", roles=["background"]),
        _doc("cut", "cutout", "scene_cut_ab12", roles=["navdot", "sheet"],
             transparent=True, prompt="background removed from scene"),
    ]

    after = _run(monkeypatch, docs)

    assert set(after) == {"src"}, "the cutout row is gone"
    source = after["src"]
    assert source["renders"] == ["cutout"]
    assert source["transparent"] is True
    assert source["roles"] == ["background", "navdot", "sheet"], "the roles join up"

    base = imagen / "loc-1" / "three_realms" / "scene_Cutout"
    assert base.with_name("scene_Cutout_Large.webp").exists(), "the matte was renamed"
    assert base.with_name("scene_Cutout_XLarge.webp").exists(), "the missing tier was rebuilt"
    assert not (imagen / "loc-1" / "three_realms" / "scene_cut_ab12_Large.webp").exists()


def test_a_cutout_with_no_source_is_left_alone(media, monkeypatch):
    imagen, _ = media
    _ladder(imagen / "loc-1" / "three_realms", "orphan_cut_ab12")
    docs = [_doc("cut", "cutout", "orphan_cut_ab12", prompt="background removed from missing")]

    after = _run(monkeypatch, docs)

    assert "cut" in after, "an unmatched cutout must not be destroyed"
    assert after["cut"]["renders"] == []


def test_a_cutout_of_a_picture_that_already_has_one_is_retired(media, monkeypatch):
    """The new writer can have added a matte during the transition; its render wins."""
    imagen, _ = media
    _ladder(imagen / "loc-1" / "three_realms", "scene")
    _ladder(imagen / "loc-1" / "three_realms", "scene_cut_ab12")
    docs = [
        _doc("src", "imagen", "scene", renders=["cutout"], transparent=True),
        _doc("cut", "cutout", "scene_cut_ab12", prompt="background removed from scene"),
    ]

    after = _run(monkeypatch, docs)

    assert set(after) == {"src"}
    assert after["src"]["renders"] == ["cutout"], "no duplicate render"


# ── loops ────────────────────────────────────────────


def test_a_sourced_loop_becomes_a_render_of_the_picture(media, monkeypatch):
    imagen, animated = media
    _ladder(imagen / "loc-1" / "three_realms", "scene", (10, 90, 200))
    # The loop's still is the same picture, re-encoded — a hash match, not a byte one.
    _ladder(imagen / "loc-1" / "three_realms", "scene_anim_ff01", (10, 90, 200))
    _video(animated / "loc-1" / "three_realms" / "scene_anim_ff01.webm")

    docs = [
        _doc("src", "imagen", "scene", roles=["navdot", "sheet"]),
        _doc("loop", "animated", "scene_anim_ff01", extension="webm",
             roles=["background"], flags=["ai_animated"]),
    ]

    after = _run(monkeypatch, docs)

    assert set(after) == {"src"}, "the loop row is gone"
    source = after["src"]
    assert source["renders"] == ["animated"]
    assert source["animated_extension"] == "webm"
    assert source["extension"] == "webp", "extension still names the still"
    assert source["roles"] == ["background", "navdot", "sheet"], "the loop's role joins up"
    assert (animated / "loc-1" / "three_realms" / "scene.webm").exists(), (
        "the loop is renamed onto the picture"
    )
    assert not (animated / "loc-1" / "three_realms" / "scene_anim_ff01.webm").exists()


def test_the_newest_of_two_loops_on_one_picture_keeps_the_render(media, monkeypatch):
    imagen, animated = media
    _ladder(imagen / "loc-1" / "three_realms", "scene", (10, 90, 200))
    for name in ("scene_anim_old", "scene_anim_new"):
        _ladder(imagen / "loc-1" / "three_realms", name, (10, 90, 200))
        _video(animated / "loc-1" / "three_realms" / f"{name}.webm")

    docs = [
        _doc("src", "imagen", "scene"),
        _doc("old", "animated", "scene_anim_old", extension="webm",
             created_at="2026-01-01T00:00:00+00:00"),
        _doc("new", "animated", "scene_anim_new", extension="webm",
             created_at="2026-02-01T00:00:00+00:00"),
    ]

    after = _run(monkeypatch, docs)

    assert set(after) == {"src"}, "both loop rows are gone"
    assert (animated / "loc-1" / "three_realms" / "scene.webm").exists()
    assert (animated / "loc-1" / "three_realms" / "scene_anim_new.webm").exists() is False
    # The retired loop's video is deliberately left on disk, not deleted.
    assert (animated / "loc-1" / "three_realms" / "scene_anim_old.webm").exists()


def test_a_fresh_loop_becomes_an_imagen_picture_with_a_motion_render(media, monkeypatch):
    imagen, _ = media
    _ladder(imagen / "loc-1" / "three_realms", "fresh_anim_01", (250, 250, 250))
    docs = [_doc("loop", "animated", "fresh_anim_01", extension="webm",
                 flags=["ai_animated"], roles=["background"])]

    after = _run(monkeypatch, docs)

    loop = after["loop"]
    assert loop["image_type"] == "imagen", "run_animate generated its still"
    assert loop["renders"] == ["animated"]
    assert loop["extension"] == "webp", "extension names the still now"
    assert loop["animated_extension"] == "webm"
    assert loop["flags"] == ["ai_animated", "ai_generated"], "the fresh loop gets its second label"
    assert loop["roles"] == ["background"], "its role is untouched"


def test_one_that_already_carries_ai_generated_is_not_stamped_twice(media, monkeypatch):
    imagen, _ = media
    _ladder(imagen / "loc-1" / "three_realms", "fresh_anim_02", (250, 250, 250))
    docs = [_doc("loop", "animated", "fresh_anim_02", extension="webm",
                 flags=["ai_animated", "ai_generated"])]

    after = _run(monkeypatch, docs)

    assert after["loop"]["flags"] == ["ai_animated", "ai_generated"]


# ── repeatability ────────────────────────────────────


def test_the_migration_is_idempotent(media, monkeypatch):
    imagen, animated = media
    _ladder(imagen / "loc-1" / "three_realms", "scene", (10, 90, 200))
    _ladder(imagen / "loc-1" / "three_realms", "scene_cut_ab12", (10, 90, 200))
    # A different picture, so this loop is *fresh* and stays its own record —
    # which is what the second run must then leave alone.
    _ladder(imagen / "loc-1" / "three_realms", "loop_anim_ff01", (200, 20, 20))
    _video(animated / "loc-1" / "three_realms" / "loop_anim_ff01.webm")
    docs = [
        _doc("src", "imagen", "scene", roles=["background"]),
        _doc("cut", "cutout", "scene_cut_ab12", roles=["navdot", "sheet"],
             prompt="background removed from scene"),
        _doc("loop", "animated", "loop_anim_ff01", extension="webm", flags=["ai_animated"]),
    ]

    first = _run(monkeypatch, docs)
    snapshot = {k: dict(v) for k, v in first.items()}
    second = _run(monkeypatch, list(first.values()))

    assert set(second) == set(snapshot) == {"src", "loop"}
    for key in snapshot:
        assert second[key] == snapshot[key], f"{key} changed on the second run"


def test_a_dry_run_writes_nothing(media, monkeypatch):
    imagen, _ = media
    _ladder(imagen / "loc-1" / "three_realms", "scene", (10, 90, 200))
    _ladder(imagen / "loc-1" / "three_realms", "scene_cut_ab12", (10, 90, 200))
    docs = [
        _doc("src", "imagen", "scene"),
        _doc("cut", "cutout", "scene_cut_ab12", prompt="background removed from scene"),
    ]

    after = _run(monkeypatch, docs, apply=False)

    assert set(after) == {"src", "cut"}, "no row was touched"
    assert after["src"]["renders"] == []
    assert (imagen / "loc-1" / "three_realms" / "scene_cut_ab12_Large.webp").exists()
    assert not (imagen / "loc-1" / "three_realms" / "scene_Cutout_Large.webp").exists()
