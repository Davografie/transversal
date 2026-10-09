"""Roll-table resolution — map a roll / tier / index to a table entry."""

from __future__ import annotations

import logging
from typing import Optional

from transversal.domain import (
    OutcomeTier,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)

log = logging.getLogger("transversal.roll_table")

#: The separator the scheme-derived fallback key uses for a RANGE band. An
#: en-dash, matching what the canvas has always *displayed* — the fallback is for
#: content authored before keys existed, and a caller comparing a displayed key
#: to a stored one must not get two different answers for the same row.
BAND_SEPARATOR = "\u2013"


def row_key(entry: RollTableEntry, index: int = 0) -> str:
    """A row's **stable** identity — authored, else derived from its scheme.

    The authored ``key`` is the answer and is what a ``LifePathBinding`` names.
    The fallback exists only so content authored before keys existed still
    addresses consistently; it is derived from the same fields the canvas shows,
    and it **changes when the row changes** — which is exactly why it is a
    fallback and why ``migrate_lifepath_wrapper`` writes real keys.
    """
    authored = getattr(entry, "key", "") or ""
    if authored:
        return authored
    if entry.min_value is not None or entry.max_value is not None:
        lo = "" if entry.min_value is None else entry.min_value
        hi = "" if entry.max_value is None else entry.max_value
        return f"{lo}{BAND_SEPARATOR}{hi}"
    if entry.weight is not None:
        return f"w{entry.weight}"
    if entry.tier is not None:
        # A tier may arrive as the enum or as its plain JSON value.
        return getattr(entry.tier, "value", None) or str(entry.tier)
    return str(index)


def entry_key_for(table: RollTable, entry: RollTableEntry) -> str:
    """The key of an entry *within its table*, for a binding lookup."""
    entries = list(getattr(table, "entries", None) or [])
    try:
        index = entries.index(entry)
    except ValueError:
        index = 0
    return row_key(entry, index)


def resolve_table(
    table: RollTable,
    *,
    roll: Optional[int] = None,
    tier: Optional[OutcomeTier] = None,
    index: Optional[int] = None,
) -> Optional[RollTableEntry]:
    """Select an entry from a roll table.

    - ``index`` (1-based) is a manual / click selection and wins when provided.
    - ``roll`` drives RANGE, WEIGHT, and INDEX schemes.
    - ``tier`` drives the TIER scheme.

    Returns None when no entry matches.
    """
    if index is not None:
        i = index - 1
        return table.entries[i] if 0 <= i < len(table.entries) else None

    if table.scheme == RollTableScheme.TIER:
        if tier is None:
            return None
        for entry in table.entries:
            if entry.tier == tier:
                return entry
        return None

    if roll is None:
        return None

    if table.scheme == RollTableScheme.RANGE:
        for entry in table.entries:
            if (
                entry.min_value is not None
                and entry.max_value is not None
                and entry.min_value <= roll <= entry.max_value
            ):
                return entry
        return None

    if table.scheme == RollTableScheme.INDEX:
        i = roll - 1
        return table.entries[i] if 0 <= i < len(table.entries) else None

    if table.scheme == RollTableScheme.WEIGHT:
        total = sum(e.weight or 0 for e in table.entries)
        if total <= 0:
            return None
        r = ((roll - 1) % total) + 1  # normalize into 1..total
        cumulative = 0
        for entry in table.entries:
            cumulative += entry.weight or 0
            if r <= cumulative:
                return entry
        return None

    return None

# ── Content migration (B164) ─────────────────────────────────────────

def backfill_rolltable_anchor_paths(repo) -> int:
    """Move roll-table tie anchors off the legacy context pair onto the owner path.

    A trait gained or stepped on a *relationship* (a tenure on a faction) used to
    say which edge through ``context.relationship`` (+ an optional
    ``relationship_type``). That pair has no declarer left — no action offers it —
    so stored rules keeping it were uneditable, and the applier's handling is a
    legacy branch kept alive by exactly this content. The owner path is the same
    fact in the vocabulary everything else uses::

        select self → relationships → filter contact_id == <faction>
                                    → filter type == <membership|authored type>

    The ``type`` filter is **always** written, defaulting to ``membership``,
    because that is what the legacy branch looked up (``relationship_type or
    "membership"``) — without it the path would also match an edge of another kind
    to the same faction, which the rule never did.

    Idempotent: an effect that already carries an ``owner_spec`` is left alone, and
    so is one whose anchor is a runtime token (``{term_faction}`` — a *shared*
    table cannot name a faction, which is why the token exists; it stays on the
    context pair until a runtime binding can carry it). Returns the number of
    effects migrated.
    """
    from transversal.services.target_spec import TargetSpec

    changed = 0
    for table in repo.list_roll_tables():
        touched = False
        for entry in table.entries or []:
            for effect in [*(entry.cost_effects or []), *(entry.effects or [])]:
                if effect.owner_spec is not None:
                    continue
                context = dict(effect.context or {})
                faction = context.get("relationship")
                if not faction:
                    continue
                if str(faction).startswith("{") and str(faction).endswith("}"):
                    log.warning(
                        "[backfill_rolltable_anchor_paths] %s/%s: anchor %s is a runtime "
                        "token — left on the context pair", table.id, entry.label, faction)
                    continue
                rel_type = (context.get("relationship_type") or "membership").strip() or "membership"
                effect.owner_spec = TargetSpec.model_validate({"steps": [
                    {"kind": "select", "collection": "self"},
                    {"kind": "navigate", "edge": "relationships"},
                    {"kind": "filter", "field": "contact_id", "operator": "==", "value": faction},
                    {"kind": "filter", "field": "type", "operator": "==", "value": rel_type},
                ]})
                context.pop("relationship", None)
                context.pop("relationship_type", None)
                # `Effect.context` is a dict and never null: an emptied one is `{}`.
                effect.context = context
                changed += 1
                touched = True
        if touched:
            repo.update_roll_table(table)
    return changed

# ── The names a table's effects may use ──────────────────────────────

#: The ambient facts every roll-table entry is applied with, in the author's terms.
#: They are seeded, not declared: the engine holds them, and there is no path that
#: could express them (``pending_term`` is a checkpoint field, invisible to
#: targeting), so making an author declare them would be busywork.
AMBIENT_TABLE_BINDINGS = ("term_faction", "term_path", "path_faction", "path_id",
                          "table_id", "roll", "entry_tier")


def table_bindings(table, entity, repo, *, entry=None, roll=None, tier=None,
                   index=None) -> dict:
    """The scope a roll-table entry's conditions and effects resolve against.

    Two kinds of name, one scope:

    * **ambient** — what the engine already knows. ``path_faction`` is the faction
      of *this table's* path, read from the entity's **enrollment** (which records
      faction × path), so it does not depend on which term happens to be in
      progress and answers correctly for an entity enrolled in several paths. A
      shared table (``life_path=None``) has no path of its own, so it falls back to
      the term that invoked it; ``term_faction``/``term_path`` are always the
      invoking term's, and ``table_id``/``roll``/``entry_tier`` describe the roll.
    * **declared** — ``table.bound_variables``: the author's own names, each a
      targeting path, resolved in declaration order into the same scope (a later
      declaration may start from an earlier one, and from any ambient name).

    A name that resolves to nothing is left *unbound*, never bound empty: for every
    reader, "no value" and "no such name" are the same state, and a downstream path
    then resolves to nobody rather than to a blank id.
    """
    from transversal.services.target_resolver import (
        Binding, TargetContext, bind_named, resolve,
    )
    from transversal.services.target_spec import ValueType

    def one(value, element=""):
        text = str(value)
        return Binding(value=text, values=[text], element=element, cardinality="one")

    bindings: dict = {}
    term = getattr(entity, "pending_term", None)
    term_faction = (getattr(term, "faction_id", "") or "") if term is not None else ""
    term_path = (getattr(term, "path_id", "") or "") if term is not None else ""

    table_path = getattr(table, "life_path", "") or ""
    enrollment = None
    if table_path:
        enrollment = next(
            (e for e in (getattr(entity, "life_paths", None) or [])
             if (getattr(e, "path_id", "") or "") == table_path),
            None,
        )
    if enrollment is not None and getattr(enrollment, "faction_id", ""):
        bindings["path_faction"] = one(enrollment.faction_id, "entity")
        bindings["path_id"] = one(enrollment.path_id or table_path)
    elif term_faction:
        # Shared table: the invoking term is the only honest answer.
        bindings["path_faction"] = one(term_faction, "entity")
    if term_faction:
        bindings["term_faction"] = one(term_faction, "entity")
    if term_path:
        bindings["term_path"] = one(term_path)
    if getattr(table, "id", ""):
        bindings["table_id"] = one(table.id)
    if roll is not None:
        bindings["roll"] = one(roll)
    # The **entry's** metadata, which is what an effect usually wants: which row
    # ran, and — on a tiered table — the effect die the tier carries. The tier
    # comes from the argument when the roll produced it, else from the entry
    # itself (a TIER table declares its tier per row), so a menu pick has it too.
    resolved_tier = tier if tier is not None else getattr(entry, "tier", None)
    if entry is not None:
        if getattr(entry, "label", ""):
            bindings["entry_label"] = one(entry.label)
        if index is not None:
            bindings["entry_index"] = one(index)
        if getattr(entry, "min_value", None) is not None:
            bindings["entry_min"] = one(entry.min_value)
        if getattr(entry, "max_value", None) is not None:
            bindings["entry_max"] = one(entry.max_value)
    if resolved_tier is not None:
        bindings["entry_tier"] = one(getattr(resolved_tier, "value", resolved_tier))
        effect_die = getattr(resolved_tier, "effect_die", None)
        if effect_die is not None:
            # `OutcomeTier.effect_die` — marginal d4, success d6, exceptional d8,
            # perfect d10, fail none. A die, so an effect's ``result`` can name it.
            bindings["entry_effect_die"] = one(getattr(effect_die, "value", effect_die))

    declared = getattr(table, "bound_variables", None) or []
    if declared and repo is not None:
        ctx = TargetContext(subject=entity, repo=repo, bindings=dict(bindings))
        for declared_var in declared:
            name = (getattr(declared_var, "name", "") or "").strip()
            spec = getattr(declared_var, "spec", None)
            if not name or spec is None or not getattr(spec, "steps", None):
                continue
            if name in ctx.bindings:
                log.info("[table_bindings] table=%s variable '%s' shadows an existing "
                         "name — refused", table.id, name)
                continue
            resolution = resolve(spec, ctx)
            last = resolution.trace[-1] if resolution.trace else None
            if resolution.errors or not resolution.values or last is None or not last.element:
                log.info("[table_bindings] table=%s variable '%s' resolved nothing",
                         table.id, name)
                continue
            bind_named(name, resolution.values, ValueType(last.element, last.cardinality), ctx)
        bindings = dict(ctx.bindings)
    return bindings

def entry_applies(entry, entity, repo, bindings: dict | None = None, *,
                  source=None, source_element: str | None = None) -> bool:
    """Whether a table entry's own conditions hold for this entity.

    The conditions read the entry scope ([[B164]]): the ambient facts — the term's
    faction, *this table's* path faction, the table, the roll and tier that reached
    the entry — plus whatever the table declares. An entry with no conditions
    always applies, which is every entry today (see [[B179]]).
    """
    conditions = list(getattr(entry, "conditions", None) or [])
    if not conditions:
        return True
    if repo is None:
        return False
    from transversal.services.conditions import evaluate_conditions

    return evaluate_conditions(entity, conditions, repo, {}, source=source,
                               source_element=source_element,
                               out_bindings=dict(bindings or {}))


def resolve_applicable_entry(table, entity, repo, *, roll=None, tier=None, index=None,
                             bindings: dict | None = None, source=None,
                             source_element: str | None = None):
    """The entry to run: the one the roll picked, or the previous one that applies.

    **Fall back, don't re-roll** (the author's call, 2026-09-25): when the selected
    entry's conditions do not hold, the nearest entry *before it in the table* whose
    conditions do hold is used. Walking back over the list is what keeps a RANGE
    table predictable — a roll keeps its row, and an excluded row hands over to the
    one below it rather than redistributing the die — and it cannot invent an entry
    that no roll could reach. When nothing applies the answer is ``None``: the
    caller reports it rather than running a row that does not fit.

    A **deliberate** pick (``index``, the menu path) is not steered this way: the
    caller refuses it instead, because silently running a different row than the one
    someone chose is a worse surprise than being told it is not available.
    """
    entry = resolve_table(table, roll=roll, tier=tier, index=index)
    if entry is None:
        return None
    if entry_applies(entry, entity, repo, bindings, source=source,
                     source_element=source_element):
        return entry
    entries = list(getattr(table, "entries", None) or [])
    try:
        position = entries.index(entry)
    except ValueError:  # a resolved entry not in the list: nothing to walk back over
        return None
    for candidate in reversed(entries[:position]):
        if entry_applies(candidate, entity, repo, bindings, source=source,
                         source_element=source_element):
            log.info("[resolve_applicable_entry] table=%s: entry %r does not apply — "
                     "fell back to %r", getattr(table, "id", ""), entry.label,
                     candidate.label)
            return candidate
    return None
