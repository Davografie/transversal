"""Life-path walkability — the entity-scoped gate ([[B194]]).

Two gates on a life path, deliberately separate: ``discovery`` (has the character
found out the path *exists*? a one-time reveal) and ``conditions`` (may they
**walk** it now?). This file pins the second, and the read that answers it.

The evaluation is the effects condition model, reused rather than reimplemented —
but only the conditions answerable from the entity *alone* may gate:

* a **context-gated** one (``arrival_kind``, ``roll_tier``, a ``{variable}``) is
  not false, it is *unknown* until the moment it would fire, so it must neither
  block a path nor appear as a reason;
* a condition that needs a **source** (``source_rating``) can never pass on a life
  path — a path is not an SFX and has no source — so letting it gate would make the
  path permanently unwalkable, silently.

The first of those is [[B195]], and the bug ran **both** ways: ``static_conditions``
omitted ``arrival_kind`` (admitted as static, then always false → silently
unwalkable) and listed ``user_role`` (dropped as context, so never evaluated at all
→ the gate silently ignored). Both are pinned below, because a life path is exactly
where they would have shown up.

Live-ArangoDB tests. They build an isolated fixture and tear it down, and skip when
ArangoDB is unavailable.
"""

import asyncio

import pytest

from transversal.api.graphql.schema import schema
from transversal.db.repository import EntityRepository
from transversal.domain import Condition, Entity, EntityType, LifePath
from transversal.domain.enums import ConditionType
from transversal.services.conditions import evaluate_condition, static_conditions
from transversal.services.entity_manager import EntityManager
from transversal.services.lifepath_walkability import (
    evaluable_conditions,
    unwalkable_reasons,
)
from transversal.services.target_spec import TargetSpec


def _spec(step: dict) -> TargetSpec:
    """A one-step targeting path, for the condition shapes below."""
    return TargetSpec.model_validate({"steps": [step]})

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

U = "test-walkability-u"
ELSEWHERE = "test-walkability-other-u"

WALKER = "test-walkability-char"
OTHER = "test-walkability-gmc"

OPEN_PATH = "lp-test-walkability-open"          # no gate at all
UNIVERSE_PATH = "lp-test-walkability-universe"  # gated on in_universe
TYPE_PATH = "lp-test-walkability-type"          # gated on entity_type
ARRIVAL_PATH = "lp-test-walkability-arrival"    # context-gated: must NOT gate
SOURCE_PATH = "lp-test-walkability-source"      # source-gated: must NOT gate
WRITE_PATH = "lp-test-walkability-write"        # for the save round-trip

_PATHS = (OPEN_PATH, UNIVERSE_PATH, TYPE_PATH, ARRIVAL_PATH, SOURCE_PATH, WRITE_PATH)


def _cleanup(repo):
    for pid in _PATHS:
        repo.delete_lifepath(pid)
    repo.delete_entity(WALKER, rmtree=True)
    repo.delete_entity(OTHER, rmtree=True)


def _seed(repo):
    """A character in U and a gmc in U, plus one path per gate shape."""
    _cleanup(repo)
    repo.create_entity(Entity(id=WALKER, type=EntityType.CHARACTER, name="Walker",
                              current_universe=U))
    repo.create_entity(Entity(id=OTHER, type=EntityType.GMC, name="Other",
                              current_universe=U))
    for pid, name, conditions in (
        (OPEN_PATH, "Open Path", []),
        (UNIVERSE_PATH, "Universe Path",
         [Condition(type=ConditionType.IN_UNIVERSE, target=U)]),
        (TYPE_PATH, "Type Path",
         [Condition(type=ConditionType.ENTITY_TYPE, target="character")]),
        (ARRIVAL_PATH, "Arrival Path",
         [Condition(type=ConditionType.ARRIVAL_KIND, target="transversal")]),
        (SOURCE_PATH, "Source Path",
         [Condition(type=ConditionType.SOURCE_RATING, operator=">=", value="d8")]),
    ):
        repo.create_lifepath(LifePath(id=pid, name=name, universe=U,
                                      # A path that cannot begin a term is unwalkable
                                      # for everyone regardless of its conditions
                                      # ([[B291]]), so the fixture paths have to be
                                      # startable for the gate to be the thing under
                                      # test.
                                      entry_table_id=f"rt-{pid}",
                                      conditions=conditions))


def _gql(query: str, variables: dict, repo):
    """Run a GraphQL document straight against the schema, over a real repository.

    No HTTP and no module globals: the schema takes the entity manager as its
    context, which is all `_em(info)` needs. Executed through the async entry point
    because the root type carries async fields, so `execute_sync` refuses to
    complete the document.
    """
    em = EntityManager(repository=repo)
    result = asyncio.run(schema.execute(query, variable_values=variables,
                                        context_value={"entity_manager": em}))
    assert result.errors is None, result.errors
    return result.data


# ── What may gate at all ─────────────────────────────

def test_arrival_kind_is_not_static():
    """B195, half one: it reads context, so it was never a listing-time gate.

    Unpatched this returned True — the condition survived the filter, was then
    evaluated with no context, matched nothing, and made the path silently
    permanently unwalkable.
    """
    c = Condition(type=ConditionType.ARRIVAL_KIND, target="transversal")
    assert static_conditions([c]) == []
    assert evaluable_conditions([c]) == []


def test_user_role_is_static():
    """B195, half two — the direction the ticket did not name.

    `user_role` reads **no** context (it prefers `context["role"]` but falls back
    to the entity's controlling player), so excluding it meant the gate was never
    evaluated at all and every role walked through it.
    """
    c = Condition(type=ConditionType.USER_ROLE, target="gm")
    assert static_conditions([c]) == [c]
    assert evaluable_conditions([c]) == [c]


def test_source_rating_is_static_but_cannot_gate_a_life_path():
    """A path has no source, so the condition can never pass here.

    It is correctly *static* for an SFX (which does have one) — the exclusion is
    this read's, not the helper's.
    """
    c = Condition(type=ConditionType.SOURCE_RATING, operator=">=", value="d8")
    assert static_conditions([c]) == [c]
    assert evaluable_conditions([c]) == []


def test_a_context_condition_alone_leaves_a_path_walkable():
    repo = _repo
    _seed(repo)
    try:
        reasons = unwalkable_reasons(repo, repo.get_entity(WALKER),
                                     [repo.get_lifepath(ARRIVAL_PATH)])
        assert reasons == {}
    finally:
        _cleanup(repo)


def test_a_source_condition_alone_leaves_a_path_walkable():
    repo = _repo
    _seed(repo)
    try:
        reasons = unwalkable_reasons(repo, repo.get_entity(WALKER),
                                     [repo.get_lifepath(SOURCE_PATH)])
        assert reasons == {}
    finally:
        _cleanup(repo)


# ── The gate itself ──────────────────────────────────

def test_an_ungated_path_is_walkable():
    repo = _repo
    _seed(repo)
    try:
        assert unwalkable_reasons(repo, repo.get_entity(WALKER),
                                  [repo.get_lifepath(OPEN_PATH)]) == {}
    finally:
        _cleanup(repo)


def test_a_satisfied_condition_is_walkable():
    repo = _repo
    _seed(repo)
    try:
        walker = repo.get_entity(WALKER)
        assert unwalkable_reasons(repo, walker, [repo.get_lifepath(UNIVERSE_PATH)]) == {}
        assert unwalkable_reasons(repo, walker, [repo.get_lifepath(TYPE_PATH)]) == {}
    finally:
        _cleanup(repo)


def test_a_condition_may_read_what_an_earlier_one_named():
    """[[B41]]: the conditions share **one scope**, so a `target_path` condition can
    publish a named output and the next can read it — `evaluate_conditions` threads
    exactly that.

    Iron Roots is authored this way: one condition declares the sect's location set
    (`literal location → navigate subtree`, with an `output`), the next tests whether
    the character's location is in it (`filter id in {that_name}`). Evaluating them
    one at a time with a fresh scope made the whole gate **silently always-false** —
    the second condition read the literal token `{…}` and matched nothing, for every
    entity, and the player saw "unmet: …" rather than a broken condition.
    """
    repo = _repo
    _seed(repo)
    try:
        lp = repo.get_lifepath(OPEN_PATH)
        # Both conditions must be **static** to reach an availability gate, and a spec
        # that seeds from `select variable` is not (`_spec_is_static` — it needs the
        # activation context). So the second one reads the earlier output through a
        # *filter value* instead, which is exactly how a real authored gate does it.
        lp.conditions = [
            Condition(type=ConditionType.TARGET_PATH, spec=_spec(
                {"kind": "select", "collection": "self", "output": "me"})),
            Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec.model_validate(
                {"steps": [
                    {"kind": "select", "collection": "self"},
                    {"kind": "filter", "field": "id", "operator": "==", "value": "{me}"},
                ]})),
        ]
        walker = repo.get_entity(WALKER)

        # With a fresh scope the token stays literal, so the second condition matches
        # nobody — the silent always-false this pins.
        assert evaluate_condition(walker, lp.conditions[1], repo) is False
        # Through the gate the two share one scope, so it resolves.
        assert unwalkable_reasons(repo, walker, [lp]) == {}
    finally:
        _cleanup(repo)


def test_a_path_that_cannot_begin_a_term_is_unwalkable():
    """[[B291]] found one live: no steps, no `entry_step`, no `entry_table_id` — an
    empty shell that `start_term` raises on. It matters here because removing the
    offering gate ([[B41]]) leaves **this** read as the only thing between the player
    and the path, so offering one that can only fail turns a disabled row with a
    reason into an error on click."""
    repo = _repo
    _seed(repo)
    try:
        shell = repo.get_lifepath(OPEN_PATH)
        shell.entry_step = ""
        shell.entry_table_id = ""
        shell.steps = []

        reasons = unwalkable_reasons(repo, repo.get_entity(WALKER), [shell])

        assert OPEN_PATH in reasons
        assert "no entry step" in reasons[OPEN_PATH][0]
    finally:
        _cleanup(repo)


def test_an_unsatisfied_condition_blocks_and_says_why():
    repo = _repo
    _seed(repo)
    try:
        # A gmc cannot walk the character-only path.
        reasons = unwalkable_reasons(repo, repo.get_entity(OTHER),
                                     [repo.get_lifepath(TYPE_PATH)])
        assert TYPE_PATH in reasons
        assert len(reasons[TYPE_PATH]) == 1
        # Phrased as the author wrote it, and framed as *unmet* — the positive
        # rendering of a failing condition would state the opposite of the truth.
        assert reasons[TYPE_PATH][0].startswith("unmet: ")
    finally:
        _cleanup(repo)


def test_an_entity_outside_the_universe_is_blocked():
    repo = _repo
    _seed(repo)
    try:
        walker = repo.get_entity(WALKER)
        walker.current_universe = ELSEWHERE
        repo.update_entity(walker)
        reasons = unwalkable_reasons(repo, repo.get_entity(WALKER),
                                     [repo.get_lifepath(UNIVERSE_PATH)])
        assert UNIVERSE_PATH in reasons
    finally:
        _cleanup(repo)


# ── The GraphQL read ─────────────────────────────────

def test_the_query_reports_walkability_per_entity():
    repo = _repo
    _seed(repo)
    try:
        data = _gql("""
            query($u: String!, $e: ID!) {
                lifePaths(universe: $u, entityId: $e) { id walkable unwalkableReasons }
            }
        """, {"u": U, "e": WALKER}, repo)
        by_id = {p["id"]: p for p in data["lifePaths"]}
        assert by_id[OPEN_PATH]["walkable"] is True
        assert by_id[UNIVERSE_PATH]["walkable"] is True
        assert by_id[TYPE_PATH]["walkable"] is True
        assert by_id[ARRIVAL_PATH]["walkable"] is True     # context: unknown, not blocking
        assert by_id[SOURCE_PATH]["walkable"] is True      # no source: cannot gate
        assert by_id[TYPE_PATH]["unwalkableReasons"] == []
    finally:
        _cleanup(repo)


def test_the_query_reports_the_blocked_path_with_its_reason():
    repo = _repo
    _seed(repo)
    try:
        data = _gql("""
            query($u: String!, $e: ID!) {
                lifePaths(universe: $u, entityId: $e) { id walkable unwalkableReasons }
            }
        """, {"u": U, "e": OTHER}, repo)
        by_id = {p["id"]: p for p in data["lifePaths"]}
        assert by_id[TYPE_PATH]["walkable"] is False
        assert by_id[TYPE_PATH]["unwalkableReasons"][0].startswith("unmet: ")
        # …and only that one: one gate failing must not tar its neighbours.
        assert by_id[OPEN_PATH]["walkable"] is True
    finally:
        _cleanup(repo)


def test_without_an_entity_walkability_is_null_not_true():
    """`not evaluated` must not read as `walkable` — the client asked no question."""
    repo = _repo
    _seed(repo)
    try:
        data = _gql("""
            query($u: String!) { lifePaths(universe: $u) { id walkable unwalkableReasons } }
        """, {"u": U}, repo)
        assert data["lifePaths"]
        for path in data["lifePaths"]:
            assert path["walkable"] is None
            assert path["unwalkableReasons"] == []
    finally:
        _cleanup(repo)


def test_an_unknown_entity_reports_nothing_rather_than_yes():
    """A bad id must not answer "everything is walkable"."""
    repo = _repo
    _seed(repo)
    try:
        data = _gql("""
            query($u: String!, $e: ID!) {
                lifePaths(universe: $u, entityId: $e) { id walkable }
            }
        """, {"u": U, "e": "no-such-entity"}, repo)
        assert all(p["walkable"] is None for p in data["lifePaths"])
    finally:
        _cleanup(repo)


def test_the_query_exposes_the_authored_gate():
    repo = _repo
    _seed(repo)
    try:
        data = _gql("""
            query($u: String!) {
                lifePaths(universe: $u) { id conditions { type target } }
            }
        """, {"u": U}, repo)
        by_id = {p["id"]: p for p in data["lifePaths"]}
        assert [c["type"] for c in by_id[TYPE_PATH]["conditions"]] == ["ENTITY_TYPE"]
        assert by_id[OPEN_PATH]["conditions"] == []
    finally:
        _cleanup(repo)


# ── Writing the gate ─────────────────────────────────

def test_the_gate_survives_a_save_round_trip():
    repo = _repo
    _seed(repo)
    try:
        _gql("""
            mutation($u: String!) {
                saveLifePath(id: "lp-test-walkability-write", name: "Write Path", universe: $u,
                             description: "", conditions: [
                                {type: ENTITY_TYPE, target: "character"}
                             ])
            }
        """, {"u": U}, repo)
        saved = repo.get_lifepath(WRITE_PATH)
        assert [c.type for c in saved.conditions] == [ConditionType.ENTITY_TYPE]
    finally:
        _cleanup(repo)


def test_omitting_conditions_leaves_the_gate_alone():
    """Editing a path's *name* must not silently drop its gate.

    `None` is "unchanged" and an explicit empty list is "clear" — the convention
    every other update mutation here uses, and the reason it is not optional for a
    gate.
    """
    repo = _repo
    _seed(repo)
    try:
        _gql("""
            mutation($u: String!) {
                saveLifePath(id: "lp-test-walkability-type", name: "Renamed", universe: $u,
                             description: "")
            }
        """, {"u": U}, repo)
        renamed = repo.get_lifepath(TYPE_PATH)
        assert renamed.name == "Renamed"
        assert [c.type for c in renamed.conditions] == [ConditionType.ENTITY_TYPE]

        _gql("""
            mutation($u: String!) {
                saveLifePath(id: "lp-test-walkability-type", name: "Cleared", universe: $u,
                             description: "", conditions: [])
            }
        """, {"u": U}, repo)
        assert repo.get_lifepath(TYPE_PATH).conditions == []
    finally:
        _cleanup(repo)
