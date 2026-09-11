"""Common — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.domain import STRUCTURAL_RELATIONSHIP_TYPES


_STRUCTURAL_TYPES_AQL = "[" + ", ".join(
    f"'{t}'" for t in sorted(STRUCTURAL_RELATIONSHIP_TYPES)
) + "]"

def _key(doc_id: str) -> str:
    return doc_id
