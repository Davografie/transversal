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
