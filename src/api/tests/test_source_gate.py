"""A rule's own source gates a roll trigger — and a disabled source needs no gate.

The author, 2026-10-13: *"Intuitively, I'd say the source would gate the trigger.
Also … if the source is traitsetting, but the actual trait instance SFX source is
disabled, then I'd also not expect the SFX to trigger."*

Only the first half became a change: `_source_was_added` answered solely
`on_pool_add`, so a trait-sourced `on_roll` rule fired on **every** roll — the one
live rule in that shape being `sfx-qi-condensation`. Measured first: exactly one live
rule is in the roll family with a trait-setting source, so the gate is narrow in
practice and its meaning is the author's to set. "Rolled" means **pooled** — a die
from the instance is in the pool, whatever became of it.

The second half is already true *because* of the first: a disabled trait instance
contributes no dice, so it cannot be in the pool. Writing it as a separate "disabled
sources never fire" check is not merely redundant, it is wrong — the portent
escalator is sourced on the disabled slot it exists to enable
(`on_challenge_completed`), and the full suite caught that when this was first
written.
"""

from __future__ import annotations

from transversal.domain import Effect, EffectTiming, SFX
from transversal.services.effects_engine import GameEvent
from transversal.services.effects_engine.engine import _source_matches


def _rule(trigger: str = "on_roll") -> SFX:
    return SFX(id="sfx-x", name="X", trigger=trigger, source_kind="trait_setting",
               effects=[Effect(timing=EffectTiming.IMMEDIATE, type="earn", action="razmerit")])


def _event(rolls=None, added=None) -> GameEvent:
    return GameEvent(type="on_roll", entity_id="kael", universe="three_realms",
                     context={"rolls": rolls or [], "added_dice": added or []})


def test_a_trait_sourced_rule_fires_only_when_its_die_is_in_the_pool():
    pooled = _event(rolls=[{"ts_id": "ts-other"}, {"ts_id": "ts-qi"}])
    not_pooled = _event(rolls=[{"ts_id": "ts-other"}])
    assert _source_matches(_rule(), pooled, "ts-qi", "traitsetting") is True
    assert _source_matches(_rule(), not_pooled, "ts-qi", "traitsetting") is False


def test_a_pool_without_the_source_does_not_fire_it():
    """The old behaviour: any roll at all fired it, pool or no pool."""
    assert _source_matches(_rule(), _event(rolls=[{"ts_id": "ts-other"}]), "ts-qi",
                           "traitsetting") is False


def test_an_event_with_no_pool_is_not_refused():
    """Deliberate tolerance: a synthetic or non-roller activation carries no pool, so
    there is nothing to decide. A real roll always carries it — every roll-family
    trigger may read `rolls` (`conditions.py`) — which is where the gate is exact."""
    assert _source_matches(_rule(), _event(), "ts-qi", "traitsetting") is True


def test_a_disabled_source_cannot_be_pooled_so_a_roll_rule_does_not_fire():
    """A disabled instance contributes no dice, so it is absent from the pool: the
    author's second expectation, satisfied by the first gate rather than a second."""
    assert _source_matches(_rule(), _event(rolls=[{"ts_id": "ts-other"}]), "ts-qi",
                           "traitsetting") is False


def test_a_trigger_about_a_disabled_trait_still_fires():
    """The portent escalator: `on_challenge_completed`, sourced on the disabled slot it
    exists to enable. It must fire — the disabled state is its *subject*, not a gate."""
    assert _source_matches(_rule("on_challenge_completed"), _event(), "ts-qi",
                           "traitsetting") is True


def test_a_source_that_is_not_a_trait_instance_is_not_gated():
    """`entity`, `table`, `location` … have no "was it rolled?" — and for an entity the
    roller *is* the source, so gating it would be a no-op at best."""
    assert _source_matches(_rule(), _event(), "kael", "entity") is True
    assert _source_matches(_rule(), _event(), "table", "") is True


def test_the_pool_add_case_still_asks_the_just_added_dice():
    rule = _rule("on_pool_add")
    assert _source_matches(rule, _event(added=[{"ts_id": "ts-qi"}]), "ts-qi",
                           "traitsetting") is True
    assert _source_matches(rule, _event(added=[{"ts_id": "ts-other"}]), "ts-qi",
                           "traitsetting") is False
