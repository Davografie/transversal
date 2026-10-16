"""Views — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator
from typing import Optional
from transversal.domain.entities import (
    Entity,
    Projection,
)
from transversal.domain.enums import (
    ImageType,
)
from transversal.domain.traits import (
    TraitSetting,
)


class CharacterView(BaseModel):
    """Full character assembled from multiple collections."""
    entity: Entity
    projections: list[Projection] = Field(default_factory=list)
    trait_settings: list[TraitSetting] = Field(default_factory=list)

#: Provenance labels an image may carry.
#:
#: **Not render roles.** These describe how an image came to exist, not where it
#: renders, so unlike `roles` they are not unique per owner, assigning one never
#: strips it from sibling images, and resolution ignores them entirely.
#: ``ai`` is set by a human who knows AI was somewhere in the workflow;
#: ``ai_generated`` by the imagen pipeline; ``ai_animated`` by the animate
#: pipeline.
IMAGE_FLAGS = ("ai", "ai_generated", "ai_animated")

#: Derived renders a picture can carry on top of its static ladder.
#:
#: ``cutout`` is a matte (the picture with its background removed) and ``animated``
#: a loop. They belong to the **picture**, not to a second record: the role map
#: (``services/media_utils.ROLE_RENDER``) reads this list to decide what a role
#: serves, which is what makes a cutout keep its credits, its flags and its id by
#: construction. See [[Image Tiers Design Log]].
IMAGE_RENDERS = ("cutout", "animated")

#: Roles a credited party can hold on an image.
#:
#: Named to line up with the established vocabularies so this data can be
#: exported or embedded later without a translation table — ``artist`` is
#: TASL's *Author*, Schema.org's `creator` and IPTC's *Creator*; ``source`` is
#: TASL's *Source* and IPTC's *Source*; ``rights`` is Schema.org's
#: `copyrightHolder`; ``publisher`` is IPTC's *Credit Line*.
CREDIT_ROLES = ("artist", "source", "rights", "publisher")


class ImageCredit(BaseModel):
    """One party credited on an image.

    ``url`` is optional and, when present, is a link the UI renders — so it is
    scheme-checked at the write boundary (http/https only), never trusted.
    """
    role: str = "artist"  # one of CREDIT_ROLES
    name: str = ""        # the person, organisation or site
    url: str = ""         # their page, or the page the image came from


class MediaImage(BaseModel):
    """Metadata for an image stored against an **owner**, per-universe.

    Stored in the `images` collection.
    Files live at media/imagen/{owner_id}/{universe}/{filename}_{variant}.{ext}

    The owner is explicit ([[Trait Images Design Log]]): ``owner_kind`` is
    ``"entity"`` or ``"trait"``, ``owner_id`` is that record's id, and
    ``variant_id`` is the second rung of the ladder — a projection for an
    entity, a traitsetting for a trait. An empty ``variant_id`` is the
    owner-level default, i.e. the *definition* image.

    Role uniqueness is keyed on the owner plus role, where the owner is
    ``variant_id`` when set, else ``owner_id``.
    """
    id: str  # uuid
    owner_kind: str = "entity"  # "entity" | "trait"
    owner_id: str = ""  # entity id (character-…, loc-…) or trait id (trait-…)
    variant_id: Optional[str] = None  # projection id / traitsetting id; empty = definition
    universe: str
    image_type: ImageType
    roles: list[str] = Field(default_factory=list)  # ["background", "sheet", "navdot"]
    #: Provenance labels — see ``IMAGE_FLAGS``. A separate field from ``roles`` on
    #: purpose: roles are unique per (owner, role) and assigning one strips it
    #: from sibling images, so putting ``ai`` in there would make ticking one
    #: image's [AI] silently untag every other image of the same owner. A cutout
    #: inherits its source's flags and adds **nothing** of its own: BiRefNet is not
    #: one of the pipelines that declares AI, and a cutout is the same picture with
    #: its background removed.
    flags: list[str] = Field(default_factory=list)
    #: Derived renders this picture has, on top of its static ladder — a subset of
    #: ``IMAGE_RENDERS``. A cutout is not a second picture but the same one with a
    #: matte, and a loop is the same one with motion, so both are recorded here and
    #: the role map decides which a surface gets. See [[Image Tiers Design Log]].
    renders: list[str] = Field(default_factory=list)
    #: Who made it and where it came from. The structured half of an attribution
    #: — Creative Commons' TASL *Author* and *Source* (and IPTC's Creator /
    #: Credit Line / Source). See [[Media Pipeline]] § Credits.
    credits: list[ImageCredit] = Field(default_factory=list)
    #: TASL's *Licence*: a licence URL, or a short name when there is no page
    #: ("CC BY-SA 4.0", "all rights reserved").
    license: str = ""
    #: The wording to *display*, when the rights holder specifies one verbatim.
    #: Empty means derive a line from ``credits`` + ``license`` — this field
    #: exists because a required attribution line is often not decomposable.
    credit_text: str = ""
    transparent: bool = False  # image has a transparent background (alpha channel)
    prompt: str = ""
    negative_prompt: str = ""
    loras: list[str] = Field(default_factory=list)
    width: int = 0
    height: int = 0
    seed: int = 0
    steps: int = 0
    filename: str = ""  # base filename without variant suffix or extension
    extension: str = "png"
    #: The loop's container, when this picture has an ``animated`` render. A merged
    #: picture is a still (``extension`` = webp) that *also* has a video, and one
    #: field cannot name both. Empty on a row written before the tier migration, and
    #: then the loop shares ``extension``.
    animated_extension: str = ""
    #: Content addresses of this picture's files, keyed by the filename suffix the
    #: blob carries — ``_Large``, ``_Cutout_Large``, ``""`` for the loop. A record
    #: that has them is served from the blob store ([[B88]]); one that does not is
    #: served from the legacy path it was written to, which is what lets the move to
    #: blobs happen without migrating everything at once.
    blobs: dict[str, str] = Field(default_factory=dict)
    created_at: str = ""  # ISO 8601

    # ── Legacy ownership fields (transitional) ───────────────────────────
    # Rows written before the `B200` backfill carry only these. They stay on
    # the model so a write still round-trips them and the older code running
    # against the same database can still read what this version writes; the
    # validator below keeps the two representations in sync. DROPPED IN A
    # LATER COMMIT, once reads have been on the owner fields long enough to
    # trust (see the design log's two-step).
    entity_id: str = ""  # == owner_id when owner_kind == "entity"
    projection_id: Optional[str] = None  # == variant_id for an entity owner

    @model_validator(mode="after")
    def _sync_legacy_owner(self) -> "MediaImage":
        """Keep the owner fields and the legacy pair consistent, either way."""
        if not self.owner_id and self.entity_id:
            self.owner_id = self.entity_id
        if self.variant_id is None and self.projection_id:
            self.variant_id = self.projection_id
        if self.owner_kind == "entity" and self.owner_id:
            self.entity_id = self.owner_id
            self.projection_id = self.variant_id
        return self

