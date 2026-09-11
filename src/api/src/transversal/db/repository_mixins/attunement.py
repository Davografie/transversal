"""Attunement — split out of src/api/src/transversal/db/repository.py."""

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import TRAITSETS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import Attunement
from transversal.domain import AttunementOp
from transversal.domain import AttunementScope
from transversal.domain import Entity
from transversal.domain import EntityType
from transversal.domain import TraitSetting
from transversal.domain import TransversalType
from typing import Optional


class RepositoryAttunement:
    """Mixin contributing 10 member(s) to the repository."""

    def _active_universe(self, entity: Entity) -> str:
        """The entity's active universe — the active projection's current universe.

        Falls back to the legacy ``current_universe`` field when the entity has
        no ``current_projection`` (or its projection is missing).
        """
        if entity.current_projection:
            proj = self.get_projection(entity.current_projection)
            if proj and proj.universe:
                return proj.universe
        return entity.current_universe

    def _active_location(self, entity: Entity) -> Optional[str]:
        """The entity's active location — the active projection's current location.

        Falls back to the denormalized ``current_location`` cache when the entity
        has no active projection (or its projection has no location).
        """
        if entity.current_projection:
            proj = self.get_projection(entity.current_projection)
            if proj and proj.current_location:
                return proj.current_location
        return entity.current_location

    def active_projections(self, entity: Entity) -> list[str]:
        """The entity's currently-active bodies — the projection-native source of truth.

        ``{current_projection}`` plus ``add`` grants minus ``remove`` grants, over
        the entity's own ``self`` grants and any ``domain``-scoped grants it sits
        under. Grant targets resolve **read-time** (see
        [[Active Projections Design Log]]), so "every body of mine from universe U"
        tracks bodies gained while the grant is live. The entity's projections are
        loaded only when a universe-form grant actually needs resolving, so the
        common (grant-free) read stays free.
        """
        active: set[str] = set()
        if entity.current_projection:
            active.add(entity.current_projection)

        grants = [g for g in entity.attunements if g.scope == AttunementScope.SELF]
        grants += self._domain_grants(entity)
        if not grants:
            return sorted(active)

        projection_universes: dict[str, str] | None = None  # lazily loaded

        def resolve(grant: Attunement) -> set[str]:
            nonlocal projection_universes
            if grant.projection_id:
                return {grant.projection_id}
            if not grant.universe:
                return set()
            if projection_universes is None:
                projection_universes = {
                    p.id: p.universe for p in self.get_projections_for_entity(entity.id)
                }
            return {pid for pid, uni in projection_universes.items() if uni == grant.universe}

        for grant in grants:
            if grant.op == AttunementOp.REMOVE:
                active -= resolve(grant)
            else:
                active |= resolve(grant)
        return sorted(active)

    def effective_universes(self, entity: Entity) -> list[str]:
        """The universes governing trait availability — derived from the active bodies.

        A compatibility view over :meth:`active_projections` (a body's universe is
        what the trait-gating queries filter on). ``transversal_type`` is never
        read for availability (see [[Projections and Transversal]]).
        """
        universes = {
            p.universe
            for p in (self.get_projection(pid) for pid in self.active_projections(entity))
            if p is not None and p.universe
        }
        if not entity.current_projection and entity.current_universe:
            # Legacy fallback: entity kinds with no active body at all (locations,
            # universes, factions) still resolve from the denormalized universe.
            # Deliberately *not* applied when a body was suppressed — an emptied
            # active set is a real state, not a missing one.
            universes.add(entity.current_universe)
        return sorted(universes)

    def is_transversal(self, entity: Entity) -> bool:
        """Whether an entity exists in multiple universes (multiversal).

        Occupant types (character/gmc/asset) are transversal when they hold more
        than one NATIVE projection in distinct universes. Factions are
        transversal when they list more than one active universe. Everything else
        (locations, universes, subtraits, relations) is universe-local.
        """
        if entity.type == EntityType.FACTION:
            return len(set(entity.active_universes or [])) > 1
        if entity.type in (EntityType.CHARACTER, EntityType.GMC, EntityType.ASSET):
            native = {
                p.universe for p in self.get_projections_for_entity(entity.id)
                if p.transversal_type == TransversalType.NATIVE and p.universe
            }
            return len(native) > 1
        return False

    def _domain_grants(self, entity: Entity) -> list[Attunement]:
        """Domain-scoped grants carried by entities along this entity's location chain.

        A pull, not a fan-out: each reader collects what covers it, so there is no
        per-fire set of affected entities to maintain (see
        [[Active Projections Design Log]]).
        """
        location = self._active_location(entity)
        if not location:
            return []
        chain = [location] + self.get_location_ancestors(location)
        query = f"""
            FOR e IN {ENTITIES}
            FILTER e.current_location IN @chain AND LENGTH(e.attunements) > 0
            FOR att IN e.attunements
            FILTER att.scope == 'domain'
            RETURN att
        """
        return [
            Attunement.model_validate(doc)
            for doc in self.db.aql.execute(query, bind_vars={"chain": chain})
        ]

    def get_effective_traitsettings_for_projections(
        self, entity_id: str, projection_ids: list[str]
    ) -> list[TraitSetting]:
        """Trait settings live for a set of **active bodies**.

        The direct test the universe-name indirection stood in for: ego traits
        (``from_type='entity'``) are always returned; a morph trait is returned iff
        the projection it is anchored to is in ``projection_ids``. Two bodies in the
        same universe therefore no longer share availability — only the live one
        counts (see [[Active Projections Design Log]]). The registry checks (the
        trait and its set must declare the projection's universe) still apply.
        """
        refs = [f"{PROJECTIONS}/{pid}" for pid in projection_ids]
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            LET is_projection = (ts.from_type == 'projection')
            LET proj = is_projection ? DOCUMENT(ts._from) : null
            LET origin = proj != null
                ? (proj.origin_universe ? proj.origin_universe : SPLIT(proj._key, ":")[1])
                : null
            LET trait = DOCUMENT(ts._to)
            LET set_doc = (trait.traitset_id != null)
                ? DOCUMENT(CONCAT('{TRAITSETS}/', trait.traitset_id)) : null
            FILTER ts.from_type == 'entity'
                OR (
                    is_projection AND proj != null
                    AND ts._from IN @refs
                    AND origin IN trait.universes
                    AND (set_doc == null OR origin IN set_doc.universes)
                )
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query, bind_vars={"eid": entity_id, "refs": refs}
            )
        ]

    def get_effective_traitsettings(
        self, entity_id: str, universes: list[str]
    ) -> list[TraitSetting]:
        """Get trait settings active in a set of universes.

        Ego traits (``from_type='entity'``) are always returned. Projection-anchored
        morph traits are gated by their projection's ``origin_universe`` being in
        ``universes`` (falling back to the projection key's universe suffix for
        pre-migration data).
        """
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            LET is_projection = (ts.from_type == 'projection')
            LET proj = is_projection ? DOCUMENT(ts._from) : null
            LET origin = proj != null
                ? (proj.origin_universe ? proj.origin_universe : SPLIT(proj._key, ":")[1])
                : null
            LET trait = DOCUMENT(ts._to)
            LET set_doc = (trait.traitset_id != null)
                ? DOCUMENT(CONCAT('{TRAITSETS}/', trait.traitset_id)) : null
            FILTER ts.from_type == 'entity'
                OR (
                    is_projection AND proj != null
                    AND origin IN @universes
                    AND origin IN trait.universes
                    AND (set_doc == null OR origin IN set_doc.universes)
                )
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query, bind_vars={"eid": entity_id, "universes": universes}
            )
        ]

    def get_effective_traitsettings_bulk(
        self, entity_ids: list[str], universes: list[str]
    ) -> dict[str, list[TraitSetting]]:
        """Batch variant of :meth:`get_effective_traitsettings` (one AQL query).

        Returns ``{entity_id: [TraitSetting]}`` with an entry for every
        requested id (empty list when the entity has none). Used by global
        boundary fan-outs so they don't pay a per-entity round-trip.
        """
        if not entity_ids:
            return {}
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id IN @eids
            LET is_projection = (ts.from_type == 'projection')
            LET proj = is_projection ? DOCUMENT(ts._from) : null
            LET origin = proj != null
                ? (proj.origin_universe ? proj.origin_universe : SPLIT(proj._key, ":")[1])
                : null
            LET trait = DOCUMENT(ts._to)
            LET set_doc = (trait.traitset_id != null)
                ? DOCUMENT(CONCAT('{TRAITSETS}/', trait.traitset_id)) : null
            FILTER ts.from_type == 'entity'
                OR (
                    is_projection AND proj != null
                    AND origin IN @universes
                    AND origin IN trait.universes
                    AND (set_doc == null OR origin IN set_doc.universes)
                )
            RETURN ts
        """
        grouped: dict[str, list[TraitSetting]] = {eid: [] for eid in entity_ids}
        for doc in self.db.aql.execute(
            query, bind_vars={"eids": list(entity_ids), "universes": universes}
        ):
            ts = TraitSetting.model_validate({**doc, "id": doc["_key"]})
            grouped.setdefault(ts.entity_id, []).append(ts)
        return grouped

    def get_prompt_traitsettings(
        self, entity_id: str, universes: list[str], projection_id: str | None = None
    ) -> list[TraitSetting]:
        """Trait settings used to build a generation prompt.

        Returns ego traits (``from_type='entity'`` — the entity soul) and, when
        ``projection_id`` is given, that projection's morph traits only.
        Projection-anchored traits are excluded for entity-level generation
        (``projection_id=None``).
        """
        query = f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER ts.entity_id == @eid
            LET is_projection = (ts.from_type == 'projection')
            LET proj = is_projection ? DOCUMENT(ts._from) : null
            LET origin = proj != null
                ? (proj.origin_universe ? proj.origin_universe : SPLIT(proj._key, ":")[1])
                : null
            LET trait = DOCUMENT(ts._to)
            LET set_doc = (trait.traitset_id != null)
                ? DOCUMENT(CONCAT('{TRAITSETS}/', trait.traitset_id)) : null
            FILTER ts.from_type == 'entity'
                OR (
                    is_projection AND @projection_id != null AND proj != null
                    AND proj._key == @projection_id
                    AND origin IN @universes
                    AND origin IN trait.universes
                    AND (set_doc == null OR origin IN set_doc.universes)
                )
            RETURN ts
        """
        return [
            TraitSetting.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(
                query,
                bind_vars={"eid": entity_id, "universes": universes, "projection_id": projection_id},
            )
        ]
