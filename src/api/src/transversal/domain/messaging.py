"""Messaging — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from transversal.domain.enums import (
    HistoricalRecordType,
    MessageKind,
)


class Message(BaseModel):
    """Persistent message between entities.

    Stored in the `messages` collection.
    Relationship descriptions are resolved at query time from
    the ``associate`` edge in ``relationships``.

    Kinds:
      letter   — entity → entity, visible to recipient + GM
      journal  — entity → GM only (private musings)
      report   — entity → GMC, visible to GM
      gm_note  — GM → entity (NPC correspondence, GM nudges)
    """
    id: str
    sender_entity_id: str
    recipient_entity_id: str
    kind: MessageKind = MessageKind.LETTER
    title: str = ""
    body: str = ""
    images: list[str] = Field(default_factory=list)  # media paths
    after_ids: list[str] = Field(default_factory=list)
    threads: list[str] = Field(default_factory=list)
    created_at: str = ""  # ISO 8601, populated by repository on insert

class HistoricalRecord(BaseModel):
    """An append-only historical event for an entity.

    Stored in the `historical_records` collection. ``record_type``
    discriminates the shape of ``data``; future event kinds (contests,
    location traversals) reuse the same collection.
    """
    id: str = ""
    entity_id: str = ""
    record_type: HistoricalRecordType = HistoricalRecordType.ROLL_TABLE
    universe: str = ""
    session_id: str = ""
    data: dict = Field(default_factory=dict)  # type-specific payload
    created_at: str = ""  # ISO 8601, populated by repository on insert
