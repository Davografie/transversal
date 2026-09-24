"""Client-directed effects ([[B132]]) — actions that tell a *device* to do something.

Separate from the world-changing sections because they are a different kind of
thing: nothing in the game state changes, so none of them take a duration or an
inverse. What they need instead is a wire contract with the client, which lives in
``services/client_actions.py``.
"""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
)


ACTIONS: list[EffectActionMeta] = [
    EffectActionMeta(
        action_id="open_sheet",
        label="Open Character Sheet",
        description=(
            "Bring a character sheet up on the recipient's screen — their own when "
            "no target is named, otherwise somebody else's"
        ),
        category="either",
        effect_type="client",
        effect_action="open_sheet",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="entity", label="On Whose Screen", field_type="entity",
                          required=False),
            EffectFieldDef(name="target", label="Owner", field_type="text",
                          required=False),
        ],
        target_kind="entity",
    ),
    EffectActionMeta(
        action_id="show_toast",
        label="Show Toast",
        description=(
            "Show a message on the recipient's screen; sticky keeps it until it is "
            "dismissed, and a tap can open a chosen entity's sheet"
        ),
        category="either",
        effect_type="client",
        effect_action="toast",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="entity", label="On Whose Screen", field_type="entity",
                          required=False),
            EffectFieldDef(name="result", label="Message", field_type="text",
                          required=True, default=""),
        ],
        context_fields=[
            # Sticky is the *action's* nature ("sticky toast"), so it defaults on;
            # off is the plain auto-expiring toast the app already has.
            EffectFieldDef(name="sticky", label="Sticky (until dismissed)",
                          field_type="boolean", required=False, default="true"),
            # What a tap does. "open_sheet" is the one behaviour the app can honour
            # today; anything else is a client capability that does not exist yet,
            # and inventing option values here would promise what no client does.
            EffectFieldDef(name="tap", label="Tap Opens", field_type="select",
                          required=False, default="none",
                          options=["none", "open_sheet"]),
            EffectFieldDef(name="target", label="Tap Target", field_type="text",
                          required=False),
        ],
        target_kind="entity",
    ),
]
