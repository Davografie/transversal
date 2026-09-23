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
    picker/spec builder. ``element`` is the catalog element type the ref must
    resolve to (drives the picker + fire-time type-check).
    """
    name: str          # key into Effect.refs, e.g. "trait", "pool", "subject"
    label: str         # editor label, e.g. "Trait", "Destination pool"
    element: str       # target_catalog element type, e.g. "traitsetting", "pool"

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

_RELATIONSHIP_CONTEXT_FIELD = EffectFieldDef(
    name="relationship",
    label="Relationship with",
    field_type="text",
    required=False,
    description=(
        "Anchor the trait to the edge to this entity instead of to you — a tie to "
        "someone. The edge must already exist: create it first (Create Relationship), "
        "then gain the trait onto it."
    ),
)

#: Which edge the anchor above means. Previously hardcoded to `membership`, which
#: made every other edge type unreachable and landed the trait on the character.
_RELATIONSHIP_TYPE_FIELD = EffectFieldDef(
    name="relationship_type",
    label="Relationship type",
    field_type="text",
    required=False,
    default="membership",
    description="The edge type to anchor to (membership, relation, agency, …).",
)

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
