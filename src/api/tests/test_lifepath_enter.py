"""`life_path/enter` — begin a term in a path from a rule ([[B303]]).

The action exists because *showing* a path and *entering* it are different acts,
and only one of them writes anything. The author's ask was the writing one: after
creating a character they expected the path's first table, ready to roll, not a
chooser — and `life_path/next_step` cannot do it, because a path with declared
`steps` owns its own graph and ignores `next_step` (see
`services/lifepath_executor`). So this pins the operation the wizard's chooser
performs, reached from a rule instead.
"""

from types import SimpleNamespace as NS

from transversal.domain import Effect, EffectTiming, TargetRef
from transversal.services.effects_applier import apply_effects
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY

PATH = "lp-24f963a8"


def _effect(**kw):
    return Effect(timing=EffectTiming.IMMEDIATE, type="life_path", action="enter", **kw)


def _entity(**over):
    kw = dict(id="char-1", name="Newcomer", type="character",
              current_universe="earth", current_projection="",
              pending_terms=None, discovered_life_paths=[])
    kw.update(over)
    return NS(**kw)


class Repo:
    """Just enough repo: the term needs the path it is entering."""

    def __init__(self, path=None):
        self._path = path if path is not None else NS(
            id=PATH, entry_step="s1", steps=[NS(id="s1", table_id="rt-earth-regions")],
            entry_table_id="")
        self.paths = {PATH: self._path}

    def get_lifepath(self, pid):
        return self.paths.get(pid)

    def get_projections_for_entity(self, eid):
        return []


# ── The declaration ────────────────────────────────────────────

def test_enter_is_declared_where_the_other_life_path_verbs_are():
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "enter_life_path")
    assert meta.effect_type == "life_path" and meta.effect_action == "enter"
    # Filed with Discover / Next Step / Draft, not under Client: an author looking
    # for "walk this path" looks on the life-path shelf.
    assert meta.group == "Life Path"
    # The path is a *target*-role ref, so `_resolve_target` finds it by role.
    assert {r.name: r.role for r in meta.refs} == {"life_path": "target"}
    assert meta.fields[0].hidden_when_ref == "life_path"


# ── The handler ────────────────────────────────────────────────

def test_entering_writes_the_cursor_at_the_paths_entry_table():
    entity = _entity()
    effect = _effect()
    effect.refs = {"life_path": TargetRef(value=PATH)}

    result = apply_effects(entity, [effect], Repo())

    # A term now exists for this body, sitting on the path's first table — which is
    # what makes the wizard open on the d100 roll instead of the chooser.
    assert entity.pending_terms, "no term was written"
    term = next(iter(entity.pending_terms.values()))
    assert term.path_id == PATH
    assert term.current_step_id == "s1"
    assert term.current_table_id == "rt-earth-regions"
    assert "entered life path" in result.applied[0].summary


def test_entering_reads_the_path_from_its_reference():
    """The authored form is a reference, never the positional field ([[B261]])."""
    entity = _entity()
    effect = _effect(target="")           # positional deliberately empty
    effect.refs = {"life_path": TargetRef(value=PATH)}
    apply_effects(entity, [effect], Repo())
    assert entity.pending_terms


def test_an_unknown_path_says_so_and_writes_nothing():
    entity = _entity()
    effect = _effect()
    effect.refs = {"life_path": TargetRef(value="lp-nope")}

    result = apply_effects(entity, [effect], Repo())

    assert not entity.pending_terms, "a term was written for a path that does not exist"
    assert "could not enter" in result.applied[0].summary


def test_entering_with_no_path_says_so_rather_than_starting_something_arbitrary():
    entity = _entity()
    result = apply_effects(entity, [_effect()], Repo())
    assert not entity.pending_terms
    assert "no life path to enter" in result.applied[0].summary


def test_entering_replaces_only_the_same_bodys_term():
    """A term belongs to a body ([[B271]]): entering must not evict another body's."""
    other = NS(faction_id="", path_id="lp-other", projection_id="proj-b",
               current_step_id="s9", current_table_id="rt-other")
    entity = _entity(pending_terms={"proj-b": other})
    effect = _effect()
    effect.refs = {"life_path": TargetRef(value=PATH)}

    apply_effects(entity, [effect], Repo())

    assert entity.pending_terms["proj-b"] is other, "another body's term was disturbed"
    assert len(entity.pending_terms) == 2
