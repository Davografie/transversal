"""Conditions — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional
from transversal.api.graphql.type_defs.enums import (
    ConditionType,
)


@strawberry.type
class Condition:
    """A configurable, automatically-evaluated gate or limit."""
    type: ConditionType
    subject: str = ""
    target: str = ""
    targets: list[str] = strawberry.field(default_factory=list)
    value: Optional[str] = None
    operator: str = ">="
    narrative: str = ""
    spec: Optional[strawberry.scalars.JSON] = None

@strawberry.input
class ConditionInput:
    type: ConditionType = ConditionType.ALWAYS
    subject: str = ""
    target: str = ""
    targets: list[str] = strawberry.field(default_factory=list)
    value: Optional[str] = None
    operator: str = ">="
    narrative: str = ""
    spec: Optional[strawberry.scalars.JSON] = None
