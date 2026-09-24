"""Suppress — the removal half of the projection grant.

[[Active Projections Design Log]]: `active = {current} ∪ adds − removes`. Attune is
an **add**, suppress a **remove**, and a swap is the pair rather than a `replace`
flag. The suppression names a **specific** body — never "whatever is current" — so
it is stable and reversible and can never cut off a body the effect never saw.

The bug this file exists for: ending one kind of grant must not end the other. The
old match was on `(universe, scope)` with no `op`, so an attunement expiring could
silently un-suppress a body — a character's suppressed body would come back to life
because an unrelated rule's timer ran out.
"""

from types import SimpleNamespace

import transversal.services.effects_applier as applier
from transversal.domain import (
    AttunementOp,
    Effect,
    EffectTiming,
)
from transversal.services.effects_applier import EffectRegistry
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY
from transversal.services.effects_registry.cards import EFFECT_ACTION_CARDS
from transversal.services.sfx_text import effect_text


class Repo:
    """A repo with just the entities the handler touches (no Arango)."""

    def __init__(self, entities):
        self.entities = {e.id: e for e in entities}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def update_entity(self, entity):
        self.entities[entity.id] = entity

    def get_projection(self, pid):
        return None


def _entity(eid="kael"):
    return SimpleNamespace(id=eid, attunements=[])


def _apply(repo, effect, entity_id="kael"):
    """Register the core handlers against a throwaway registry and apply once."""
    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None,
                              transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=repo, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)
        applier.effect_registry.apply(effect, entity_id, "earth", {})
    finally:
        applier.effect_registry = original


def _grant(action, **overrides):
    kwargs = dict(timing=EffectTiming.IMMEDIATE, type="attune", action=action,
                  target="self")
    kwargs.update(overrides)
    return Effect(**kwargs)


# ── The declaration ───────────────────────────────────────────

def test_the_action_is_declared_beside_attune():
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "suppress")
    assert (meta.effect_type, meta.effect_action) == ("attune", "suppress")
    assert meta.target_kind == "entity"
    assert meta.supports_duration is True, "a suppression expires like any other grant"
    assert meta.inverse == ("attune", "unsuppress")
    # The body is named by the reference when there is one, and by the field when
    # there is not — the same precedence attune's universe has.
    result_field = next(f for f in meta.fields if f.name == "result")
    assert result_field.hidden_when_ref == "projection"
    # Scope is authorable (the "the laws here cut you off" case).
    assert [f.name for f in meta.context_fields] == ["scope"]


def test_the_card_says_suppress():
    assert EFFECT_ACTION_CARDS[("attune", "suppress")] == "suppress {result}"
    assert effect_text(_grant("suppress", result="the Earth body")) == \
        "suppress the Earth body"


def test_the_self_cycle_is_authorable_as_a_pair():
    """The human's decision: a swap is `attune` + `suppress`, two effects, no
    `replace` flag. That is only true if both exist and compose."""
    ids = {m.action_id for m in EFFECT_ACTION_REGISTRY}
    assert {"attune", "suppress"} <= ids


# ── The grant ─────────────────────────────────────────────────

def test_suppressing_writes_a_remove_grant_for_that_body():
    kael = _entity()
    repo = Repo([kael])
    _apply(repo, _grant("suppress", result="body-earth"))
    assert len(kael.attunements) == 1
    grant = kael.attunements[0]
    assert grant.op == AttunementOp.REMOVE
    assert grant.projection_id == "body-earth"
    # A suppression is a body, not a world: no universe is stored for it, or the
    # derived effective-universe view would read a projection id as one.
    assert grant.universe is None


def test_suppressing_twice_does_not_stack():
    kael = _entity()
    repo = Repo([kael])
    _apply(repo, _grant("suppress", result="body-earth"))
    _apply(repo, _grant("suppress", result="body-earth"))
    assert len(kael.attunements) == 1


def test_attuning_still_stores_the_world():
    """`enable` keeps its own shape — existing content and the derived
    effective-universe view depend on it."""
    kael = _entity()
    repo = Repo([kael])
    _apply(repo, _grant("enable", result="three_realms"))
    grant = kael.attunements[0]
    assert (grant.op, grant.universe, grant.projection_id) == (AttunementOp.ADD, "three_realms", None)


# ── Ending a grant ends the right one ─────────────────────────

def test_ending_an_attunement_does_not_lift_a_suppression():
    """**The bug.** `disable` used to match on `(universe, scope)` alone, so an
    attunement expiring stripped any grant with the same world — including a
    suppression, which is not even world-keyed."""
    kael = _entity()
    repo = Repo([kael])
    _apply(repo, _grant("suppress", result="body-earth"))
    _apply(repo, _grant("enable", result="three_realms"))
    assert len(kael.attunements) == 2

    _apply(repo, _grant("disable", result="three_realms"))
    remaining = kael.attunements
    assert len(remaining) == 1, "ending the attunement must leave the suppression standing"
    assert remaining[0].op == AttunementOp.REMOVE
    assert remaining[0].projection_id == "body-earth"


def test_ending_a_suppression_does_not_lift_an_attunement():
    """...and the mirror image, which the same fix covers."""
    kael = _entity()
    repo = Repo([kael])
    _apply(repo, _grant("enable", result="three_realms"))
    _apply(repo, _grant("suppress", result="body-earth"))

    _apply(repo, _grant("unsuppress", result="body-earth"))
    remaining = kael.attunements
    assert len(remaining) == 1
    assert remaining[0].op == AttunementOp.ADD
    assert remaining[0].universe == "three_realms"


def test_unsuppressing_only_the_named_body():
    kael = _entity()
    repo = Repo([kael])
    _apply(repo, _grant("suppress", result="body-earth"))
    _apply(repo, _grant("suppress", result="body-three-realms"))
    _apply(repo, _grant("unsuppress", result="body-earth"))
    assert [g.projection_id for g in kael.attunements] == ["body-three-realms"]


def test_a_suppression_is_scoped_like_an_attunement():
    """`domain` and `self` grant the same body differently, so ending one scope
    must not end the other."""
    kael = _entity()
    repo = Repo([kael])
    _apply(repo, _grant("suppress", result="body-earth", context={"scope": "self"}))
    _apply(repo, _grant("suppress", result="body-earth", context={"scope": "domain"}))
    assert len(kael.attunements) == 2

    _apply(repo, _grant("unsuppress", result="body-earth", context={"scope": "self"}))
    assert [str(g.scope.value) for g in kael.attunements] == ["domain"]
