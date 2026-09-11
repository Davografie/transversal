"""Views — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
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

class EntityImage(BaseModel):
    """Metadata for a generated image stored per-entity, per-universe.

    Stored in the `entity_images` collection.
    Files live at media/imagen/{entity_id}/{universe}/{image_id}_{variant}.{ext}

    ``projection_id`` ties the image to a specific body (projection). When
    empty the image is entity-level — the soul's default, used as fallback
    for any body that has no body-specific image for a role. Role uniqueness
    is keyed on the owner (projection id when set, else entity id) plus role.
    """
    id: str  # uuid
    entity_id: str
    projection_id: Optional[str] = None  # owning body; empty = entity-level default
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
