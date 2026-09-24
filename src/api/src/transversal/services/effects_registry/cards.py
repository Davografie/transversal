"""Card-text templates, keyed by (effect_type, effect_action).

Split out of ``effects_registry.py``."""




EFFECT_ACTION_CARDS: dict[tuple[str, str], str] = {
    ("modify_roll", "play_as_rating"): "play {target} as {result}",
    ("modify_roll", "double_die"): "double {target}",
    ("modify_roll", "split_die"): "split {target}",
    ("modify_roll", "reroll_die"): "reroll {target}",
    ("modify_roll", "set_die"): "set {target} to {result}",
    # The step-die pair needs its target on the card: an effect that names a die
    # (usually by a path) with no card template fell back to the action's own
    # words — "step down die" — which said nothing about *which* die.
    ("modify_roll", "step_up_die"): "step up {target}",
    ("modify_roll", "step_down_die"): "step down {target}",
    ("modify_trait", "step_up"): "step up {target}",
    ("modify_trait", "step_down"): "step down {target}",
    ("modify_trait", "gain_or_step_up"): "gain or step up {target}",
    ("modify_trait", "disable"): "disable {target}",
    ("modify_trait", "gain"): "gain {target}",
    ("modify_trait", "gain_relationship"): "gain {target} on your tie to {owner}",
    ("modify_trait", "gain_subtrait"): "gain {target} under {owner}",
    ("modify_trait", "remove"): "remove {target}",
    ("modify_trait", "cortex_gain"): "gain {target} as a complication at {result}",
    # "a {result} trait" reads wrong for `empty` ("a empty trait"), and the
    # template cannot pick an article per value; naming the rating type
    # outright reads correctly for all four.
    ("modify_trait", "set_rating_type"): "change the rating type of {target} to {result}",
    ("modify_trait", "add_die"): "add a {result} die to {target}",
    ("modify_trait", "change"): "change {target} into {result}",
    ("modify_trait", "copy"): "give {target} a copy of {result}",
    ("modify_trait", "move"): "move {result} to {target}",
    ("modify_trait", "reduce_by_effect"): "reduce {target} by the effect die",
    ("modify_trait", "increase_by_effect"): "increase {target} by the effect die",
    ("transfer_razmerit", "earn"): "gain {result} razmerit",
    ("transfer_razmerit", "spend"): "spend {result} razmerit",
    ("transfer_razmerit", "transfer"): "transfer {result} razmerit to {target}",
    ("modify_pool", "add_dice"): "add dice to {target}",
    ("modify_pool", "add_trait_rating"): "add the trait's rating dice to {target}",
    # No "from the pool": a die has two homes now, and the target phrase says
    # which one ("remove the highest rating die of your trait instances").
    ("modify_roll", "remove_die"): "remove {target}",
    ("modify_pool", "resolve"): "resolve {target}",
    # The limit is a *choice* (total vs effect), so the card has to carry it —
    # otherwise two effects that do different things read identically.
    ("modify_dice_limit", "increase"): "increase the {limit} dice limit by {result}",
    ("modify_dice_limit", "decrease"): "decrease the {limit} dice limit by {result}",
    ("entity", "targeting_ban"): "impose a targeting ban on {target}",
    ("contest", "start"): "start a contest with {target}",
    ("entity", "learn"): "learn {target}",
    ("relationship", "create"): "create a relationship with {target}",
    ("attune", "enable"): "attune {target} to {result}",
    ("attune", "suppress"): "suppress {result}",
    ("location", "set"): "move to {target}",
    ("set_destination", "set"): "grant directions to {target}",
    ("life_path", "discover"): "discover the {target} life path",
    ("roll_table", "menu"): "roll on {target}",
    # The granted rule reads as its own name (resolved from the registry), and
    # whoever receives it is the clause's subject — see ``_effects_text``.
    ("sfx", "grant"): "gain {target}",
}
