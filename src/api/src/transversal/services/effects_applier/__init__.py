"""Effects applier — registry-based dispatch for Effect records.

Rather than hardcoding if/elif for each effect type, the applier maintains a
registry of handlers keyed by (type, action). New handlers can be registered at
any time — by core services, by universe-specific modules, or by content
plugins.

The implementation is grouped by concern in this package's submodules; this
module re-exports every name it used to define, so
``from transversal.services.effects_applier import X`` is unchanged.
"""

from __future__ import annotations



# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.datatypes import (  # noqa: F401
    AppliedEffect,
    PendingChoice,
    EffectsResult,
    SOURCE_CONTEXT_KEY,
    SOURCE_ELEMENT_CONTEXT_KEY,
    BINDINGS_CONTEXT_KEY,
    ACTIVATION_CONTEXT_KEY,
    EFFECT_NOTES_CONTEXT_KEY,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.trait_helpers import (  # noqa: F401
    _resolve_traitset_id,
    _trait_owner,
    _find_traitsetting,
    _find_traitsetting_by_target,
    _step_up,
    _step_down_one,
    _steps,
    _has_steps,
    _step_up_trait,
    _die,
    _die_opt,
    _ctx,
    _rating_type,
    _new_traitsetting,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.targeting import (  # noqa: F401
    context_choice,
    _SELF_FIELDS,
    _parse_self_field,
    _resolve_target,
    _effect_subject,
    _track_subject,
    resolve_choice,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.reverts import (  # noqa: F401
    _queue_trait_revert,
    _queue_entity_revert,
    _queue_explicit,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.handlers_traits import (  # noqa: F401
    _apply_gain,
    _replicate_traitsetting,
    _apply_copy_trait,
    _apply_move_trait,
    _apply_gain_or_step_up,
    _apply_cortex_gain,
    _apply_step_up,
    _apply_step_down,
    _maybe_complete_challenge,
    _apply_remove,
    _apply_reveal,
    _resolve_learners,
    _apply_discover,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.handlers_dice import (  # noqa: F401
    _apply_add_die,
    _apply_remove_die,
    _apply_reduce_by_effect,
    _apply_increase_by_effect,
    _apply_set,
    _apply_disable,
    _apply_enable,
    _apply_toggle,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.handlers_pools import (  # noqa: F401
    _find_traitsetsetting,
    _apply_set_traitset_limit,
    _apply_dice_limit,
    _apply_set_hitch_threshold,
    _resolve_pool,
    _apply_add_dice,
    _add_trait_rating_to_pool,
    _apply_add_trait_rating,
    _resolve_pool_ref,
    _roll_stored_pool,
    _apply_roll_pool,
    _apply_resolve_pool,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.handlers_world import (  # noqa: F401
    _apply_attune_projection,
    _apply_attune_universe,
    _next_projection_id,
    _apply_create_projection,
    _apply_restore_projection,
    _apply_set_location,
    _apply_travel,
    _apply_cancel_scheduled_event,
    _apply_relationship_create,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.handlers_economy import (  # noqa: F401
    _apply_earn,
    _apply_spend,
    _apply_transfer,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.registry import (  # noqa: F401
    EffectRegistry,
    EffectHandler,
    _register_core_handlers,
    _razmerit_entity,
)

# The global handler registry. It lives here, at the package root, because both
# production code and tests reach it as ``effects_applier.effect_registry`` and
# swap it by rebinding that attribute; the submodules resolve it from this module
# at call time, so a rebind stays effective everywhere.
effect_registry = EffectRegistry()


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_applier.entry import (  # noqa: F401
    apply_effects,
    resolve_effect_entity,
    resolve_branch_effects,
    branch_options,
    resolve_effect_owner,
    resolve_effect_result,
    _resolve_entity_spec,
    _MUTATION_HANDLERS,
)
