"""Messaging — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional
from transversal.api.graphql.type_defs.enums import (
    MessageKind,
)


@strawberry.type
class Message:
    """A persistent message between entities, with resolved relationship info."""
    id: strawberry.ID
    sender_entity_id: strawberry.ID
    recipient_entity_id: strawberry.ID
    kind: MessageKind = MessageKind.LETTER
    title: str = ""
    body: str = ""
    images: list[str] = strawberry.field(default_factory=list)
    created_at: str = ""
    relationship_description: str = ""  # resolved from associate edge at query time
    after_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    threads: list[str] = strawberry.field(default_factory=list)

@strawberry.input
class SendMessageInput:
    """Input for sending a message to another entity."""
    sender_entity_id: strawberry.ID
    recipient_entity_id: strawberry.ID
    kind: MessageKind = MessageKind.LETTER
    title: str = ""
    body: str = ""
    images: list[str] = strawberry.field(default_factory=list)
    after_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    threads: list[str] = strawberry.field(default_factory=list)

@strawberry.input
class JournalEntryInput:
    """Input for adding a personal journal entry (self-referential, GM-visible)."""
    entity_id: strawberry.ID
    title: str = ""
    body: str = ""
    images: list[str] = strawberry.field(default_factory=list)
    after_ids: list[strawberry.ID] = strawberry.field(default_factory=list)
    threads: list[str] = strawberry.field(default_factory=list)

@strawberry.input
class UpdateMessageInput:
    """Input for updating a message's after_ids and/or threads."""
    id: strawberry.ID
    after_ids: Optional[list[strawberry.ID]] = None
    threads: Optional[list[str]] = None

@strawberry.type
class HistoricalRecord:
    """An append-only historical event for an entity."""
    id: strawberry.ID
    entity_id: strawberry.ID
    record_type: str = "roll_table"
    universe: str = ""
    session_id: str = ""
    data: strawberry.scalars.JSON = strawberry.field(default_factory=dict)
    created_at: str = ""
