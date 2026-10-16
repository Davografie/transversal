"""Content-addressed media blobs (B88).

A campaign is an ArangoDB database, and a fork is a **verbatim clone** — identical
entity ids, therefore identical media paths. That is what let a delete in the global
multiverse unlink the playroom's images. The fix that follows is not "put the campaign
in the path" (which is what the first cut did, and it defeats sharing): it is to make
the **bytes** the address.

A file's name is the digest of its content, so:

- **identical content is stored once**, whoever uploaded it, in whichever campaign;
- a fork costs **no media copying** — its records point at blobs that already exist;
- a delete cannot destroy another campaign's picture, because a blob goes away only
  when the **last** record referencing it does. That count lives in the registry,
  beside the campaigns rather than inside one, since it spans them.

Legacy files stay where they are and keep serving: a record with no digest recorded
falls back to the old path (``db/repository_mixins/images._image_url``), so adoption is
incremental and nothing has to be migrated for the app to keep working.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from transversal.services import media_store

logger = logging.getLogger("transversal.media")


def blob_dir() -> Path:
    """Where blobs live: ``<media root>/blobs``.

    Resolved per call rather than bound at import: the media root is configurable (and
    patched in tests), and a module-level constant would keep writing to whichever root
    happened to be set when this module was first imported.
    """
    return media_store.MEDIA_ROOT / "blobs"


def digest(data: bytes) -> str:
    """The address of some bytes."""
    return hashlib.sha256(data).hexdigest()


def path_for(digest_: str, *, suffix: str = "", ext: str = "webp") -> Path:
    """Where a blob lives: sharded by its first two hex digits.

    Two levels rather than one because a flat directory of tens of thousands of files
    is slow to list on every filesystem this runs on, and the shard is derivable from
    the name — no index needed.
    """
    return blob_dir() / digest_[:2] / f"{digest_}{suffix}.{ext}"


def url_for(digest_: str, *, suffix: str = "", ext: str = "webp") -> str:
    """The public URL for a blob — what a record hands the browser."""
    return f"/media/blobs/{digest_[:2]}/{digest_}{suffix}.{ext}"


def put(data: bytes, *, suffix: str = "", ext: str = "webp") -> str:
    """Store bytes, returning their digest. Writes nothing if they are already there.

    The dedup is the whole point: this is what makes the same picture uploaded to two
    campaigns, or inherited by a fork, occupy one file.
    """
    digest_ = digest(data)
    path = path_for(digest_, suffix=suffix, ext=ext)
    if path.exists():
        return digest_
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the target and rename: a reader can never see a half-written blob,
    # and the rename is atomic within the directory.
    temporary = path.with_name(f".{path.name}.incoming")
    temporary.write_bytes(data)
    temporary.replace(path)
    return digest_


def put_file(source: Path, *, suffix: str = "", ext: str = "webp") -> str:
    """Move an existing file into the blob store, returning its digest.

    Moving rather than copying because the caller has just written this file to a
    temporary directory and has no further use for it — the blob store is the only
    place a picture should end up.
    """
    digest_ = digest(source.read_bytes())
    path = path_for(digest_, suffix=suffix, ext=ext)
    if path.exists():
        source.unlink(missing_ok=True)
        return digest_
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(path))
    return digest_


def forget(digest_: str, *, suffix: str = "", ext: str = "webp") -> bool:
    """Delete one blob file. Only the refcount may call this."""
    path = path_for(digest_, suffix=suffix, ext=ext)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        logger.warning("[media] could not remove blob %s", path)
        return False


# ── The refcount, which lives in the registry because it spans campaigns ──


def retain(digest_: str, *, ext: str = "", size: int = 0) -> int:
    """Record one more reference to a blob. Imported lazily: repositories import
    this module, and the registry pulls in the whole data layer."""
    from transversal.db.registry_repository import RegistryRepository

    return RegistryRepository().retain_blob(digest_, ext=ext, size=size)


def release(digest_: str, *, suffix: str = "", ext: str = "webp") -> int | None:
    """Drop one reference, deleting the file when it was the last one.

    Returns the remaining count, or **None when the blob was never counted** — and
    then nothing is deleted, because an uncounted blob is not this caller's to remove.
    Together with ``release_blob``'s "unknown means keep", that is the whole safety
    argument: a file goes only when a counter this system wrote reaches zero.
    """
    from transversal.db.registry_repository import RegistryRepository

    remaining = RegistryRepository().release_blob(digest_)
    if remaining == 0:
        forget(digest_, suffix=suffix, ext=ext)
    return remaining
