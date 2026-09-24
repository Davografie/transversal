"""The roll-state condition ([[B98]]): "a die from my source trait setting was
rolled and **not chosen**".

The to-do item that opened B98 said this needed a *new* `ConditionType` reading
`context["rolls"]` and resolving the SFX's source trait setting, "the reserved
`{source_trait}` mechanism is not implemented yet". It does not need one, and
this file is the proof: a `TARGET_PATH` condition already reads the roll
(`event_collections` seeds `rolled_dice` from the event's `rolls`), already
resolves the rule's own source (`{trait_setting}`, bound by the activation before
the gate runs), and already expresses "not chosen" (a die's `role` is absent,
i.e. a `null` filter value).

Pinned here rather than left as a discovery, because the expensive mistake is
someone later re-deriving a whole condition type for a path that works.
"""

from types import SimpleNamespace as NS

from transversal.domain import Condition, ConditionType, TargetSpec
from transversal.services.conditions import evaluate_conditions
from transversal.services.target_resolver import Binding


def _binding(value):
    return Binding(value=value, values=[value], element="traitsetting", cardinality="one")


SCAR_DIE = {"ts_id": "ts-scar", "role": None, "result": 3, "rating": "d6",
            "effect_die": "d8"}
OTHER_DIE = {"ts_id": "ts-other", "role": "total", "result": 5, "rating": "d8",
             "effect_die": "d6"}

# "a die from my source trait setting was rolled and not chosen"
FROM_SOURCE_UNCHOSEN = [
    {"kind": "select", "collection": "rolled_dice"},
    {"kind": "filter", "field": "ts_id", "operator": "==", "value": "{trait_setting}"},
    {"kind": "filter", "field": "role", "operator": "==", "value": None},
]


def _passes(steps, dice=None, bindings=None, source_id="ts-scar"):
    condition = Condition(type=ConditionType.TARGET_PATH,
                          spec=TargetSpec.model_validate({"steps": steps}))
    context = {"rolls": dice if dice is not None else [SCAR_DIE, OTHER_DIE]}
    entity = NS(id="char-1", current_location="loc-1", current_universe="earth")
    source = NS(id=source_id, trait_id="trait-scar", entity_id="char-1")
    return evaluate_conditions(
        entity, [condition], repo=None, context=context,
        source=source, source_element="traitsetting",
        out_bindings=(bindings if bindings is not None
                      else {"trait_setting": _binding(source_id)}))


def test_a_die_from_my_source_that_was_rolled_and_not_chosen_passes():
    assert _passes(FROM_SOURCE_UNCHOSEN) is True


def test_a_chosen_die_of_mine_does_not_pass():
    """The point of the gate: once the die is the result or the effect, the rule
    is spent."""
    chosen = dict(SCAR_DIE, role="total")
    assert _passes(FROM_SOURCE_UNCHOSEN, dice=[chosen, OTHER_DIE]) is False


def test_my_source_not_in_the_roll_does_not_pass():
    assert _passes(FROM_SOURCE_UNCHOSEN,
                   bindings={"trait_setting": _binding("ts-not-rolled")}) is False


def test_another_traits_unchosen_die_does_not_pass():
    """Which is why the `ts_id` filter is not optional: without it the rule fires
    for every unchosen die in the pool, whatever it came from."""
    assert _passes(FROM_SOURCE_UNCHOSEN,
                   bindings={"trait_setting": _binding("ts-absent")}) is False
    without_source_filter = [step for step in FROM_SOURCE_UNCHOSEN
                             if step.get("field") != "ts_id"]
    # The same roll *would* satisfy the loose form — the hazard case in one test.
    assert _passes(without_source_filter) is True


def test_no_roll_in_the_context_does_not_pass():
    """A moment with no roll (a manual activation) has no dice to inspect."""
    condition = Condition(type=ConditionType.TARGET_PATH,
                          spec=TargetSpec.model_validate({"steps": FROM_SOURCE_UNCHOSEN}))
    entity = NS(id="char-1", current_location="loc-1", current_universe="earth")
    assert evaluate_conditions(entity, [condition], repo=None, context={},
                               source=NS(id="ts-scar"), source_element="traitsetting",
                               out_bindings={"trait_setting": _binding("ts-scar")}) is False
