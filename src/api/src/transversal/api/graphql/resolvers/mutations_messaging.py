"""Mutations messaging — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import CreateRelationshipInput
from transversal.api.graphql.types import DeleteRelationshipInput
from transversal.api.graphql.types import DieType as GqlDieType
from transversal.api.graphql.types import JournalEntryInput
from transversal.api.graphql.types import Message
from transversal.api.graphql.types import Relationship
from transversal.api.graphql.types import SendMessageInput
from transversal.api.graphql.types import TraitSetting
from transversal.api.graphql.types import UpdateHistoricalRecordInput
from transversal.api.graphql.types import UpdateMessageInput
from transversal.domain import TraitSetting as DomainTraitSetting
from transversal.domain import is_structural_relationship_type
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _em,
    _message_to_gql,
    _resolve_relationship_endpoint,
    _ts_to_gql,
)


@strawberry.type
class MutationsMessaging:
    """Mixin contributing 6 field(s) to the root type."""

    @strawberry.mutation
    def send_message(self, info: strawberry.Info, input: SendMessageInput) -> Message:
        """Send a persistent message from one entity to another.

        Publishes a ``message_received`` SSE event to all active sessions.
        """
        from transversal.api.sse.bus import StreamEvent, event_bus
        from transversal.services.session_manager import session_manager

        repo = _em(info).repo
        msg = repo.send_message(
            str(input.sender_entity_id),
            str(input.recipient_entity_id),
            body=input.body,
            kind=input.kind.value if input.kind else "letter",
            title=input.title,
            images=list(input.images or []),
            after_ids=[str(a) for a in (input.after_ids or [])],
            threads=list(input.threads or []),
        )

        gql_msg = _message_to_gql(msg, repo)
        for s in session_manager.list_active():
            event_bus.publish(StreamEvent(
                event="message_received",
                session_id=s.id,
                data={
                    "id": msg.id,
                    "sender_entity_id": msg.sender_entity_id,
                    "recipient_entity_id": msg.recipient_entity_id,
                    "kind": msg.kind.value if hasattr(msg.kind, 'value') else msg.kind,
                    "title": msg.title,
                    "body": msg.body,
                    "images": msg.images,
                    "after_ids": msg.after_ids,
                    "threads": msg.threads,
                    "created_at": msg.created_at,
                    "relationship_description": gql_msg.relationship_description,
                },
            ))

        return gql_msg

    @strawberry.mutation
    def add_journal_entry(self, info: strawberry.Info, input: JournalEntryInput) -> Message:
        """Add a personal journal entry for an entity.

        Journal entries are self-referential (character writes to themself)
        and visible to the GM. No recipient parameter needed.
        """
        from transversal.api.sse.bus import StreamEvent, event_bus
        from transversal.services.session_manager import session_manager

        repo = _em(info).repo
        msg = repo.send_message(
            str(input.entity_id),
            str(input.entity_id),
            body=input.body,
            kind="journal",
            title=input.title,
            images=list(input.images or []),
            after_ids=[str(a) for a in (input.after_ids or [])],
            threads=list(input.threads or []),
        )

        gql_msg = _message_to_gql(msg, repo)
        for s in session_manager.list_active():
            event_bus.publish(StreamEvent(
                event="message_received",
                session_id=s.id,
                data={
                    "id": msg.id,
                    "sender_entity_id": msg.sender_entity_id,
                    "recipient_entity_id": msg.recipient_entity_id,
                    "kind": "journal",
                    "title": msg.title,
                    "body": msg.body,
                    "images": msg.images,
                    "after_ids": msg.after_ids,
                    "threads": msg.threads,
                    "created_at": msg.created_at,
                    "relationship_description": "",
                },
            ))

        return gql_msg

    @strawberry.mutation
    def update_message(self, info: strawberry.Info, input: UpdateMessageInput) -> bool:
        """Update after_ids and/or threads on an existing message."""
        repo = _em(info).repo
        return repo.update_message(
            str(input.id),
            after_ids=[str(a) for a in input.after_ids] if input.after_ids is not None else None,
            threads=input.threads,
        )

    @strawberry.mutation
    def update_historical_record(
        self, info: strawberry.Info, input: UpdateHistoricalRecordInput
    ) -> bool:
        """Set a historical record's Blue Book chain position.

        Records are append-only; ``after_ids`` is the single writable field, so
        the Blue Book can order a location relative to its neighbours.
        """
        repo = _em(info).repo
        return repo.update_historical_record(
            str(input.id),
            after_ids=[str(a) for a in input.after_ids] if input.after_ids is not None else None,
        )

    @strawberry.mutation
    def create_relationship(self, info: strawberry.Info, input: CreateRelationshipInput) -> Relationship:
        """Create (or update) a directional relationship edge between two entities.

        Personal types (anything non-structural, i.e. ``relation``) resolve each
        endpoint to the entity (elevated + multiversal) or its active projection
        (default). Structural types (super/transversal/membership/…) stay
        entity→entity.
        Returns the real ArangoDB edge key as ``id``.
        """
        repo = _em(info).repo
        from_id = str(input.from_entity_id)
        to_id = str(input.to_entity_id)
        if not is_structural_relationship_type(input.type):
            frm, from_proj = _resolve_relationship_endpoint(repo, from_id, input.elevated)
            to, to_proj = _resolve_relationship_endpoint(repo, to_id, input.elevated)
        else:
            frm, from_proj = from_id, False
            to, to_proj = to_id, False
        # Upsert: delete first if exists, then create fresh.
        repo.delete_relationship(frm, to, input.type, from_projection=from_proj, to_projection=to_proj)
        edge = repo.create_relationship(
            frm, to, input.type, description=input.description,
            from_projection=from_proj, to_projection=to_proj,
        )
        return Relationship(
            id=edge["_key"],
            from_entity_id=from_id,
            to_entity_id=to_id,
            type=input.type,
            description=input.description,
        )

    @strawberry.mutation
    def delete_relationship(self, info: strawberry.Info, input: DeleteRelationshipInput) -> bool:
        """Delete a directional relationship edge between two entities."""
        repo = _em(info).repo
        from_id = str(input.from_entity_id)
        to_id = str(input.to_entity_id)
        if not is_structural_relationship_type(input.type):
            frm, from_proj = _resolve_relationship_endpoint(repo, from_id, input.elevated)
            to, to_proj = _resolve_relationship_endpoint(repo, to_id, input.elevated)
        else:
            frm, from_proj = from_id, False
            to, to_proj = to_id, False
        return repo.delete_relationship(
            frm, to, input.type, from_projection=from_proj, to_projection=to_proj,
        )

    @strawberry.mutation
    def add_relationship_trait(self, info: strawberry.Info, from_entity_id: strawberry.ID,
                               to_entity_id: strawberry.ID, rel_type: str = "relation",
                               trait_id: strawberry.ID = "", die: GqlDieType = GqlDieType.D6,
                               traitset_id: Optional[str] = None,
                               elevated: bool = False,
                               statement: str = "") -> TraitSetting:
        """Create a rated trait on a relationship edge.

        Attaches to the *real* ArangoDB edge key (not a synthetic key), so the
        faction canvas can read rank/role traits back. The trait set is derived
        from the trait registry entry unless explicitly overridden. Personal
        relationship types resolve to projection→projection by default, or
        entity→entity when ``elevated`` and both sides are multiversal.
        """
        repo = _em(info).repo
        trait = repo.get_trait(str(trait_id))
        ts_id = traitset_id or (trait.traitset_id if trait else None)
        if not ts_id:
            raise ValueError(f"Cannot resolve traitset for trait '{trait_id}'")

        if not is_structural_relationship_type(rel_type):
            frm, from_proj = _resolve_relationship_endpoint(repo, str(from_entity_id), elevated)
            to, to_proj = _resolve_relationship_endpoint(repo, str(to_entity_id), elevated)
        else:
            frm, from_proj = str(from_entity_id), False
            to, to_proj = str(to_entity_id), False

        rel = repo.get_relationship(frm, to, rel_type, from_projection=from_proj, to_projection=to_proj)
        if not rel:
            rel = repo.create_relationship(frm, to, rel_type, from_projection=from_proj, to_projection=to_proj)
        edge_key = rel["_key"]

        ts = DomainTraitSetting(
            id=f"{edge_key}:{trait_id}",
            entity_id=edge_key,
            trait_id=str(trait_id),
            traitset_id=ts_id,
            from_type="relationship",
            dice=[die],
            statement=statement,
        )
        created = repo.create_traitsetting(ts)
        return _ts_to_gql(created)
