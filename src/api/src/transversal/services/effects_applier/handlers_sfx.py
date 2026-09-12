"""Handlers for the rule registry itself — granting a rule to an owner."""

from __future__ import annotations

from transversal.domain import Effect
from transversal.domain import Entity
from transversal.domain import EntityType
from transversal.domain import Projection
from transversal.domain import TraitSetting
from transversal.domain import TraitSetSetting
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    EffectsResult,
)
from transversal.services.effects_applier.targeting import (
    _effect_subject,
    _track_subject,
)


def owner_surface_for(owner) -> tuple[str | None, str]:
    """The (owner surface, id) an object attaches rules *as*.

    A rule's ``sfx_ids`` list lives on a specific kind of thing, and the write
    path keys on that kind — an entity and a location are both ``Entity``
    objects but different surfaces, so a place keeps being a place.
    """
    if isinstance(owner, TraitSetting):
        return "trait_instance", owner.id
    if isinstance(owner, TraitSetSetting):
        return "trait_set", owner.id
    if isinstance(owner, Projection):
        return "projection", owner.id
    if isinstance(owner, Entity):
        surface = "location" if owner.type == EntityType.LOCATION else "entity"
        return surface, owner.id
    return None, ""


def _owner_for_subject(repo, subject) -> tuple[str | None, str]:
    """The owner surface a resolved subject attaches as, object or id.

    A bare id arrives whenever the subject came from a *path*: the applier
    flattens ``entity_spec`` into ``entity`` before dispatch, so the kind has to
    be recovered by asking which surface holds that id. That is the sect-training
    case — a technique landing on a trait instance rather than on the entity.
    """
    surface, owner_id = owner_surface_for(subject)
    if surface:
        return surface, owner_id
    if not isinstance(subject, str):
        return None, ""
    for getter_name in ("get_traitsetting", "get_traitsetsetting",
                        "get_projection", "get_entity"):
        getter = getattr(repo, getter_name, None)
        if not callable(getter):
            continue
        found = getter(subject)
        if found is not None:
            return owner_surface_for(found)
    return None, ""


def _apply_grant_sfx(entity, effect: Effect, repo, result: EffectsResult) -> None:
    """Grant one rule from the registry to a target owner.

    The recipient is the effect's *subject* — an entity, or a trait instance
    reached by a path. That is the teacher case: a place's rule grants a
    technique to the trait instance the training lands on, rather than the rule
    offering itself to a selection.

    Note this reads the subject itself rather than going through
    ``_effect_subject``: that helper insists on an *entity*, and the whole point
    here is that the recipient may be a trait instance (a path rewrites the spec
    into a bare id before dispatch, which is exactly how a trait instance gets
    here).

    The write goes through ``add_sfx_to_owner`` rather than touching the list, so
    a grant obeys exactly what an attach obeys: the rule's declared source must
    permit that surface, and its acquire gate must hold. A grant is not a back
    door around either.
    """
    subject: object = (effect.entity or "").strip()
    if subject in ("", "self"):
        subject = entity
    elif str(subject).startswith("{"):
        # A ``{choose_entity}`` / ``{random:…}`` placeholder resolves through the
        # candidate machinery, which yields entities.
        subject = _effect_subject(entity, effect, result, repo)
        if subject is None:
            return
    if not isinstance(subject, str):
        # Only an object can be persisted; an id's owner already exists.
        _track_subject(result, entity, subject)

    ref = (effect.refs or {}).get("sfx")
    sfx_id = (getattr(ref, "value", "") or "") or (effect.target or "")
    if not sfx_id or sfx_id.startswith("{"):
        result.applied.append(AppliedEffect(effect, "no SFX to grant"))
        return

    owner_type, owner_id = _owner_for_subject(repo, subject)
    if owner_type is None:
        result.applied.append(
            AppliedEffect(effect, f"no owner to grant to ({getattr(subject, 'id', subject)})"))
        return

    from transversal.services.sfx_owner import add_sfx_to_owner

    if not add_sfx_to_owner(repo, owner_type, owner_id, sfx_id):
        # The same refusal an attach would give: wrong surface, or a rule that
        # may not be acquired here. Named rather than silent.
        result.applied.append(
            AppliedEffect(effect, f"{sfx_id} can't attach to {owner_type} {owner_id}"))
        return

    sfx = repo.get_sfx(sfx_id) if hasattr(repo, "get_sfx") else None
    label = getattr(sfx, "name", "") or sfx_id
    result.applied.append(AppliedEffect(effect, f"granted {label}", owner_id))
