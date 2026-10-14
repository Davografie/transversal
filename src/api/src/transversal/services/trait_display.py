"""What a rolled pool die needs for the client to draw its **trait** ([[B289]]).

A pool die carries ``ts_id`` — the **trait setting** it came from — plus a ``label``
(the trait's name). That is enough to *name* what is opposing you and not enough to
*show* it: the receiving player's difficulty splash draws each trait as the map's own
chip ([[B92]]), which wants the trait's navdot picture and the instance's statement.

The client cannot resolve either, and the reason is not permissions or the owner: it is
that ``ts_id`` is a *setting* id and **nothing is keyed by one**. The GraphQL surface
reaches a navdot image per *registry trait* (``TraitRef.image(role:)``), and the only
settings a client holds are the ones it happened to load — the current location's scene
traits. So the server answers it here, at the point it already resolves the label, and
**once for both publishers** of ``difficulty_set``.
"""

from __future__ import annotations

import logging

from transversal.db.repository_mixins.images import pick_role_image

logger = logging.getLogger(__name__)


def dice_with_trait_display(dice: list[dict], repo=None) -> list[dict]:
    """Copies of ``dice``, each carrying its trait's ``statement`` and navdot picture.

    **Copies**, because the caller may be holding the stored pool: the store's own dice
    are not the wire's, and mutating them would grow the pool with presentation keys.

    Tolerant by design, matching the location payloads: a die with no ``ts_id``, a
    setting that no longer exists, or a trait with no navdot picture keeps exactly the
    keys it had. An entry with no picture draws as it did before, so nothing here can
    make a splash worse than the name it already had.
    """
    out = [dict(d) for d in (dice or [])]
    wanted = list(dict.fromkeys(d.get("ts_id") for d in out if d.get("ts_id")))
    if not wanted:
        return out

    if repo is None:
        repo = _repo_or_none()
    if repo is None:
        return out

    settings = {}
    for ts_id in wanted:
        try:
            ts = repo.get_traitsetting(ts_id)
        except Exception:  # a stale id must not take the difficulty down with it
            ts = None
        if ts is not None:
            settings[ts_id] = ts

    trait_ids = list(dict.fromkeys(ts.trait_id for ts in settings.values() if ts.trait_id))
    try:
        by_owner = repo.get_images_for_owners(trait_ids) if trait_ids else {}
    except Exception:
        by_owner = {}

    for die in out:
        ts = settings.get(die.get("ts_id") or "")
        if ts is None:
            continue
        if ts.statement:
            die["statement"] = ts.statement
        image = pick_role_image(
            by_owner.get(ts.trait_id, []), "navdot", ts.id,
            picked_id=getattr(ts, "picked_image_id", "") or "",
        )
        if image is not None:
            die["navdot_image"] = repo.role_image_url(image, "navdot")
            die["navdot_transparent"] = bool(getattr(image, "transparent", False))
    return out


def _repo_or_none():
    """The boot repo, or ``None`` — never an exception.

    The seam both publishers already use (``api/rest/scene_state.py`` reaches it the
    same way), and a splash is not worth failing a difficulty over.
    """
    try:
        from transversal.main import _get_repo
        repo = _get_repo()
    except Exception:
        return None
    return repo if getattr(repo, "db", None) is not None else None
