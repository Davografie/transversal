"""Declarative targeting catalog.

The single source of truth for the spec pipeline (``select`` / ``filter`` /
``navigate`` / ``aggregate``): which element types exist, which navigation
edges connect them, which scalar fields are comparable/aggregatable, which
aggregations collapse a collection to a scalar, and which context collections
a spec may seed from.

Both the resolver and the authoring wizard read this catalog, so they can only
compose valid, type-checked steps. Adding a new element type, edge, field,
aggregation, or collection is a declaration here plus a repo read in the
resolver — nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Element types ──────────────────────────────────────────────

@dataclass(frozen=True)
class ElementType:
    """A kind of game object a spec can resolve to."""
    name: str
    label: str


ELEMENT_TYPES: dict[str, ElementType] = {
    # Two kinds of *die*, because a die lives in one of two places and where it
    # lives decides what changing it means. A pool die is a die the player has
    # assembled for a roll — transient, rebuilt every roll. A rating die is part
    # of a trait instance's definition — a fact about the character, so changing
    # it persists (and can carry a duration). One action family targets either;
    # the element it lands on is what tells them apart.
    "die": ElementType("die", "Pool die"),
    "rating_die": ElementType("rating_die", "Rating die"),
    "traitsetting": ElementType("traitsetting", "Trait instance"),
    "traitsetsetting": ElementType("traitsetsetting", "Trait set instance"),
    "trait": ElementType("trait", "Trait"),
    "traitset": ElementType("traitset", "Trait set"),
    "entity": ElementType("entity", "Entity"),
    "projection": ElementType("projection", "Projection"),
    "location": ElementType("location", "Location"),
    "universe": ElementType("universe", "Universe"),
    # A relationship *edge* (a membership, an agency, any typed `_from → _to`).
    # Its own element because a trait instance can hang off the edge rather than
    # off the entity — a faction membership carries your standing with that
    # faction — and until this existed the only way to say so was a field
    # (`context.relationship`), which no path could express.
    "relationship": ElementType("relationship", "Relationship"),
    # A rule in the registry, as a *targetable thing*: a path can select one
    # (`select sfxs`) or filter to the ones a grant should reach. Read-only from
    # the pipeline's point of view — nothing navigates *out* of an SFX yet.
    "sfx": ElementType("sfx", "SFX"),
    "pool": ElementType("pool", "Dice pool"),
}


# ── Scalar fields (comparable / aggregatable) ─────────────────

@dataclass(frozen=True)
class ScalarField:
    """A scalar value on an element, usable in a filter or an aggregation.

    ``options`` lists the accepted values for enum-like string fields so the
    wizard can render a dropdown instead of a free-text input. ``operators``
    overrides the operators valid for this field (default derived from ``type``).
    ``references`` names the element type the field points at (e.g. ``traitset_id``
    → ``traitset``), so the wizard can render a picker for id-reference fields.
    ``suggest`` names a *value source* for a free-form field whose values are data
    rather than schema (e.g. ``trait_tags``) — the wizard renders an autosuggest
    over the values that actually exist.
    """
    element: str
    name: str
    type: str  # "int" | "number" | "die" | "string"
    options: tuple[str, ...] = ()
    operators: tuple[str, ...] = ()
    references: str = ""
    suggest: str = ""  # value source for a data-driven field ("" → free text)
    label: str = ""  # card-facing name; "" → humanized ``name``


def field_label(field: ScalarField) -> str:
    """The card-facing name of a field (explicit label, else humanized)."""
    return field.label or field.name.replace("_", " ")


# ── Element narrowing (filters that prove a type) ─────────────
#
# A filter can prove *what* an element is: `entity.type == location` means the
# value **is** a location, so the path may take the steps only a location has
# (`occupants`, `difficulty_pool`) afterwards. Without this, such a hop is
# simply unavailable — the author sees an `entity` and cannot navigate to the
# room's occupants.
#
# Only values that name a catalog element narrow (there is no `character` or
# `gmc` element to narrow to). Declared here so the type-checker, the resolver
# and the card text all read one rule.
ELEMENT_NARROWING: dict[tuple[str, str], dict[str, str]] = {
    ("entity", "type"): {e: e for e in ("location", "universe") if e in ELEMENT_TYPES},
}


def narrowed_element(element: str, field: str, operator: str, value: object) -> str | None:
    """The element a filter *proves* the value is, or ``None`` when it proves nothing.

    Only equality narrows: ``!=``, the ordering operators, and a bound ``{name}``
    value (whose type is only known at run time) all leave the element as it was.
    """
    if operator != "==" or not isinstance(value, str):
        return None
    table = ELEMENT_NARROWING.get((element, field))
    return table.get(value.strip()) if table else None


# Operators valid per field type. Ordering operators only make sense on
# comparable (numeric/die/timestamp) fields; plain strings only support
# equality/membership.
_ORDERED_OPERATORS = ("==", "!=", ">", ">=", "<", "<=", "in", "not in")
_STRING_OPERATORS = ("==", "!=", "in", "not in")
_COMPARABLE_TYPES = ("int", "number", "die", "datetime")


def operators_for(field: ScalarField) -> tuple[str, ...]:
    """The operators valid for a field (explicit override, else by type)."""
    if field.operators:
        return field.operators
    if field.type in _COMPARABLE_TYPES:
        return _ORDERED_OPERATORS
    return _STRING_OPERATORS


def is_orderable(field: ScalarField) -> bool:
    """True when a field can be ordered (its operators include a comparison).

    What a ``top`` step checks before it can keep the highest/lowest element.
    """
    ops = operators_for(field)
    return ">" in ops or "<" in ops


# A "die" field is comparable (d4 < d6 < … < d12); numeric for mean after
# converting to its max value (resolver's job).
SCALAR_FIELDS: dict[str, dict[str, ScalarField]] = {
    "die": {
        "result": ScalarField("die", "result", "int"),
        "rating": ScalarField("die", "rating", "die", ("d4", "d6", "d8", "d10", "d12")),
        "effect_die": ScalarField("die", "effect_die", "die", ("d4", "d6", "d8", "d10", "d12")),
        "tier": ScalarField("die", "tier", "string", ("fail", "marginal", "success", "exceptional", "perfect")),
        "role": ScalarField("die", "role", "string"),
        "source_kind": ScalarField("die", "source_kind", "string", ("trait", "difficulty", "manual", "entity", "projection", "location", "resource", "challenge")),
        "ts_id": ScalarField("die", "ts_id", "string", label="trait instance"),
        # A list of SFX ids stamped on the die; filtered via the `contains` operator.
        "armed_sfx_ids": ScalarField("die", "armed_sfx_ids", "string",
                                      operators=("contains", "==", "!="), label="armed SFX"),
    },
    "rating_die": {
        # The die's own size. Named `rating` on both loci — a pool die reads it
        # through the derived reader below, so an aggregate or filter over
        # `rating` means the same thing whichever die a path landed on.
        "rating": ScalarField("rating_die", "rating", "die", ("d4", "d6", "d8", "d10", "d12")),
        # Which die of the rating this is: a rating is a *list* (a resource trait
        # holds several), and an effect that changes one has to say which.
        "index": ScalarField("rating_die", "index", "int"),
        "ts_id": ScalarField("rating_die", "ts_id", "string",
                             references="traitsetting", label="trait instance"),
    },
    "traitsetting": {
        "rating": ScalarField("traitsetting", "rating", "die", ("d4", "d6", "d8", "d10", "d12")),
        "rating_type": ScalarField("traitsetting", "rating_type", "string", ("static", "resource", "challenge", "empty")),
        "polarity": ScalarField("traitsetting", "polarity", "string", ("positive", "negative")),
        "trait_id": ScalarField("traitsetting", "trait_id", "string", references="trait", label="trait"),
        "traitset_id": ScalarField("traitsetting", "traitset_id", "string", references="traitset", label="trait set"),
        "entity_id": ScalarField("traitsetting", "entity_id", "string", references="entity", label="entity"),
        "projection_id": ScalarField("traitsetting", "projection_id", "string", references="projection", label="projection"),
        "from_type": ScalarField("traitsetting", "from_type", "string", ("entity", "projection"), label="owner type"),
        # Free-form labels carried by the *registry* trait this instance points at
        # (e.g. "violent"). A list, so it is matched with `contains` — the same
        # shape as `armed_sfx_ids` below. Read through the trait, not the setting
        # (see the resolver's derived fields).
        "tags": ScalarField("traitsetting", "tags", "string",
                            operators=("contains", "==", "!="), suggest="trait_tags",
                            label="tag"),
    },
    "traitsetsetting": {
        "entity_id": ScalarField("traitsetsetting", "entity_id", "string", references="entity"),
        "traitset_id": ScalarField("traitsetsetting", "traitset_id", "string", references="traitset"),
        "projection_id": ScalarField("traitsetsetting", "projection_id", "string", references="projection"),
        "from_type": ScalarField("traitsetsetting", "from_type", "string", ("entity", "projection")),
        "limit": ScalarField("traitsetsetting", "limit", "int"),
    },
    "trait": {
        "id": ScalarField("trait", "id", "string"),
        "traitset_id": ScalarField("trait", "traitset_id", "string", references="traitset"),
        "default_die_type": ScalarField("trait", "default_die_type", "die"),
        # The trait's own labels, matched the same way as on a trait instance.
        "tags": ScalarField("trait", "tags", "string",
                            operators=("contains", "==", "!="), suggest="trait_tags",
                            label="tag"),
    },
    "traitset": {
        "id": ScalarField("traitset", "id", "string"),
        "name": ScalarField("traitset", "name", "string"),
    },
    "entity": {
        "id": ScalarField("entity", "id", "string"),
        "razmerit": ScalarField("entity", "razmerit", "int"),
        "type": ScalarField("entity", "type", "string", ("character", "location", "faction", "asset", "gmc", "universe", "subtrait", "relation")),
        "current_location": ScalarField("entity", "current_location", "string", references="location"),
        "current_universe": ScalarField("entity", "current_universe", "string", references="universe"),
    },
    "projection": {
        "type": ScalarField("projection", "type", "string"),
        # The world a life lives in — an autosuggest picker over the universes,
        # storing the *handle* (`three_realms`) because that is what a projection
        # holds. The builder also allows a bound name instead (`{universe}`), so a
        # path can join to a world chosen elsewhere.
        "universe": ScalarField("projection", "universe", "string", references="universe"),
        "origin_universe": ScalarField("projection", "origin_universe", "string", references="universe"),
        "entity_id": ScalarField("projection", "entity_id", "string", references="entity"),
        "current_location": ScalarField("projection", "current_location", "string", references="location"),
        # A timestamp: ordered by when it happened, which is what lets a path ask
        # for "the most recently used body" (`top field=last_used_at`).
        "last_used_at": ScalarField("projection", "last_used_at", "datetime", label="recently used"),
    },
    "location": {
        "id": ScalarField("location", "id", "string"),
        "name": ScalarField("location", "name", "string"),
        "type": ScalarField("location", "type", "string"),
        "universe": ScalarField("location", "universe", "string"),
    },
    "relationship": {
        # The edge's own type ("membership", "agency", …) — content, not schema,
        # so it is a plain string rather than an enum.
        "type": ScalarField("relationship", "type", "string"),
        "description": ScalarField("relationship", "description", "string"),
        "owner_id": ScalarField("relationship", "owner_id", "string",
                                references="entity", label="holding entity"),
        "contact_id": ScalarField("relationship", "contact_id", "string",
                                  references="entity", label="other entity"),
        "contact_name": ScalarField("relationship", "contact_name", "string", label="other entity's name"),
    },
    "universe": {
        "id": ScalarField("universe", "id", "string"),
        "name": ScalarField("universe", "name", "string"),
    },
    # The SFX registry's own columns, so a path can say "the manual rules", "the
    # ones sourced on a location", or name one outright. All three value sources
    # are data (see ``suggest``): the wizard autosuggests what exists rather than
    # freezing a vocabulary here, so adding a trigger or a source kind needs no
    # change to this table.
    "sfx": {
        "id": ScalarField("sfx", "id", "string"),
        "name": ScalarField("sfx", "name", "string", suggest="sfx_names"),
        "trigger": ScalarField("sfx", "trigger", "string", suggest="sfx_triggers"),
        "source_kind": ScalarField("sfx", "source_kind", "string",
                                   suggest="sfx_source_kinds", label="source"),
    },
}


# ── Navigation edges ───────────────────────────────────────────

@dataclass(frozen=True)
class Edge:
    """A named hop from one element type to another.

    ``target`` is a tuple of possible element types (union-capable). Most edges
    are single-typed (length 1); a polymorphic hop like ``traitsetting._from``
    can later declare ``("entity", "projection")`` without a schema change.
    """
    name: str
    source: str
    target: tuple[str, ...]
    cardinality: str  # "one" (1→1) or "many" (1→N)
    label: str = ""
    # Card vocabulary (see [[SFX Natural Language Plan]]): the singular/plural
    # noun a path step lands on, and the phrase replacing "of {source}" when the
    # source is a *bare* collection (no filters applied), e.g. "you rolled".
    noun: str = ""
    plural: str = ""
    card_origin: str = ""


def edge_noun(e: Edge) -> tuple[str, str]:
    """The edge's card noun as ``(singular, plural)``."""
    singular = e.noun or e.label.lower() or e.name
    return singular, (e.plural or pluralize(singular))


def pluralize(word: str) -> str:
    """Naive English plural (the catalog supplies explicit forms where it matters)."""
    if not word:
        return word
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return word[:-1] + "ies"
    if word == "die":
        return "dice"
    return word + "s"


EDGES: tuple[Edge, ...] = (
    # die → its trait instance (ts_id) and its pool/roll owner
    # No first-person default here: *whose* dice these are is the seed's business
    # (`rolled_dice` / `opposing_dice` / `added_dice` each carry their own party
    # phrase), so a path through a *pool* does not get to claim "you rolled".
    Edge("traitsetting", "die", ("traitsetting",), "one", "Owning trait instance",
         noun="trait instance", plural="trait instances"),
    Edge("owner", "die", ("entity",), "one", "Pool owner", noun="pool owner"),

    # traitsetting → the dice that make up its *rating*. A rating is a list, so
    # this is the second way to reach a `die` element — and the other locus a
    # `Change a Die` effect can land on. The two hops are deliberately distinct
    # element types: a rating die has no result, role or pool position, and
    # changing it is persistent where changing a pool die is not.
    Edge("rating_dice", "traitsetting", ("rating_die",), "many", "Rating dice",
         noun="rating die", plural="rating dice"),
    Edge("traitsetting", "rating_die", ("traitsetting",), "one", "Trait instance",
         noun="trait instance", plural="trait instances"),

    # traitsetting → registry trait / traitset / owners
    # (the polymorphic `_from` anchor is split into already-distinct fields)
    Edge("trait", "traitsetting", ("trait",), "one", "Registry trait", noun="trait"),
    Edge("traitset", "traitsetting", ("traitset",), "one", "Trait set"),
    Edge("entity", "traitsetting", ("entity",), "one", "Owning entity", noun="owner"),
    Edge("projection", "traitsetting", ("projection",), "one", "Owning projection"),

    # traitsetting → the trait instances nested *under* it (sub-traits).
    # A root is a facet of the trait it hangs from, not an independent thing the
    # entity holds, so it is deliberately absent from `entity → traitsettings`
    # (that read filters `from_type != 'traitsetting'`) and reachable only here:
    # *my Spiritual Power → its elemental roots*. See [[Elements and Spiritual Roots]].
    Edge("subtraits", "traitsetting", ("traitsetting",), "many", "Sub-traits",
         noun="sub-trait", plural="sub-traits"),

    # entity → location / universe / projections / its trait instances
    Edge("location", "entity", ("location",), "one", "Current location", noun="location"),
    Edge("universe", "entity", ("universe",), "one", "Current universe", noun="universe"),
    Edge("projection", "entity", ("projection",), "one", "Current projection",
         noun="projection"),
    Edge("projections", "entity", ("projection",), "many", "All projections",
         noun="projection"),
    Edge("traitsettings", "entity", ("traitsetting",), "many", "Trait instances",
         noun="trait instance", plural="trait instances"),

    # projection → owning entity / current location
    Edge("entity", "projection", ("entity",), "one", "Owning entity", noun="owner"),
    Edge("location", "projection", ("location",), "one", "Current location", noun="location"),

    # entity → its relationship edges → the trait instances anchored to one.
    # A trait instance can live on the *edge* rather than on the entity (your
    # standing with a faction), and this is the route that reaches it. Outgoing
    # only, matching the sheet's own reading of "what I hold about others".
    Edge("relationships", "entity", ("relationship",), "many", "Relationships",
         noun="relationship"),
    Edge("traitsettings", "relationship", ("traitsetting",), "many", "Trait instances",
         noun="trait instance", plural="trait instances"),
    Edge("entity", "relationship", ("entity",), "one", "Holding entity", noun="owner"),
    Edge("relationship", "traitsetting", ("relationship",), "one", "Owning relationship",
         noun="relationship"),

    # location → universe / occupants
    Edge("universe", "location", ("universe",), "one", "Universe", noun="universe"),
    Edge("occupants", "location", ("entity",), "many", "Occupants", noun="occupant"),

    # entity / location → their dice pool (pool-assembly target for add_dice)
    Edge("pool", "entity", ("pool",), "one", "Dice pool"),
    Edge("difficulty_pool", "location", ("pool",), "one", "GM difficulty pool",
         noun="GM difficulty pool", plural="GM difficulty pools"),

    # pool → the dice currently assembled in it. A pool element is a *handle*
    # (owner + location + kind); its dice live in the scene store, which is what
    # makes "whose pool → which dice → the trait behind one" walkable — e.g. the
    # opponent's water technique, from the entity you are facing.
    Edge("dice", "pool", ("die",), "many", "Dice in the pool",
         noun="die", plural="dice"),

    # traitset ↔ trait, trait → universes
    Edge("traits", "traitset", ("trait",), "many", "Traits", noun="trait"),
    Edge("traitset", "trait", ("traitset",), "one", "Trait set"),
    Edge("universes", "trait", ("universe",), "many", "Universes", noun="universe"),
)


# ── Aggregations ───────────────────────────────────────────────

@dataclass(frozen=True)
class Aggregation:
    """What an ``aggregate`` step does with a collection.

    ``output`` is ``"int"`` (count), ``"number"`` (mean/avg_*), ``"same"`` (the
    field's own type — min/max) or ``"element"`` (the element *carrying* the
    extreme value — top/bottom). ``needs_field`` is False for count and random;
    ``needs_count`` is True for random (how many to sample). ``accepts`` lists the
    field types the function can run on, so a `datetime` field yields only the
    functions that make sense for it.
    """
    name: str
    label: str
    output: str
    needs_field: bool
    card: str = ""  # template with {field} and {src}; "" → derived
    needs_count: bool = False
    accepts: tuple[str, ...] = ()  # field types; () with needs_field = any


#: Ordering needs a comparable field; averaging needs a numeric one.
_ORDERABLE_TYPES = ("int", "number", "die", "datetime")
_NUMERIC_TYPES = ("int", "number", "die")


def aggregation_card(agg: Aggregation, src: str, field: str) -> str:
    """The card phrase for collapsing ``src`` with ``agg`` (over ``field``)."""
    if agg.card:
        return agg.card.format(field=field, src=src)
    if agg.name == "count":
        return f"the number of {src}"
    return f"the {agg.label.lower()} {field} among {src}"


AGGREGATIONS: tuple[Aggregation, ...] = (
    Aggregation("count", "Count", "int", False, card="the number of {src}"),
    Aggregation("random", "Random", "element", False, needs_count=True,
                card="a random {src}"),
    Aggregation("min", "Lowest value", "same", True, accepts=_ORDERABLE_TYPES,
                card="the lowest {field} among {src}"),
    Aggregation("max", "Highest value", "same", True, accepts=_ORDERABLE_TYPES,
                card="the highest {field} among {src}"),
    # The element *carrying* the extreme value — argmax/argmin, the old `top`
    # step. `max` gives the value (a number or a date); these give the thing, so
    # the path keeps walking to what the element can do.
    Aggregation("top", "Highest element", "element", True, accepts=_ORDERABLE_TYPES),
    Aggregation("bottom", "Lowest element", "element", True, accepts=_ORDERABLE_TYPES),
    Aggregation("mean", "Mean", "number", True, accepts=_NUMERIC_TYPES,
                card="the average {field} among {src}"),
    Aggregation("avg_floor", "Average (floor)", "number", True, accepts=_NUMERIC_TYPES,
                card="the average {field} among {src}, rounded down"),
    Aggregation("avg_ceil", "Average (ceil)", "number", True, accepts=_NUMERIC_TYPES,
                card="the average {field} among {src}, rounded up"),
)


def aggregations_for(field_type: str | None) -> tuple[Aggregation, ...]:
    """The functions a field of ``field_type`` can run (``None`` = no field).

    One declaration, two readers: the editor filters its function list with this,
    and the type-checker refuses a function the field cannot support — so what is
    offered is what resolves.
    """
    if field_type is None:
        return tuple(a for a in AGGREGATIONS if not a.needs_field)
    return tuple(
        a for a in AGGREGATIONS
        if a.needs_field and (not a.accepts or field_type in a.accepts)
    )


# ── Starting collections (the `select` step's options) ────────

@dataclass(frozen=True)
class Collection:
    """A context collection a spec may seed from via ``select``."""
    name: str
    element: str
    label: str
    singular: bool = False  # True for singleton seeds like "self"
    # Card vocabulary ([[SFX Natural Language Plan]]): the head noun a filter can
    # qualify, an optional trailing qualifier, and whether the phrase reads in the
    # possessive ("your trait instances") or as a bare pronoun ("you").
    noun: str = ""
    plural: str = ""
    origin: str = ""
    possessive: bool = False
    pronoun: bool = False
    # The phrase a hop *from* this seed absorbs into ("you rolled" / "they
    # rolled"). Where a seed knows its own party, the hop uses it instead of the
    # edge's default, so the other side's dice never read as the actor's.
    card_origin: str = ""


COLLECTIONS: tuple[Collection, ...] = (
    Collection("self", "entity", "The acting entity", singular=True, pronoun=True),
    Collection("rolled_dice", "die", "Dice in the current roll",
               noun="die", plural="dice", origin="in your roll",
               card_origin="you rolled"),
    # The other side of a contest, at the moment a pool is saved. Seeded from the
    # event's ``opposing_rolls`` (see [[Elements and Spiritual Roots]]) — this is
    # what makes "their metal against my fire" writable as one rule: each side is
    # a condition path, and the two are compared by both having to pass.
    Collection("opposing_dice", "die", "Dice in the opposing pool",
               noun="die", plural="dice", origin="in the opposing pool",
               card_origin="they rolled"),
    # What a pool save *added*, as opposed to what is in the pool (that is the
    # `pool → dice` hop). Only the pool-change moment can know it — the client
    # PUTs the whole pool, so the previous list is the only record of what
    # changed.
    Collection("added_dice", "die", "Dice just added to the pool",
               noun="die", plural="dice", origin="just added", card_origin="you added"),
    Collection("occupants", "entity", "Entities at the current location",
               noun="entity", origin="here"),
    Collection("locations", "location", "All locations", noun="location"),
    Collection("entities", "entity", "All entities", noun="entity"),
    # The two whole-world seeds: every trait *definition* in the registry, and
    # every universe. A definition seed is how an action that creates or teaches
    # names what it is about without a picker (`gain_trait`), and the universes
    # seed is how a path ranges over worlds instead of starting from one entity.
    Collection("traits", "trait", "Traits in the registry", noun="trait"),
    Collection("universes", "universe", "All universes", noun="universe"),
    Collection("self_traitsettings", "traitsetting", "The acting entity's trait instances",
               noun="trait instance", possessive=True),
    Collection("sfxs", "sfx", "Rules in the registry", noun="rule"),
)


# ── Display fields (choose-picker labels) ──────────────────
#
# Declarative picker labels per element type. The interactive ``choose`` step
# resolves candidates on the backend; the frontend dialog needs a primary label
# and a secondary label for each. This table names which element field carries
# each, so the serializer and the picker renderer stay data-driven and share one
# source of truth (rather than a bespoke component per type).

@dataclass(frozen=True)
class DisplayFields:
    element: str
    name_field: str = ""        # field for the primary label (empty → element id)
    subtitle_field: str = ""    # field for the secondary label (empty → none)


DISPLAY_FIELDS: dict[str, DisplayFields] = {
    "die": DisplayFields("die", "rating", "role"),
    "rating_die": DisplayFields("rating_die", "rating", "index"),
    "traitsetting": DisplayFields("traitsetting", "trait_id", "rating"),
    "traitsetsetting": DisplayFields("traitsetsetting", "traitset_id", ""),
    "trait": DisplayFields("trait", "name", "traitset_id"),
    "traitset": DisplayFields("traitset", "name", ""),
    "entity": DisplayFields("entity", "name", "type"),
    "projection": DisplayFields("projection", "name", "universe"),
    "location": DisplayFields("location", "name", "universe"),
    "relationship": DisplayFields("relationship", "contact_name", "type"),
    "universe": DisplayFields("universe", "name", ""),
    "pool": DisplayFields("pool", "kind", ""),
    "sfx": DisplayFields("sfx", "name", "trigger"),
}


# ── Source kinds (SFX activation origin) ────────────────────
#
# The declarative owner type an SFX can state. Each entry maps an author-facing
# ``source_kind`` to the catalog element its ``{variable}`` resolves to, the
# variable token name, and the owner surface it must attach to. This is the
# single seam for the entity/projection question: if those two ever merge, only
# the ``entity``/``projection`` rows here (and the runtime resolver) change.

@dataclass(frozen=True)
class SourceKind:
    value: str          # source_kind stored on SFX
    label: str          # editor dropdown label
    element: str        # catalog element the source variable resolves to
    variable: str       # the ``{variable}`` token exposed to effect authoring
    owner_surface: str  # SfxOwnerKind value this SFX must attach to


SOURCE_KINDS: tuple[SourceKind, ...] = (
    SourceKind("trait_setting", "Trait setting", "traitsetting", "trait_setting", "trait_instance"),
    SourceKind("traitset_setting", "Trait set setting", "traitsetsetting", "traitset_setting", "trait_set"),
    SourceKind("entity", "Entity", "entity", "entity", "entity"),
    # A *place* is its own kind of source: the rule is attached to a location and
    # applies to whoever is in it, so the source is the location itself — not the
    # acting entity, which is what `entity` resolves to at fire time. The owner
    # surface is the location one (not `entity`), so a location-sourced rule
    # attached to a character is caught rather than silently resolving to them.
    SourceKind("location", "Location", "location", "location", "location"),
    SourceKind("projection", "Projection", "projection", "projection", "projection"),
    # Bucket sources: attached to the table/GM owner buckets, not a typed
    # instance. Non-resolving — empty element/variable, so ``source_element``
    # and ``source_variable`` return None and there is no ``select source`` /
    # ``{variable}`` / ``source_rating`` for them.
    SourceKind("table", "Table", "", "", "table"),
    SourceKind("gm", "GM", "", "", "gm"),
)

_SOURCE_KINDS_BY_VALUE: dict[str, SourceKind] = {s.value: s for s in SOURCE_KINDS}


def source_kind(value: str) -> SourceKind | None:
    """The declared ``SourceKind`` for ``value``, or None when unknown/unset."""
    return _SOURCE_KINDS_BY_VALUE.get(value)


def source_variable(value: str) -> str | None:
    """The ``{variable}`` token a ``source_kind`` exposes (None when unset/non-resolving)."""
    sk = _SOURCE_KINDS_BY_VALUE.get(value)
    return sk.variable if sk and sk.variable else None


def source_element(value: str) -> str | None:
    """The catalog element type a ``source_kind``'s source resolves to (None when unset/non-resolving)."""
    sk = _SOURCE_KINDS_BY_VALUE.get(value)
    return sk.element if sk and sk.element else None


def bind_source(source_kind: str, source_id: str | None, context: dict) -> dict:
    """Inject the declared source variable into a fire-time context.

    Maps ``source_kind`` → its ``{variable}`` token and binds ``source_id``
    under that key, so ``_substitute_effect_context`` replaces ``{trait_setting}``
    etc. with the concrete id. No-op when ``source_kind`` is unset/unknown or
    ``source_id`` is empty. This is the runtime half of the seam: the *type* is
    declared on the SFX, the *id* arrives from the activation (client click).
    """
    if not source_id:
        return context
    sk = _SOURCE_KINDS_BY_VALUE.get(source_kind)
    if sk is None or not sk.variable:
        return context  # unknown kind or non-resolving bucket source (table/gm)
    return {**context, sk.variable: source_id}


# ── The activation's own names ─────────────────────────────────
#
# A declared ``{variable}`` type is what the token holds in the author's words
# (``trait_setting``, ``entity``); a catalog *element* is what a targeting path
# can walk (``traitsetting``, ``entity``). Close — but not the same vocabulary,
# because the instance/registry split is spelled differently on each side. The
# mapping lives here once, so the editor offers exactly what the fire binds.
_VARIABLE_ELEMENTS: dict[str, str] = {
    "die": "die",
    "trait_setting": "traitsetting",
    "traitsetting": "traitsetting",
    "traitset_setting": "traitsetsetting",
    "traitsetsetting": "traitsetsetting",
    "trait": "trait",
    "traitset": "traitset",
    "entity": "entity",
    "projection": "projection",
    "location": "location",
    "universe": "universe",
    "pool": "pool",
    "sfx": "sfx",
}


def element_for_variable(type_name: str) -> str:
    """The catalog element a declared ``{variable}`` type resolves to ("" = not walkable)."""
    return _VARIABLE_ELEMENTS.get(type_name or "", "")


def scope_seed_names(trigger: str, source_kind_value: str | None) -> dict[str, str]:
    """The names the *activation itself* puts in scope, as ``{name: element}``.

    These are the tokens the SFX editor already lists under *Available
    variables*: the source token (``{trait_setting}``, ``{location}``, …) and
    whatever the trigger declares (``{contest_entity_opponent}``, ``{effect_die}``,
    …). Declared tokens that a path cannot walk (a number, a string, a boolean)
    are left out — the wizard should not offer a seed that cannot be navigated.

    One declaration, two readers: the editor's ``effectVariables`` types the
    wizard's ``select variable`` candidates from this, and the engine binds the
    same names from the live event — so what is offered is what resolves.
    """
    from transversal.services.menu_contexts import trigger_variables

    seeds: dict[str, str] = {}
    declared = _SOURCE_KINDS_BY_VALUE.get(source_kind_value or "")
    if declared is not None and declared.variable and declared.element:
        seeds[declared.variable] = declared.element
    for v in trigger_variables(trigger or ""):
        element = element_for_variable(v.type)
        if element:
            seeds.setdefault(v.name, element)
    return seeds


# ── Query helpers ──────────────────────────────────────────────

def element(name: str) -> ElementType | None:
    return ELEMENT_TYPES.get(name)


def edge(source: str, name: str) -> Edge | None:
    for e in EDGES:
        if e.source == source and e.name == name:
            return e
    return None


def edges_from(source: str) -> list[Edge]:
    return [e for e in EDGES if e.source == source]


def fields_for(element: str) -> list[ScalarField]:
    return list(SCALAR_FIELDS.get(element, {}).values())


def field(element: str, name: str) -> ScalarField | None:
    return SCALAR_FIELDS.get(element, {}).get(name)


def aggregation(name: str) -> Aggregation | None:
    for a in AGGREGATIONS:
        if a.name == name:
            return a
    return None


def collection(name: str) -> Collection | None:
    for c in COLLECTIONS:
        if c.name == name:
            return c
    return None


def display_fields(element: str) -> DisplayFields | None:
    """The picker label fields for ``element``, or None when undeclared."""
    return DISPLAY_FIELDS.get(element)


# ── Validation ─────────────────────────────────────────────────

def validate() -> list[str]:
    """Return internal-consistency problems (empty = valid)."""
    problems: list[str] = []
    seen_edges: set[tuple[str, str]] = set()
    for e in EDGES:
        if e.source not in ELEMENT_TYPES:
            problems.append(f"edge {e.source}.{e.name}: unknown source type")
        for t in e.target:
            if t not in ELEMENT_TYPES:
                problems.append(f"edge {e.source}.{e.name}: unknown target type {t!r}")
        if e.cardinality not in ("one", "many"):
            problems.append(f"edge {e.source}.{e.name}: bad cardinality {e.cardinality!r}")
        key = (e.source, e.name)
        if key in seen_edges:
            problems.append(f"duplicate edge {e.source}.{e.name}")
        seen_edges.add(key)

    for element_name, fields in SCALAR_FIELDS.items():
        if element_name not in ELEMENT_TYPES:
            problems.append(f"scalar fields for unknown element {element_name!r}")
        for f in fields.values():
            if f.type not in ("int", "number", "die", "string", "datetime"):
                problems.append(f"field {element_name}.{f.name}: bad type {f.type!r}")

    for a in AGGREGATIONS:
        if a.output not in ("int", "number", "same", "element"):
            problems.append(f"aggregation {a.name}: bad output {a.output!r}")
        # A function's accepted types must be real field types, or the editor's
        # gating would offer a function that can never run.
        for t in a.accepts:
            if t not in ("int", "number", "die", "string", "datetime"):
                problems.append(f"aggregation {a.name}: unknown accepted type {t!r}")
        if not a.needs_field and a.accepts:
            problems.append(f"aggregation {a.name}: accepts fields but needs none")

    for c in COLLECTIONS:
        if c.element not in ELEMENT_TYPES:
            problems.append(f"collection {c.name}: unknown element {c.element!r}")

    for sk in SOURCE_KINDS:
        # Bucket sources (``table``/``gm``) are non-resolving: empty element.
        if sk.element and sk.element not in ELEMENT_TYPES:
            problems.append(f"source_kind {sk.value}: unknown element {sk.element!r}")

    return problems
