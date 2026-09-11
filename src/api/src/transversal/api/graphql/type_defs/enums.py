"""Enums — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from transversal.domain import ConditionType as DomainConditionType
from transversal.domain import DieType as DomainDieType
from transversal.domain import EffectTiming as DomainEffectTiming
from transversal.domain import EntityType as DomainEntityType
from transversal.domain import MessageKind as DomainMessageKind
from transversal.domain import OutcomeTier as DomainOutcomeTier
from transversal.domain import Polarity as DomainPolarity
from transversal.domain import RatingType as DomainRatingType
from transversal.domain import RollSource as DomainRollSource
from transversal.domain import RollTableScheme as DomainRollTableScheme
from transversal.domain import TimerCombine as DomainTimerCombine
from transversal.domain import TransversalType as DomainTransversalType


DieType = strawberry.enum(DomainDieType)

RatingType = strawberry.enum(DomainRatingType)

EntityType = strawberry.enum(DomainEntityType)

TransversalTypeEnum = strawberry.enum(DomainTransversalType)

Polarity = strawberry.enum(DomainPolarity)

EffectTimingEnum = strawberry.enum(DomainEffectTiming)

MessageKind = strawberry.enum(DomainMessageKind)

OutcomeTier = strawberry.enum(DomainOutcomeTier)

RollTableScheme = strawberry.enum(DomainRollTableScheme)

RollSource = strawberry.enum(DomainRollSource)

ConditionType = strawberry.enum(DomainConditionType)

TimerCombineGql = strawberry.enum(DomainTimerCombine)
