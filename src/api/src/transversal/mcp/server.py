"""MCP server — exposes Transversal tools over stdio for AI-driven content creation.

Tools:
  create_location, create_npc, create_entity, roll_dice,
  query_entities, get_entity, manage_session, generate_from_table
"""

import json
import sys
from typing import Any

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    DicePoolRequest,
    EntityType,
    Opposition,
    Trait,
    TraitSet,
    TraitSetting,
)
from transversal.services.dice_resolver import resolve
from transversal.services.entity_manager import EntityManager


def _repo() -> EntityRepository:
    return EntityRepository()


def _em() -> EntityManager:
    return EntityManager(repository=_repo())


# ── Tool implementations ────────────────────────────

def create_entity(args: dict) -> dict:
    name = args["name"]
    etype = EntityType(args["type"])
    universe = args["universe"]
    location = args.get("location")
    razmerit = args.get("razmerit", 0)
    entity = _em().create(name=name, entity_type=etype, universe=universe,
                          location=location, razmerit=razmerit)
    return entity.model_dump()


def create_npc(args: dict) -> dict:
    name = args["name"]
    universe = args["universe"]
    location = args.get("location", "")
    distinction = args.get("distinction", "")
    traits = args.get("traits", [])

    entity = _em().create(name=name, entity_type=EntityType.GMC,
                          universe=universe, location=location)

    # Add distinction as ego trait
    if distinction:
        ts = TraitSetting(
            id=f"{entity.id}:distinction",
            entity_id=entity.id, trait_id="npc-distinction",
            traitset_id="ts-npc", dice=[DieType.D8],
            ego=True, statement=distinction,
        )
        _em().add_traitsetting(ts)

    return entity.model_dump()


def roll_dice(args: dict) -> dict:
    entity_id = args["entity_id"]
    universe = args.get("universe", "earth")
    dice = [(DieType(d), s) for d, s in args["dice"]]
    opposition = None
    if "opposition" in args:
        opp = args["opposition"]
        opposition = Opposition(
            type=opp.get("type", "static_difficulty"),
            dice=[(DieType(d), s) for d, s in opp.get("dice", [])],
            challenge_die=DieType(opp["challenge_die"]) if "challenge_die" in opp else None,
            static_difficulty=opp.get("static_difficulty"),
        )

    request = DicePoolRequest(entity_id=entity_id, universe=universe,
                               dice=dice, opposition=opposition)
    result = resolve(request)
    # Return as dict — handle both SimplifiedResult and PoolResult
    if hasattr(result, 'highest'):
        return {"pipeline": "simplified", "highest": result.highest,
                "tier": result.tier.value, "effect_die": result.effect_die.value if result.effect_die else None,
                "botch": result.botch, "razmerit_earned": result.razmerit_earned}
    else:
        return {"pipeline": "pool", "total": result.total,
                "effect_die": result.effect_die.value if result.effect_die else None,
                "botch": result.botch, "razmerit_earned": result.razmerit_earned}


def get_entity(args: dict) -> dict:
    entity_id = args["entity_id"]
    entity = _em().get(entity_id)
    return entity.model_dump()


def query_entities(args: dict) -> dict:
    etype = EntityType(args.get("type", "character"))
    universe = args.get("universe")
    entities = _repo().list_entities_by_type(etype, universe)
    return {"count": len(entities), "results": [e.model_dump() for e in entities]}


# ── Tool registry ───────────────────────────────────

TOOLS = {
    "create_entity": create_entity,
    "create_npc": create_npc,
    "roll_dice": roll_dice,
    "get_entity": get_entity,
    "query_entities": query_entities,
}

TOOL_SCHEMAS = {
    "create_entity": {
        "name": "create_entity",
        "description": "Create a new entity (character, location, faction, asset, or GMC)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entity name"},
                "type": {"type": "string", "enum": ["character", "location", "faction", "asset", "gmc"]},
                "universe": {"type": "string", "description": "Universe (earth, three_realms, etc.)"},
                "location": {"type": "string", "description": "Starting location"},
                "razmerit": {"type": "integer", "description": "Starting razmerit"},
            },
            "required": ["name", "type", "universe"],
        },
    },
    "create_npc": {
        "name": "create_npc",
        "description": "Create a GMC with a distinction",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "universe": {"type": "string"},
                "location": {"type": "string"},
                "distinction": {"type": "string", "description": "The NPC's defining trait"},
                "traits": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "universe"],
        },
    },
    "roll_dice": {
        "name": "roll_dice",
        "description": "Resolve a dice pool using the dual-pipeline system",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "universe": {"type": "string"},
                "dice": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                         "description": "List of [die_type, source] pairs, e.g. [['d8', 'shooting']]"},
                "opposition": {"type": "object"},
            },
            "required": ["entity_id", "dice"],
        },
    },
    "get_entity": {
        "name": "get_entity",
        "description": "Retrieve an entity by ID",
        "inputSchema": {
            "type": "object",
            "properties": {"entity_id": {"type": "string"}},
            "required": ["entity_id"],
        },
    },
    "query_entities": {
        "name": "query_entities",
        "description": "List entities by type and optional universe",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "universe": {"type": "string"},
            },
        },
    },
}


# ── JSON-RPC handler (stdio) ────────────────────────

def handle_request(request: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": list(TOOL_SCHEMAS.values())},
        }

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}}

        try:
            result = TOOLS[tool_name](arguments)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(result)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32000, "message": str(e)}}

    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not supported"}}


def main():
    """Run the MCP server over stdio."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    main()
