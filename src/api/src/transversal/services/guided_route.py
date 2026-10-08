"""Guidance — the arrival half of the guided route ([[Guided Route]]).

An SFX grants a character **directions in the fiction** (a mayor asks the party to
clear the goblin cave), and the viewer lights exactly one hop at a time. The
destination is stored on the entity (``Entity.destination_location``) and read by
the viewer; the destination's *name*, the *route* and the *next hop* are all
derived, so nothing here caches a label or a path that a later edit could make
wrong.

Reaching the destination ends the guidance. That is **state maintenance, not a
rule**: it has to happen however the character got there — a portal, a GM
placement, a step up the hierarchy, an effect — so it rides the one
``location_changed`` dispatch that every arrival passes through, rather than a new
event or three remembered call sites that would drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from transversal.services.effect_refs import target_value

if TYPE_CHECKING:  # pragma: no cover - typing only
    from transversal.domain import Effect, SFX


def clear_arrived_destination(repo, entity_id: Optional[str], arrived_at: Optional[str]) -> bool:
    """Clear an entity's destination when it is standing on it.

    Returns whether it cleared anything. The comparison is against **the
    destination**, not "any location change": a route runs through places, and a
    character with an objective may make a side trip — clearing on any move would
    retire the guidance the first time they went anywhere.

    A missing destination, an unknown entity, or an arrival with no location is a
    no-op rather than an error: most arrivals have nothing to do with guidance.
    """
    if not entity_id or not arrived_at:
        return False
    entity = repo.get_entity(entity_id)
    if entity is None:
        return False
    if not getattr(entity, "destination_location", None):
        return False
    if entity.destination_location != arrived_at:
        return False
    entity.destination_location = None
    repo.update_entity(entity)
    return True


# ── Directions that lead nowhere ──────────────────────────────
#
# A rule that grants directions from a place that cannot reach the destination is
# a **lie that looks like a rule**: the map lights nothing, and the GM who authored
# "ask the mayor for the way" has no way to see it cannot work. The graph is
# fragmentary in practice (195 of 410 locations are unreachable from the one
# authored control point), so this is a real authoring situation.
#
# The origin is the place the guidance starts from. Only a **location** owner has
# one: an entity moves, so what it could tell you depends on where it is when the
# rule fires, and refusing on a snapshot of that would be a guess. This refuses
# only what it can prove.


def literal_destination(effect: "Effect", repo) -> Optional[str]:
    """The location a ``set_destination`` effect names outright, if it names one.

    A *path* target is skipped on purpose: which place it resolves to is the
    world's answer at fire time, so there is nothing to check while authoring.
    """
    if (effect.type, effect.action) != ("set_destination", "set"):
        return None
    if effect.target_spec is not None and effect.target_spec.steps:
        return None
    raw = target_value(effect).strip()
    if not raw or raw.startswith("{"):
        return None
    loc = repo.get_entity(raw)
    if loc is None or getattr(loc, "type", "") != "location":
        return None
    return raw


def place_name(repo, location_id: str) -> str:
    loc = repo.get_entity(location_id)
    return (getattr(loc, "name", "") or location_id) if loc is not None else location_id


def declares_literal_directions(sfx: "SFX") -> bool:
    """Whether this rule grants directions to a place it names outright.

    A cheap pre-check that reads no repository at all, so a caller can skip the
    (rep-backed) ownership and reachability reads for the overwhelming majority of
    rules that grant no directions.
    """
    for effect in getattr(sfx, "effects", None) or []:
        if (effect.type, effect.action) != ("set_destination", "set"):
            continue
        if effect.target_spec is not None and effect.target_spec.steps:
            continue
        raw = target_value(effect).strip()
        if raw and not raw.startswith("{"):
            return True
    return False


@dataclass(frozen=True)
class UnreachableDirections:
    """A ``set_destination`` effect whose destination nothing leads to.

    Returned structured rather than as a sentence because there are two audiences
    with different room: the editor's warning list can afford the whole story
    (which place, which destination, what to do), while the *attach* refusal is
    spliced into ``'<name>' <reason>, not <owner type>`` and has to stay a phrase.
    One predicate, two renderings — so they cannot disagree about what is wrong.
    """
    effect_index: int
    destination: str
    origins: tuple[str, ...]


def find_unreachable_directions(sfx: "SFX", repo, origins: list[str]) -> list[UnreachableDirections]:
    """Every ``set_destination`` that cannot be followed from ``origins``.

    Empty when there is nothing to prove: no such effect, no literal destination,
    or no origin to measure from.
    """
    if repo is None or not origins or not declares_literal_directions(sfx):
        return []
    findings: list[UnreachableDirections] = []
    for i, effect in enumerate(sfx.effects):
        destination = literal_destination(effect, repo)
        if destination is None:
            continue
        if any(repo.get_location_distances_from(origin, {destination}) for origin in origins):
            continue
        findings.append(UnreachableDirections(i, destination, tuple(origins)))
    return findings


def describe_unreachable(finding: UnreachableDirections, repo) -> str:
    """The whole story, for the editor's authoring warnings."""
    from_names = " or ".join(place_name(repo, o) for o in finding.origins)
    return (
        f"Effect {finding.effect_index + 1}: nothing leads from {from_names} to "
        f"{place_name(repo, finding.destination)}, so these directions could never be "
        f"followed — give one of them a route, or grant them from a place that can reach it"
    )


def refusal_reason(finding: UnreachableDirections, repo) -> str:
    """The phrase for ``attach_refusal``, whose caller appends ``, not <owner type>``.

    Every other refusal there is a verb phrase ("belongs on Trait", "can't be
    acquired here") and reads as the answer to *why not here?*; a full sentence
    left that template trailing.
    """
    return (f"belongs on a place that can reach "
            f"{place_name(repo, finding.destination)}")
