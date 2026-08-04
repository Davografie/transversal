"""Domain validation — schema enforcement."""

from transversal.domain import DieType, Entity, RatingType


VALID_DIE_TYPES = {dt.value for dt in DieType}
VALID_RATING_TYPES = {rt.value for rt in RatingType}


class ValidationError(Exception):
    pass


def validate_entity(entity: Entity) -> None:
    """Validate entity metadata."""
    if entity.razmerit < 0:
        raise ValidationError("Razmerit cannot be negative")
