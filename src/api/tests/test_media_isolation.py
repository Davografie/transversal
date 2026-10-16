"""Media isolation between campaigns (B88).

The incident these exist for: every media path was derived from the owner's id and
the volume is shared, so deleting a character in the global multiverse unlinked that
character's images in the playroom. A fork is a **verbatim clone**, so the same owner
id exists in every campaign cloned from the same ancestor — which is what makes a
path with no campaign in it dangerous rather than merely untidy.

The rule under test: a delete always takes this campaign's own copy, and takes the
**shared** copy only when no other campaign's database still references that owner.
"""

import pytest

from transversal.services import media_store

try:
    from transversal.db.repository import EntityRepository
    from transversal.domain import Entity, EntityType

    _repo = EntityRepository()
    HAVE_DB = True
except Exception:  # pragma: no cover - depends on the machine
    _repo = None
    HAVE_DB = False


@pytest.fixture
def volume(tmp_path, monkeypatch):
    """A media volume with a shared root and a campaign root, both populated."""
    monkeypatch.setattr(media_store, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(media_store, "campaign_name", lambda: "campaign_b")

    owner = "character-probe"
    shared = tmp_path / "imagen" / owner
    shared.mkdir(parents=True)
    (shared / "portrait_Large.webp").write_bytes(b"shared")
    mine = tmp_path / "campaign_b" / "imagen" / owner
    mine.mkdir(parents=True)
    (mine / "portrait_Large.webp").write_bytes(b"mine")
    flat = tmp_path / f"{owner}.webp"
    flat.write_bytes(b"flat")

    return {"root": tmp_path, "owner": owner, "shared": shared, "mine": mine, "flat": flat}


# ── What a delete may remove ──────────────────────────────────────────


def test_the_campaign_copy_goes_even_when_the_shared_one_is_kept(volume, monkeypatch):
    monkeypatch.setattr(media_store, "owner_referenced_elsewhere", lambda owner: True)

    outcome = media_store.delete_owner_media(volume["owner"])

    assert not volume["mine"].exists(), "this campaign's own copy is its own"
    assert volume["shared"].exists(), "another campaign still needs the shared file"
    assert volume["flat"].exists()
    assert outcome["kept"]


def test_the_shared_copy_goes_when_no_other_campaign_references_it(volume, monkeypatch):
    monkeypatch.setattr(media_store, "owner_referenced_elsewhere", lambda owner: False)

    media_store.delete_owner_media(volume["owner"])

    assert not volume["shared"].exists(), "the last reference releases the file"
    assert not volume["flat"].exists()
    assert not volume["mine"].exists()


def test_kinds_decide_which_trees_are_touched(volume, monkeypatch):
    monkeypatch.setattr(media_store, "owner_referenced_elsewhere", lambda owner: True)
    animated = volume["root"] / "animated" / volume["owner"]
    animated.mkdir(parents=True)

    media_store.delete_owner_media(volume["owner"], kinds=("imagen",))

    assert not volume["mine"].exists()
    assert animated.exists(), "a kind that was not asked for is left alone"
    assert volume["flat"].exists()


def test_an_owner_with_nothing_on_disk_is_not_an_error(volume, monkeypatch):
    monkeypatch.setattr(media_store, "owner_referenced_elsewhere", lambda owner: False)

    outcome = media_store.delete_owner_media("character-never-existed")

    assert outcome["removed"] == []
    assert outcome["kept"] == []


# ── The guard itself ──────────────────────────────────────────────────


def test_the_guard_fails_closed_when_it_cannot_list_campaigns(monkeypatch):
    def _boom():
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(media_store, "_other_campaign_databases", _boom)

    assert media_store.owner_referenced_elsewhere("character-probe") is True


def test_the_guard_fails_closed_when_a_database_cannot_be_checked(monkeypatch):
    monkeypatch.setattr(media_store, "_other_campaign_databases", lambda: ["other"])

    def _boom(database, owner_id):
        raise RuntimeError("no connection")

    monkeypatch.setattr(media_store, "_database_references_owner", _boom)

    assert media_store.owner_referenced_elsewhere("character-probe") is True


def test_the_guard_stops_at_the_first_campaign_that_has_the_owner(monkeypatch):
    monkeypatch.setattr(media_store, "_other_campaign_databases", lambda: ["a", "b"])
    seen = []

    def _check(database, owner_id):
        seen.append(database)
        return database == "b"

    monkeypatch.setattr(media_store, "_database_references_owner", _check)

    assert media_store.owner_referenced_elsewhere("character-probe") is True
    assert seen == ["a", "b"]


def test_the_guard_says_no_when_no_other_campaign_has_the_owner(monkeypatch):
    monkeypatch.setattr(media_store, "_other_campaign_databases", lambda: ["a", "b"])
    monkeypatch.setattr(media_store, "_database_references_owner", lambda d, o: False)

    assert media_store.owner_referenced_elsewhere("character-probe") is False


def test_the_campaign_itself_is_not_counted_as_another(monkeypatch):
    """Otherwise nothing shared could ever be released."""
    monkeypatch.setattr(media_store, "campaign_name", lambda: "campaign_b")
    monkeypatch.setattr(
        "transversal.services.provisioner.campaign_databases",
        lambda registry: ["campaign_a", "campaign_b"],
    )
    monkeypatch.setattr(
        "transversal.db.registry_repository.RegistryRepository", lambda: object()
    )

    assert media_store._other_campaign_databases() == ["campaign_a"]


def test_an_owner_id_with_glob_metacharacters_cannot_widen_a_match(tmp_path, monkeypatch):
    monkeypatch.setattr(media_store, "MEDIA_ROOT", tmp_path)
    (tmp_path / "victim.webp").write_bytes(b"someone else's")
    (tmp_path / "char*X.webp").write_bytes(b"mine")

    found = media_store.paths_for("char*X", "flat", root=tmp_path)

    assert [path.name for path in found] == ["char*X.webp"]


# ── The delete paths use it ───────────────────────────────────────────


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
def test_deleting_an_entity_sends_its_media_through_the_store(monkeypatch):
    """The entity delete must not unlink paths of its own — it asks the store."""
    import transversal.db.repository_mixins.entities as mixin

    entity_id = "test-media-isolation-entity"
    _repo.create_entity(
        Entity(
            id=entity_id,
            name="Probe",
            type=EntityType.CHARACTER,
            current_universe="test-universe",
        )
    )

    seen = []
    monkeypatch.setattr(
        mixin,
        "delete_owner_media",
        lambda owner_id, **kwargs: seen.append((owner_id, kwargs)),
    )

    assert _repo.delete_entity(entity_id) is True
    assert seen == [(entity_id, {"kinds": ("imagen", "flat")})]
