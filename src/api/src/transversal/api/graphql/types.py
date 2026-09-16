"""Strawberry GraphQL types — mapping domain models to GraphQL schema.

The type definitions are grouped by concern in
:mod:`transversal.api.graphql.type_defs`; this module re-exports them, so
``from transversal.api.graphql.types import X`` is unchanged.
"""

from transversal.api.graphql.type_defs.enums import (  # noqa: F401
    DieType,
    RatingType,
    EntityType,
    TransversalTypeEnum,
    Polarity,
    EffectTimingEnum,
    MessageKind,
    OutcomeTier,
    RollTableScheme,
    RollSource,
    ConditionType,
    TimerCombineGql,
    SheetTab,
)
from transversal.api.graphql.type_defs.conditions import (  # noqa: F401
    Condition,
    ConditionInput,
)
from transversal.api.graphql.type_defs.sfx import (  # noqa: F401
    SfxOwnerKind,
    SfxOwnerKindGql,
    SfxRef,
    SfxInput,
    SfxUpdateInput,
    SfxOwnerRef,
    PlaceSfxRules,
    OwnerRefInput,
)
from transversal.api.graphql.type_defs.traits import (  # noqa: F401
    TraitDisplayName,
    TraitDisplayNameInput,
    TraitRef,
    TraitSetRef,
    _gql_trait_setting,
    TraitInput,
    TraitUpdateInput,
    TraitSetting,
    TraitSettingInput,
    TraitSettingUpdateInput,
    TraitSetSetting,
)
from transversal.api.graphql.type_defs.entities import (  # noqa: F401
    Projection,
    Zone,
    Attunement,
    PendingTerm,
    Entity,
    CreateEntityInput,
    UpdateEntityInput,
    RazmeritResult,
    CharacterView,
)
from transversal.api.graphql.type_defs.effects import (  # noqa: F401
    Timer,
    TimerInput,
    EffectDuration,
    EffectDurationInput,
    Effect,
    EffectInput,
    ScheduledEvent,
    ActiveSfx,
    ActiveSfxBinding,
    EffectFieldDef,
    RefDef,
    EffectActionMeta,
    ConsequenceOption,
    ConsequenceOptionInput,
    PendingChoiceRef,
    EffectApplicationResult,
    TargetChoiceAnswerInput,
    EffectTargetResolutionInput,
)
from transversal.api.graphql.type_defs.targeting import (  # noqa: F401
    TargetCandidate,
    FilterFieldOption,
    ScopeVariable,
    EffectVariable,
    TriggerOption,
    ConditionTypeOption,
    TargetCatalogElement,
    TargetCatalogEdge,
    TargetCatalogField,
    TargetLabel,
    TargetCatalogAggregation,
    TargetCatalogCollection,
    SourceKindOption,
    TargetCatalog,
    TargetSpecStepInput,
    TargetSpecInput,
    TargetTraceType,
    TargetTraceError,
    TargetTraceResult,
)
from transversal.api.graphql.type_defs.rolltables import (  # noqa: F401
    RollTableCheck,
    RollTableEntry,
    RollTable,
    RollTableCheckInput,
    RollTableEntryInput,
    RollTableInput,
)
from transversal.api.graphql.type_defs.messaging import (  # noqa: F401
    Message,
    SendMessageInput,
    JournalEntryInput,
    UpdateMessageInput,
    UpdateHistoricalRecordInput,
    HistoricalRecord,
)
from transversal.api.graphql.type_defs.relationships import (  # noqa: F401
    Relationship,
    CreateRelationshipInput,
    DeleteRelationshipInput,
    RelatedEntity,
)
from transversal.api.graphql.type_defs.lifepath import (  # noqa: F401
    DiscoveryBlock,
    LifePath,
    LifePathStepResult,
)
from transversal.api.graphql.type_defs.players import (  # noqa: F401
    AgencyEdge,
    Player,
    SetAgencyMainInput,
    SupportCharacter,
    ActiveMain,
    PlayerBody,
)
