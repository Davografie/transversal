"""Plan service — promote staged drafts into real entities and relationships.

Plans live in the *same* ArangoDB as live data, in separate staging collections
(``plan_entities``, ``plan_relationships``). A draft may reference either another
draft or a real entity, so a plan can be pre-wired to the live world before it is
applied. Nothing is written to the live ``entities``/``relationships`` collections
until ``promote`` runs.

Reference convention (used by the REST/MCP layer, stored as ArangoDB handles):
  - ``draft:<ref>`` → a draft entity in this plan (its key is ``{plan_id}:<ref>``)
  - ``entity:<id>`` → a real entity id
  - a bare id     → treated as a real entity id (passthrough)
"""

from __future__ import annotations

from transversal.db.repository import EntityRepository
from transversal.domain import EntityType
from transversal.services.entity_manager import EntityManager


class PlanService:
    def __init__(self, repository: EntityRepository | None = None,
                 entity_manager: EntityManager | None = None):
        self.repo = repository or EntityRepository()
        self.em = entity_manager or EntityManager(repository=self.repo)

    def read(self, plan_id: str) -> dict:
        """Return the staged entities and relationships for a plan."""
        return {
            "plan_id": plan_id,
            "entities": self.repo.list_plan_entities(plan_id),
            "relationships": self.repo.list_plan_relationships(plan_id),
        }

    def discard(self, plan_id: str) -> dict:
        """Delete all staged docs for a plan (no live data is touched)."""
        n_entities = self.repo.delete_plan_entities(plan_id)
        n_relationships = self.repo.delete_plan_relationships(plan_id)
        return {
            "plan_id": plan_id,
            "deleted_entities": n_entities,
            "deleted_relationships": n_relationships,
        }

    def promote(self, plan_id: str) -> dict:
        """Create live entities/relationships from a staged plan.

        Returns the draft-key → real-id mapping so callers can see what was
        created. Fresh ids are generated at promotion time, so there is no
        possibility of colliding with existing live keys.
        """
        entities = self.repo.list_plan_entities(plan_id)
        relationships = self.repo.list_plan_relationships(plan_id)

        # Pass 1 — create the real entities, record draft key → real id.
        key_to_id: dict[str, str] = {}
        for e in entities:
            entity = self.em.create(
                name=e["name"],
                entity_type=EntityType(e["type"]),
                universe=e.get("universe", ""),
                location=None,  # resolved in pass 2
                razmerit=e.get("razmerit", 0),
            )
            key_to_id[e["_key"]] = entity.id

        # Pass 2 — resolve cross-references (location, owned_by) and update.
        for e in entities:
            real_id = key_to_id[e["_key"]]
            updates: dict = {}
            if e.get("location"):
                updates["current_location"] = self._resolve_ref(e["location"], plan_id, key_to_id)
            if e.get("owned_by"):
                updates["owned_by"] = self._resolve_ref(e["owned_by"], plan_id, key_to_id)
            # Promoted entities start unpublished (GM-only) until revealed.
            updates["unpublished"] = bool(e.get("unpublished", True))
            if updates:
                self._apply_updates(real_id, updates)

        # Pass 3 — create the real relationships with resolved endpoints.
        for r in relationships:
            from_id = self._resolve_handle(r.get("_from", ""), key_to_id)
            to_id = self._resolve_handle(r.get("_to", ""), key_to_id)
            if from_id and to_id:
                self.repo.create_relationship(
                    from_id, to_id,
                    r.get("type", "associate"),
                    description=r.get("description", ""),
                )

        return {"plan_id": plan_id, "created": key_to_id}

    # ── Reference resolution ──────────────────────────

    def _resolve_ref(self, ref: str, plan_id: str, key_to_id: dict) -> str | None:
        """Resolve a location/owned_by reference to a real entity id (or None)."""
        if not ref:
            return None
        if ref.startswith("draft:"):
            return key_to_id.get(f"{plan_id}:{ref[len('draft:'):]}")
        if ref.startswith("entity:"):
            return ref[len("entity:"):]
        return ref  # bare id → passthrough

    def _resolve_handle(self, handle: str, key_to_id: dict) -> str:
        """Resolve an ArangoDB handle (``plan_entities/x`` or ``entities/x``) to a real id."""
        if not handle or "/" not in handle:
            return handle
        collection, key = handle.split("/", 1)
        if collection == "plan_entities":
            return key_to_id.get(key, "")
        return key  # real entity id

    def _apply_updates(self, real_id: str, updates: dict) -> None:
        entity = self.repo.get_entity(real_id)
        if entity is None:
            return
        for field, value in updates.items():
            setattr(entity, field, value)
        self.repo.update_entity(entity)
