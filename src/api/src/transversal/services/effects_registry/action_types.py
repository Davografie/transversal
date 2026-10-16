"""Action metadata types and the shared effect-context field definitions.

Split out of ``effects_registry.py``."""

from dataclasses import dataclass
from dataclasses import field


@dataclass
class EffectFieldDef:
    """A single input field needed by an effect action."""
    name: str              # e.g. "result", "target", "amount"
    label: str             # e.g. "Die Rating", "Target Trait"
    field_type: str        # "die_select" | "text" | "number" | "select"
    required: bool = True
    default: str | None = None
    options: list[str] | None = None   # for select / die_select
    # Dynamic option source for fields whose values are *content*, not an enum
    # ("universes" today). The editor asks the server to fill these from the DB;
    # ``options`` stays as the fallback when the source yields nothing.
    # Recognised by the GraphQL layer — see ``_field_options`` in schema.py.
    options_from: str = ""
    # Name of an ``EffectActionMeta.refs`` entry that supersedes this field. When
    # that reference is authored the editor hides the field (it is the fallback
    # form) while keeping its stored value, so existing content keeps working.
    hidden_when_ref: str = ""
    # One line of help under the label. A shared field like the entity targeter
    # reads differently per action ("Give To" for Move Trait), so an action can
    # say what *this* action wants the value for.
    description: str = ""

@dataclass
class RefDef:
    """A named reference an effect action declares (the multi-target model).

    Each ref is a targeting-wizard selection the editor renders as its own
    picker/spec builder. ``elements`` is the catalog element type (or types) the
    ref must resolve to, and drives the picker + the fire-time type-check.

    It is a **set**, not one string, because the positional fields this replaces
    already were: a target may be a die in a pool or a die of a rating
    (``path_element``), and an owner may be a trait instance or a relationship
    edge (``owner_elements``). A single-element ref is written as a plain string —
    ``RefDef("trait", "Trait", "traitsetting")`` — and normalised to a tuple here,
    so the two forms cannot be confused at a call site.
    """
    name: str          # key into Effect.refs, e.g. "trait", "pool", "learner"
    label: str         # editor label, e.g. "Trait", "Destination pool"
    elements: str | tuple[str, ...] = ""
    # What this reference **is**, so a reader can ask for it without knowing its
    # name: "target" (what the effect acts on), "entity" (who it lands on), "owner"
    # (where what it makes is anchored). The accessors in `services.effect_refs`
    # look the ref up by role, so renaming one cannot leave a reader behind
    # ([[B261]]).
    role: str | None = None
    # An **anchor** is authored as a reference but is not a per-fire multiplier:
    # it says where the thing the effect *makes* lives, and its own resolver
    # (`resolve_effect_owner`) settles it once. A reference that is not an anchor
    # fans the effect out per resolved value; an anchor resolving to three edges
    # would make three things rather than one thing anchored three ways. The owner
    # path is the only one ([[B261]]).
    anchor: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.elements, str):
            self.elements = (self.elements,) if self.elements else ()

@dataclass
class EffectActionMeta:
    """Metadata for one effect action the editor can create."""
    action_id: str              # unique key, e.g. "play_as_rating"
    label: str                  # "Play as Rating"
    description: str            # tooltip / help text
    category: str               # "cost" | "benefit" | "either" (UI hint)
    effect_type: str            # maps to Effect.type
    effect_action: str          # maps to Effect.action
    group: str = ""             # functional group for the editor dropdown (optgroup)
    valid_timings: list[str] = field(default_factory=lambda: [
        "IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION",
        "ON_ROLL", "ON_SET", "ON_RESULT",
        "ON_CONTEST_WIN", "ON_CONTEST_LOSS", "ON_SUCCESS", "ON_FAILURE",
    ])
    fields: list[EffectFieldDef] = field(default_factory=list)
    context_fields: list[EffectFieldDef] = field(default_factory=list)
    implicit_target: str | None = None   # if always the same, hide field
    implicit_result: str | None = None   # if always the same, hide field
    implicit_timing: str | None = None   # if only one valid timing, hide field
    requires_choice: bool = False        # target must be resolved at runtime
    target_kind: str | None = None       # trait | entity | life_path | ...
    # What this action *produces*, when it produces something worth naming: the
    # catalog element type of ``Effect.output`` ("traitsetting" for a gain). The
    # runtime binds the produced id under the author's chosen name, and the editor
    # offers that name as a `select variable` seed — one declaration, both readers.
    output_element: str = ""
    # The catalog elements a *targeting path* must resolve to, when that differs
    # from the picker kind — or exists where there is no picker at all. The two
    # questions are separate: `target_kind` names what the literal/choose/random
    # modes offer (there is no "die" picker), while a path to a die in a pool is
    # perfectly writable. Declaring this is what lets such an action offer the
    # path mode without inventing a picker kind for it.
    #
    # A **tuple**, because an action can accept more than one kind of thing: the
    # change-die family lands on a die in a pool *or* a die of a trait's rating
    # (`("die", "rating_die")`), and the UI greys out the verbs that only make
    # sense on one of them. The trace refuses a spec whose final type is none of
    # these, naming every type that would have worked.
    path_element: tuple[str, ...] = ()
    # The catalog elements this action's **owner path** (`Effect.owner_spec`) may
    # land on, when it anchors what it makes somewhere other than the subject
    # entity: a `relationship` edge (a tie to someone), a `traitsetting` (a facet
    # of another trait), a `projection` (a specific body), or the `entity` itself.
    # Empty = the action has no owner path, and the subject entity is the owner —
    # the ordinary case.
    #
    # A **set**, not a kind: the element the path actually landed on is what the
    # anchor is (it travels with the id), and this tuple is the permission that
    # element is checked against. Trait verbs that create or move an instance all
    # declare the same set (see :data:`TRAIT_OWNER_ELEMENTS`), because which anchor
    # a rule wants is a fact about the rule, not about the verb.
    owner_elements: tuple[str, ...] = ()
    refs: list[RefDef] = field(default_factory=list)  # named references (multi-target model)
    # Render the refs above the fields. A ref that names the *subject* ("Trait to
    # Move") reads before the field that names where it goes; an action whose ref
    # is a secondary path (Attune's "life it comes from") keeps the default order.
    refs_first: bool = False
    # The order the editor renders this action's inputs in, by name, when the
    # default does not read right. Names may be refs, fields or context fields —
    # the editor does not care which, only where each one goes. Anything not named
    # keeps its default place (refs, then fields, then context fields), so an
    # action only has to say what it wants moved.
    #
    # The dice-limit pair is the case that motivated it: the pool is the *subject*
    # ("whose limit"), so it reads before the limit being chosen and the amount
    # applied — where the default put the amount first and the pool last.
    field_order: tuple[str, ...] = ()
    supports_duration: bool = False      # UI shows a duration/timers builder
    # When a duration is meaningful for *some* destinations but not others, name
    # the elements it is offered for. The change-die family changes a die in a
    # pool (rebuilt every roll — nothing to revert) or a die of a trait's rating
    # (a fact, so revertible); only the latter can carry a duration, and the
    # editor reads the path's resolved element to decide. Empty = always offered
    # when `supports_duration` is set, which is what every other action means.
    duration_elements: tuple[str, ...] = ()
    supports_polarity: bool = False      # UI shows a negative (complication) toggle
    supports_return_exit: bool = False   # UI offers a "{return:<name>}" target mode (shared tables)
    inverse: tuple[str, str] | None = None  # (type, action) to undo this effect
    inverse_captures_prior: bool = False    # revert needs the pre-apply value
    # Retired from *authoring*, not from the engine. The editor no longer offers
    # it, so a superseded action cannot be picked again — but the meta stays in
    # the registry, because that is where its inverse, its card template and its
    # dispatch live. Content that already uses it keeps working and keeps
    # reverting; nothing is silently rewritten under an author.
    retired: bool = False

_STEPS_CONTEXT_FIELD = EffectFieldDef(
    name="steps",
    label="Steps",
    field_type="text",
    required=False,
    default="1",
)

_ENTITY_FIELD = EffectFieldDef(
    name="entity",
    label="Entity",
    field_type="entity",
    required=False,
    # Superseded by the ``recipient`` reference below ([[B261]]): *who an effect
    # lands on* is a path like any other. This stays as the fallback form for
    # content authored before the reference, and steps aside once one is authored.
    hidden_when_ref="recipient",
)

#: Every anchor a trait instance can hang on, declared together on the verbs that
#: create or move one. The anchor is a path (`Effect.owner_spec`), and this is what
#: that path may land on:
#:
#: * ``entity`` — the subject's own sheet. A non-ego trait granted this way is
#:   **morph-anchored** (``_new_traitsetting`` re-anchors it to the active
#:   projection), which is why ``projection`` is also declared: a path may name a
#:   *specific* body instead of "whichever one is active".
#: * ``relationship`` — a tie to someone (your standing with a faction, a rank on a
#:   membership).
#: * ``traitsetting`` — another trait instance (a facet of a trait, an agenda step).
#:
#: One set for all of them, because *which* anchor a rule wants is a fact about the
#: rule, not about the verb: the same "gain or step up" action serves a sheet trait
#: and a tenure on a faction edge.
TRAIT_OWNER_ELEMENTS = ("entity", "projection", "relationship", "traitsetting")

#: *Gain Trait* only, and the reason it is a real field rather than prose: with it
#: set, a trait that is already there is **left alone** and the step still names
#: **that** instance as its output — so a later *Step Up Die* / *Increase by Effect
#: Die* can act on "the trait, whether it was just made or already mine". That is
#: the composition which replaces `cortex_gain` and `gain_or_step_up`.
_IF_NOT_EXISTS_FIELD = EffectFieldDef(
    name="if_not_exists",
    label="Only if missing",
    field_type="select",
    required=False,
    default="false",
    options=["false", "true"],   # "true" = only create when missing
    description=(
        "When set, an already-present trait is untouched (rather than the step "
        "failing), and the step's output name still points at it."
    ),
)

_STATEMENT_CONTEXT_FIELD = EffectFieldDef(
    name="statement",
    label="Statement",
    field_type="text",
    required=False,
)

_NOTES_CONTEXT_FIELD = EffectFieldDef(
    name="notes",
    label="Notes",
    field_type="text",
    required=False,
)

#: The **whole rating** a trait-creating effect makes, when it is more than one die.
#: A rating is a row — a resource holds several dice and a challenge usually three
#: ([[B307]]) — and ``result`` (the action's single "Die Rating" field) carries the
#: row's **first** die, which is what every single-die reader already understands.
#: Authoring is one control: the in-line trait editor renders this row and the
#: editor does not render this field separately on a gain verb.
_DICE_CONTEXT_FIELD = EffectFieldDef(
    name="dice",
    label="Rating dice",
    field_type="dice_array",
    required=False,
    description=(
        "Every die of the rating this effect creates. A path on the Die Rating "
        "field fills this from the world (and takes the whole rating); 'Die "
        "Rating' itself carries the first die of it."
    ),
)
