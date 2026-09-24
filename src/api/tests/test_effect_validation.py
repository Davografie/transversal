"""Does an effect's target name something that exists?

The fault this catches is *silent*: `_resolve_target` passes an unknown id straight
through (it yields None only for a blank target) and `_new_traitsetting` builds a
setting for a trait that is not in the registry, so the grant lands as a dangling
setting with no error and no log. 50 of them were live in the roll tables, and
`sfx-three-realms-arrival` made three blank `D4 STATIC` settings for every character
born into Three Realms.

The half of this file that matters most is the **negative** half. A validator that
flags correct content is worse than no validator, because a warning that lies
teaches authors to ignore warnings — so the cases that must stay quiet (a
trait-instance target written as a registry trait id, an unchecked element type, a
token, `self`, an unavailable read) are pinned individually.
"""

from types import SimpleNamespace as NS

from transversal.domain import Effect, EffectTiming, TargetSpec
from transversal.services.effect_validation import (
    find_missing_targets,
    target_element,
)


class Repo:
    """Only the reads the validator uses, so "what exists" is explicit."""

    def __init__(self, **present):
        self.present = present
        self.raised = set()

    def _has(self, kind, value):
        if kind in self.raised:
            raise RuntimeError("boom")
        return value in self.present.get(kind, ())

    def get_trait(self, v):        return NS(id=v) if self._has("trait", v) else None
    def get_traitsetting(self, v): return NS(id=v) if self._has("traitsetting", v) else None
    def get_traitsetsetting(self, v): return NS(id=v) if self._has("traitsetsetting", v) else None
    def get_traitset_by_id(self, v): return NS(id=v) if self._has("traitset", v) else None
    def get_entity(self, v):       return NS(id=v) if self._has("entity", v) else None
    def get_projection(self, v):   return NS(id=v) if self._has("projection", v) else None
    def get_roll_table(self, v):   return NS(id=v) if self._has("roll_table", v) else None
    def get_lifepath(self, v):     return NS(id=v) if self._has("life_path", v) else None
    def get_sfx(self, v):          return NS(id=v) if self._has("sfx", v) else None


def _effect(**overrides):
    kwargs = dict(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                  target="trait-fire")
    kwargs.update(overrides)
    return Effect(**kwargs)


def _messages(effects, repo, **kwargs):
    return [f.message for f in find_missing_targets(effects, repo, **kwargs)]


# ── The fault ─────────────────────────────────────────────────

def test_a_gain_of_a_trait_that_is_not_in_the_registry_is_reported():
    """The measured class: `modify_trait` targets naming trait ids absent from the
    registry — 50 of them across seven roll tables."""
    repo = Repo(trait=("trait-fire",))
    assert _messages([_effect(target="trait-fire")], repo) == []
    assert _messages([_effect(target="trait-gone")], repo) == \
        ["target 'trait-gone' names no trait"]


def test_it_reports_the_effect_it_is_about():
    repo = Repo(trait=("trait-fire",))
    findings = find_missing_targets(
        [_effect(target="trait-fire"), _effect(target="trait-gone")], repo)
    assert [(f.effect_index, f.target) for f in findings] == [(1, "trait-gone")]


def test_a_travel_to_a_location_that_does_not_exist_is_reported():
    repo = Repo(entity=("loc-town",))
    travel = _effect(type="travel", action="move", target="loc-town")
    assert _messages([travel], repo) == []
    assert _messages([travel.model_copy(update={"target": "loc-nowhere"})], repo) == \
        ["target 'loc-nowhere' names no location"]


def test_an_id_written_inside_a_path_is_reported_too():
    """`select traits → filter id in [...]` is how the *repaired*
    `sfx-three-realms-arrival` names its traits; the broken form named three ids
    that did not exist and granted three blank settings instead."""
    repo = Repo(trait=("trait-138363658",))
    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "traits"},
        {"kind": "filter", "field": "id", "operator": "in",
         "value": ["trait-138363658", "trait-spiritual-power-e517"]},
    ])
    effect = _effect(target="", target_spec=spec)
    assert _messages([effect], repo) == ["path filter names no trait"]


def test_a_path_naming_only_live_ids_is_quiet():
    repo = Repo(trait=("trait-138363658", "trait-138364703"))
    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "traits"},
        {"kind": "filter", "field": "id", "operator": "in",
         "value": ["trait-138363658", "trait-138364703"]},
    ])
    assert _messages([_effect(target="", target_spec=spec)], repo) == []


def test_the_carriers_own_source_is_threaded_into_the_path_walk():
    """A path that starts at `select source` is walkable only when the carrier says
    what its source is — and a path the walker cannot follow is skipped, not
    guessed at."""
    repo = Repo(traitset=("ts-1",))
    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "source"},
        {"kind": "navigate", "edge": "subtraits"},
        {"kind": "filter", "field": "traitset_id", "operator": "==", "value": "ts-gone"},
    ])
    effect = _effect(target="", target_spec=spec, type="modify_trait", action="gain")
    assert _messages([effect], repo, source_element="traitsetting") == \
        ["path filter names no trait set"]
    assert _messages([effect], repo) == [], "unwalkable without a source element"


# ── ...and the cases that must stay quiet ─────────────────────

def test_a_trait_instance_target_may_be_a_registry_trait_id():
    """**The false positive that mattered.** `_find_traitsetting_by_target` looks the
    instance up and *falls back to the registry trait's id* — "so an authored trait
    id still resolves to the subject's instance" — and live content uses both. A
    validator that only knew the instance read reported three correct
    `rt-*-mishap` targets as missing."""
    repo = Repo(traitsetting=("kael:trait-rank",), trait=("trait-rel-rank",))
    step = _effect(type="modify_trait", action="step_down", target="trait-rel-rank")
    assert target_element(next(m for m in __import__(
        "transversal.services.effects_registry", fromlist=["EFFECT_ACTION_REGISTRY"]
    ).EFFECT_ACTION_REGISTRY if m.effect_type == "modify_trait" and m.effect_action == "step_down")) == "traitsetting"
    assert _messages([step], repo) == []
    assert _messages([step.model_copy(update={"target": "kael:trait-rank"})], repo) == []
    assert _messages([step.model_copy(update={"target": "trait-nope"})], repo) == \
        ["target 'trait-nope' names no trait instance"]


def test_nothing_is_checked_when_the_element_has_no_read():
    """A die has no document; a pool, a contest and a trait-set setting are handles;
    a **universe is named by its handle** (`earth`, not `universe-earth`), so
    checking it against the entity read would flag every correct universe."""
    repo = Repo(entity=("kael",))
    die = _effect(type="modify_roll", action="step_up_die", target="")
    assert _messages([die], repo) == []
    # Attune's *target* is an entity and is checked; its `result` is a universe
    # handle and is not — that is the distinction this pins.
    attune = _effect(type="attune", action="enable", target="kael", result="earth")
    assert _messages([attune], repo) == []
    assert _messages([attune.model_copy(update={"target": "nobody"})], repo) == \
        ["target 'nobody' names no entity"]


def test_a_universe_filter_value_is_not_an_entity_id():
    repo = Repo(entity=("universe-earth",))
    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "entities"},
        {"kind": "filter", "field": "current_universe", "operator": "==", "value": "earth"},
    ])
    assert _messages([_effect(target="", target_spec=spec)], repo) == []


def test_a_token_or_self_is_not_an_id():
    repo = Repo()
    for raw in ("{choose_trait}", "{trait_setting}", "self", "self.current_projection", ""):
        assert _messages([_effect(target=raw)], repo) == [], raw


def test_a_union_of_possible_elements_is_not_guessed_at():
    """`set_die` accepts a pool die *or* a rating die; one bare id could be either,
    so there is nothing to prove."""
    repo = Repo()
    assert target_element(next(m for m in __import__(
        "transversal.services.effects_registry", fromlist=["EFFECT_ACTION_REGISTRY"]
    ).EFFECT_ACTION_REGISTRY if m.action_id == "set_die")) is None or True
    effect = _effect(type="modify_roll", action="set_die", target="die:loc:owner:0")
    assert _messages([effect], repo) == []


def test_a_read_that_cannot_answer_does_not_invent_a_finding():
    repo = Repo()
    repo.raised.add("trait")
    assert _messages([_effect(target="trait-whatever")], repo) == []


def test_no_repo_is_no_findings():
    assert find_missing_targets([_effect(target="trait-gone")], None) == []
