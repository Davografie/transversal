"""Images — split out of src/api/src/transversal/db/repository.py.

An image is owned by an **entity** or a **trait** (`owner_kind` + `owner_id`),
and may belong to one rung below it: a projection for an entity, a traitsetting
for a trait (`variant_id`; empty means the owner-level *definition* image). The
id spaces are type-prefixed (`character-…`, `loc-…`, `trait-…`) so resolution
does not need the kind — see [[Trait Images Design Log]].
"""

from __future__ import annotations

import logging
from typing import Callable

from transversal.db.arango import ENTITIES
from transversal.db.arango import IMAGES
from transversal.domain import MediaImage
from transversal.domain import ImageType
from transversal.services import blobs
from transversal.services.media_utils import render_for

logger = logging.getLogger("transversal.media")


def pick_role_image(
    images: list[MediaImage],
    role: str,
    variant_id: str | None = None,
    universes: Callable[[], list[str]] | None = None,
    picked_id: str = "",
) -> MediaImage | None:
    """The image carrying ``role``, from an already-loaded list — the ladder.

    1. the **picked** owner-level picture ([[B288]]) — the one this instance chose
       among its owner's own, which answers **every** role (see below);
    2. the **variant's** own image carrying ``role`` (newest first) — a
       projection's for an entity, a traitsetting's for a trait;
    3. an owner-level image in one of ``universes``;
    4. any owner-level image carrying ``role``.

    The list is a parameter so a caller that already holds the images can use the
    ladder without re-reading them: the sheet's trait rows come from the
    per-request loader, which fetches every row's owner in one query. That is why
    the ladder is a function rather than a loop inside
    :meth:`RepositoryImages.resolve_role_image_entry` — one ladder, two ways to
    supply the list.

    ``universes`` is a **callable** because step 3 needs a projection lookup, and
    skipping it when an earlier step already matched is the whole reason the
    original code tried the variant first. A trait's variant is a traitsetting
    rather than a projection, so its lookup answers empty and one picture serves
    every universe.

    ``picked_id`` is a **pointer** at one of the owner's pictures, and it comes
    **first**, ahead of the instance's own rung: it is the instance's *chosen*
    picture, so a pick that an old picture could outrank would look like it did
    nothing — which is exactly what the copies [[B215]] used to write would do to
    every instance that still holds one. The pick is visible in the editor and one
    click to clear, so nothing is hidden: clear it and the instance's own pictures
    (then the definition) take over again.

    **The pick answers every role, not just the ones its picture carries** — and
    that is not a shortcut. Roles are unique per rung: ``set_image_roles`` strips a
    role from its siblings, so at the owner level exactly *one* picture holds
    `sheet`, and a pick that only answered the roles it carries could only ever
    name that same picture — it would be a provable no-op. Answering every role is
    also exactly what the copy it replaces did: on an empty instance rung the
    sole-image rule gave the copy all three. Which *render* and tier each role
    serves still comes from ``ROLE_RENDER``, so a picked picture with a matte
    floats and one without does not.

    An id that names nothing — a picture since deleted, or a variant-owned one — is
    ignored rather than fatal, which is what keeps a stale pointer from blanking a
    surface.
    """
    # The instance's picked picture ([[B288]]) — a pointer at one of the owner's
    # own, and the instance's **chosen** picture, so it comes before the rung the
    # instance owns. Restricted to owner-level pictures so a pointer can never drag
    # in another instance's rung.
    if picked_id:
        for img in images:
            if img.id == picked_id and not img.variant_id:
                return img
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
        self._retain_image_blobs(image)
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

    def set_image_roles(self, image_id: str, roles: list[str]) -> MediaImage | None:
        """Set a picture's roles, keeping each role unique per (owner, rung).

        Assigning a role **strips it from the sibling pictures** on the same rung,
        so a role names exactly one picture at a time. The PATCH route used to
        spell this out inline — and `copy_media` therefore bypassed it, leaving two
        pictures claiming `sheet`. One implementation, one invariant.
        """
        img = self.get_image(image_id)
        if img is None:
            return None
        added = set(roles) - set(img.roles or [])
        if added:
            for sibling in self.get_images_for_owner(img.owner_id, img.variant_id):
                if sibling.id == image_id:
                    continue
                kept = [r for r in (sibling.roles or []) if r not in added]
                if kept != sibling.roles:
                    self.update_image(sibling.id, {"roles": kept})
        return self.update_image(image_id, {"roles": list(roles)})

    def delete_image(self, image_id: str) -> bool:
        img = self.get_image(image_id)
        if img is not None:
            self._release_image_blobs(img)
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

    def _blob_ext(self, img: MediaImage, suffix: str) -> str:
        """The container a blob uses: a matte is WebP whatever the still is, a loop
        keeps its own, a tier is the still's."""
        if suffix == "":
            return img.animated_extension or img.extension
        if suffix.startswith("_Cutout_"):
            return "webp"
        return img.extension

    def _image_blobs(self, img: MediaImage) -> list[tuple[str, str, str]]:
        """``(digest, suffix, ext)`` for every blob this record points at."""
        return [
            (digest, suffix, self._blob_ext(img, suffix))
            for suffix, digest in (img.blobs or {}).items()
            if digest
        ]

    def _retain_image_blobs(self, img: MediaImage) -> None:
        """Count this record's claim on its blobs, in the registry.

        Best-effort but **loud**: the count is derived state, so a lost increment keeps
        a file past its last user, while the dangerous direction — deleting a file that
        is still referenced — is prevented separately, by ``blobs.release`` refusing to
        delete a blob that has no counter.
        """
        for digest, _suffix, ext in self._image_blobs(img):
            try:
                blobs.retain(digest, ext=ext)
            except Exception:
                logger.exception(
                    "[media] could not count blob %s for image %s; its file will be "
                    "kept rather than removed",
                    digest,
                    img.id,
                )

    def _release_image_blobs(self, img: MediaImage) -> None:
        for digest, suffix, ext in self._image_blobs(img):
            try:
                blobs.release(digest, suffix=suffix, ext=ext)
            except Exception:
                logger.exception(
                    "[media] could not release blob %s for image %s", digest, img.id
                )

    def image_url(self, img: MediaImage, render: str = "static", tier: str = "Large") -> str:
        """Public media URL for one render of a picture — the one place its shape lives.

        ``render`` is ``static`` (a tier of the image itself), ``cutout`` (a tier of
        the matte) or ``animated`` (the loop). A matte is always WebP whatever the
        still's extension is; a loop keeps its own container, which a merged picture
        records separately because ``extension`` names the still.

        **Content-addressed first, legacy path second** (B88): a record that carries a
        digest is served from the blob store, which is what makes identical pictures
        one file and lets a fork share its ancestor's media. A record with no digest —
        everything written before the blob store, until it is migrated — is served
        exactly as it always was, so adoption needs no migration and no downtime.
        """
        if render == "animated":
            suffix, ext = "", (img.animated_extension or img.extension)
        elif render == "cutout":
            suffix, ext = f"_Cutout_{tier}", "webp"
        else:
            suffix, ext = f"_{tier}", img.extension

        digest = (img.blobs or {}).get(suffix)
        if digest:
            return blobs.url_for(digest, suffix=suffix, ext=ext)

        if render == "animated":
            return f"/media/animated/{img.owner_id}/{img.universe}/{img.filename}.{ext}"
        if render == "cutout":
            return f"/media/imagen/{img.owner_id}/{img.universe}/{img.filename}_Cutout_{tier}.webp"
        return f"/media/imagen/{img.owner_id}/{img.universe}/{img.filename}_{tier}.{img.extension}"

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

    def role_image_url(self, img: MediaImage | None, role: str) -> str | None:
        """Public media URL for a resolved image, at the render that ``role`` serves.

        The render (the matte, the loop, or the plain image) and the tier both come
        from ``ROLE_RENDER`` and the record's own ``renders``, so **no caller names a
        tier** — a role cannot mean a different file on one surface than another, and
        a picture that has a matte serves it without anyone re-tagging a second
        record.
        """
        if img is None:
            return None
        render, tier = render_for(role, img.renders)
        return self.image_url(img, render, tier)

    def resolve_role_image(
        self, owner_id: str, role: str, variant_id: str | None = None
    ) -> str | None:
        """Resolve a role image URL — see ``resolve_role_image_entry`` for order."""
        return self.role_image_url(self.resolve_role_image_entry(owner_id, role, variant_id), role)

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

    def get_role_images(self, entity_ids: list[str], role: str) -> dict[str, str]:
        """Resolve one image URL per entity for any role tag, in one batch."""
        return self._role_urls(entity_ids, role)
