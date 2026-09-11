"""Entity repository — v2 multi-collection model.

CRUD across entities, projections, traits, traitsets, traitsettings, and sfxs.

The implementation is split by concern into
:mod:`transversal.db.repository_mixins`; ``EntityRepository`` composes them, so
the public surface of this module is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arango.database import StandardDatabase

from transversal.db.arango import (
    ENTITIES,
    ENTITY_IMAGES,
    HISTORICAL_RECORDS,
    LIFE_PATHS,
    MESSAGES,
    PLAN_ENTITIES,
    PLAN_RELATIONSHIPS,
    PLAYERS,
    PROJECTIONS,
    RELATIONSHIPS,
    ROLL_TABLES,
    SCHEDULED_EVENTS,
    SFXS,
    SFX_OWNERS,
    TRAITS,
    TRAITSETS,
    TRAITSETSETTINGS,
    TRAITSETTINGS,
    get_db,
)
from transversal.db.repository_mixins.attunement import RepositoryAttunement
from transversal.db.repository_mixins.canvas import RepositoryCanvas
from transversal.db.repository_mixins.common import (  # noqa: F401
    _STRUCTURAL_TYPES_AQL,
    _key,
)
from transversal.db.repository_mixins.core import RepositoryCore
from transversal.db.repository_mixins.entities import RepositoryEntities
from transversal.db.repository_mixins.images import RepositoryImages
from transversal.db.repository_mixins.lifepath import RepositoryLifepath
from transversal.db.repository_mixins.messaging import RepositoryMessaging
from transversal.db.repository_mixins.plans import RepositoryPlans
from transversal.db.repository_mixins.players import RepositoryPlayers
from transversal.db.repository_mixins.projections import RepositoryProjections
from transversal.db.repository_mixins.relationships import RepositoryRelationships
from transversal.db.repository_mixins.scheduled_events import RepositoryScheduledEvents
from transversal.db.repository_mixins.sfx import RepositorySfx
from transversal.db.repository_mixins.trait_settings import RepositoryTraitSettings
from transversal.db.repository_mixins.traits import RepositoryTraits
from transversal.db.repository_mixins.traitset_settings import RepositoryTraitsetSettings


class EntityRepository(
    RepositoryCore,
    RepositoryEntities,
    RepositoryProjections,
    RepositoryAttunement,
    RepositoryTraits,
    RepositoryTraitSettings,
    RepositoryTraitsetSettings,
    RepositorySfx,
    RepositoryScheduledEvents,
    RepositoryLifepath,
    RepositoryRelationships,
    RepositoryPlans,
    RepositoryMessaging,
    RepositoryPlayers,
    RepositoryCanvas,
    RepositoryImages,
):
    """Multi-collection entity repository."""

    def __init__(self, db: "StandardDatabase | None" = None):
        self.db = db or get_db()
        self._entities = self.db.collection(ENTITIES)
        self._projections = self.db.collection(PROJECTIONS)
        self._traits = self.db.collection(TRAITS)
        self._traitsets = self.db.collection(TRAITSETS)
        self._traitsettings = self.db.collection(TRAITSETTINGS)
        self._traitsetsettings = self.db.collection(TRAITSETSETTINGS)
        self._sfxs = self.db.collection(SFXS)
        self._sfx_owners = self.db.collection(SFX_OWNERS)
        self._scheduled_events = self.db.collection(SCHEDULED_EVENTS)
        self._life_paths = self.db.collection(LIFE_PATHS)
        self._roll_tables = self.db.collection(ROLL_TABLES)
        self._relationships = self.db.collection(RELATIONSHIPS)
        self._players = self.db.collection(PLAYERS)
        self._entity_images = self.db.collection(ENTITY_IMAGES)
        self._messages = self.db.collection(MESSAGES)
        self._historical_records = self.db.collection(HISTORICAL_RECORDS)
        self._plan_entities = self.db.collection(PLAN_ENTITIES)
        self._plan_relationships = self.db.collection(PLAN_RELATIONSHIPS)

        # Registry read cache: the traits/traitsets registries are small
        # (hundreds) and read on every trait-setting resolution, so they are
        # memoized per-process as a whole-collection index, invalidated on the
        # repository's own writes and refreshed after a TTL (self-healing
        # against out-of-process writers such as migrations).
        self._traits_index_cache: dict[str, dict] = {}
        self._traits_index_at = 0.0
        self._traitsets_index_cache: dict[str, dict] = {}
        self._traitsets_index_at = 0.0
