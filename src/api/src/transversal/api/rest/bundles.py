"""Content bundles — plan and export authored elements as a file ([[B301]]).

Two endpoints, in the two phases the design asks for: ``plan`` says what a bundle
*would* contain and what it would leave out, and ``export`` writes it. Nothing here
writes to the database — a bundle is a **read** of documents that already exist,
which is why it needs no staging collection and no schema.

Both are owner-gated. A bundle reaches the whole authored surface of the campaign
(registry traits and sets, SFX, life paths, roll tables, entities), which is GM
material rather than player material.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from transversal.api.auth import require_owner
from transversal.services.content_bundle import (
    BUNDLE_FORMAT,
    ELEMENT_KINDS,
    ContentBundleService,
)

router = APIRouter(prefix="/api/v1/bundles", tags=["bundles"])

#: ``depth=0`` walks the closure to a fixpoint; anything above counts frontier
#: rounds, and is only bounded so a caller cannot ask for a million of them.
_MAX_DEPTH = 20


class BundleElement(BaseModel):
    kind: str
    id: str


class BundleRequest(BaseModel):
    selection: list[BundleElement] = Field(default_factory=list)
    depth: int = 1


def _service() -> ContentBundleService:
    return ContentBundleService()


def _check(req: BundleRequest) -> list[dict]:
    """Validate the selection and return it in the service's shape.

    An unknown kind is an **error**, not an empty answer: a bundle that silently
    exports nothing is indistinguishable from a bundle of nothing, and the caller
    has no way to tell which it got.
    """
    if req.depth < 0 or req.depth > _MAX_DEPTH:
        raise HTTPException(
            status_code=400, detail=f"depth must be between 0 and {_MAX_DEPTH}"
        )
    selectable = {k.key: k for k in ELEMENT_KINDS if k.selectable}
    selection: list[dict] = []
    for item in req.selection:
        kind = (item.kind or "").strip()
        if kind not in selectable:
            raise HTTPException(
                status_code=400,
                detail=f"unknown kind '{kind}'; expected one of "
                + ", ".join(sorted(selectable)),
            )
        if not (item.id or "").strip():
            raise HTTPException(status_code=400, detail=f"'{kind}' needs an id")
        selection.append({"kind": kind, "id": item.id.strip()})
    if not selection:
        raise HTTPException(status_code=400, detail="selection is empty")
    return selection


@router.get("/kinds")
async def bundle_kinds(request: Request) -> dict:
    """The vocabulary: what a bundle can be asked for.

    Served rather than documented twice, so a picker cannot drift from the map the
    exporter walks.
    """
    await require_owner(request)
    return {
        "format": BUNDLE_FORMAT,
        "kinds": [
            {"kind": k.key, "collection": k.collection, "labelField": k.label_field}
            for k in ELEMENT_KINDS
            if k.selectable
        ],
        # Anchored kinds are never asked for by id — they arrive with their owner,
        # and they are not optional. Named here so a reader of the export knows what
        # it will find inside one element.
        "anchored": [
            {"kind": k.key, "collection": k.collection}
            for k in ELEMENT_KINDS
            if k.anchored
        ],
    }


@router.post("/plan")
async def plan_bundle(request: Request, req: BundleRequest) -> dict:
    """What this selection would carry, and what it would leave behind.

    Read-only. The answer is meant to be read before exporting: ``required`` lists
    the references that leave the selection (with the exact document path that named
    each), ``invited`` the relationships whose far endpoint is outside, and
    ``incidental`` the placement and play state that will not travel.
    """
    await require_owner(request)
    return _service().plan(_check(req), depth=req.depth)


@router.post("/export")
async def export_bundle(request: Request, req: BundleRequest) -> Response:
    """Write the bundle and hand it back as a file.

    ``selection`` is the **final** set — the caller widens it from the plan's
    ``required``/``invited`` lists and posts again. The report is embedded in the
    file, so an importer can refuse a bundle that expects something it does not
    carry instead of discovering it at the table.
    """
    await require_owner(request)
    bundle = _service().emit(_check(req), depth=req.depth)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"transversal-bundle-{stamp}.json"
    return Response(
        content=ContentBundleService.to_json(bundle),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
