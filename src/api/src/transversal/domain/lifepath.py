"""Lifepath — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from typing import Optional
from transversal.domain.enums import (
    DieType,
)


class DiscoveryBlock(BaseModel):
    """Conditions for discovering a hidden life path.  Any one condition met → discovered."""
    at_location: list[str] = Field(default_factory=list)
    knows_entity: list[str] = Field(default_factory=list)
    possesses_trait: list[str] = Field(default_factory=list)
    has_trait_rating: dict[str, DieType] = Field(default_factory=dict)
    has_relationship: list[str] = Field(default_factory=list)

class LifePath(BaseModel):
    """A life path definition — an entry point into a graph of linked roll tables.

    Stored in the `life_paths` collection. Term structure lives in RollTable
    documents linked by ``next_step`` effects; discovery gating is optional.
    """
    id: str
    name: str
    universe: str
    description: str = ""
    entry_table_id: str = ""  # _key of the first RollTable in the flow
    discovery: Optional[DiscoveryBlock] = None  # null → always visible

class Enrollment(BaseModel):
    """A character's membership in a faction's life path."""
    faction_id: str
    path_id: str
    mustered: bool = False
    mishap_muster: bool = False

class PendingTerm(BaseModel):
    """In-progress life path term checkpoint.

    Holds where the entity is in the linked roll-table flow so a term can be
    resumed mid-way (reload / another device).
    """
    faction_id: str = ""
    path_id: str = ""
    current_table_id: str = ""
    continuation: list[str] = Field(default_factory=list)  # return-address stack (legacy single-exit)
    return_map: dict[str, str] = Field(default_factory=dict)  # named-exit map for shared tables (no nesting)
