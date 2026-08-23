"""REST endpoints for staged content-authoring plans.

Plans live in the same database as live data, in the ``plan_entities`` /
``plan_relationships`` staging collections. Drafting writes only to staging;
``apply`` promotes a plan into the live ``entities`` / ``relationships``
collections (fresh ids, no key collisions). ``discard`` deletes staging only.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from transversal.services.plan_service import PlanService

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


def _service() -> PlanService:
    return PlanService()


class PlanEntityRequest(BaseModel):
    draft_ref: str
    name: str
    type: str  # universe | faction | location | gmc | asset | character
    universe: str
    location: str | None = None  # "entity:<id>" | "draft:<ref>" | bare id
    owned_by: str | None = None  # "entity:<id>" | "draft:<ref>" | bare id
    razmerit: int = 0
    unpublished: bool = True  # GM-only until revealed (default for drafted content)


class PlanRelationshipRequest(BaseModel):
    from_ref: str  # "draft:<ref>" | "entity:<id>" | bare id
    to_ref: str
    type: str = "associate"
    description: str = ""


def _handle(ref: str, plan_id: str) -> str:
    """Convert a reference string to an ArangoDB document handle."""
    if ref.startswith("draft:"):
        return f"plan_entities/{plan_id}:{ref[len('draft:'):]}"
    if ref.startswith("entity:"):
        return f"entities/{ref[len('entity:'):]}"
    return f"entities/{ref}"


@router.post("/{plan_id}/entities")
async def draft_entity(plan_id: str, req: PlanEntityRequest):
    """Stage a draft entity (upserts by draft_ref)."""
    svc = _service()
    key = f"{plan_id}:{req.draft_ref}"
    doc = {
        "_key": key,
        "plan_id": plan_id,
        "draft_ref": req.draft_ref,
        "name": req.name,
        "type": req.type,
        "universe": req.universe,
        "location": req.location,
        "owned_by": req.owned_by,
        "razmerit": req.razmerit,
        "unpublished": req.unpublished,
    }
    # Upsert by stable key so re-drafting a ref never creates a duplicate key.
    if svc.repo.get_plan_entity(key) is not None:
        svc.repo._plan_entities.delete(key)
    svc.repo.create_plan_entity(doc)
    return {"drafted": key, **doc}


@router.post("/{plan_id}/relationships")
async def draft_relationship(plan_id: str, req: PlanRelationshipRequest):
    """Stage a draft relationship edge (bridges may point at real entities)."""
    svc = _service()
    doc = {
        "_from": _handle(req.from_ref, plan_id),
        "_to": _handle(req.to_ref, plan_id),
        "plan_id": plan_id,
        "type": req.type,
        "description": req.description,
    }
    created = svc.repo.create_plan_relationship(doc)
    return {"created": created["_key"], **{k: v for k, v in doc.items() if k != "_key"}}


@router.get("/{plan_id}")
async def read_plan(plan_id: str):
    return _service().read(plan_id)


@router.post("/{plan_id}/apply")
async def apply_plan(plan_id: str):
    """Promote the staged plan into live entities/relationships."""
    svc = _service()
    plan = svc.read(plan_id)
    if not plan["entities"] and not plan["relationships"]:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found or empty")
    return svc.promote(plan_id)


@router.delete("/{plan_id}")
async def discard_plan(plan_id: str):
    return _service().discard(plan_id)
