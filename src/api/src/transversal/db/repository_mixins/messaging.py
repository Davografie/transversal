"""Messaging — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import HISTORICAL_RECORDS
from transversal.db.arango import MESSAGES
from transversal.domain import HistoricalRecord
from transversal.domain import Message


class RepositoryMessaging:
    """Mixin contributing 11 member(s) to the repository."""

    def _doc_to_message(self, doc: dict) -> "Message":
        """Convert an ArangoDB messages document to a Message model."""
        return Message(
            id=doc["_key"],
            sender_entity_id=doc["sender_entity_id"],
            recipient_entity_id=doc["recipient_entity_id"],
            kind=doc.get("kind", "letter"),
            title=doc.get("title", ""),
            body=doc.get("body", ""),
            images=doc.get("images", []),
            after_ids=doc.get("after_ids", []),
            threads=doc.get("threads", []),
            created_at=doc.get("created_at", ""),
        )

    def send_message(
        self,
        sender_entity_id: str,
        recipient_entity_id: str,
        body: str = "",
        kind: str = "letter",
        title: str = "",
        images: list[str] | None = None,
        after_ids: list[str] | None = None,
        threads: list[str] | None = None,
    ) -> "Message":
        import uuid
        from datetime import datetime, timezone

        # Journal entries are self-referential — the character writes to themselves
        if kind == "journal":
            recipient_entity_id = sender_entity_id

        msg_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        doc = {
            "_key": msg_id,
            "sender_entity_id": sender_entity_id,
            "recipient_entity_id": recipient_entity_id,
            "kind": kind,
            "title": title,
            "body": body,
            "images": images or [],
            "after_ids": after_ids or [],
            "threads": threads or [],
            "created_at": created_at,
        }
        self._messages.insert(doc)
        return self._doc_to_message(doc)

    def get_incoming_messages(self, entity_id: str) -> list["Message"]:
        """Get messages addressed to an entity, newest first."""
        query = f"""
            FOR m IN {MESSAGES}
            FILTER m.recipient_entity_id == @eid
            SORT m.created_at DESC
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars={"eid": entity_id})
        return [self._doc_to_message(m) for m in results]

    def get_conversation(self, entity_a: str, entity_b: str) -> list["Message"]:
        """Get all messages between two entities (for GM view), newest first."""
        query = f"""
            FOR m IN {MESSAGES}
            FILTER (m.sender_entity_id == @a AND m.recipient_entity_id == @b)
                OR (m.sender_entity_id == @b AND m.recipient_entity_id == @a)
            SORT m.created_at DESC
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars={"a": entity_a, "b": entity_b})
        return [self._doc_to_message(m) for m in results]

    def get_recent_messages(
        self, since: str = "", kind: str = ""
    ) -> list["Message"]:
        """Get all messages across all entities (GM activity feed), newest first.

        Optionally filter by kind (letter, journal, report, gm_note)
        and/or by a minimum created_at timestamp.
        """
        filters = []
        bind_vars = {}
        if since:
            filters.append("m.created_at >= @since")
            bind_vars["since"] = since
        if kind:
            filters.append("m.kind == @kind")
            bind_vars["kind"] = kind
        filter_clause = f"FILTER {' AND '.join(filters)}" if filters else ""
        query = f"""
            FOR m IN {MESSAGES}
            {filter_clause}
            SORT m.created_at DESC
            LIMIT 200
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars=bind_vars)
        return [self._doc_to_message(m) for m in results]

    def get_journal(self, entity_id: str) -> list["Message"]:
        """Get an entity's personal journal entries (self-referential, kind=journal)."""
        query = f"""
            FOR m IN {MESSAGES}
            FILTER m.sender_entity_id == @eid
                AND m.recipient_entity_id == @eid
                AND m.kind == 'journal'
            SORT m.created_at DESC
            RETURN m
        """
        results = self.db.aql.execute(query, bind_vars={"eid": entity_id})
        return [self._doc_to_message(m) for m in results]

    def add_historical_record(
        self,
        entity_id: str,
        record_type,
        data: dict,
        universe: str = "",
        session_id: str = "",
        after_ids: list[str] | None = None,
    ) -> HistoricalRecord:
        """Append a historical event for an entity.

        ``record_type`` is a ``HistoricalRecordType`` (or its string value).
        ``data`` is the type-specific payload. ``after_ids`` is the Blue Book
        chain position (see ``update_historical_record``).
        """
        import uuid
        from datetime import datetime, timezone

        rtype = record_type.value if hasattr(record_type, "value") else record_type
        rec_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        doc = {
            "_key": rec_id,
            "entity_id": entity_id,
            "record_type": rtype,
            "universe": universe,
            "session_id": session_id,
            "data": data or {},
            "after_ids": after_ids or [],
            "created_at": created_at,
        }
        self._historical_records.insert(doc)
        return HistoricalRecord(
            id=rec_id,
            entity_id=entity_id,
            record_type=rtype,
            universe=universe,
            session_id=session_id,
            data=data or {},
            after_ids=after_ids or [],
            created_at=created_at,
        )

    def list_historical_records(
        self,
        entity_id: str = "",
        record_type: str = "",
    ) -> list[HistoricalRecord]:
        """List historical records, newest first, optionally filtered."""
        filters = []
        bind_vars = {}
        if entity_id:
            filters.append("h.entity_id == @eid")
            bind_vars["eid"] = entity_id
        if record_type:
            filters.append("h.record_type == @rtype")
            bind_vars["rtype"] = record_type
        where = f"FILTER {' AND '.join(filters)}" if filters else ""
        query = f"""
            FOR h IN {HISTORICAL_RECORDS}
            {where}
            SORT h.created_at DESC
            RETURN h
        """
        results = self.db.aql.execute(query, bind_vars=bind_vars)
        return [
            HistoricalRecord(
                id=h["_key"],
                entity_id=h.get("entity_id", ""),
                record_type=h.get("record_type", "roll_table"),
                universe=h.get("universe", ""),
                session_id=h.get("session_id", ""),
                data=h.get("data") or {},
                after_ids=h.get("after_ids", []),
                created_at=h.get("created_at", ""),
            )
            for h in results
        ]

    def get_all_threads(self) -> list[str]:
        """Return all distinct threads across all messages, sorted."""
        query = f"""
            FOR m IN {MESSAGES}
            FOR tag IN (m.threads || [])
            COLLECT tags = tag
            SORT tags
            RETURN tags
        """
        return list(self.db.aql.execute(query))

    def get_timeline(
        self,
        entity_id: str = "",
        threads: list[str] | None = None,
    ) -> list["Message"]:
        """Fetch messages and return them in topological (causal) order.

        Filters by entity (sender or recipient) and/or threads.
        Orders messages by their ``after_ids`` DAG using Kahn's algorithm.
        Messages with no ``after_ids`` come first; ties break on ``created_at``.
        Cycles are broken by removing the oldest edge and logging a warning.
        """
        import logging
        logger = logging.getLogger(__name__)

        # ── Fetch candidate messages ─────────────────
        filters = []
        bind_vars = {}
        if entity_id:
            filters.append("(m.sender_entity_id == @eid OR m.recipient_entity_id == @eid)")
            bind_vars["eid"] = entity_id
        if threads:
            # Any tag match (OR semantics)
            filters.append("LENGTH(INTERSECTION(m.threads, @tags)) > 0")
            bind_vars["tags"] = threads
        filter_clause = f"FILTER {' AND '.join(filters)}" if filters else ""
        query = f"""
            FOR m IN {MESSAGES}
            {filter_clause}
            RETURN m
        """
        raw = list(self.db.aql.execute(query, bind_vars=bind_vars))
        messages = [self._doc_to_message(m) for m in raw]

        # ── Build index and DAG ───────────────────────
        msg_map = {m.id: m for m in messages}
        in_degree: dict[str, int] = {m.id: 0 for m in messages}
        children: dict[str, list[str]] = {m.id: [] for m in messages}

        for m in messages:
            for after_id in m.after_ids:
                if after_id in msg_map:
                    children.setdefault(after_id, []).append(m.id)
                    in_degree[m.id] = in_degree.get(m.id, 0) + 1

        # ── Kahn's topological sort ───────────────────
        # Start with nodes that have no predecessors
        queue = [m.id for m in messages if in_degree.get(m.id, 0) == 0]
        # Stable sort: floaters tiebreak by created_at descending (newest first for equal-rank)
        queue.sort(key=lambda mid: msg_map[mid].created_at)

        result: list[Message] = []
        while queue:
            node_id = queue.pop(0)
            result.append(msg_map[node_id])
            for child_id in children.get(node_id, []):
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)
                    # Re-sort to maintain stable order
                    queue.sort(key=lambda mid: msg_map[mid].created_at)

        # ── Cycle detection ───────────────────────────
        if len(result) < len(messages):
            missing = [m.id for m in messages if m.id not in {r.id for r in result}]
            logger.warning(
                "timeline: %d message(s) in cycle, breaking at oldest edge — %s",
                len(missing), missing[:5],
            )
            # Break cycles: for each missing node, remove all after_ids and re-insert
            for mid in missing:
                msg_map[mid].after_ids = []
            result.extend(msg_map[mid] for mid in missing)
            result.sort(key=lambda m: m.created_at, reverse=True)

        return result

    def update_message(
        self, message_id: str, after_ids: list[str] | None = None, threads: list[str] | None = None
    ) -> bool:
        """Update the after_ids and/or threads of an existing message."""
        doc = self._messages.get(message_id)
        if not doc:
            return False
        if after_ids is not None:
            doc["after_ids"] = after_ids
        if threads is not None:
            doc["threads"] = threads
        self._messages.update(doc)
        return True

    def update_historical_record(
        self, record_id: str, after_ids: list[str] | None = None
    ) -> bool:
        """Set a historical record's Blue Book chain position.

        The record itself stays immutable — only ``after_ids`` is writable, so
        the append-only event log can still be ordered by hand.
        """
        doc = self._historical_records.get(record_id)
        if not doc:
            return False
        if after_ids is not None:
            doc["after_ids"] = after_ids
        self._historical_records.update(doc)
        return True
