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
    DieRoll,
    DieSpec,
    DieType,
    EntityType,
    Trait,
    TraitSet,
    TraitSetting,
)
from transversal.services.dice_resolver import (
    compare_totals as _compare_totals,
    detect_hitches,
    is_botch,
    pick_effect_die as _pick_effect_die,
    pick_total as _pick_total,
    roll_dice as _roll_pool,
)
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
            statement=distinction,
        )
        _em().add_traitsetting(ts)

    return entity.model_dump()


def _rolls_to_wire(rolls) -> list[dict]:
    return [
        {
            "die": r.die.value,
            "result": r.result,
            "source_id": r.source_id,
            "source_kind": r.source_kind,
            "label": r.label,
        }
        for r in rolls
    ]


def _wire_to_rolls(wire) -> list[DieRoll]:
    return [
        DieRoll(
            die=DieType(r["die"]),
            result=int(r["result"]),
            source_id=r.get("source_id", ""),
            source_kind=r.get("source_kind", "manual"),
            label=r.get("label", ""),
        )
        for r in wire
    ]


def roll_dice(args: dict) -> dict:
    """Roll a pool and return rolls + hitch data only.

    Nothing is auto-picked — the caller drives total/effect selection via
    ``pick_total`` / ``pick_effect_die`` and comparison via ``compare_totals``.
    """
    dice = [DieSpec(die=DieType(d), source_id=s, label=s) for d, s in args["dice"]]
    rolls = _roll_pool(dice)
    return {
        "pipeline": "pool" if len(rolls) > 2 else "simplified",
        "rolls": _rolls_to_wire(rolls),
        "hitches": _rolls_to_wire(detect_hitches(rolls)),
        "botch": is_botch(rolls),
    }


def pick_total(args: dict) -> dict:
    rolls = _wire_to_rolls(args["rolls"])
    return {"total": _pick_total(rolls, args["indices"])}


def pick_effect_die(args: dict) -> dict:
    rolls = _wire_to_rolls(args["rolls"])
    effect = _pick_effect_die(
        rolls,
        args.get("total_indices", []),
        args.get("hitches_apply", True),
    )
    return {"effect_die": effect.die.value if effect else "d4"}


def compare_totals(args: dict) -> dict:
    return {"winner": _compare_totals(args["player_total"], args["opponent_total"]).value}


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
    "pick_total": pick_total,
    "pick_effect_die": pick_effect_die,
    "compare_totals": compare_totals,
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
        "description": "Roll a dice pool and return the rolled dice + hitches only (no auto-picking)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dice": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                         "description": "List of [die_type, source] pairs, e.g. [['d8', 'shooting']]"},
            },
            "required": ["dice"],
        },
    },
    "pick_total": {
        "name": "pick_total",
        "description": "Sum the results of the chosen dice (by roll index) into a total",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rolls": {"type": "array", "description": "The rolls returned by roll_dice"},
                "indices": {"type": "array", "items": {"type": "integer"},
                           "description": "Indices of the dice to sum"},
            },
            "required": ["rolls", "indices"],
        },
    },
    "pick_effect_die": {
        "name": "pick_effect_die",
        "description": "Choose the effect die from dice not used in the total",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rolls": {"type": "array", "description": "The rolls returned by roll_dice"},
                "total_indices": {"type": "array", "items": {"type": "integer"},
                                 "description": "Indices of the dice used for the total"},
                "hitches_apply": {"type": "boolean",
                                 "description": "Whether rolled 1s are ineligible (default true)"},
            },
            "required": ["rolls"],
        },
    },
    "compare_totals": {
        "name": "compare_totals",
        "description": "Compare two totals and declare a contest winner (tie favors the challenger)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "player_total": {"type": "integer"},
                "opponent_total": {"type": "integer"},
            },
            "required": ["player_total", "opponent_total"],
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
