"""Trait helpers — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import DieType
from transversal.domain import Effect
from transversal.domain import Entity
from transversal.domain import Polarity
from transversal.domain import RatingType
from transversal.domain import TraitSetting
from typing import Optional
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
)


def _resolve_traitset_id(trait_id: str, repo) -> str:
    trait = repo.get_trait(trait_id)
    return trait.traitset_id if trait else ""

def _trait_owner(entity: Entity, effect: Effect, repo) -> tuple[str, str]:
    """Return ``(from_type, owner_id)`` for the trait targeted by an effect.

    **A resolved owner path wins.** The action declares what that path may land on
    (``owner_elements``) and the engine resolves it, so the kind is read from the
    declaration rather than guessed from the value — which is how a tie (a
    relationship edge) and a facet (another trait instance) are anchored now.

    With no owner path the owner is the subject entity.

    **The legacy branch below is for stored content only.** No action declares
    ``context.relationship`` / ``relationship_type`` any more — that pair was the
    old way to anchor a tie, and it survives here because **14 roll-table effects**
    still carry it (plus one seeded ``{term_faction}`` rule). Reading it keeps
    their anchors working; migrating them to the owner path is [[B164]], after
    which this branch and its reserved token can go.

    An absent edge is **not** created here: ``create_relationship`` takes its key
    from Arango and a trait setting stores its owner by that key, so the edge must
    be committed first. Effects commit one at a time within an activation, so the
    working shape is *two* effects — a Create Relationship, then the gain.
    Returns ``("missing", target)`` when a relationship was asked for but no such
    edge exists, so the caller can say so instead of guessing.
    """
    from transversal.services.effects_applier.datatypes import OWNER_ID_CONTEXT_KEY
    from transversal.services.effects_applier.datatypes import OWNER_KIND_CONTEXT_KEY
    from transversal.services.effects_registry.lookup import owner_elements_for

    # A resolved owner path wins: the kind is the element the path landed on, and
    # the action's declaration is the permission it is checked against. Content
    # stored when a verb declared a *single* kind carries an id and no kind, and
    # still means that one — a verb that declares several cannot guess from an id
    # alone, so an untyped id anchors to nobody rather than to a foreign
    # collection's row.
    resolved_owner = (effect.context or {}).get(OWNER_ID_CONTEXT_KEY)
    declared = owner_elements_for(effect.type, effect.action)
    if resolved_owner and declared:
        landed = (effect.context or {}).get(OWNER_KIND_CONTEXT_KEY) or ""
        if landed in declared:
            return (landed, resolved_owner)
        if len(declared) == 1:
            return (declared[0], resolved_owner)

    # A declared owner **path** that resolved to nothing is not "no owner": it is a
    # missing anchor, and falling back to the subject entity would write the trait
    # in the wrong place — silently, because the effect then reports success. The
    # spec survives resolution exactly when it resolved nothing
    # (`resolve_effect_owner` clears it only on a hit), so that is the signal.
    # This is also what keeps the [[B164]] migration faithful: the legacy branch
    # below answers ``("missing", …)`` for an absent edge, and a migrated rule must
    # not quietly behave worse while looking better.
    if declared and getattr(effect, "owner_spec", None) is not None:
        return ("missing", f"no {declared[0]} matched the anchor path")

    rel_target = (effect.context or {}).get("relationship")
    if rel_target == "{term_faction}":
        # Shared tables can't hardcode a faction; resolve to the faction **the
        # acting body** is currently in a term with ([[B271]]).
        from transversal.services.lifepath_scope import active_term

        term = active_term(entity, repo)
        rel_target = (term.faction_id or "") if term is not None else ""
    if rel_target:
        rel_type = (_ctx(effect, "relationship_type") or "membership").strip() or "membership"
        rel = repo.get_relationship(entity.id, rel_target, rel_type)
        if rel and rel.get("_key"):
            return ("relationship", rel["_key"])
        return ("missing", f"{rel_target} ({rel_type})")
    return ("entity", entity.id)

def _find_traitsetting(owner: tuple[str, str], repo, trait_id: str) -> Optional[TraitSetting]:
    from_type, owner_id = owner
    if from_type == "relationship":
        settings = repo.get_relationship_traitsettings(owner_id)
    elif from_type == "projection":
        # A body's own traits: the entity is the same either way, so the read is
        # by projection id.
        settings = repo.get_projection_traitsettings(owner_id)
    elif from_type == "traitsetting":
        # A nested instance's "already here?" is asked of its *parent*, not of the
        # entity — the entity's own settings deliberately exclude them.
        settings = repo.get_sub_traitsettings(owner_id)
    else:
        settings = repo.get_traitsettings_for_entity(owner_id)
    for ts in settings:
        if ts.trait_id == trait_id:
            return ts
    return None

def _find_traitsetting_by_target(subject: Entity, effect: Effect, repo, target: str) -> Optional[TraitSetting]:
    """Resolve a trait-mutation target to a TraitSetting.

    Prefers a direct *instance* lookup — the target is a traitsetting id (e.g.
    ``kael-1:trait-martial``) produced by the ``die→traitsetting`` drillthrough.
    Falls back to the legacy registry-trait + owner lookup so an authored trait
    id (``trait-martial``) still resolves to the subject's instance.
    """
    if target:
        getter = getattr(repo, "get_traitsetting", None)
        if getter is not None:
            ts = getter(target)
            if ts is not None:
                return ts
    return _find_traitsetting(_trait_owner(subject, effect, repo), repo, target)

def _allow_duplicates(trait_id: str, repo) -> bool:
    """Whether the trait's set permits more than one instance (default refuse)."""
    traitset_id = _resolve_traitset_id(trait_id, repo)
    get_traitset = getattr(repo, "get_traitset_by_id", None)
    traitset = get_traitset(traitset_id) if traitset_id and get_traitset else None
    return bool(getattr(traitset, "allow_duplicates", False))

def _resolve_new_traitsetting_id(owner: tuple[str, str], trait_id: str, statement: str, repo, *, negative: bool = False, parent=None) -> str:
    """The key a new instance lands under, honouring the set's duplicate rule.

    A set that allows duplicates distinguishes same-trait instances by their
    statement, so the id and the collision check have to use the same scheme —
    this is the one place that decides it for the gain path (copy/move ask the
    repository directly, because there the statement comes from the *source*
    instance rather than from the effect's context).

    A **negative** instance keeps the ``:complication`` suffix it has always had,
    so the polarity stays visible in the key and a positive instance of the same
    registry trait on the same owner cannot take its place — one live row
    (``gmc-40729203:trait-148427798:complication``) depends on the old shape.
    """
    if parent is not None:
        # A nested instance is scoped to its **parent container**, not the entity:
        # one registry trait legitimately appears many times under one parent (every
        # portent is a setting of the same generic trait), so the key is
        # parent-scoped and the statement disambiguates — the repository owns that
        # convention, and the collision check asks the same question.
        resolve_sub = getattr(repo, "resolve_subtrait_id", None)
        if resolve_sub is not None:
            return resolve_sub(getattr(parent, "id", ""), trait_id, statement)

    owner_id = owner[1]
    resolve = getattr(repo, "resolve_traitsetting_id", None)
    base = (resolve(owner_id, trait_id, statement, _allow_duplicates(trait_id, repo))
            if resolve is not None else f"{owner_id}:{trait_id}")
    return f"{base}:complication" if negative else base

def _find_conflicting_traitsetting(subject: Entity, effect: Effect, repo, target: str, statement: str) -> Optional[TraitSetting]:
    """The existing instance a gain of ``target`` would collide with.

    The gain path's twin of ``_find_traitsetting_by_target``: it keeps the
    direct-instance lookup (a target may *be* a traitsetting id) but asks the
    repository's duplicate rule instead of treating "any instance of the trait"
    as a collision. A set that allows duplicates collides only on the same
    statement, which is what makes two portents of one registry trait possible.

    Only entity-anchored traits have this rule — a relationship-anchored trait is
    one instance per edge by construction — so that case keeps the plain lookup.
    """
    if target:
        getter = getattr(repo, "get_traitsetting", None)
        if getter is not None and getter(target) is not None:
            return getter(target)
    owner = _trait_owner(subject, effect, repo)
    if owner[0] != "entity":
        return _find_traitsetting(owner, repo, target)
    conflict = getattr(repo, "find_traitsetting_collision", None)
    if conflict is None:
        # No duplicate rule to consult (a bare repo double) — refuse as before.
        return _find_traitsetting(owner, repo, target)
    return conflict(subject.id, target, statement, _allow_duplicates(target, repo))

def _resync_pool(ts: TraitSetting) -> None:
    """Let an assembled pool follow its trait's new rating.

    One home for the call, because a rating change and its undo must both do it —
    a pool that follows the forward change but not the restore would show a
    temporary size against a trait that reads its own. Tolerates a double without
    an owning entity (there is then no pool to follow).
    """
    entity_id = getattr(ts, "entity_id", "")
    if not entity_id:
        return
    from transversal.services.scene_state import resync_pool_dice_for_trait
    resync_pool_dice_for_trait(entity_id, ts.id, [d.value for d in (ts.dice or [])])

def _step_up(ts: TraitSetting) -> bool:
    """Step up the smallest die, capped at d12. Restores an empty rating to d4."""
    if not ts.dice:
        ts.dice = [DieType.D4]
        return True
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D12:
        return False
    ts.dice[ts.dice.index(smallest)] = smallest.step_up()
    return True

def _step_down_one(ts: TraitSetting) -> str:
    """Step down the smallest die. Returns ``"stepped" | "empty"``.

    A d4 die steps down to no die (empty rating) — the trait *persists* with an
    empty rating rather than being deleted, so a temporary step-down can revert.
    """
    if not ts.dice:
        return "empty"
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D4:
        ts.dice.remove(smallest)
        return "stepped"
    ts.dice[ts.dice.index(smallest)] = smallest.step_down()
    return "stepped"

def _steps(effect: Effect) -> int:
    """Read the optional step magnitude from an effect's context (default 1)."""
    raw = (effect.context or {}).get("steps")
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1

def _opt_int(effect: Effect, key: str) -> Optional[int]:
    """An optional integer context value, or None when unauthored.

    ``None`` matters: an order of 0 and "no order given" are different answers, and
    the model treats an unordered instance as unranked rather than first.
    """
    raw = (effect.context or {}).get(key)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _opt_bool(effect: Effect, key: str) -> Optional[bool]:
    """An optional boolean context value, or None when unauthored."""
    raw = (effect.context or {}).get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def _has_steps(effect: Effect) -> bool:
    """True when ``steps`` was explicitly provided in the effect's context."""
    return "steps" in (effect.context or {})

def _step_up_trait(entity: Entity, ts: TraitSetting, target: str, effect: Effect, result, repo, steps: int = 1) -> bool:
    """Step up a trait setting up to ``steps`` times.

    Returns True when the rating changed (caller persists + reverts). A negative
    trait pushed beyond d12 takes the entity out (once) and leaves the trait at
    d12.
    """
    applied = 0
    for _ in range(steps):
        if _step_up(ts):
            applied += 1
        else:
            break  # empty dice or already at d12

    if applied < steps:
        if ts.polarity == Polarity.NEGATIVE:
            entity.taken_out = True
            result.applied.append(AppliedEffect(effect, f"{target} stepped beyond d12 — taken out"))
            from transversal.domain import Effect as _Effect, EffectTiming as _ET, Timer as _Timer, TimerCombine as _TC
            from transversal.services.scheduled_events import schedule_event
            schedule_event(
                repo, "entity", entity.id,
                _Effect(timing=_ET.IMMEDIATE, type="entity", action="clear_taken_out", target="self"),
                [_Timer(event="scene", remaining=1)],
                _TC.FIRST_TO_FIRE,
            )
        elif applied == 0:
            result.applied.append(AppliedEffect(effect, f"{target} already at d12"))
    return applied > 0

def _die(result: Optional[str]) -> DieType:
    return DieType(str(result).lower()) if result else DieType.D4

def _die_opt(result: Optional[str]) -> Optional[DieType]:
    """Parse a die rating, or ``None`` when the value is not one.

    Used where an unreadable rating must *skip* rather than default: a
    substituted roll variable is empty when the die's tier has no effect die
    (a fail), and a token that never substituted is not a die either.
    """
    raw = str(result or "").strip().lower()
    if not raw:
        return None
    try:
        return DieType(raw)
    except ValueError:
        return None

def _effect_dice(effect: Effect) -> list[DieType]:
    """The **rating** an effect creates a trait at — a row of dice, never empty.

    A rating is a list: a resource holds several dice, a challenge usually three
    (measured on live content: 774 instances carry more than one). So the author's
    row lives in ``context['dice']``, and ``result`` stays the *first* die of it —
    which is what every single-die reader in this module and elsewhere already
    understands, and what all content authored before the row existed carries
    ([[B307]]).

    A path that names the dice (``result_spec``) writes the same two fields, so
    "gain this at the rating the source already has" and a literal row arrive here
    identically (``effects_applier.resolve_effect_result``).

    Unreadable entries are refused **whole** rather than dropped: a row of three
    where one fails to parse would otherwise create a two-die rating, which is a
    wrong rating that looks like a right one. An empty return means "nothing to
    apply", and every caller reports it instead of inventing a die — a substituted
    roll variable is empty when the die's tier has no effect die (a fail), and a
    token that never substituted is not a die either.
    """
    raw = (effect.context or {}).get("dice")
    if isinstance(raw, list) and raw:
        dice = [_die_opt(v) for v in raw]
        return [] if any(d is None for d in dice) else dice  # type: ignore[return-value]
    single = _die_opt(effect.result)
    return [single] if single is not None else []


def _dice_label(dice: list[DieType]) -> str:
    """A rating as the author reads it: ``d6``, or ``d6 ×3`` when it is a row.

    The report lines are prose the author reads in the activation summary, and a
    challenge's three ``d6`` are one fact about it, not three.
    """
    values = [getattr(d, "value", str(d)) for d in dice]
    if len(values) == 1:
        return values[0]
    if len(set(values)) == 1:
        return f"{values[0]} ×{len(values)}"
    return ", ".join(values)


def _ctx(effect: Effect, key: str) -> str:
    """Read a string context value (empty when absent)."""
    return str((effect.context or {}).get(key) or "")

def _rating_type(effect: Effect) -> RatingType:
    """Rating type authored on a trait-gain effect (default STATIC)."""
    raw = _ctx(effect, "rating_type").lower() or "static"
    try:
        return RatingType(raw)
    except ValueError:
        return RatingType.STATIC

def _new_traitsetting(owner: tuple[str, str], trait_id: str, dice: list[DieType], repo, *, negative: bool = False, statement: str = "", notes: str = "", rating_type: RatingType = RatingType.STATIC, parent=None, order=None, enabled=None) -> TraitSetting:
    """Build a new instance, on an owner or nested under ``parent``.

    ``dice`` is the instance's whole rating — one die for a static trait, several
    for a resource or a challenge — because that is what a rating *is*
    ([[B307]]). Callers get it from :func:`_effect_dice`.

    ``parent`` is the facet case: the instance hangs under another *instance*
    (an agenda's step under its container) rather than off the entity, so it takes
    the parent's entity, ``from_type='traitsetting'`` and the parent-scoped key
    scheme. ``order``/``enabled`` are the fields that only mean anything there —
    an agenda rule creating the next step needs both.
    """
    from transversal.services.polarity import default_polarity

    from_type, owner_id = owner
    if parent is not None:
        from_type, owner_id = "traitsetting", getattr(parent, "entity_id", "") or owner_id
    traitset_id = _resolve_traitset_id(trait_id, repo)
    trait = repo.get_trait(trait_id)
    get_traitset = getattr(repo, "get_traitset_by_id", None)
    traitset = get_traitset(traitset_id) if traitset_id and get_traitset else None
    polarity = Polarity.NEGATIVE if negative else default_polarity(trait, traitset)
    if not traitset_id and polarity == Polarity.NEGATIVE:
        traitset_id = "ts-complications-a190"
    projection_id = None
    if from_type == "projection":
        # An explicit body anchor: the owner id *is* the projection. Without this
        # the row kept `from_type='projection'` and no id, so it anchored to
        # `projections/<entity_id>` — a body that does not exist.
        projection_id = owner_id
    elif from_type == "entity" and trait is not None and not getattr(trait, "default_ego", False):
        # Morph-by-default — anchor the grant to the entity's active projection.
        get_entity = getattr(repo, "get_entity", None)
        entity = get_entity(owner_id) if get_entity else None
        if entity is not None and entity.current_projection:
            from_type = "projection"
            projection_id = entity.current_projection
    return TraitSetting(
        id=_resolve_new_traitsetting_id(owner, trait_id, statement, repo,
                                       negative=polarity == Polarity.NEGATIVE,
                                       parent=parent),
        entity_id=owner_id,
        trait_id=trait_id,
        from_type=from_type,
        parent_traitsetting_id=getattr(parent, "id", None),
        **({"order": order} if order is not None else {}),
        **({"enabled": enabled} if enabled is not None else {}),
        projection_id=projection_id,
        dice=list(dice),
        rating_type=rating_type,
        polarity=polarity,
        statement=statement,
        notes=notes,
        source_type="effect",
    )
