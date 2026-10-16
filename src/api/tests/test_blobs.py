"""Content-addressed media blobs (B88).

The address is the content, so identical pictures are one file, a fork shares its
ancestor's media instead of copying it, and a delete cannot take a picture another
campaign still points at. These tests hold the invariants that argument rests on.
"""

import pytest

from transversal.db.repository_mixins.images import RepositoryImages
from transversal.domain import ImageType, MediaImage
from transversal.services import blobs
from transversal.services import media_store


@pytest.fixture(autouse=True)
def _tmp_media(tmp_path, monkeypatch):
    monkeypatch.setattr(media_store, "MEDIA_ROOT", tmp_path)


def _image(**overrides) -> MediaImage:
    fields = dict(
        id="img-1",
        owner_kind="entity",
        owner_id="character-1",
        universe="earth",
        image_type=ImageType.UPLOADED,
        filename="upload_1",
        extension="webp",
    )
    fields.update(overrides)
    return MediaImage(**fields)


# ── The store ─────────────────────────────────────────────────────────


def test_a_blob_is_addressed_by_its_content(tmp_path):
    digest = blobs.put(b"a picture", ext="webp")

    assert digest == blobs.digest(b"a picture")
    assert blobs.path_for(digest, ext="webp").read_bytes() == b"a picture"
    assert blobs.url_for(digest, ext="webp") == f"/media/blobs/{digest[:2]}/{digest}.webp"


def test_the_same_bytes_are_stored_once(tmp_path):
    first = blobs.put(b"same", ext="webp")
    second = blobs.put(b"same", ext="webp")

    assert first == second
    assert len([p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]) == 1


def test_a_suffix_names_a_tier_of_the_same_picture(tmp_path):
    digest = blobs.put(b"same", suffix="_Large", ext="webp")

    assert blobs.path_for(digest, suffix="_Large", ext="webp").exists()
    assert not blobs.path_for(digest, ext="webp").exists(), "a tier is its own blob"


def test_a_file_is_moved_into_the_store(tmp_path):
    source = tmp_path / "incoming_Large.webp"
    source.write_bytes(b"moving in")

    digest = blobs.put_file(source, suffix="_Large", ext="webp")

    assert not source.exists(), "the caller's file is not left behind"
    assert blobs.path_for(digest, suffix="_Large", ext="webp").read_bytes() == b"moving in"


# ── How a record is served ────────────────────────────────────────────


def test_a_record_with_blobs_is_served_from_the_store():
    digest = blobs.put(b"picture", suffix="_Large", ext="webp")

    url = RepositoryImages().image_url(_image(blobs={"_Large": digest}))

    assert url == blobs.url_for(digest, suffix="_Large", ext="webp")


def test_a_record_without_blobs_keeps_its_legacy_url():
    """What lets adoption be incremental: an unmigrated row serves as it always did."""
    repo = RepositoryImages()
    img = _image()

    assert repo.image_url(img) == "/media/imagen/character-1/earth/upload_1_Large.webp"
    assert (
        repo.image_url(img, render="cutout")
        == "/media/imagen/character-1/earth/upload_1_Cutout_Large.webp"
    )
    assert repo.image_url(img, render="animated") == "/media/animated/character-1/earth/upload_1.webp"


def test_a_cutout_blob_is_webp_whatever_the_still_is():
    digest = blobs.put(b"matte", suffix="_Cutout_Large", ext="webp")

    url = RepositoryImages().image_url(
        _image(extension="png", blobs={"_Cutout_Large": digest}), render="cutout"
    )

    assert url == blobs.url_for(digest, suffix="_Cutout_Large", ext="webp")


def test_a_loop_uses_its_own_container():
    digest = blobs.put(b"loop", ext="webm")

    url = RepositoryImages().image_url(
        _image(extension="webp", animated_extension="webm", blobs={"": digest}),
        render="animated",
    )

    assert url == blobs.url_for(digest, ext="webm")


# ── The refcount, which is what makes deletion safe ───────────────────


def test_an_uncounted_blob_is_never_deleted(tmp_path):
    """The fail-safe direction: no counter means "not this caller's to remove".

    A blob with no count is one this system never registered — a legacy file, or a
    record written before the store existed. Deleting on that basis is precisely the
    incident the whole mechanism exists to prevent.
    """
    digest = blobs.put(b"someone else's", suffix="_Large", ext="webp")

    assert blobs.release(digest, suffix="_Large", ext="webp") is None
    assert blobs.path_for(digest, suffix="_Large", ext="webp").exists()


def test_the_last_reference_releases_the_file(tmp_path):
    digest = blobs.put(b"mine", suffix="_Large", ext="webp")
    path = blobs.path_for(digest, suffix="_Large", ext="webp")

    assert blobs.retain(digest, ext="webp") == 1
    assert blobs.retain(digest, ext="webp") == 2
    assert blobs.release(digest, suffix="_Large", ext="webp") == 1
    assert path.exists(), "another record still points at it"
    assert blobs.release(digest, suffix="_Large", ext="webp") == 0
    assert not path.exists(), "the last reference is what releases the file"
