"""Where campaign media lives, and what a delete is allowed to remove (B88).

A campaign is an ArangoDB database — but **media was the exception**. Every path was
derived from the owner's id and the volume was shared, so
``/app/media/imagen/<owner-id>`` named no campaign at all. A fork is a **verbatim
clone**, so the same owner id exists in every campaign cloned from the same ancestor:
on 2026-10-16 deleting a character in the global multiverse unlinked that character's
images in the playroom.

Two rules, cheapest first:

- **A delete removes the campaign's own copy**, and removes the *shared* copy only
  when no other campaign's database still references that owner. A shared file may
  only be deleted by the last campaign holding a reference to it.
- **New media is written under the campaign** (``/app/media/<database>/…``), so a
  campaign owns what it creates. Serving keeps its URLs: the static mount resolves
  campaign-first and falls back to the shared copy, which is how every file that
  predates this keeps working with no migration at all.

Content-addressed blobs with refcounted deletion is the target once fork creation is
public — that is what keeps "clone the multiverse" cheap. This module is the step
that makes the current shape safe.
"""

from __future__ import annotations

import glob as globlib
import logging
import shutil
from pathlib import Path

from transversal.db.arango import ArangoConfig
from transversal.db.arango import current_database
from transversal.db.arango import get_db

logger = logging.getLogger("transversal.media")

#: The media volume, as every container mounts it (``./media:/app/media``).
MEDIA_ROOT = Path("/app/media")

#: The owner's media directories, by kind. ``flat`` is the uploaded-background form
#: (``<root>/<owner>.<ext>``) rather than a directory.
KINDS = ("imagen", "animated", "flat")


def campaign_name() -> str:
    """The campaign the current context acts on — its database name.

    ``current_database()`` is None for a request that named no campaign (the apex
    host), which means the default database: the playroom.
    """
    return current_database() or ArangoConfig.from_env().database


def campaign_root(name: str | None = None) -> Path:
    """Where this campaign's own media goes."""
    return MEDIA_ROOT / (name or campaign_name())


def write_dir(*parts: str, campaign: str | None = None) -> Path:
    """A directory for **new** media, under the campaign's own tree, created.

    This is the write half of the rule: a campaign owns what it creates, so nothing
    it generates can land on a path another campaign also writes. Components are
    checked, because a request supplies some of them and ``rmtree`` is not the only
    thing that should not be handed a ``..``.
    """
    name = campaign or campaign_name()
    for part in (name, *parts):
        if not part or part in (".", "..") or "/" in part or "\\" in part:
            raise ValueError(f"unsafe media path component: {part!r}")
    path = MEDIA_ROOT.joinpath(name, *parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def paths_for(owner_id: str, kind: str, *, root: Path) -> list[Path]:
    """What one owner's media occupies under ``root``, for one kind.

    The owner id is glob-escaped: these are generated ids today, but this runs
    inside ``rmtree``'s neighbourhood and a stray metacharacter must not widen it.
    """
    if kind == "flat":
        return sorted(root.glob(globlib.escape(owner_id) + ".*"))
    return [root / kind / owner_id]


def owner_referenced_elsewhere(owner_id: str) -> bool:
    """Does any *other* campaign's database still hold an image for this owner?

    Conservative on purpose: when the question cannot be answered the answer is
    **yes**. Keeping a file costs disk; removing one costs another campaign's
    images, which is the incident this exists to prevent.
    """
    try:
        others = _other_campaign_databases()
    except Exception:
        logger.exception(
            "[media] could not list campaigns; keeping shared media for %s", owner_id
        )
        return True

    for name in others:
        try:
            if _database_references_owner(name, owner_id):
                return True
        except Exception:
            logger.exception(
                "[media] could not check %s; keeping shared media for %s", name, owner_id
            )
            return True
    return False


def delete_owner_media(owner_id: str, *, kinds: tuple[str, ...] = ("imagen", "flat")) -> dict:
    """Delete one owner's media, respecting what is shared. Returns what happened.

    The campaign's own copy is the campaign's alone, so it always goes. The shared
    tree is where a clone's files live, so it goes only when the last referencing
    campaign is this one.
    """
    removed: list[str] = []
    kept: list[str] = []

    for kind in kinds:
        for path in paths_for(owner_id, kind, root=campaign_root()):
            if _remove(path):
                removed.append(str(path))

    if owner_referenced_elsewhere(owner_id):
        for kind in kinds:
            kept += [
                str(path)
                for path in paths_for(owner_id, kind, root=MEDIA_ROOT)
                if path.exists()
            ]
        if kept:
            logger.warning(
                "[media] %s deleted here; kept %d shared path(s) another campaign still "
                "references: %s",
                owner_id,
                len(kept),
                ", ".join(kept),
            )
    else:
        for kind in kinds:
            for path in paths_for(owner_id, kind, root=MEDIA_ROOT):
                if _remove(path):
                    removed.append(str(path))

    return {"owner": owner_id, "removed": removed, "kept": kept}


def _remove(path: Path) -> bool:
    """Remove a file or directory. True when something was there."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return True
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            logger.warning("[media] could not remove %s", path)
            return False
    return False


def _other_campaign_databases() -> list[str]:
    """Every campaign database except this one.

    Imported here rather than at module scope: the provisioner pulls in the whole
    data layer, and this module is imported by repository mixins.
    """
    from transversal.db.registry_repository import RegistryRepository
    from transversal.services.provisioner import campaign_databases

    here = campaign_name()
    return [name for name in campaign_databases(RegistryRepository()) if name != here]


def _database_references_owner(database: str, owner_id: str) -> bool:
    """Does ``database`` hold any image row owned by ``owner_id``?

    Both image collections are checked: ``images`` is what a delete cleans today and
    ``entity_images`` is the newer one, so trusting either alone would under-report
    and hand a delete permission it has not earned.
    """
    from transversal.db.arango import IMAGES
    from transversal.services.provisioner import database_exists

    if not database_exists(database):
        return False

    base = ArangoConfig.from_env()
    config = ArangoConfig(
        url=base.url,
        username=base.username,
        password=base.password,
        database=database,
    )
    db = get_db(config, ensure_indexes=False)

    for collection in (IMAGES, "entity_images"):
        if not db.has_collection(collection):
            continue
        row = next(
            iter(
                db.aql.execute(
                    f"FOR img IN {collection} FILTER img.owner_id == @owner LIMIT 1 RETURN 1",
                    bind_vars={"owner": owner_id},
                )
            ),
            None,
        )
        if row:
            return True
    return False
