"""Client-directed effect actions — the SSE contract ([[B132]]).

Some effects act on the **client** rather than on game state: bring a character
sheet up on someone's screen, or show a toast that stays until it is dismissed.
Nothing about the world changes, so there is no revert and no persistence — the
whole effect is "tell a device to do something".

Two homes, on purpose:

  - :func:`publish_client_action` here is the **contract** — one place that names
    the event and shapes its payload, so a rule and a client cannot drift;
  - the applier handlers (``effects_applier/handlers_client.py``) are the
    *decision* — who is told, and what about.

The event goes to every active session and carries the **recipient**, rather than
being narrowly addressed: the bus is session-scoped and the client already filters
by the ids in each payload (``trait_updated`` names its entity the same way). A
client that is not the recipient ignores it, which is also what makes the same
event safe to replay to a reconnecting tab.

Payload (all ids are entity ids):

    action        "open_sheet" | "toast"
    recipient_id  whose screen reacts
    target_id     the entity the action is about ("whoses sheet", a tap target)
    message       toast text
    sticky        toast stays until dismissed
    tap           what tapping the toast does: "none" | "open_sheet"
    sfx_id        provenance, for dedupe and for saying where a toast came from
"""

from __future__ import annotations

from typing import Any


#: The SSE event every client-directed effect publishes under.
CLIENT_ACTION_EVENT = "client_action"


def client_action_payload(
    action: str,
    recipient_id: str,
    *,
    target_id: str = "",
    message: str = "",
    sticky: bool = False,
    tap: str = "none",
    sfx_id: str = "",
) -> dict[str, Any]:
    """The wire shape of one client action, with the empties left out.

    Absent keys rather than null ones: a client reading ``message`` only for a
    toast should not have to tell "no message" from "a toast with an empty one".
    """
    payload: dict[str, Any] = {"action": action, "recipient_id": recipient_id}
    if target_id:
        payload["target_id"] = target_id
    if message:
        payload["message"] = message
    if sticky:
        payload["sticky"] = True
    if tap and tap != "none":
        payload["tap"] = tap
    if sfx_id:
        payload["sfx_id"] = sfx_id
    return payload


def publish_client_action(payload: dict[str, Any]) -> None:
    """Publish one built client action to every active session.

    Takes the payload rather than building it, so a handler reports the *same*
    object it sent (and a test can assert the wire shape without a subscriber or a
    return value to trust).
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(event=CLIENT_ACTION_EVENT, session_id=s.id, data=payload))
