"""Walkability — may *this* entity walk a life path? ([[B194]])

A life path's ``conditions`` are an **entity-scoped** gate. They are deliberately
not ``discovery``: discovery is a one-time reveal of the path's *existence*, while
these answer whether the character may actually **walk** it now. The human draws
that line explicitly.

The evaluation is the effects system's, reused whole rather than reimplemented:
``static_conditions`` narrows to the conditions that need no trigger/menu
context, ``evaluate_condition`` reads them against the entity, and
``condition_text`` phrases them the way the author wrote them. This is the same
treatment ``sfx_owner.unavailable_sfx_reasons`` gives a rule, for the same reason:
the human's call (2026-09-25) is that an unwalkable path stays **visible and
disabled, carrying why** — and a disabled thing with no reason is worse than one
that is merely disabled.

**What may be a reason.** Only a condition this read can actually answer from the
entity alone:

* a **context-gated** one (``roll_tier``, ``arrival_kind``, a ``{variable}``) is
  not false, it is *unknown* until the moment it would fire, so reporting it would
  disable a path that is perfectly walkable;
* a condition that needs a **source** (``source_rating``) can never be satisfied
  here at all — a life path is not an SFX and has none — so letting it gate would
  make the path permanently unwalkable by accident, silently.

Neither kind is a gate *or* a reason. Keeping them out of the authoring surface is
[[B197]]'s business, exactly as the SFX editor already greys out "Source rating"
for a source-less rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from transversal.db.repository import EntityRepository
    from transversal.domain import Condition, Entity, LifePath


def _needs_source(condition: "Condition") -> bool:
    """True when the condition's type declares it reads the rule's own source."""
    from transversal.services.conditions import CONDITION_TYPES

    name = getattr(condition.type, "name", str(condition.type))
    meta = next((t for t in CONDITION_TYPES if t.value == name), None)
    return bool(meta and meta.requires_source_elements)


def evaluable_conditions(conditions: Optional[list["Condition"]]) -> list["Condition"]:
    """The conditions answerable from the entity alone — no context, no source.

    ``static_conditions`` answers the first half (it derives "reads no context"
    from the catalog's declaration — [[B195]]); this adds the second.
    """
    from transversal.services.conditions import static_conditions

    return [c for c in static_conditions(list(conditions or [])) if not _needs_source(c)]


def unwalkable_reasons(
    repo: "EntityRepository", entity: Optional["Entity"], paths: list["LifePath"]
) -> dict[str, list[str]]:
    """``path_id →`` the conditions that stop this entity walking it.

    A path absent from the result is walkable. One entry per failing condition,
    phrased as the author wrote it and framed as **unmet**: ``condition_text``
    renders the *positive* form ("you are in Three Realms"), which on a failing
    condition reads as its opposite, so a bare phrase would state the reverse of
    the truth. Same framing, and same reason, as ``unavailable_sfx_reasons``.
    """
    from transversal.services.conditions import evaluate_condition
    from transversal.services.sfx_text import condition_text, repo_name_resolver

    if entity is None:
        return {}
    resolve = repo_name_resolver(repo)
    reasons: dict[str, list[str]] = {}
    for path in paths:
        gate = evaluable_conditions(getattr(path, "conditions", None))
        if not gate:
            continue
        failing: list[str] = []
        for condition in gate:
            if evaluate_condition(entity, condition, repo):
                continue
            phrase = condition_text(condition, resolve=resolve)
            failing.append(f"unmet: {phrase}" if phrase else "unmet: a condition it declares")
        if failing:
            reasons[str(path.id)] = failing
    return reasons
