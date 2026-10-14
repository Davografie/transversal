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


def declared_type_of(declared) -> Optional["ValueType"]:
    """The type a declaration **states** about itself, or None when it states none.

    The one definition of what ``element``/``cardinality`` mean, so the engine and
    the save-time validator cannot disagree about whether a name is typed.
    """
    from transversal.services.target_spec import ValueType

    element = (getattr(declared, "element", "") or "").strip()
    if not element:
        return None
    cardinality = (getattr(declared, "cardinality", "") or "").strip() or "one"
    return ValueType(element, cardinality)


def is_reservation(declared) -> bool:
    """A typed slot with **no value** — a table's promise to its own rows.

    Distinct from a typed *declaration*, which has both a type and a path: that
    resolves a value, and its path is checked against the type it stated.
    """
    spec = getattr(declared, "spec", None)
    return declared_type_of(declared) is not None and not (
        spec is not None and getattr(spec, "steps", None)
    )


def _table_scope_types(table) -> dict:
    """The types a table's **own** declarations put in scope, in declaration order.

    Built by tracing rather than resolving, because the question is only what type
    each name reaches — which is what lets a later declaration start from an
    earlier one (``select variable``) without a repo or an entity in hand. A
    **reservation** contributes nothing: it has no value, so a path cannot start
    from it, and pretending otherwise would validate a path that can never resolve.
    """
    from transversal.services.target_spec import trace

    scope: dict = {}
    for declared in (getattr(table, "bound_variables", None) or []):
        name = (getattr(declared, "name", "") or "").strip()
        spec = getattr(declared, "spec", None)
        if not name or spec is None or not getattr(spec, "steps", None):
            continue
        reached = traced_type(spec, scope)
        if reached is not None:
            scope[name] = reached
    return scope


def traced_type(spec, scope: Optional[dict] = None) -> Optional["ValueType"]:
    """The type a path reaches, or None when the walk cannot say.

    None is deliberately **not** a failure: a path that starts from a name this
    table does not state cannot be typed here, and "I cannot tell" must never be
    reported as "you are wrong" — the same rule that keeps a name resolving to
    nothing unbound rather than bound empty. Callers that must be sure of a type
    ask a question this cannot answer by refusing, not by guessing.
    """
    from transversal.services.target_spec import trace

    types, errors = trace(spec, None, dict(scope or {}))
    if errors or not types:
        return None
    return types[-1]


def override_names(*layers) -> set:
    """The names these declaration layers mean to **replace**, not merely shadow.

    The one definition of what ``override`` means ([[B290]]), so the resolver and
    the editor cannot disagree about it. It is meaningful only on a **caller's**
    declaration — a life path or a life path step, the holder that wraps a shared
    table — and it suppresses the table's own declaration of the name before any
    layer resolves, so an activation where the caller's path resolves to nothing
    leaves the name *unbound* rather than quietly falling back to the table's value.
    """
    return {
        name
        for declared in layers
        for d in (declared or [])
        if getattr(d, "override", False)
        and (name := (getattr(d, "name", "") or "").strip())
    }


def table_bindings(table, entity, repo, *, entry=None, roll=None, tier=None,
                   index=None, path=None, step=None) -> dict:
    """The scope a roll-table entry's conditions and effects resolve against.

    Two kinds of name, one scope:

    * **ambient** — what the engine already knows. ``path_faction`` is the faction
      of *this table's* path, read from the entity's **enrollment** (which records
      faction × path), so it does not depend on which term happens to be in
      progress and answers correctly for an entity enrolled in several paths. A
      shared table (``life_path=None``) has no path of its own, so it falls back to
      the term that invoked it; ``term_faction``/``term_path`` are always the
      invoking term's, and ``table_id``/``roll``/``entry_tier`` describe the roll.
    * **declared** — the author's own names, each a targeting path, resolved in
      declaration order into the same scope (a later declaration may start from an
      earlier one, and from any ambient name). There are **four layers**, and they
      resolve outermost first ([[B281]], [[B290]]):

      ```
      path → step → table → row
      ```

      ``path``/``step`` are the **caller's** layer — supplied by whichever path's
      step invoked this table, and **optional** because a table may also be rolled
      where there is no step at all (``roll_table_menu``, outside any term). They
      are what lets a **shared** table read the context its caller gives it:
      ``rt-advance`` reads ``{sect}`` rather than hardcoding a faction. ``table``
      resolves before any row is chosen, which is what lets a row's *conditions*
      read it; ``row`` resolves once that row has applied. A name an earlier layer
      already bound is **refused** rather than rebound — unless the caller's
      declaration marks itself an ``override``, which suppresses the table's own
      declaration of that name up front (see ``override_names``).

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
    # The *body's* term ([[B271]]): the ambient faction and path are facts about
    # the life being lived, and a character has one body per universe.
    from transversal.services.lifepath_scope import (
        active_term, enrollment_for_path, resolve_projection_id,
    )

    term = active_term(entity, repo)
    term_faction = (getattr(term, "faction_id", "") or "") if term is not None else ""
    term_path = (getattr(term, "path_id", "") or "") if term is not None else ""

    # Which path this table is being rolled in. A table that still names its own
    # path wins: that is a statement about *this table*, and a term running in
    # some other path must not re-anchor it. Everything else — every shared table,
    # and every table once the deprecated field goes ([[B270]]) — takes the
    # invoking term's path, which is what the wrapper made authoritative.
    table_path = (getattr(table, "life_path", "") or "") or term_path
    enrollment = None
    if table_path:
        enrollment = enrollment_for_path(
            entity, table_path, resolve_projection_id(entity, repo))
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

    # The declaration layers, resolved outermost first so a later one may start from
    # an earlier one: the **caller's** (a life path, then its step — [[B290]]), the
    # **table's** (resolved before any row is chosen, which is what lets a row's
    # conditions test them) and then the **chosen row's own** ([[B281]]).
    #
    # The caller's layers are **optional and absent rather than empty**: a step is
    # the only thing that knows which of a path's steps is speaking (a path may wrap
    # one table twice), and a table may also be rolled with no step at all
    # (`roll_table_menu`, outside any term), so neither can be inferred here.
    #
    # A table-level declaration may also be a **reservation**: a type with no value,
    # which binds nothing but fixes the type of the name it reserves. Every row that
    # assigns that name is then checked against the reservation instead of being
    # trusted, because a name's type was otherwise only as consistent as every
    # hand-written path that happened to use it — one row starting from a collection
    # where the rest pinned a value made the same name `many` for that row alone,
    # and nothing objected ([[B285]]).
    layers: list[tuple[str, list]] = []
    if path is not None and (getattr(path, "bound_variables", None) or []):
        layers.append(("path", list(path.bound_variables)))
    if step is not None and (getattr(step, "bound_variables", None) or []):
        layers.append(("step", list(step.bound_variables)))
    layers.append(("table", getattr(table, "bound_variables", None) or []))
    layers.append(("entry", getattr(entry, "bound_variables", None) or []))

    # An **override** is decided before any layer resolves: a caller's declaration
    # marked as such replaces the table's own declaration of that name outright, so
    # the table's value can never surface on an activation where the caller's path
    # resolved nothing. The table is the shared content, the path/step the caller,
    # and only the caller can mark one — a row overriding the table cannot work,
    # because the row does not exist yet when its conditions run.
    overridden = override_names(
        getattr(path, "bound_variables", None) if path is not None else None,
        getattr(step, "bound_variables", None) if step is not None else None,
    )
    if overridden:
        layers = [
            (owner, [d for d in declared
                     if (getattr(d, "name", "") or "").strip() not in overridden])
            if owner == "table" else (owner, declared)
            for owner, declared in layers
        ]

    if repo is not None and any(declared for _, declared in layers):
        reservations: dict = {}
        ctx = TargetContext(subject=entity, repo=repo, bindings=dict(bindings))
        for owner, declared in layers:
            for declared_var in declared:
                name = (getattr(declared_var, "name", "") or "").strip()
                spec = getattr(declared_var, "spec", None)
                if not name:
                    continue
                stated = declared_type_of(declared_var)
                if is_reservation(declared_var):
                    # Only a table reserves, and first one wins. The reservation
                    # deliberately does **not** join the value scope: it is a slot
                    # for a row to fill, and a name with no value stays unbound.
                    if owner == "table" and name not in reservations:
                        reservations[name] = stated
                    continue
                if spec is None or not getattr(spec, "steps", None):
                    continue
                # An existing name wins: the declaration is refused rather than
                # rebinding something a condition or an earlier layer already read.
                # The editor flags the collision, so this is the backstop — unless
                # the caller marked it an override, which is the explicit way to say
                # "I mean to replace the table's" (the table's is already gone).
                if name in ctx.bindings:
                    log.info("[table_bindings] table=%s %s variable '%s' shadows an "
                             "existing name — refused", table.id, owner, name)
                    continue
                resolution = resolve(spec, ctx)
                last = resolution.trace[-1] if resolution.trace else None
                if resolution.errors or not resolution.values or last is None or not last.element:
                    log.info("[table_bindings] table=%s %s variable '%s' resolved nothing",
                             table.id, owner, name)
                    continue
                reached = ValueType(last.element, last.cardinality)
                # The reservation is the promise, so it is what a mismatch is
                # measured against — and the value is bound with the **reserved**
                # type, so a reader cannot see the traced one by accident.
                wanted = reservations.get(name) or stated
                if wanted is not None and not wanted.matches(reached):
                    log.info("[table_bindings] table=%s %s variable '%s' is declared "
                             "%s/%s but resolves %s/%s — refused", table.id, owner, name,
                             wanted.element, wanted.cardinality, reached.element, reached.cardinality)
                    continue
                bind_named(name, resolution.values, wanted or reached, ctx)
        bindings = dict(ctx.bindings)
    return bindings

def entry_applies(entry, entity, repo, bindings: dict | None = None, *,
                  source=None, source_element: str | None = None) -> bool:
    """Whether a table entry's own conditions hold for this entity.

    The conditions read the entry scope ([[B164]]): the ambient facts — the term's
    faction, *this table's* path faction, the table, the roll and tier that reached
    the entry — plus whatever the invoking path and step supply ([[B290]]) and
    **the table** declares. Not the entry's own declarations: those cannot be known
    until this row is the row being considered, which is the question being asked
    ([[B281]]). An entry with no conditions always applies, which is every entry
    today (see [[B179]]).

    ``bindings`` defaults to ``None``, and a caller that passes nothing gets ``{}``
    — so pass ``table_bindings(table, entity, repo, roll=…, tier=…, index=…)`` (or
    go through ``resolve_applicable_entry``, which does it for you) if the row's
    conditions are meant to read the table's names.
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
                             source_element: str | None = None,
                             path=None, step=None):
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

    ``path``/``step`` are the caller's declaration layers ([[B290]]), forwarded to
    the scope the conditions read: a condition that tests a name the *path*
    supplies is the case this layer exists for, so the row being considered has to
    see the same scope the effect after it will.
    """
    entry = resolve_table(table, roll=roll, tier=tier, index=index)
    if entry is None:
        return None
    if bindings is None:
        # The scope a row's conditions are checked against: ambient facts plus the
        # declared layers — the caller's, then the table's own — resolved *without* an
        # entry because which row applies is exactly what is being decided ([[B281]],
        # [[B290]]). Doing it here rather than at each call site is what makes the
        # table-level layer usable in a condition at all — before this, every caller
        # passed nothing and a row's conditions saw no declared name.
        bindings = table_bindings(table, entity, repo, roll=roll, tier=tier, index=index,
                                  path=path, step=step)
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


def roll_table_problems(table) -> list[str]:
    """What a roll table states about itself that cannot all be true ([[B285]]).

    Pure and catalog-driven, so it runs where the table is **authored** rather than
    where it is rolled: a reservation is a promise to every reader of that name, and
    a row whose path resolves something else has to be refused at the write boundary
    or the promise is decoration.

    What it checks:

    * a statement must be meaningful — a name, a known element, a cardinality of
      ``one`` or ``many``, and no name reserved twice;
    * a declaration that states a type **and** has a path must reach that type;
    * within a table that reserves **anything**, every **row** assignment must name a
      reserved name, and must reach the reserved type. That second half is the point:
      a table that reserves is a table that has stated what its names mean, so a row
      cannot introduce one behind its back.

    The leak check is scoped to a *governed* table — one that reserves at least one
    name — rather than to every table, and that is narrower than the ticket first
    proposed. Closing it globally would refuse the next save of every table whose
    rows declare anything, on live content, before the editors can author a
    reservation at all: the panel writes the whole table, so the refusal would take
    the author's unrelated in-flight edits with it ([[B285]]). A table that reserves
    nothing is the free-form table that exists today, and it cannot break a promise
    it never made.

    What it deliberately does **not** check: whether a path resolves to anything.
    That needs values, a repo and a subject, and it is the run time's job — a name
    resolving to nothing stays unbound. Nor does it report a path it cannot type
    (one starting from a name the table does not state); the trace is evidence, and
    missing evidence must not read as a verdict.

    Returns human-readable problems; an empty list means the table is consistent.
    """
    from transversal.services import target_catalog as tc

    problems: list[str] = []
    reserved: dict = {}
    for i, declared in enumerate(getattr(table, "bound_variables", None) or []):
        name = (getattr(declared, "name", "") or "").strip()
        if not name:
            problems.append(f"table variable {i + 1} has no name — nothing can refer to it")
            continue
        stated = declared_type_of(declared)
        if stated is not None:
            problems.extend(_type_problems(f"table variable '{name}'", stated, tc))
        if is_reservation(declared):
            if name in reserved:
                problems.append(f"table variable '{name}' is reserved twice")
            else:
                reserved[name] = stated
            continue  # a reservation: a type, no path, nothing to trace
        if name in reserved:
            # A slot and a default for it at once: the table's own value binds first,
            # so the shadow rule refuses every row's assignment and the reservation is
            # a slot nothing can fill. Say it rather than shipping a dead name.
            problems.append(
                f"table variable '{name}' is both reserved and given a value — a row "
                f"assigning it would be refused")
        spec = getattr(declared, "spec", None)
        if spec is None or not getattr(spec, "steps", None):
            continue
        # Traced against the scope of the declarations **before** it: computed inside
        # the loop rather than hoisted, because a declaration may only start from an
        # earlier one — a scope built from the whole list would let it start from a
        # later one, which the resolver would then fail to resolve.
        reached = traced_type(spec, _table_scope_types(table))
        if reached is not None and stated is not None and not stated.matches(reached):
            problems.append(
                f"table variable '{name}' is declared {stated.element}/{stated.cardinality} "
                f"but its path resolves {reached.element}/{reached.cardinality}")

    # A row **assigns** a reserved name; it cannot introduce one. Checked only where
    # the table reserves something — see the docstring on why this is scoped.
    governed = bool(reserved)
    scope = _table_scope_types(table)
    for row in (getattr(table, "entries", None) or []):
        where = getattr(row, "label", "") or getattr(row, "key", "") or "?"
        for i, declared in enumerate(getattr(row, "bound_variables", None) or []):
            name = (getattr(declared, "name", "") or "").strip()
            if not name:
                problems.append(f"row '{where}' variable {i + 1} has no name")
                continue
            spec = getattr(declared, "spec", None)
            if spec is None or not getattr(spec, "steps", None):
                problems.append(
                    f"row '{where}' variable '{name}' has no path — it assigns nothing")
                continue
            if name not in reserved:
                if governed:
                    problems.append(
                        f"row '{where}' assigns '{name}', which the table does not reserve")
                continue
            reached = traced_type(spec, scope)
            if reached is not None and not reserved[name].matches(reached):
                problems.append(
                    f"row '{where}' assigns '{name}' as {reached.element}/{reached.cardinality}, "
                    f"but the table reserves it as "
                    f"{reserved[name].element}/{reserved[name].cardinality}")
    return problems


def _type_problems(where: str, stated, tc) -> list[str]:
    """A stated type has to be a type the catalog knows, in the vocabulary it uses."""
    problems = []
    if tc.element(stated.element) is None:
        problems.append(f"{where} declares an unknown element '{stated.element}'")
    if stated.cardinality not in ("one", "many"):
        problems.append(
            f"{where} declares an unknown cardinality '{stated.cardinality}' "
            f"(one or many)")
    return problems
