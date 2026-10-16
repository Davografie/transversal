"""Content bundles — export authored elements as a portable file ([[B301]]).

A **bundle** is one JSON file holding whole documents for a set of authored
elements, so a GM can hand content to another world. It is deliberately *not*
[[B251]]'s package mechanism (no registry, no publish, no acquisition record) and
deliberately *not* the whole-world path — a fork already copies a database
verbatim with no handle remapping and no closure at all, because every ``_key`` is
a string. What a bundle buys over a fork is the thing a fork cannot do: share
**part** of a world.

Three design calls, made by the human on 2026-09-29 and load-bearing here:

1. **Purpose — share authored content as a file.**
2. **Ids — reassign, recompute derived keys.** Four collections mint keys as pure
   functions of their references (``projections`` ``{entity}:{universe}``,
   ``traitsettings`` ``{anchor}:{trait}``, ``traitsetsettings`` ``{entity}:{set}``,
   ``relationships`` ``edge:{from}:{to}:{type}``), so an importer must *recompute*
   those keys from its remapped parts. Because an id **is** the composite —
   ``DOCUMENT("traitsettings", "gmc-x:ts-3")`` resolves — nothing here has to parse
   one, which is why the closure can be exact rather than pattern-matched.
3. **Closure — report it and let the chooser decide.** So export is two-phase:
   :meth:`ContentBundleService.plan` computes the closure and reports every
   reference leaving the selection, and :meth:`ContentBundleService.emit` writes
   the file. A reference is never silently dropped.

**The map declares meaning; the database decides identity.** Each rule says what a
field *is* — required, invited, incidental — and never whether a value is a real
reference; that question goes to the database (`RepositoryBundles.locate_documents`).
A rule a future session forgets to add therefore cannot cause a silently
incomplete closure: the value lands in ``unruled`` and the completeness test
fails. That matters, because a missed field is how [[B156]]'s 50 dangling targets
arrived, and because the live world already carries **204** trait settings pointing
at **13** traits that do not exist.

Reference classes:

* **required** — the element is incoherent without it (a trait needs its trait set;
  an SFX needs the trait its path names). Following these *is* the closure.
* **invited** — content-shaped but separable: a relationship whose far endpoint is
  outside the bundle. Reported with that endpoint, never fanned out on its own.
* **incidental** — placement and play state (``current_location``, ``known_to``,
  ``owned_by``, attunements, in-progress terms). Shown so the chooser can see what
  it is leaving behind. Never followed.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from transversal.db.arango import (
    ENTITIES,
    LIFE_PATHS,
    PROJECTIONS,
    RELATIONSHIPS,
    ROLL_TABLES,
    SFXS,
    TRAITS,
    TRAITSETS,
    TRAITSETSETTINGS,
    TRAITSETTINGS,
    current_database,
)
from transversal.db.repository import EntityRepository

#: Bumped only when a reader of the old shape could not read the new one.
BUNDLE_FORMAT = "transversal.bundle/1"

#: How deep the recursive sub-document rule expansion goes. `effects[].branches[]`
#: is an effect containing effects, so the expansion needs a floor; three levels
#: covers the nesting the data has (measured: `branches` is declared on 135 live
#: effects and **empty on every one**).
_MAX_RULE_DEPTH = 3


# ── The elements a bundle can carry ──────────────────────────────────────────


@dataclass(frozen=True)
class ElementKind:
    """One kind of thing a bundle holds.

    ``anchored`` kinds are never named in a selection — they arrive because the
    element that owns them did, and they are not optional. A trait setting *is* an
    entity's trait surface, so an entity exported without its traits is an empty
    shell; leaving that to the chooser would be a footgun rather than a choice.
    """

    key: str
    collection: str
    label_field: str
    selectable: bool = True
    anchored: bool = False
    #: Fallback label when ``label_field`` is empty (projections carry "").
    label_fallback: str = ""


ELEMENT_KINDS: tuple[ElementKind, ...] = (
    ElementKind("traitset", TRAITSETS, "name"),
    ElementKind("trait", TRAITS, "name"),
    ElementKind("sfx", SFXS, "name"),
    ElementKind("life_path", LIFE_PATHS, "name"),
    ElementKind("roll_table", ROLL_TABLES, "name"),
    ElementKind("entity", ENTITIES, "name"),
    ElementKind("projection", PROJECTIONS, "name", label_fallback="entity_id"),
    ElementKind("traitsetting", TRAITSETTINGS, "statement", selectable=False, anchored=True),
    ElementKind(
        "traitsetsetting", TRAITSETSETTINGS, "traitset_id", selectable=False, anchored=True
    ),
    ElementKind("relationship", RELATIONSHIPS, "type", selectable=False, anchored=True),
)

KINDS: dict[str, ElementKind] = {k.key: k for k in ELEMENT_KINDS}

KIND_BY_COLLECTION: dict[str, str] = {k.collection: k.key for k in ELEMENT_KINDS}

COLLECTIONS: tuple[str, ...] = tuple(k.collection for k in ELEMENT_KINDS)

#: Things a bundle can *point at* without carrying. Named so the report can phrase
#: an absence precisely instead of calling it unknown.
CONTEXT_KINDS = {"universe": "a world handle", "media": "an image file"}

SKIP = "@skip"
RESOLVE = "@resolve"
LITERAL_STEP = "@literal-step"
SPEC = "@spec"
EFFECTS = "@effects"
CONDITIONS = "@conditions"
ANCHOR = "@anchor"

REQUIRED = "required"
INVITED = "invited"
INCIDENTAL = "incidental"


@dataclass(frozen=True)
class Rule:
    """What one document path means. ``target`` is a kind name or a marker."""

    target: str
    klass: str = REQUIRED


# ── The reference map ────────────────────────────────────────────────────────
#
# Paths are tuples of keys, ``"[]"`` for every item of a list and ``"*"`` for
# every key of a map. They were read off the live data — every collection
# profiled for its nested paths on 2026-09-29 — not guessed at.

_SPEC_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # A `literal` step names its target in `value` and its own `element` says what
    # kind — which is how a reference to something **absent** is still reported by
    # name ("missing traitset ts-complications-a190") rather than as a bare id.
    (("steps", "[]", "value"), LITERAL_STEP, REQUIRED),
    (("steps", "[]", "value", "[]"), LITERAL_STEP, REQUIRED),
    # Not references: the seed name ("self", "occupants"), a bound variable name, an
    # edge name, an operator, and `element` — which is a *catalog* element name and,
    # for `trait`/`entity`/`traitset`/`sfx`, coincides with one of ours. Reading it
    # as a reference would invent dangling refs out of nothing.
    (("steps", "[]", "collection"), SKIP, REQUIRED),
    (("steps", "[]", "variable"), SKIP, REQUIRED),
    (("steps", "[]", "edge"), SKIP, REQUIRED),
    (("steps", "[]", "field"), SKIP, REQUIRED),
    (("steps", "[]", "element"), SKIP, REQUIRED),
    (("steps", "[]", "output"), SKIP, REQUIRED),
    (("steps", "[]", "kind"), SKIP, REQUIRED),
    (("steps", "[]", "fn"), SKIP, REQUIRED),
    (("steps", "[]", "operator"), SKIP, REQUIRED),
    (("steps", "[]", "dedup"), SKIP, REQUIRED),
    (("steps", "[]", "count"), SKIP, REQUIRED),
)

_CONDITION_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # `subject`/`target` hold a literal id, "" (the acting entity) or `{variable}`.
    # A variable name is not id-shaped, so it falls out on its own.
    (("subject",), RESOLVE, REQUIRED),
    (("target",), RESOLVE, REQUIRED),
    (("targets", "[]"), RESOLVE, REQUIRED),
    (("spec",), SPEC, REQUIRED),
    (("value",), RESOLVE, INCIDENTAL),
    (("narrative",), SKIP, REQUIRED),
    (("operator",), SKIP, REQUIRED),
    (("type",), SKIP, REQUIRED),
)

_EFFECT_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("target",), RESOLVE, REQUIRED),
    (("entity",), RESOLVE, REQUIRED),
    (("target_spec",), SPEC, REQUIRED),
    (("entity_spec",), SPEC, REQUIRED),
    (("owner_spec",), SPEC, REQUIRED),
    (("result_spec",), SPEC, REQUIRED),
    (("refs", "*", "value"), RESOLVE, REQUIRED),
    (("refs", "*", "spec"), SPEC, REQUIRED),
    (("refs", "*", "scope"), SKIP, REQUIRED),
    (("conditions",), CONDITIONS, REQUIRED),
    (("branches",), EFFECTS, REQUIRED),
    # A deferred effect carries the activation it belongs to, and that identity is a
    # composite (`gmc-x:three_realms:trait-y`) — a real reference, not a label.
    (("context", "activation_source"), RESOLVE, INCIDENTAL),
    (("die_filter", "*"), RESOLVE, INCIDENTAL),
    # `result` is an operand (a die, a number, a relationship type), never a target.
    (("result",), SKIP, REQUIRED),
    (("output",), SKIP, REQUIRED),
    (("timing",), SKIP, REQUIRED),
    (("type",), SKIP, REQUIRED),
    (("action",), SKIP, REQUIRED),
    (("negative",), SKIP, REQUIRED),
    (("duration",), SKIP, REQUIRED),
    (("context", "*"), SKIP, REQUIRED),
)

_TOP_RULES: dict[str, tuple[tuple[tuple[str, ...], str, str], ...]] = {
    ENTITIES: (
        # `current_location` is where the entity *stands*. Telling that apart from
        # what the entity *is* is the whole reason the incidental class exists.
        (("current_location",), "entity", INCIDENTAL),
        (("current_projection",), "projection", INCIDENTAL),
        (("current_universe",), "universe", INCIDENTAL),
        (("active_universes", "[]"), "universe", INCIDENTAL),
        (("destination_location",), "entity", INCIDENTAL),
        # A zone is a *link* to a child location — the pin is meaningless without it.
        (("zones", "[]", "location_id"), "entity", REQUIRED),
        (("zones", "[]", "background_image"), "media", INCIDENTAL),
        (("background_image",), "media", INCIDENTAL),
        (("sfx_ids", "[]"), "sfx", REQUIRED),
        (("owned_by",), "entity", INCIDENTAL),
        (("known_to", "[]"), "entity", INCIDENTAL),
        (("node_ids", "[]"), "entity", INCIDENTAL),
        (("discovered_life_paths", "[]"), "life_path", INCIDENTAL),
        (("suitable_life_path_ids", "[]"), "life_path", REQUIRED),
        (("life_paths", "[]", "faction_id"), "entity", INCIDENTAL),
        (("life_paths", "[]", "path_id"), "life_path", INCIDENTAL),
        (("life_paths", "[]", "projection_id"), "projection", INCIDENTAL),
        (("pending_terms", "*", "faction_id"), "entity", INCIDENTAL),
        (("pending_terms", "*", "path_id"), "life_path", INCIDENTAL),
        (("pending_terms", "*", "projection_id"), "projection", INCIDENTAL),
        (("pending_terms", "*", "current_table_id"), "roll_table", INCIDENTAL),
        (("pending_term", "*"), SKIP, INCIDENTAL),
        (("attunements", "[]", "projection_id"), "projection", INCIDENTAL),
        (("attunements", "[]", "universe"), "universe", INCIDENTAL),
        (("attunements", "[]", "source_sfx_id"), "sfx", INCIDENTAL),
        (("targeting_bans", "[]", "target_id"), "entity", INCIDENTAL),
        (("consequence_options", "[]", "effects", "[]"), EFFECTS, REQUIRED),
        # `trait_positions` is keyed BY traitsetting id — a reference in the key,
        # and the map layout is presentation, so it does not travel.
        (("trait_positions", "*"), SKIP, INCIDENTAL),
        (("nav_positions", "*"), SKIP, INCIDENTAL),
        (("lora_config", "*"), SKIP, INCIDENTAL),
        (("palette", "*"), SKIP, INCIDENTAL),
    ),
    PROJECTIONS: (
        (("entity_id",), "entity", REQUIRED),
        (("current_location",), "entity", INCIDENTAL),
        (("universe",), "universe", INCIDENTAL),
        (("origin_universe",), "universe", INCIDENTAL),
        (("background_image",), "media", INCIDENTAL),
        (("sfx_ids", "[]"), "sfx", REQUIRED),
    ),
    TRAITSETS: ((("universes", "[]"), "universe", INCIDENTAL),),
    TRAITS: (
        (("universes", "[]"), "universe", INCIDENTAL),
        (("traitset_id",), "traitset", REQUIRED),
        (("required_trait_ids", "[]"), "trait", REQUIRED),
        (("possible_subtrait_ids", "[]"), "trait", REQUIRED),
        (("possible_subtraitset_ids", "[]"), "traitset", REQUIRED),
        (("possible_sfx_ids", "[]"), "sfx", REQUIRED),
        (("default_sfx_ids", "[]"), "sfx", REQUIRED),
        (("display_names", "[]", "universe"), "universe", INCIDENTAL),
        # Tags are data. A tag that looks like an id ("character-quality") is the
        # false positive this rule exists to rule out.
        (("tags", "[]"), SKIP, INCIDENTAL),
        (("display_names", "[]", "name"), SKIP, INCIDENTAL),
        (("name",), SKIP, INCIDENTAL),
    ),
    SFXS: (
        (("conditions", "[]"), CONDITIONS, REQUIRED),
        (("effects", "[]"), EFFECTS, REQUIRED),
        (("reach", "[]", "spec"), SPEC, REQUIRED),
        (("reach", "[]", "flavour"), SKIP, REQUIRED),
        (("acquire_spec",), SPEC, REQUIRED),
        (("listener_spec",), SPEC, REQUIRED),
        (("bound_variables", "[]", "spec"), SPEC, REQUIRED),
        # The variable's own *name* is a label the author chose, not a reference.
        (("bound_variables", "[]", "name"), SKIP, REQUIRED),
        (("bound_variables", "[]"), SKIP, REQUIRED),
        # An owner *surface* name ("table", "trait_setting"), not a bucket id —
        # although "table" and "gm" collide with live `sfx_owners` keys, which is
        # exactly the coincidence the resolver must not be asked about.
        (("source_kind",), SKIP, REQUIRED),
    ),
    LIFE_PATHS: (
        (("universe",), "universe", INCIDENTAL),
        (("entry_table_id",), "roll_table", REQUIRED),
        (("steps", "[]", "table_id"), "roll_table", REQUIRED),
        # `next` is a **step id in this path**, not a table and not a path id.
        (("steps", "[]", "next"), SKIP, REQUIRED),
        (("steps", "[]", "bindings", "[]", "next"), SKIP, REQUIRED),
        (("steps", "[]", "bindings", "[]", "exit_path"), "life_path", REQUIRED),
        (("steps", "[]", "bindings", "[]", "exit_kind"), SKIP, REQUIRED),
        (("steps", "[]", "bindings", "[]", "effects", "[]"), EFFECTS, REQUIRED),
        (("steps", "[]", "effects", "[]"), EFFECTS, REQUIRED),
        (("steps", "[]", "bound_variables", "[]", "spec"), SPEC, REQUIRED),
        (("steps", "[]", "bound_variables", "[]", "name"), SKIP, REQUIRED),
        (("conditions", "[]"), CONDITIONS, REQUIRED),
        (("bound_variables", "[]", "spec"), SPEC, REQUIRED),
        (("bound_variables", "[]", "name"), SKIP, REQUIRED),
    ),
    ROLL_TABLES: (
        (("universe",), "universe", INCIDENTAL),
        (("life_path",), "life_path", REQUIRED),
        (("entries", "[]", "effects", "[]"), EFFECTS, REQUIRED),
        # `cost_effects` is on 169 live rows and in no [[Data Model]] table: the cost
        # is part of what a row means, so it travels and its references are followed
        # exactly like `effects`.
        (("entries", "[]", "cost_effects", "[]"), EFFECTS, REQUIRED),
        (("entries", "[]", "conditions", "[]"), CONDITIONS, REQUIRED),
        (("entries", "[]", "bound_variables", "[]", "spec"), SPEC, REQUIRED),
        (("entries", "[]", "bound_variables", "[]", "name"), SKIP, REQUIRED),
        (("entries", "[]", "key"), SKIP, REQUIRED),
        (("entries", "[]", "label"), SKIP, REQUIRED),
        (("entries", "[]", "description"), SKIP, REQUIRED),
        (("check", "trait_ids", "[]"), "trait", REQUIRED),
        (("subject_kind",), SKIP, REQUIRED),
    ),
    TRAITSETTINGS: (
        (("trait_id",), "trait", REQUIRED),
        (("entity_id",), "entity", REQUIRED),
        (("projection_id",), "projection", REQUIRED),
        (("parent_traitsetting_id",), "traitsetting", REQUIRED),
        (("sfx_ids", "[]"), "sfx", REQUIRED),
        # A setting's en/disabled locations are semantic — the trait works here and
        # not there — so they are followed even though 0 live rows carry one.
        (("locations_enabled", "[]"), "entity", REQUIRED),
        (("locations_disabled", "[]"), "entity", REQUIRED),
        (("known_to", "[]"), "entity", INCIDENTAL),
        (("source_entity_id",), "entity", INCIDENTAL),
        (("source_life_path_id",), "life_path", INCIDENTAL),
        (("source_trait_setting_id",), "traitsetting", INCIDENTAL),
        (("source_type",), SKIP, INCIDENTAL),
        (("picked_image_id",), "image", INCIDENTAL),
        (("scheduled_events", "[]"), SKIP, INCIDENTAL),
        (("_from",), ANCHOR, REQUIRED),
        (("_to",), ANCHOR, REQUIRED),
    ),
    TRAITSETSETTINGS: (
        (("traitset_id",), "traitset", REQUIRED),
        (("entity_id",), "entity", REQUIRED),
        (("projection_id",), "projection", REQUIRED),
        (("sfx_ids", "[]"), "sfx", REQUIRED),
        (("_from",), ANCHOR, REQUIRED),
        (("_to",), ANCHOR, REQUIRED),
    ),
    RELATIONSHIPS: (
        (("effects", "[]"), EFFECTS, REQUIRED),
        (("transversal_type",), SKIP, REQUIRED),
        (("_from",), ANCHOR, REQUIRED),
        (("_to",), ANCHOR, REQUIRED),
    ),
}

#: Catalog element names that are *not* one of ours, and the kind they resolve to
#: (`location` is an entity type; a die or a pool is not a document at all).
_STEP_ELEMENT_ALIASES = {"location": "entity"}


def _camel(segment: str) -> str:
    """``target_spec`` → ``targetSpec``; identity fields and list markers untouched."""
    if segment.startswith("_") or "_" not in segment or segment == "[]":
        return segment
    head, *rest = segment.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _build_rules() -> dict[str, dict[tuple[str, ...], Rule]]:
    """Expand the sub-document rule sets into one flat lookup per collection."""
    out: dict[str, dict[tuple[str, ...], Rule]] = {}

    def expand(
        table: dict[tuple[str, ...], Rule],
        prefix: tuple[str, ...],
        rules: Iterable[tuple[tuple[str, ...], str, str]],
        depth: int,
    ) -> None:
        if depth > _MAX_RULE_DEPTH:
            return
        for path, target, klass in rules:
            full = prefix + path
            if target == SPEC:
                expand(table, full, _SPEC_RULES, depth + 1)
            elif target in (EFFECTS, CONDITIONS):
                # The marker names the *list*; a declaration that already ends in
                # `[]` has said so itself.
                sub = _EFFECT_RULES if target == EFFECTS else _CONDITION_RULES
                descend = full if full[-1:] == ("[]",) else full + ("[]",)
                expand(table, descend, sub, depth + 1)
            else:
                table.setdefault(full, Rule(target, klass))

    for collection, rules in _TOP_RULES.items():
        expand(out.setdefault(collection, {}), (), rules, 0)

    # A document's own identity is not a reference to itself. `_key` and `id` are
    # both the key, and both are id-shaped, so without this every element reports a
    # required reference to itself.
    for table in out.values():
        for identity in (("_key",), ("id",), ("_id",), ("_rev",)):
            table.setdefault(identity, Rule(SKIP, INCIDENTAL))

    # **Both spellings are live.** The GraphQL inputs are camelCase on the wire, so
    # a document written through them can carry `targetSpec` where the model says
    # `target_spec` — measured: one live relationship edge has
    # `effects[].targetSpec.steps[].value`, and this guard found it. A map that only
    # knew the Python spelling would have dropped that reference silently.
    for table in out.values():
        for path, rule in list(table.items()):
            alias = tuple(_camel(segment) for segment in path)
            if alias != path:
                table.setdefault(alias, rule)
    return out


RULES: dict[str, dict[tuple[str, ...], Rule]] = _build_rules()


class _Trie:
    """A rule table as a tree, so ``*`` can match a key the path names literally.

    The walker reports the keys a document actually has — ``refs.trait.value``,
    not ``refs.*.value`` — so a flat lookup would miss every wildcard rule. Trying
    the literal segment first and ``*`` second keeps the declaration readable while
    making it match.
    """

    __slots__ = ("rule", "children")

    def __init__(self) -> None:
        self.rule: Optional[Rule] = None
        self.children: dict[str, "_Trie"] = {}


def _build_tries() -> dict[str, _Trie]:
    out: dict[str, _Trie] = {}
    for collection, table in RULES.items():
        root = _Trie()
        for path, rule in table.items():
            node = root
            for seg in path:
                node = node.children.setdefault(seg, _Trie())
            node.rule = rule
        out[collection] = root
    return out


RULE_TRIES: dict[str, _Trie] = _build_tries()


def _rule_for(root: _Trie, path: tuple[str, ...]) -> Optional[Rule]:
    node = root
    for seg in path:
        nxt = node.children.get(seg)
        if nxt is None:
            nxt = node.children.get("*")
        if nxt is None:
            return None
        node = nxt
    return node.rule

#: A string that *looks* like an id. It decides only whether an unruled path is
#: worth reporting — the database still decides what the value really is. Every
#: carried collection's keys carry one of these prefixes, composites included.
_ID_SHAPED = re.compile(
    r"^(loc-|faction-|asset-|gmc-|character-|universe-|trait-|ts-|sfx-|lp-|rt-"
    r"|edge:|se-|player-)"
)

#: Media references are *files*, not rows: `images` points at a filename and the
#: bytes live under `media/` (1.1 GB, 446 files, measured 2026-09-29).
_MEDIA_SHAPED = re.compile(r"^(?:/media/|media/)")


def _candidate_keys(value: str) -> list[str]:
    """The keys a string could name.

    Either itself, when it is id-shaped, or the bare half of a **carried handle**
    (``entities/x`` → ``x``) — the edge endpoints, which name real documents but
    are not themselves keys anywhere.
    """
    if _ID_SHAPED.match(value):
        return [value]
    collection, sep, bare = value.partition("/")
    if sep and bare and collection in KIND_BY_COLLECTION:
        return [bare]
    return []


def _path_str(path: tuple[str, ...]) -> str:
    """Render a path the way a human reads it: ``entries[].effects[].target``."""
    parts: list[str] = []
    for seg in path:
        if seg == "[]":
            if parts:
                parts[-1] += "[]"
            else:
                parts.append("[]")
        else:
            parts.append(seg)
    return ".".join(parts)


def _iter_strings(node, path: tuple[str, ...] = ()):
    """Yield ``(path, value, container)`` for every non-empty string in a document.

    ``container`` is the dict the string sits in, which is what lets a targeting
    step be classified by its own ``element``.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                if value:
                    yield path + (key,), value, node
            elif isinstance(value, (dict, list)):
                yield from _iter_strings(value, path + (key,))
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str):
                if item:
                    yield path + ("[]",), item, None
            elif isinstance(item, (dict, list)):
                yield from _iter_strings(item, path + ("[]",))


@dataclass
class Reference:
    """One reference found in one document, with the path that carries it."""

    kind: str
    value: str
    path: str
    klass: str
    from_kind: str
    from_id: str
    from_label: str = ""
    #: True when this names a document a bundle *could* carry. A reference to a
    #: context or external kind is a declaration, not a gap, so it is never
    #: reported as unresolved.
    carried: bool = False
    exists: bool = False

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "value": self.value,
            "path": self.path,
            "class": self.klass,
            "fromKind": self.from_kind,
            "fromId": self.from_id,
            "fromLabel": self.from_label,
            "carried": self.carried,
            "exists": self.exists,
        }


class ContentBundleService:
    """Plan and emit a content bundle. Reads only — nothing here writes."""

    def __init__(self, repository: Optional[EntityRepository] = None):
        self.repo = repository or EntityRepository()

    # ── the public surface ───────────────────────────────────────────────────

    def plan(self, selection: list[dict], depth: int = 1) -> dict:
        """What a bundle of ``selection`` would contain, and what it would leave out.

        **Nothing is written and nothing is serialised.** ``depth`` is how many
        frontier rounds to walk: ``1`` (the default) reports the references that
        leave the selection, so the caller adds the ones it wants and asks again;
        ``0`` walks to a fixpoint, for a caller that wants *take everything it
        needs*.
        """
        included, refs, expects, unruled = self._collect(selection, depth)
        return {
            "format": BUNDLE_FORMAT,
            "included": [self._summary(kind, doc) for (kind, _), doc in self._order(included)],
            "counts": self._counts(included),
            "required": [r.as_dict() for r in refs if r.klass == REQUIRED],
            "invited": [r.as_dict() for r in refs if r.klass == INVITED],
            "incidental": [r.as_dict() for r in refs if r.klass == INCIDENTAL],
            "expects": expects,
            "unruled": unruled,
        }

    def emit(self, selection: list[dict], depth: int = 1) -> dict:
        """Build the bundle. ``selection`` is the **final** set, after any widening.

        The report is embedded rather than recomputed: a bundle states what it
        expected and what it could not find, so an importer can refuse a broken
        bundle at the door instead of discovering it at the table.
        """
        included, refs, expects, unruled = self._collect(selection, depth)
        documents = [
            {
                "kind": kind,
                "key": doc.get("_key", ""),
                "label": self._label(kind, doc),
                "document": self._stripped(doc),
            }
            for (kind, _), doc in self._order(included)
        ]
        return {
            "format": BUNDLE_FORMAT,
            "bundleId": str(uuid.uuid4()),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "source": {
                "database": current_database() or "",
                "selection": selection,
                "depth": depth,
            },
            "documents": documents,
            "counts": self._counts(included),
            "expects": expects,
            "unresolved": [
                r.as_dict() for r in refs if r.klass == REQUIRED and r.carried and not r.exists
            ],
            "leftBehind": [r.as_dict() for r in refs if r.klass == INCIDENTAL],
            "invited": [r.as_dict() for r in refs if r.klass == INVITED],
            "unruled": unruled,
        }

    @staticmethod
    def to_json(bundle: dict) -> str:
        return json.dumps(bundle, indent=2, sort_keys=False, default=str)

    # ── the closure ──────────────────────────────────────────────────────────

    def _collect(
        self, selection: list[dict], depth: int
    ) -> tuple[dict[tuple[str, str], dict], list[Reference], dict, list[dict]]:
        """Walk the closure. Returns ``(included, references, expects, unruled)``."""
        included: dict[tuple[str, str], dict] = {}
        refs: list[Reference] = []
        looks: dict[str, Optional[str]] = {}
        expects: dict[str, set[str]] = {"universes": set(), "media": set()}
        unruled: list[dict] = []

        wanted = self._normalise(selection)
        rounds = 0
        while wanted:
            fresh = {
                k: v for k, v in self._fetch(wanted).items() if k not in included
            }
            if not fresh:
                break
            included.update(fresh)

            # Anchored kinds are part of the element, not a choice: everything that
            # landed this round pulls the trait settings, set settings and edges
            # that belong to it, to a fixpoint (a sub-trait is anchored to its
            # parent setting, so the chain is walked rather than guessed at).
            added = dict(fresh)
            pending = list(fresh)
            while pending:
                more = {
                    k: v
                    for k, v in self._fetch(self._anchored_for(pending, included)).items()
                    if k not in included
                }
                if not more:
                    break
                included.update(more)
                added.update(more)
                pending = list(more)

            looks = self._locate(added, looks)
            frontier: dict[tuple[str, str], None] = {}
            for (kind, key), doc in added.items():
                for ref in self._references(kind, key, doc, looks):
                    if ref.kind in CONTEXT_KINDS:
                        bucket = "media" if ref.kind == "media" else "universes"
                        expects[bucket].add(ref.value)
                    elif ref.kind == "unruled":
                        unruled.append(ref.as_dict())
                    else:
                        refs.append(ref)
                        if ref.klass == REQUIRED and ref.carried and ref.exists:
                            frontier[(ref.kind, ref.value)] = None

            rounds += 1
            wanted = list(frontier) if depth <= 0 or rounds < depth else []

        refs.extend(self._edge_report(included, refs))
        # The report is about what **leaves** the bundle. A reference to something
        # already in it is not a decision for the chooser — without this, a set's
        # 208-trait closure would list hundreds of internal edges back at you.
        outside = [r for r in refs if (r.kind, r.value) not in included]
        return included, self._dedupe(outside), self._expects_out(expects), unruled

    def _anchored_for(
        self, pending: list[tuple[str, str]], included: dict[tuple[str, str], dict]
    ) -> list[tuple[str, str]]:
        """What the elements that just landed own, as ``(kind, key)`` pairs.

        Anchor reads go through ``_from``, never ``entity_id``: a projection's
        settings share the owning entity's ``entity_id``, so the indexed field would
        over-pull — asking for an entity would return its other bodies' settings.
        """
        handles = [f"{KINDS[kind].collection}/{key}" for kind, key in pending if kind in KINDS]
        if not handles:
            return []
        out: list[tuple[str, str]] = []
        for doc in self.repo.raw_traitsettings_by_anchor(handles):
            out.append(("traitsetting", doc["_key"]))
        for doc in self.repo.raw_traitsetsettings_by_anchor(handles):
            out.append(("traitsetsetting", doc["_key"]))
        # A set's traits point *up* at it, so the reach back down is a reverse read:
        # a trait set exported without its traits is an empty grouping.
        traitset_ids = [key for kind, key in pending if kind == "traitset"]
        for doc in self.repo.raw_traits_for_traitsets(traitset_ids):
            out.append(("trait", doc["_key"]))
        # An edge is carried **iff both endpoints are**: an edge with one end
        # missing is not a fact, and following one would walk the whole world.
        every = {f"{KINDS[kind].collection}/{key}" for kind, key in included if kind in KINDS}
        for edge in self.repo.raw_relationships_touching(handles):
            if edge["_from"] in every and edge["_to"] in every:
                out.append(("relationship", edge["_key"]))
        return out

    def _edge_report(
        self, included: dict[tuple[str, str], dict], already: list[Reference]
    ) -> list[Reference]:
        """Edges of included elements whose far endpoint is outside the bundle."""
        known = {(r.kind, r.value) for r in already}
        carried = {key for (kind, key) in included if kind == "relationship"}
        handles = {
            f"{KINDS[kind].collection}/{key}": kind
            for (kind, key) in included
            if kind in ("entity", "projection")
        }
        if not handles:
            return []
        found: list[Reference] = []
        for edge in self.repo.raw_relationships_touching(list(handles)):
            if edge["_key"] in carried:
                continue
            for endpoint in (edge["_from"], edge["_to"]):
                if endpoint in handles:
                    continue
                kind = KIND_BY_COLLECTION.get(endpoint.split("/", 1)[0])
                target = endpoint.split("/", 1)[-1]
                if kind is None or (kind, target) in known:
                    continue
                known.add((kind, target))
                found.append(
                    Reference(
                        kind=kind,
                        value=target,
                        path=f"relationships/{edge['_key']}",
                        klass=INVITED,
                        from_kind="relationship",
                        from_id=edge["_key"],
                        from_label=edge.get("type", ""),
                        carried=True,
                        exists=True,
                    )
                )
        return found

    # ── reading ──────────────────────────────────────────────────────────────

    def _fetch(self, wanted: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
        """Load documents by ``(kind, key)``, one query per kind."""
        by_kind: dict[str, list[str]] = {}
        for kind, key in wanted:
            if kind in KINDS:
                by_kind.setdefault(kind, []).append(key)
        out: dict[tuple[str, str], dict] = {}
        for kind, keys in by_kind.items():
            collection = KINDS[kind].collection
            for key, doc in self.repo.raw_documents(collection, keys).items():
                out[(kind, key)] = doc
        return out

    def _locate(
        self, added: dict[tuple[str, str], dict], cache: dict[str, Optional[str]]
    ) -> dict[str, Optional[str]]:
        """Resolve every id-shaped value in this round through **one** round trip.

        This is the join between the map and the data: the map says what a field
        means, and this says what a value *is* and whether it exists. It is why an
        id nothing holds still gets reported with its kind — the field's own
        declaration supplies it.
        """
        candidates: list[str] = []
        for doc in added.values():
            for _, value, _ in _iter_strings(doc):
                for candidate in _candidate_keys(value):
                    if candidate not in cache:
                        candidates.append(candidate)
        candidates = list(dict.fromkeys(candidates))
        if candidates:
            found = self.repo.locate_documents(list(COLLECTIONS), candidates)
            for value in candidates:
                cache[value] = KIND_BY_COLLECTION.get(found.get(value, ""))
        return cache

    def _references(
        self,
        kind: str,
        key: str,
        doc: dict,
        looks: dict[str, Optional[str]],
    ) -> list[Reference]:
        """Every reference in one document, classified.

        An id-shaped string on a path with **no rule** is reported as
        ``kind="unruled"`` rather than dropped: a silently incomplete closure is the
        failure this module is arranged to prevent.
        """
        root = RULE_TRIES.get(KINDS[kind].collection)
        label = self._label(kind, doc)
        out: list[Reference] = []
        for path, value, container in _iter_strings(doc):
            rule = _rule_for(root, path) if root is not None else None
            if rule is not None and rule.target == SKIP:
                continue
            klass = rule.klass if rule is not None else REQUIRED
            target = rule.target if rule is not None else None

            if target == ANCHOR:
                # An edge's endpoint is a *handle* (`entities/x`); an id is what a
                # bundle carries, so the handle is stripped here and the bare id is
                # what gets reported and existence-checked.
                collection, _, bare = value.partition("/")
                if bare and collection == "players":
                    target, value = "player", bare
                elif bare and collection in KIND_BY_COLLECTION:
                    target, value = KIND_BY_COLLECTION[collection], bare
                else:
                    target = None
            elif target == LITERAL_STEP:
                # The step's own `element` first, so a reference to something
                # *absent* is still named by kind; the database otherwise.
                element = container.get("element") if container else None
                if isinstance(element, str) and element:
                    target = _STEP_ELEMENT_ALIASES.get(element, element)
                else:
                    target = looks.get(value)
            elif target is None or target == RESOLVE:
                target = looks.get(value)

            if target is None:
                if _MEDIA_SHAPED.match(value):
                    target, klass = "media", rule.klass if rule is not None else INCIDENTAL
                elif rule is not None and _ID_SHAPED.match(value):
                    # The map declares this path; the database just cannot say what
                    # kind the value is — which is itself the finding, because
                    # nothing holds it. Reporting it as *unruled* would blame the map
                    # for a dangling reference.
                    target, klass = "unknown", rule.klass
                elif _ID_SHAPED.match(value):
                    out.append(
                        Reference(
                            kind="unruled",
                            value=value,
                            path=_path_str(path),
                            klass=REQUIRED,
                            from_kind=kind,
                            from_id=key,
                            from_label=label,
                        )
                    )
                    continue
                else:
                    continue

            # `unknown` counts as carryable on purpose: a bundle *would* carry it if
            # the kind were known, so it belongs in `unresolved` rather than being
            # quietly dropped for want of a label.
            carried = target in KINDS or target == "unknown"
            out.append(
                Reference(
                    kind=target,
                    value=value,
                    path=_path_str(path),
                    klass=klass,
                    from_kind=kind,
                    from_id=key,
                    from_label=label,
                    carried=carried,
                    exists=(looks.get(value) is not None) if target in KINDS else False,
                )
            )
        return out

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise(selection: list[dict]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for item in selection or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()
            key = str(item.get("id") or item.get("key") or "").strip()
            spec = KINDS.get(kind)
            if not key or spec is None or not spec.selectable:
                continue
            out.append((kind, key))
        return out

    @staticmethod
    def _dedupe(refs: list[Reference]) -> list[Reference]:
        """One row per ``(class, kind, value)``, keeping the first path that named
        it — the report is read as a list of decisions, not as a call graph."""
        seen: set[tuple[str, str, str]] = set()
        out: list[Reference] = []
        for ref in refs:
            sig = (ref.klass, ref.kind, ref.value)
            if sig in seen:
                continue
            seen.add(sig)
            out.append(ref)
        return out

    @staticmethod
    def _expects_out(expects: dict[str, set[str]]) -> dict[str, list[str]]:
        return {k: sorted(v) for k, v in expects.items() if v}

    @staticmethod
    def _order(included: dict[tuple[str, str], dict]):
        return sorted(included.items(), key=lambda kv: (kv[0][0], kv[0][1]))

    @staticmethod
    def _label(kind: str, doc: dict) -> str:
        spec = KINDS[kind]
        label = str(doc.get(spec.label_field) or "").strip()
        if not label and spec.label_fallback:
            label = str(doc.get(spec.label_fallback) or "").strip()
        return label or str(doc.get("_key", ""))

    def _summary(self, kind: str, doc: dict) -> dict:
        return {"kind": kind, "key": doc.get("_key", ""), "label": self._label(kind, doc)}

    @staticmethod
    def _counts(included: dict[tuple[str, str], dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for kind, _ in included:
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    @staticmethod
    def _stripped(doc: dict) -> dict:
        """A document as it travels: ``_key`` kept (edges and derived ids are keyed
        by it), the volatile ``_id``/``_rev`` dropped (both are database-local)."""
        return {k: v for k, v in doc.items() if k not in ("_id", "_rev")}
