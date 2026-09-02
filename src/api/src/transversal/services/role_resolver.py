"""Resolve the acting human role (player/architect) for an entity.

The role is a *human* attribute (``Player.role``), not an entity attribute, so
it is resolved through the player↔entity ``agency`` relationship rather than
read off the entity directly. Fire/menu contexts may already carry a role
(``context["role"]``); this module is the fallback for entity-only evaluation
(e.g. availability listing).
"""

from __future__ import annotations

from typing import Optional


def resolve_role(entity_id: str, repo) -> Optional[str]:
    """Resolve the role of the player(s) controlling ``entity_id``.

    Returns ``"player"`` / ``"architect"``, or ``None`` when the entity has no
    controlling player. When several players control one entity the architect
    role wins (GM override). Uses ``getattr`` so lightweight test doubles only
    need the two repo methods this relies on.
    """
    if not entity_id or repo is None:
        return None
    get_players = getattr(repo, "get_entity_players", None)
    get_player = getattr(repo, "get_player", None)
    if get_players is None or get_player is None:
        return None

    roles: list[str] = []
    for pid in (get_players(entity_id) or []):
        player = get_player(pid)
        role = (player or {}).get("role") if isinstance(player, dict) else getattr(player, "role", None)
        if role:
            roles.append(role)

    if not roles:
        return None
    return "architect" if "architect" in roles else roles[0]
