"""Does an effect's target name something that exists? One answer, every carrier.

An effect whose ``target`` names nothing applies **silently**: ``targeting.py`` ·
`_resolve_target` returns the raw string — it yields ``None`` only for a *blank*
target — so an unknown-but-non-empty id passes straight through, and
``trait_helpers.py`` · `_new_traitsetting` builds a ``TraitSetting`` for a trait
that is not in the registry. The grant lands as a dangling setting with no error
and no log.

That is not hypothetical. **50** ``modify_trait`` targets across seven roll tables
named trait ids absent from the registry (found by hand, repaired by hand), and
``sfx-three-realms-arrival`` created three blank ``D4 STATIC`` settings for every
character born into Three Realms — discovered only because somebody looked at a
sheet.

This is **one** implementation for every carrier — an SFX, a roll-table entry's
``effects`` and its ``cost_effects``, and whatever comes next — because two copies
of the resolution rules is exactly how the drift went unnoticed. A carrier composes
the message prefix: `validate_sfx` names the *effect*, [[B157]] names the *entry*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from transversal.domain import Effect


#: Picker kinds (the editor's vocabulary) → the catalog element they name.
#
# The two vocabularies differ on one word: the editor's ``trait`` is a trait
# **instance** (``traitsetting``), because that is what a gain leaves on a sheet.
# Getting this backwards would flag every ``step_up`` in the game.
_KIND_ELEMENT: dict[str, str] = {
    "trait": "traitsetting",
    "traitsetting": "traitsetting",
    "entity": "entity",
    "occupant": "entity",
    "location": "location",
    "projection": "projection",
    "traitset": "traitset",
    "roll_table": "roll_table",
    "life_path": "life_path",
    "scheduled_event": "scheduled_event",
}

#: Catalog element → ``(repository reads, the noun a message calls it)``.
#
# **Several reads for one element** where the applier accepts more than one
# spelling, and an id that *any* of them resolves is not missing. A trait-instance
# target is the case that matters: `_find_traitsetting_by_target` looks the
# **instance** up first and falls back to the registry trait's id ("so an authored
# trait id still resolves to the subject's instance"), and live content uses both —
# so checking only the instance read reported three correct `rt-*-mishap` targets
# as missing.
#
# An element **absent here is not checked**, deliberately. A die has no document to
# look up; a pool, a contest and a trait set *setting* are handles; a universe is
# named by its **handle** (`earth`) rather than its entity id (`universe-earth`), so
# looking one up by the stored value would report a finding on every correct
# universe reference; and a relationship is an edge. Inventing a finding on good
# content is worse than the gap it would close — a warning that lies teaches authors
# to ignore warnings.
_EXISTENCE: dict[str, tuple[tuple[str, ...], str]] = {
    "trait": (("get_trait",), "trait"),
    "traitsetting": (("get_traitsetting", "get_trait"), "trait instance"),
    "traitsetsetting": (("get_traitsetsetting",), "trait set instance"),
    "traitset": (("get_traitset_by_id",), "trait set"),
    "entity": (("get_entity",), "entity"),
    "location": (("get_entity",), "location"),
    "projection": (("get_projection",), "body"),
    "roll_table": (("get_roll_table",), "roll table"),
    "life_path": (("get_lifepath",), "life path"),
    "sfx": (("get_sfx",), "rule"),
}


@dataclass(frozen=True)
class MissingTarget:
    """One effect position whose target cannot be resolved to anything.

    Carried structured rather than as a sentence so each carrier can name the thing
    in its own words — *"Effect 2: …"* for a rule, *"Entry 3 (Crimson Scars): …"*
    for a roll table — while both say the same thing about the same fault.
    """
    effect_index: int
    target: str
    element: str
    #: Where the id was written: ``"target"`` or a path step's filter.
    where: str = "target"

    @property
    def message(self) -> str:
        noun = _EXISTENCE.get(self.element, ((), self.element))[1]
        if self.where == "target":
            return f"target '{self.target}' names no {noun}"
        return f"{self.where} names no {noun}"


def _action_meta(effect: "Effect"):
    from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY

    return next((m for m in EFFECT_ACTION_REGISTRY
                 if m.effect_type == effect.type and m.effect_action == effect.action), None)


def target_element(meta) -> Optional[str]:
    """The catalog element a bare ``target`` names, per the action's declaration.

    ``path_element`` is the **catalog** vocabulary and wins when it names exactly
    one thing — that is the action saying what a path resolves to. ``target_kind``
    is the *picker* vocabulary and is consulted only when the path declaration is
    absent; a **union** (``("die", "rating_die")``) means one bare id could be
    either, so there is nothing to prove and nothing is reported.
    """
    if meta is None:
        return None
    elements = tuple(getattr(meta, "path_element", ()) or ())
    if len(elements) == 1:
        return elements[0]
    kind = (getattr(meta, "target_kind", "") or "").strip()
    return _KIND_ELEMENT.get(kind) if kind else None


def _is_literal_id(value: str) -> bool:
    """Whether a written value is an id at all.

    A ``{token}``/``{choose:…}`` placeholder names something only at fire time, and
    ``self`` / ``self.<field>`` are resolved by the applier — none of them is a
    document to look up.
    """
    if not value or value.startswith("{"):
        return False
    return value != "self" and not value.startswith("self.")


def _existence(repo, element: str):
    """The reads that can prove this element's ids exist, or ``None`` when unchecked."""
    entry = _EXISTENCE.get(element)
    if entry is None or repo is None:
        return None
    reads = [getattr(repo, name) for name in entry[0]
             if callable(getattr(repo, name, None))]
    return reads or None


def _missing(repo, element: str, value: str) -> bool:
    """True only when **every** applicable read proves the id absent.

    A read that is unavailable, or that raises, proves nothing — so it does not
    contribute to "missing", and the validator stays quiet rather than guessing.
    """
    reads = _existence(repo, element)
    if not reads:
        return False
    for read in reads:
        try:
            if read(value) is not None:
                return False
        except Exception:
            return False
    return True


def _spec_findings(index: int, effect: "Effect", repo, source_element) -> list[MissingTarget]:
    """Ids written inside a targeting path — the shape the repaired rules use.

    ``select traits → filter id in [three ids]`` is how the *repaired*
    `sfx-three-realms-arrival` names its traits, and the broken form named three
    that did not exist. The catalog's ``references`` on the filtered field is the
    declaration that says which read proves it; a field without one (a tag, a
    rating, a handle) is not an id and is left alone.

    The walk is the type-checker's own (`target_spec.trace`), so this cannot come to
    a different conclusion about what a step is looking at than the wizard does.
    """
    from transversal.services import target_catalog as tc
    from transversal.services.target_spec import FilterStep, trace

    specs = [effect.target_spec, effect.entity_spec, effect.result_spec, effect.owner_spec]
    specs += [r.spec for r in (effect.refs or {}).values() if getattr(r, "spec", None)]

    out: list[MissingTarget] = []
    for spec in specs:
        if spec is None or not getattr(spec, "steps", None):
            continue
        types, errors = trace(spec, source_element)
        if errors:
            # An unfinished or unresolvable path is a different conversation; a
            # finding here would be about *this* check's inability to walk it.
            continue
        for step, value_type in zip(spec.steps, types):
            if not isinstance(step, FilterStep) or value_type is None:
                continue
            field = tc.field(value_type.element, step.field)
            element = getattr(field, "references", "") if field is not None else ""
            if not element or _existence(repo, element) is None:
                continue
            written = step.value if isinstance(step.value, list) else [step.value]
            for item in written:
                if isinstance(item, str) and _is_literal_id(item) and _missing(repo, element, item):
                    out.append(MissingTarget(index, item, element, where="path filter"))
    return out


def find_missing_targets(effects, repo, source_element: str | None = None) -> list[MissingTarget]:
    """Every effect position whose target names nothing that exists.

    ``source_element`` is the catalog element of the carrier's declared source, so a
    path that starts at ``select source`` can be walked; without it such a path is
    skipped rather than guessed at.
    """
    if repo is None:
        return []
    out: list[MissingTarget] = []
    for i, effect in enumerate(effects or []):
        raw = (effect.target or "").strip()
        if _is_literal_id(raw):
            element = target_element(_action_meta(effect))
            if element and _missing(repo, element, raw):
                out.append(MissingTarget(i, raw, element))
        out.extend(_spec_findings(i, effect, repo, source_element))
    return out
