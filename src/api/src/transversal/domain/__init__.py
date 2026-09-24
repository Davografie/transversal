"""Transversal domain models — v2.

Multi-collection data model inspired by the v1 ArangoDB schema.

Collections:
  entities      — metadata (name, type, razmerit, universe state)
  projections   — per-universe body grouping
  traits        — registry of all possible traits per universe
  traitsets     — registry of trait groupings
  traitsettings — edge: entity → trait, carries rating/type/statement
  sfxs          — SFX registry
  relationships — edge: entity → entity
  life_paths    — life path definitions (Traveller-style term loops)

The models are grouped by concern in the sibling modules; this package
re-exports every one of them, so ``from transversal.domain import X`` is
unchanged.
"""

# Re-exported unchanged: every model below now lives in a sibling module
# of this package.  ``TargetSpec`` was re-exported by this module before the
# split and stays part of its public surface.

from transversal.services.target_spec import TargetSpec  # noqa: F401

from transversal.domain.enums import (  # noqa: F401
    DieType,
    RatingType,
    Polarity,
    OutcomeTier,
    EntityType,
    TransversalType,
    ArrivalKind,
    RollKind,
    ContestWinner,
    EffectTiming,
    AttunementScope,
    AttunementOp,
    TimerCombine,
    ConditionType,
    RollTableScheme,
    RollSource,
    ImageType,
    MessageKind,
    HistoricalRecordType,
    SheetTab,
)

from transversal.domain.dice import (  # noqa: F401
    DieSpec,
    DieRoll,
    Opposition,
    DicePoolRequest,
    ChallengeResult,
    SimplifiedResult,
    PoolResult,
    ContestResult,
    CommittedResult,
    ContestOutcome,
    ContestCompare,
    RollResult,
    _coerce_die_list,
    dice_list_to_rating,
)

from transversal.domain.traits import (  # noqa: F401
    CONTAINER_TAG,
    TraitDisplayName,
    Trait,
    TraitSet,
    TraitSetting,
    TraitSetSetting,
    resolve_trait_display_name,
    derive_placement,
    derive_arming_scope,
)

from transversal.domain.entities import (  # noqa: F401
    Projection,
    Zone,
    TargetingBan,
    Attunement,
    Entity,
    STRUCTURAL_RELATIONSHIP_TYPES,
    PERSONAL_RELATIONSHIP_TYPE,
    MEMBERSHIP_HOLDER_TYPES,
    is_structural_relationship_type,
)

from transversal.domain.lifepath import (  # noqa: F401
    DiscoveryBlock,
    LifePath,
    Enrollment,
    PendingTerm,
)

from transversal.domain.effects import (  # noqa: F401
    TargetRef,
    Effect,
    Timer,
    EffectDuration,
    ScheduledEvent,
    ConsequenceOption,
    Condition,
)

from transversal.domain.sfx import (  # noqa: F401
    SFX,
    BoundVariable,
    SfxOwner,
)

from transversal.domain.rolltables import (  # noqa: F401
    RollTableEntry,
    RollTableCheck,
    RollTable,
)

from transversal.domain.views import (  # noqa: F401
    CharacterView,
    EntityImage,
)

from transversal.domain.messaging import (  # noqa: F401
    Message,
    HistoricalRecord,
)

from transversal.domain.players import (  # noqa: F401
    Player,
)
