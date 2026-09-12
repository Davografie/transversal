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
    # The catalog element a *targeting path* must resolve to, when that differs
    # from the picker kind — or exists where there is no picker at all. The two
    # questions are separate: `target_kind` names what the literal/choose/random
    # modes offer (there is no "die" picker), while a path to a die in a pool is
    # perfectly writable. Declaring this is what lets such an action offer the
    # path mode without inventing a picker kind for it.
    path_element: str = ""
    refs: list[RefDef] = field(default_factory=list)  # named references (multi-target model)
    supports_duration: bool = False      # UI shows a duration/timers builder
    supports_polarity: bool = False      # UI shows a negative (complication) toggle
    supports_return_exit: bool = False   # UI offers a "{return:<name>}" target mode (shared tables)
    inverse: tuple[str, str] | None = None  # (type, action) to undo this effect
    inverse_captures_prior: bool = False    # revert needs the pre-apply value

_RELATIONSHIP_CONTEXT_FIELD = EffectFieldDef(
    name="relationship",
    label="Faction (relationship)",
    field_type="text",
    required=False,
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
