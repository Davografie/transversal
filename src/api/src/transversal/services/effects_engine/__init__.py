"""Effects engine — SFX registry, trigger matching, and execution.

Handles the full lifecycle of an SFX activation: matching a game event to the
SFX that listen for it, resolving targets and references, dispatching effects
through the applier, and persisting deferred work to the timer store.

The implementation is grouped by concern in this package's submodules; this
module re-exports every name it used to define, so
``from transversal.services.effects_engine import X`` is unchanged.
"""

from __future__ import annotations



# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_engine.events import (  # noqa: F401
    GameEvent,
    PendingSfxEffect,
    PendingSfxLoop,
    StructuredChoice,
    EventOutcome,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_engine.wire import (  # noqa: F401
    _EFFECT_CAMEL_FIELDS,
    effect_to_wire_dict,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_engine.shared import (  # noqa: F401
    log,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_engine.refs import (  # noqa: F401
    _bind_ref_value,
    resolve_refs,
    _substitute_effect_context,
    _resolved_id,
    _structured_choice,
    resolve_effect_spec_choices,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_engine.firing import (  # noqa: F401
    EffectApplier,
    _resolve_activation_source,
    _attach_continuation,
    _emit_sfx_triggered,
    _emit_sfx_ended,
    _emit_sfx_armed,
    _fire_context,
    _resolve_primary_targets,
    _apply_immediate_spec,
    _noop_applier,
)


# Re-exported for backwards compatibility (previously defined here).
from transversal.services.effects_engine.engine import (  # noqa: F401
    EffectsEngine,
)
