"""Images — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITIES
from transversal.db.arango import ENTITY_IMAGES
from transversal.domain import EntityImage
from transversal.domain import ImageType


class RepositoryImages:
    """Mixin contributing 12 member(s) to the repository."""

    def create_entity_image(self, image: EntityImage) -> EntityImage:
        doc = image.model_dump()
        doc["_key"] = image.id
        self._entity_images.insert(doc)
        return image

    def get_entity_images(
        self, entity_id: str, universe: str | None = None, image_type: ImageType | None = None
    ) -> list[EntityImage]:
        filters = [("entity_id", entity_id)]
        if universe:
            filters.append(("universe", universe))
        if image_type:
            filters.append(("image_type", image_type.value))

        # Build simple filter query
        parts = [f"doc.{f} == @v{i}" for i, (f, _) in enumerate(filters)]
        binds = {f"v{i}": v for i, (_, v) in enumerate(filters)}
        query = f"""
            FOR doc IN {ENTITY_IMAGES}
            FILTER {' AND '.join(parts)}
            SORT doc.created_at DESC
            RETURN doc
        """
        return [
            EntityImage.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars=binds)
        ]

    def get_entity_image(self, image_id: str) -> EntityImage | None:
        doc = self._entity_images.get(image_id)
        return EntityImage.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def update_entity_image(self, image_id: str, updates: dict) -> EntityImage | None:
        doc = self._entity_images.get(image_id)
        if not doc:
            return None
        self._entity_images.update({**doc, **updates})
        return self.get_entity_image(image_id)

    def delete_entity_image(self, image_id: str) -> bool:
        return self._entity_images.delete(image_id)

    def get_images_for_owner(self, entity_id: str, projection_id: str | None = None) -> list[EntityImage]:
        """Images belonging to an owner: a specific projection, or the entity.

        ``projection_id=None`` returns entity-level images only (those with an
        empty ``projection_id``); a concrete id returns that projection's images.
        """
        images = self.get_entity_images(entity_id)
        return [
            img for img in images
            if (img.projection_id or None) == projection_id
        ]

    def _image_url(self, img: EntityImage, variant: str = "Large") -> str:
        """Public media URL for an image, honoring animated vs static variant."""
        if img.image_type == ImageType.ANIMATED:
            return f"/media/animated/{img.entity_id}/{img.universe}/{img.filename}.{img.extension}"
        return f"/media/imagen/{img.entity_id}/{img.universe}/{img.filename}_{variant}.{img.extension}"

    def resolve_role_image_entry(
        self, entity_id: str, role: str, projection_id: str | None = None
    ) -> EntityImage | None:
        """Resolve the EntityImage carrying ``role`` — same order as
        ``resolve_role_image`` (projection-scoped with entity fallback)."""
        images = self.get_entity_images(entity_id)
        if projection_id:
            for img in images:
                if (img.projection_id or None) == projection_id and role in img.roles:
                    return img
            proj = self.get_projection(projection_id)
            universes: list[str] = []
            if proj is not None:
                if proj.universe:
                    universes.append(proj.universe)
                if proj.origin_universe and proj.origin_universe not in universes:
                    universes.append(proj.origin_universe)
            for u in universes:
                for img in images:
                    if not img.projection_id and role in img.roles and img.universe == u:
                        return img
        for img in images:
            if not img.projection_id and role in img.roles:
                return img
        return None

    def resolve_role_image(
        self, entity_id: str, role: str, projection_id: str | None = None, variant: str = "Large"
    ) -> str | None:
        """Resolve a role image URL, projection-scoped with entity fallback.

        Resolution order:
        1. The projection's own image carrying ``role`` (newest first).
        2. Entity-level image carrying ``role`` whose universe matches the
           projection's current, then origin, universe.
        3. Any entity-level image carrying ``role``.

        With no ``projection_id`` only entity-level images are considered.
        """
        entry = self.resolve_role_image_entry(entity_id, role, projection_id)
        return self._image_url(entry, variant) if entry else None

    def get_navdot_images(
        self, entity_ids: list[str], bodies: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Resolve navdot role image URLs for many entities.

        Resolves through a body first, falling back to entity-level images.
        Returns ``{entity_id: media_url}``. The location navigate endpoint uses
        this for occupants, children, transversal destinations, and the parent.

        ``bodies`` chooses **which** body per entity (``{entity_id: body_id}``),
        defaulting to the entity's active body. A caller listing the entities at a
        *place* must pass the body standing there — a left-behind body would
        otherwise wear the face of the body the consciousness travelled to
        ([[B137]] S1).
        """
        return self._navdot_urls(entity_ids, bodies=bodies)

    def get_navdot_transparency(
        self, entity_ids: list[str], bodies: dict[str, str] | None = None
    ) -> dict[str, bool]:
        """Map entity_id → whether its resolved navdot image is transparent.

        Same resolution order as ``get_navdot_images`` — the body given in
        ``bodies``, else the active one, then entity-level fallback. Entities
        without a navdot image are omitted from the result.
        """
        if not entity_ids:
            return {}
        proj_query = f"""
            FOR e IN {ENTITIES}
            FILTER e._key IN @ids
            RETURN {{ id: e._key, current_projection: e.current_projection }}
        """
        current_proj: dict[str, str | None] = {
            row["id"]: row.get("current_projection")
            for row in self.db.aql.execute(proj_query, bind_vars={"ids": entity_ids})
        }
        for eid, body_id in (bodies or {}).items():
            if body_id:
                current_proj[eid] = body_id
        result: dict[str, bool] = {}
        for eid in entity_ids:
            entry = self.resolve_role_image_entry(eid, "navdot", current_proj.get(eid))
            if entry is not None:
                result[eid] = entry.transparent
        return result

    def get_role_images(self, entity_ids: list[str], role: str, variant: str = "Large") -> dict[str, str]:
        """Resolve one image URL per entity for any role tag, in one batch."""
        return self._role_urls(entity_ids, role, variant)
