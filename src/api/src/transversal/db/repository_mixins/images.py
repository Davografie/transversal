"""Images — split out of src/api/src/transversal/db/repository.py.

An image is owned by an **entity** or a **trait** (`owner_kind` + `owner_id`),
and may belong to one rung below it: a projection for an entity, a traitsetting
for a trait (`variant_id`; empty means the owner-level *definition* image). The
id spaces are type-prefixed (`character-…`, `loc-…`, `trait-…`) so resolution
does not need the kind — see [[Trait Images Design Log]].
"""

from __future__ import annotations

from typing import Callable

from transversal.db.arango import ENTITIES
from transversal.db.arango import IMAGES
from transversal.domain import MediaImage
from transversal.domain import ImageType


def pick_role_image(
    images: list[MediaImage],
    role: str,
    variant_id: str | None = None,
    universes: Callable[[], list[str]] | None = None,
) -> MediaImage | None:
    """The image carrying ``role``, from an already-loaded list — the ladder.

    1. the **variant's** own image carrying ``role`` (newest first) — a
       projection's for an entity, a traitsetting's for a trait;
    2. an owner-level image in one of ``universes``;
    3. any owner-level image carrying ``role``.

    The list is a parameter so a caller that already holds the images can use the
    ladder without re-reading them: the sheet's trait rows come from the
    per-request loader, which fetches every row's owner in one query. That is why
    the ladder is a function rather than a loop inside
    :meth:`RepositoryImages.resolve_role_image_entry` — one ladder, two ways to
    supply the list.

    ``universes`` is a **callable** because step 2 needs a projection lookup, and
    skipping it when step 1 already matched is the whole reason the original code
    tried the variant first. A trait's variant is a traitsetting rather than a
    projection, so its lookup answers empty and one picture serves every universe.
    """
    if variant_id:
        for img in images:
            if (img.variant_id or None) == variant_id and role in img.roles:
                return img
    for u in (universes() if universes else []):
        for img in images:
            if not img.variant_id and role in img.roles and img.universe == u:
                return img
    for img in images:
        if not img.variant_id and role in img.roles:
            return img
    return None


class RepositoryImages:
    """Mixin contributing 12 member(s) to the repository."""

    def create_image(self, image: MediaImage) -> MediaImage:
        doc = image.model_dump()
        doc["_key"] = image.id
        self._images.insert(doc)
        return image

    def get_images(
        self, owner_id: str, universe: str | None = None, image_type: ImageType | None = None
    ) -> list[MediaImage]:
        """Every image owned by ``owner_id`` — an entity or a trait, newest first."""
        filters = [("owner_id", owner_id)]
        if universe:
            filters.append(("universe", universe))
        if image_type:
            filters.append(("image_type", image_type.value))

        # Build simple filter query
        parts = [f"doc.{f} == @v{i}" for i, (f, _) in enumerate(filters)]
        binds = {f"v{i}": v for i, (_, v) in enumerate(filters)}
        query = f"""
            FOR doc IN {IMAGES}
            FILTER {' AND '.join(parts)}
            SORT doc.created_at DESC
            RETURN doc
        """
        return [
            MediaImage.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars=binds)
        ]

    def get_images_for_owners(self, owner_ids: list[str]) -> dict[str, list[MediaImage]]:
        """Every image for each of ``owner_ids``, newest first — **one** query.

        The batched twin of :meth:`get_images`, for the sheet's hot path: a trait
        row asks for a picture per trait-setting, and one round trip per owner
        measured ~2.7ms each on a 22-trait sheet — ~60ms on a page that otherwise
        loads in ~10ms. Same shape and ordering as the single-owner read, so a
        caller may use either; see ``api/graphql/loaders.py``.
        """
        ids = [i for i in dict.fromkeys(owner_ids) if i]
        if not ids:
            return {}
        grouped: dict[str, list[MediaImage]] = {}
        query = f"""
            FOR doc IN {IMAGES}
            FILTER doc.owner_id IN @ids
            SORT doc.created_at DESC
            RETURN doc
        """
        for doc in self.db.aql.execute(query, bind_vars={"ids": ids}):
            img = MediaImage.model_validate({**doc, "id": doc["_key"]})
            grouped.setdefault(img.owner_id, []).append(img)
        return grouped

    def get_image(self, image_id: str) -> MediaImage | None:
        doc = self._images.get(image_id)
        return MediaImage.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def update_image(self, image_id: str, updates: dict) -> MediaImage | None:
        """Patch a row, normalising through the model.

        The merge is validated back through ``MediaImage`` on purpose: the owner
        fields and the legacy ``entity_id``/``projection_id`` pair are two
        representations of one fact, and a raw dict merge is how they would drift
        apart — a caller updating ``projection_id`` alone would leave
        ``variant_id`` (which resolution actually reads) stale.
        """
        doc = self._images.get(image_id)
        if not doc:
            return None
        merged = {**doc, **updates}
        normalised = MediaImage.model_validate({**merged, "id": doc["_key"]}).model_dump()
        self._images.update({**merged, **normalised})
        return self.get_image(image_id)

    def delete_image(self, image_id: str) -> bool:
        return self._images.delete(image_id)

    def get_images_for_owner(self, owner_id: str, variant_id: str | None = None) -> list[MediaImage]:
        """Images on one rung of the ladder: a variant, or the owner's default.

        ``variant_id=None`` returns the **definition**-level images only (those
        with an empty ``variant_id``); a concrete id returns that variant's
        images — a projection's, or a traitsetting's.
        """
        images = self.get_images(owner_id)
        return [
            img for img in images
            if (img.variant_id or None) == variant_id
        ]

    def _image_url(self, img: MediaImage, variant: str = "Large") -> str:
        """Public media URL for an image, honoring animated vs static variant."""
        if img.image_type == ImageType.ANIMATED:
            return f"/media/animated/{img.owner_id}/{img.universe}/{img.filename}.{img.extension}"
        return f"/media/imagen/{img.owner_id}/{img.universe}/{img.filename}_{variant}.{img.extension}"

    def resolve_role_image_entry(
        self, owner_id: str, role: str, variant_id: str | None = None
    ) -> MediaImage | None:
        """Resolve the MediaImage carrying ``role`` for an owner.

        One ladder for both owner kinds:

        1. the **variant's** own image carrying ``role`` (newest first) — a
           projection's for an entity, a traitsetting's for a trait;
        2. the owner-level image carrying ``role`` whose ``universe`` matches the
           variant's current, then origin, universe;
        3. any owner-level image carrying ``role``.

        Rung 2 needs a projection to supply a universe, so it is simply skipped
        for a trait — which is what lets one canonical trait image serve every
        universe the trait belongs to. With no ``variant_id`` only owner-level
        images are considered, exactly as before.
        """
        return pick_role_image(
            self.get_images(owner_id), role, variant_id,
            lambda: self._variant_universes(variant_id),
        )

    def _variant_universes(self, variant_id: str | None) -> list[str]:
        """The universes rung 2 prefers: a body's own, then its origin.

        A **callable**'s worth of work, because it costs a projection read and
        rung 2 is only reached when the variant itself carries no such image.
        Empty for anything that is not a projection — a traitsetting — which is
        what makes a trait's one picture answer for every universe.
        """
        if not variant_id:
            return []
        proj = self.get_projection(variant_id)
        if proj is None:
            return []
        universes: list[str] = []
        if proj.universe:
            universes.append(proj.universe)
        if proj.origin_universe and proj.origin_universe not in universes:
            universes.append(proj.origin_universe)
        return universes

    def role_image_url(self, img: MediaImage | None, variant: str = "Large") -> str | None:
        """Public media URL for a resolved image — the one place its shape lives."""
        return self._image_url(img, variant) if img else None

    def resolve_role_image(
        self, owner_id: str, role: str, variant_id: str | None = None, variant: str = "Large"
    ) -> str | None:
        """Resolve a role image URL — see ``resolve_role_image_entry`` for order."""
        return self.role_image_url(self.resolve_role_image_entry(owner_id, role, variant_id), variant)

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
