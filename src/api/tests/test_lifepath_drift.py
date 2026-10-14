"""The drift audit reports what it claims ([[B291]]).

Every line of `lifepath_drift` exists because a shim's status was argued rather
than measured and the argument was wrong at least once. So each finding is fed
the state it is meant to catch, and the two that are easy to get backwards are
pinned explicitly:

* an unwrapped path's `life_path` effect is **live** flow, while the same effect
  on a wrapped path's row is **ignored** — the audit says which, because the
  removal decision is the opposite in the two cases;
* `RollTable.life_path` is redundant when a step wraps the table and still the
  legacy owner when one does not.

A clean fixture is asserted too, so the report cannot pass by reporting
everything everywhere.
"""

from types import SimpleNamespace as NS

from transversal.services.lifepath_drift import (
    VERDICT_LEGACY_OWNER,
    VERDICT_ORPHANED,
    VERDICT_REDUNDANT,
    format_report,
    lifepath_drift,
)


def _effect(effect_type="modify_trait"):
    return NS(type=effect_type)


def _row(label="Row", effects=(), cost_effects=()):
    return NS(label=label, key=label.lower(), effects=list(effects), cost_effects=list(cost_effects))


def _table(tid, life_path="", entries=(), check=None, subject_kind=""):
    return NS(id=tid, life_path=life_path, entries=list(entries), check=check,
              subject_kind=subject_kind)


def _step(sid, table_id, effects=(), bindings=()):
    return NS(id=sid, table_id=table_id, effects=list(effects), bindings=list(bindings))


def _binding(key="k", effects=()):
    return NS(key=key, effects=list(effects))


def _path(pid, steps=(), entry_table_id="", entry_step="", conditions=(), discovery=None):
    return NS(id=pid, name=pid, steps=list(steps), entry_table_id=entry_table_id,
              entry_step=entry_step, conditions=list(conditions), discovery=discovery)


def _term(path_id="lp-a", continuation=(), return_map=None):
    return NS(path_id=path_id, continuation=list(continuation), return_map=return_map or {})


class FakeRepo:
    def __init__(self, paths=(), tables=(), entities=(), factions=()):
        self._paths, self._tables = list(paths), list(tables)
        self._entities, self._factions = list(entities), list(factions)

    def list_all_lifepaths(self):
        return self._paths

    def list_roll_tables(self):
        return self._tables

    def list_all_entities(self):
        return self._entities

    def list_entities_by_type(self, _kind):
        return self._factions


def test_a_modern_store_reports_nothing_deprecated():
    repo = FakeRepo(
        paths=[_path("lp-a", steps=[_step("s1", "rt-a")])],
        tables=[_table("rt-a", entries=[_row()])],
        entities=[NS(id="char-1", pending_term=None,
                     pending_terms={"": _term("lp-a")})],
        factions=[NS(id="fac-1", suitable_life_path_ids=["lp-a"])],
    )
    report = lifepath_drift(repo)

    assert report["paths"]["unwrapped"] == []
    assert report["paths"]["entry_table_id"] == []
    assert report["tables"]["legacy_life_path"] == []
    assert report["tables"]["legacy_flow_effects"] == []
    assert report["tables"]["legacy_check"] == []
    assert report["tables"]["subject_kind"] == []
    assert report["terms"]["deprecated_pending_term"] == []
    assert report["terms"]["continuation_or_return_map"] == []
    assert report["offering"]["offered_by_nobody"] == []
    assert report["offering"]["dangling"] == []
    assert report["terms"]["live"] == [{"entity": "char-1", "projection": "", "path": "lp-a"}]


def test_an_unwrapped_paths_legacy_flow_effect_is_live():
    """The distinction the audit exists for: same effect, opposite verdict."""
    repo = FakeRepo(
        paths=[_path("lp-street")],
        tables=[_table("rt-street", entries=[_row("go", effects=[_effect("life_path")])])],
    )
    report = lifepath_drift(repo)

    assert [p["id"] for p in report["paths"]["unwrapped"]] == ["lp-street"]
    flow = report["tables"]["legacy_flow_effects"]
    assert len(flow) == 1 and flow[0]["table"] == "rt-street"
    assert flow[0]["wrapped_by"] == [], "nothing wraps it, so the effect is the flow"

    text = format_report(report)
    assert "unwrapped (no steps): 1" in text
    assert "LIVE (unwrapped path)" in text


def test_a_wrapped_paths_row_effect_is_reported_as_ignored():
    repo = FakeRepo(
        paths=[_path("lp-a", steps=[_step("s1", "rt-a")])],
        tables=[_table("rt-a", entries=[_row("go", effects=[_effect("life_path")])])],
    )
    flow = lifepath_drift(repo)["tables"]["legacy_flow_effects"]

    assert flow and flow[0]["wrapped_by"] == ["lp-a"]
    assert "ignored (wrapped)" in format_report(lifepath_drift(repo))
    # …and a `life_path` effect authored on the path itself is dead wherever it sits.
    assert lifepath_drift(repo)["paths"]["legacy_flow_effects"] == []


def test_a_life_path_effect_on_a_step_or_binding_is_reported():
    repo = FakeRepo(paths=[_path("lp-a", steps=[
        _step("s1", "rt-a", effects=[_effect("life_path")],
              bindings=[_binding("r", effects=[_effect("life_path")])]),
    ])])
    found = lifepath_drift(repo)["paths"]["legacy_flow_effects"]

    assert {(r["step"], r["where"]) for r in found} == {("s1", "step"), ("s1", "binding 'r'")}


def test_the_deprecated_ownership_field_says_whether_a_step_replaces_it():
    repo = FakeRepo(
        paths=[_path("lp-a", steps=[_step("s1", "rt-a")])],
        tables=[_table("rt-a", life_path="lp-a"), _table("rt-b", life_path="lp-b")],
    )
    legacy = lifepath_drift(repo)["tables"]["legacy_life_path"]

    assert [r["id"] for r in legacy] == ["rt-a", "rt-b"]
    assert legacy[0]["wrapped_by"] == ["lp-a"], "redundant: a step wraps it"
    assert legacy[0]["verdict"] == VERDICT_REDUNDANT
    assert legacy[1]["wrapped_by"] == []
    assert legacy[1]["verdict"] == VERDICT_LEGACY_OWNER, "its path has no steps at all"
    text = format_report(lifepath_drift(repo))
    assert VERDICT_REDUNDANT in text and VERDICT_LEGACY_OWNER in text


def test_an_orphaned_table_is_distinguished_from_a_redundant_one():
    """The finding this audit caught on live content: a table naming a path that has
    steps and does *not* wrap it. The path's own listing comes from its steps, so the
    table is in no path's list at all — neither redundant nor a legacy owner."""
    repo = FakeRepo(
        paths=[_path("lp-a", steps=[_step("s1", "rt-wrapped")])],
        tables=[_table("rt-orphan", life_path="lp-a")],
    )
    row = lifepath_drift(repo)["tables"]["legacy_life_path"][0]

    assert row["wrapped_by"] == []
    assert row["verdict"] == VERDICT_ORPHANED
    assert "ORPHANED" in format_report(lifepath_drift(repo))


def test_an_unwrapped_path_says_whether_a_term_can_even_start():
    """Not every unwrapped path is a dependency on the legacy shim: one with no steps
    and no entry table cannot begin a term at all, so it argues for removing the shim
    rather than keeping it."""
    empty = FakeRepo(paths=[_path("lp-empty")])
    legacy = FakeRepo(paths=[_path("lp-legacy", entry_table_id="rt-old")])

    empty_row = lifepath_drift(empty)["paths"]["unwrapped"][0]
    legacy_row = lifepath_drift(legacy)["paths"]["unwrapped"][0]

    assert empty_row["startable"] is False
    assert legacy_row["startable"] is True
    assert "EMPTY SHELL" in format_report(lifepath_drift(empty))
    assert "STARTABLE" in format_report(lifepath_drift(legacy))


def test_the_deprecated_term_fields_are_reported_separately():
    repo = FakeRepo(entities=[
        NS(id="char-old", pending_term=NS(path_id="lp-a"), pending_terms={}),
        NS(id="char-live", pending_term=None,
           pending_terms={"": _term("lp-a", continuation=["rt-x"], return_map={"a": "b"})}),
    ])
    report = lifepath_drift(repo)

    assert report["terms"]["deprecated_pending_term"] == ["char-old"]
    assert [r["entity"] for r in report["terms"]["continuation_or_return_map"]] == ["char-live"]


def test_the_offering_gap_and_a_dangling_offering_are_both_reported():
    repo = FakeRepo(
        paths=[_path("lp-offered"), _path("lp-lonely")],
        factions=[NS(id="fac-1", suitable_life_path_ids=["lp-offered", "lp-ghost"])],
    )
    offering = lifepath_drift(repo)["offering"]

    assert offering["offered_by_nobody"] == ["lp-lonely"], "the original complaint"
    assert offering["dangling"] == ["lp-ghost"], "an offering that names no path"
    text = format_report(lifepath_drift(repo))
    assert "offered by nobody: lp-lonely" in text and "DANGLING" in text


def test_the_remaining_path_and_table_findings_are_reported():
    repo = FakeRepo(
        paths=[_path("lp-a", steps=[_step("s1", "rt-a")], entry_table_id="rt-a",
                     conditions=[NS(type="NARRATIVE")], discovery=NS(at_location=[]))],
        tables=[_table("rt-a", check=NS(trait_ids=[]), subject_kind="projection")],
    )
    report = lifepath_drift(repo)

    assert [r["entry_table_id"] for r in report["paths"]["entry_table_id"]] == ["rt-a"]
    assert report["paths"]["with_conditions"] == ["lp-a"]
    assert report["paths"]["without_conditions"] == []
    assert report["paths"]["with_discovery"] == ["lp-a"]
    assert report["tables"]["legacy_check"] == ["rt-a"]
    assert report["tables"]["subject_kind"] == [{"id": "rt-a", "subject_kind": "projection"}]


def test_factions_are_read_from_the_entity_list_when_the_repo_cannot_list_by_type():
    """A real repo lists factions by type; a lighter one only knows every entity, and the
    audit must still answer the question it is run for rather than reporting zero factions."""
    class ListOnlyRepo:
        def list_all_lifepaths(self):
            return [_path("lp-a")]

        def list_roll_tables(self):
            return []

        def list_all_entities(self):
            return [NS(id="fac-1", type="faction", suitable_life_path_ids=["lp-a"]),
                    NS(id="char-1", type="character", pending_term=None, pending_terms={})]

    offering = lifepath_drift(ListOnlyRepo())["offering"]

    assert offering["factions"] == 1
    assert offering["offered_by_nobody"] == []
