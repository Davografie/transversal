"""Client-directed effect handlers ([[B132]]).

These two effects change nothing in the world: they tell a *device* to do
something — open a sheet, show a toast. So they have no inverse, nothing to
persist, and no duration; the undo of "your screen showed a toast" is not a
mechanism, it is the toast being dismissed.

The recipient is the effect's **subject** (``entity``, defaulting to the actor),
and the thing the action is *about* is its **target**. Keeping those two apart is
what lets "when you enter the court, the herald's sheet opens on the herald's
player's screen" be written at all.
"""

from __future__ import annotations

from transversal.domain import Effect
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    EffectsResult,
)
from transversal.services.effects_applier.targeting import (
    _effect_subject,
    _resolve_target,
    _track_subject,
)


def _recipient(subject) -> str:
    return getattr(subject, "id", "") or ""


def _apply_open_sheet(entity, effect: Effect, repo, result: EffectsResult) -> None:
    """Bring a character sheet up on the recipient's screen ([[B132]]).

    With no target the recipient's **own** sheet opens, which is the common case
    ("show me my sheet"); with one, somebody else's does — a GM handing a player
    the sheet they need to look at.
    """
    from transversal.services.client_actions import (
        client_action_payload,
        publish_client_action,
    )

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    target_id = _resolve_target(subject, effect, result, repo) or ""
    if target_id == "self":
        target_id = _recipient(subject)
    payload = client_action_payload(
        "open_sheet", _recipient(subject),
        target_id=target_id or _recipient(subject),
        sfx_id=str((effect.context or {}).get("sfx_id") or ""),
    )
    publish_client_action(payload)
    result.applied.append(AppliedEffect(
        effect, f"opened the sheet of {payload.get('target_id')} on {_recipient(subject)}"))


def _apply_toast(entity, effect: Effect, repo, result: EffectsResult) -> None:
    """Show a toast on the recipient's screen ([[B132]]).

    The text is the effect's ``result`` — the slot an action "produces" — so the
    card reads the same words the toast shows. ``sticky`` keeps it until it is
    dismissed (the action's default), and ``tap`` says what tapping it does:
    nothing, or open the target's sheet. Swipe-to-dismiss is the client's, and
    needs no field.
    """
    from transversal.services.client_actions import (
        client_action_payload,
        publish_client_action,
    )

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    message = (effect.result or "").strip()
    if not message:
        result.applied.append(AppliedEffect(effect, "no message to show"))
        return
    ctx = effect.context or {}
    tap = str(ctx.get("tap") or "none").lower()
    target_id = _resolve_target(subject, effect, result, repo) or ""
    if target_id == "self":
        target_id = _recipient(subject)
    payload = client_action_payload(
        "toast", _recipient(subject),
        target_id=target_id if tap == "open_sheet" else "",
        message=message,
        sticky=bool(ctx.get("sticky", True)),
        tap=tap if tap == "open_sheet" else "none",
        sfx_id=str(ctx.get("sfx_id") or ""),
    )
    publish_client_action(payload)
    result.applied.append(AppliedEffect(
        effect, f"toast on {_recipient(subject)}: {payload['message']}"))
