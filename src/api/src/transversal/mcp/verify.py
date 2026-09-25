"""Conformance check for the MCP layer.

Why this exists: the tool layer's failures are *silent*. A write can succeed,
land somewhere unexpected, or change nothing at all, and the caller — often an
LLM — sees a well-formed response either way. This module is the repeatable
audit that turns those properties into measurements, so a regression shows up
as a failing command instead of as wrong content discovered days later.

Checks, in order of severity:

1. **Parity** — every tool has a schema and every schema has a tool. A tool with
   no schema is invisible to clients; a schema with no tool is a lie.
2. **Document validity** — every GraphQL document in the layer validates against
   the *live* introspected schema. This catches field drift when another session
   changes the API under us.
3. **Response coverage** — for every mutation the layer reaches, the response
   selection is compared with the input type the mutation accepts. A field the
   caller can write but cannot read back is the "a write response hides what was
   just written" trap; `BASELINE_GAPS` records the ones that are known and
   deliberate, so any *new* gap fails the check.
4. **Reachability** — which live mutations no document reaches (informational;
   the absences are a product decision, not a defect).

Run it against a live API:

    python -m transversal.mcp.verify                 # report + fail on new gaps
    python -m transversal.mcp.verify --no-readback   # skip the read-back gate

`TRANSVERSAL_API_URL` is honoured the same way the server honours it.
"""

from __future__ import annotations

import json
import sys
import types
import urllib.error
import urllib.request
from typing import Any

from graphql import build_client_schema, get_introspection_query, parse, validate
from graphql.language import ast as A

from . import server as S

# Response gaps that are known and deliberate: `mutation -> {field: reason}`.
# Anything not listed here fails the read-back gate, so this file is the single
# place where "we accept not being able to read that back" is recorded.
BASELINE_GAPS: dict[str, dict[str, str]] = {
    "updateEntity": {
        "suitableLifePathIds": "write-only: `Entity` does not expose it; read from "
        "the other side via list_life_paths(factionIds)",
    },
    "createEntity": {
        "location": "echoed as currentLocation -- the resolver's own name for it",
        "universe": "echoed as currentUniverse -- the resolver's own name for it",
    },
    "deleteRelationship": {
        "*": "returns Boolean; a delete has no record left to read back",
    },
    "addJournalEntry": {
        "entityId": "echoed as senderEntityId for a self-addressed journal entry",
    },
    "createRelationship": {
        "elevated": "not a field on `Relationship`; the tool echoes the requested "
        "value in its step description",
    },
    "setAgencyMain": {
        "entityId": "echoed as lastMainEntityId on the returned Player",
        "main": "echoed as lastMainEntityId / mainEntity on the returned Player",
        "playerId": "the returned Player *is* the identified player",
    },
    "updateTrait": {
        "clearPolarity": "a command flag with no counterpart field on TraitRef",
    },
    "applyEffects": {
        "*": "the input is a spec of effects to *run*, not a record to store; the "
        "response reports the outcome instead (applied / structured / pendingChoices)",
    },
    "resolveEffectTargets": {
        "*": "same shape as applyEffects: the input answers pending *choices*, and the "
        "response reports what applied plus any next choice rather than echoing them",
    },
    "setConsequenceOptions": {
        "label": "not a field on `Entity`; pass side + menu_context and the tool confirms "
        "through the consequenceOptions read",
        "side": "as above -- side is a read coordinate, not an entity field",
        "effects": "as above -- the authored effects are read back via consequenceOptions",
    },
}


def _api_url() -> str:
    import os

    return os.environ.get("TRANSVERSAL_API_URL", "http://localhost:8085").rstrip("/")


def _introspect(url: str):
    gql = f"{url}/api/v1/graphql"
    body = json.dumps({"query": get_introspection_query()}).encode()
    req = urllib.request.Request(
        gql, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(f"introspection failed: {payload['errors']}")
    return build_client_schema(payload["data"])


def documents() -> dict[str, str]:
    """Every module-level GraphQL document, by constant name, as *values*."""
    return {
        name: value
        for name, value in vars(S).items()
        if isinstance(value, str)
        and name.startswith(("_MUT_", "_QUERY_"))
        and value.strip().startswith(("query", "mutation"))
    }


def _functions() -> dict[str, types.FunctionType]:
    return {
        name: value
        for name, value in vars(S).items()
        if isinstance(value, types.FunctionType)
    }


def _referenced(func: types.FunctionType, funcs: dict[str, types.FunctionType]) -> set[str]:
    """Names a function references, transitively through other functions.

    Read from the compiled code rather than the source so that documents built by
    string concatenation or ``%`` substitution are seen as the client sees them.
    """
    seen: set[types.FunctionType] = set()
    stack = [func]
    out: set[str] = set()
    while stack:
        current = stack.pop()
        for name in current.__code__.co_names:
            out.add(name)
            target = funcs.get(name)
            if target is not None and target not in seen:
                seen.add(target)
                stack.append(target)
    return out


def _type_node_name(node: Any) -> str | None:
    while isinstance(node, (A.NonNullTypeNode, A.ListTypeNode)):
        node = node.type
    return node.name.value if isinstance(node, A.NamedTypeNode) else None


def payloads(text: str) -> dict[str, tuple[list[str], set[str]]]:
    """Map each top-level operation field to (variable type names, selected fields).

    Every variable type is returned, not just the first: a mutation's first
    argument is often a scalar (``$id: ID!``), and picking it blindly makes the
    coverage check silently skip the mutation. The caller picks the input object.
    """
    out: dict[str, tuple[list[str], set[str]]] = {}
    try:
        doc = parse(text)
    except Exception:
        return out
    for definition in doc.definitions:
        variables = {
            v.variable.name.value: _type_node_name(v.type)
            for v in getattr(definition, "variable_definitions", [])
        }
        selection = getattr(definition, "selection_set", None)
        if selection is None:
            continue
        for field in selection.selections:
            selected = {
                sub.name.value
                for sub in (field.selection_set.selections if field.selection_set else [])
            }
            used = [
                variables[a.value.name.value]
                for a in field.arguments
                if isinstance(a.value, A.VariableNode)
                and variables.get(a.value.name.value)
            ]
            out[field.name.value] = ([t for t in used if t], selected)
    return out


def _input_object(schema: Any, type_names: list[str]) -> Any:
    """The first named type that is an input object (i.e. has writable fields)."""
    for name in type_names:
        candidate = schema.get_type(name)
        if candidate is not None and type(candidate).__name__ == "GraphQLInputObjectType":
            return candidate
    return None


def tool_documents() -> dict[str, list[str]]:
    docs = documents()
    funcs = _functions()
    return {
        tool: sorted(n for n in _referenced(fn, funcs) if n in docs)
        for tool, fn in S.TOOLS.items()
    }


def run(readback: bool = True) -> int:
    url = _api_url()
    print(f"API: {url}")
    schema = _introspect(url)
    docs = documents()
    failures: list[str] = []

    # 1. parity
    tools, schemas = set(S.TOOLS), set(S.TOOL_SCHEMAS)
    print(f"\n[tools] {len(tools)} tools / {len(schemas)} schemas")
    if tools - schemas:
        failures.append(f"tools with no schema: {sorted(tools - schemas)}")
    if schemas - tools:
        failures.append(f"schemas with no tool: {sorted(schemas - tools)}")

    # 2. document validity
    invalid = []
    for name, text in sorted(docs.items()):
        errors = validate(schema, parse(text))
        if errors:
            invalid.append((name, [e.message for e in errors]))
    print(f"[documents] {len(docs)} checked, {len(invalid)} invalid")
    for name, errors in invalid:
        failures.append(f"invalid document {name}: {errors[0]}")

    # 3. reachability
    live_mutations = set(schema.mutation_type.fields) if schema.mutation_type else set()
    reached: set[str] = set()
    per_tool: dict[str, list[str]] = {}
    for tool, names in tool_documents().items():
        ops: list[str] = []
        for name in names:
            for op, (_arg, _sel) in payloads(docs[name]).items():
                if op in live_mutations:
                    ops.append(op)
                    reached.add(op)
        if ops:
            per_tool[tool] = sorted(set(ops))
    missing = sorted(live_mutations - reached)
    print(
        f"[reach] {len(live_mutations)} live mutations, {len(reached)} reached, "
        f"{len(missing)} without a tool"
    )
    for op in missing:
        print(f"         - {op}")

    # 4. response coverage
    gaps: dict[str, dict[str, list[str]]] = {}
    scalar: list[str] = []
    for tool, names in sorted(tool_documents().items()):
        for name in names:
            for op, (type_names, selected) in payloads(docs[name]).items():
                if op not in live_mutations:
                    continue
                if not selected:
                    scalar.append(op)
                    continue
                input_type = _input_object(schema, type_names)
                if input_type is None:
                    continue
                omitted = set(input_type.fields) - selected
                if omitted:
                    gaps.setdefault(op, {})[tool] = sorted(omitted)

    print(f"[read-back] {len(gaps)} writes omit fields they accept; "
          f"{len(set(scalar))} return a scalar")
    new_gaps: list[str] = []
    for op, by_tool in sorted(gaps.items()):
        allowed = BASELINE_GAPS.get(op, {})
        for tool, omitted in sorted(by_tool.items()):
            if "*" in allowed:
                continue
            unaccounted = [f for f in omitted if f not in allowed]
            if unaccounted:
                new_gaps.append(f"{op} ({tool}) omits {unaccounted}")
    for op in sorted(set(scalar)):
        line = f"scalar return: {op}"
        print(f"         ~ {line}")
    for line in new_gaps:
        print(f"         ! {line}")

    if readback and new_gaps:
        failures.extend(new_gaps)

    print()
    if failures:
        print(f"FAIL ({len(failures)}):")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("OK -- parity, document validity and read-back coverage all conform.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return run(readback="--no-readback" not in argv)


if __name__ == "__main__":
    raise SystemExit(main())
