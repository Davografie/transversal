"""The departure board: where a portal currently sends you ([[B323]]).

The human's design (2026-10-17): instead of a portal asking *where to?* when it is
fired, **the board is set when you arrive** — an ordinary `on_location_change` rule
at the airport points the portal somewhere, and stepping through just goes. Two
decisions are the spec: the value lives **on the edge** (not the place), and it is
**not persistent** (session state, so a restart forgets it and content is never
rewritten by play).

What these tests protect, in order:

* the store is campaign-scoped, and "no campaign" is a refusal — not a wildcard;
* the effect actually reaches the store through the ref machinery (a portal is an
  **edge**, resolved to its key; the destination is an **anchor**, settled once);
* every refusal is *reported*, because an effect that looks applied and set no
  board is the failure mode this area keeps producing.
"""

from types import SimpleNamespace

import pytest

from transversal.domain import Effect, EffectTiming, Entity, EntityType, TargetRef
from transversal.services.effects_applier.entry import apply_effects
from transversal.services.portal_board import (
    clear_portal_destinations,
    get_portal_destination,
    set_portal_destination,
)
from transversal.services.campaign_scope import use_campaign
from transversal.services.target_spec import LiteralStep, TargetSpec

A, B = "campaign-a", "campaign-b"
PORTAL = "edge:loc-air:loc-zurich:transversal"


@pytest.fixture(autouse=True)
def _clean():
    """Every test starts and ends with nobody's board set."""
    for campaign in (A, B):
        clear_portal_destinations(campaign)
    yield
    for campaign in (A, B):
        clear_portal_destinations(campaign)


# ── The store ────────────────────────────────────────

def test_the_board_is_set_and_read_within_a_campaign():
    assert get_portal_destination(PORTAL, A) is None
    assert set_portal_destination(PORTAL, "loc-zurich", A) is True
    assert get_portal_destination(PORTAL, A) == "loc-zurich"


def test_one_campaigns_board_is_not_anothers():
    """Two campaigns are two airports' worth of flights ([[B305]])."""
    set_portal_destination(PORTAL, "loc-zurich", A)
    assert get_portal_destination(PORTAL, B) is None

    set_portal_destination(PORTAL, "loc-cape-town", B)
    assert get_portal_destination(PORTAL, A) == "loc-zurich"
    assert get_portal_destination(PORTAL, B) == "loc-cape-town"


def test_the_board_follows_the_context_scope_when_none_is_named():
    """A handler never passes a campaign: it runs in the request's scope."""
    with use_campaign(A):
        assert set_portal_destination(PORTAL, "loc-zurich") is True
        assert get_portal_destination(PORTAL) == "loc-zurich"
    with use_campaign(B):
        assert get_portal_destination(PORTAL) is None


def test_no_campaign_means_no_board():
    """"No campaign" is a refusal, never "every campaign's"."""
    assert get_portal_destination(PORTAL, "") is None
    assert set_portal_destination(PORTAL, "loc-zurich", "") is False
    assert clear_portal_destinations("") == 0


def test_setting_a_board_again_moves_the_same_portal():
    """The rotating board: one portal has one destination, not a history."""
    set_portal_destination(PORTAL, "loc-zurich", A)
    set_portal_destination(PORTAL, "loc-cape-town", A)
    assert get_portal_destination(PORTAL, A) == "loc-cape-town"


def test_clearing_forgets_one_campaign_only():
    set_portal_destination(PORTAL, "loc-zurich", A)
    set_portal_destination(PORTAL, "loc-cape-town", B)
    assert clear_portal_destinations(A) == 1
    assert get_portal_destination(PORTAL, A) is None
    assert get_portal_destination(PORTAL, B) == "loc-cape-town"


# ── The effect ───────────────────────────────────────

class FakeRepo:
    """The three reads the two paths need: an edge, a place, and a place's name."""

    PLACES = {"loc-zurich": "Zurich", "loc-cape-town": "Cape Town"}

    def __init__(self, edge=None):
        self.edge = edge or {
            "id": PORTAL, "type": "transversal",
            "owner_id": "loc-air", "contact_id": "loc-zurich",
            "contact_name": "Zurich",
        }

    def get_entity(self, eid):
        if eid in self.PLACES:
            return SimpleNamespace(id=eid, name=self.PLACES[eid], type="location")
        return None

    def get_relationship_by_key(self, key):
        return self.edge if self.edge.get("id") == key else None

    def list_relationships_for_entity(self, eid):
        return [self.edge] if self.edge.get("owner_id") == eid else []

    # The applier asks a repository for these on other effects' paths.
    def get_traitsetting(self, tsid):
        return None

    def list_entities_by_type(self, entity_type):
        return [SimpleNamespace(id=pid, name=n, type="location")
                for pid, n in self.PLACES.items()]


def _subject():
    return Entity(id="loc-air", type=EntityType.LOCATION, name="Eindhoven Airport",
                  current_universe="earth")


def _effect(portal="literal", destination="literal"):
    """A board effect authored the way the editor writes it — as refs."""
    refs = {}
    if portal == "literal":
        refs["portal"] = TargetRef(spec=TargetSpec(
            steps=[LiteralStep(element="relationship", value=PORTAL)]))
    if destination == "literal":
        refs["owner"] = TargetRef(spec=TargetSpec(
            steps=[LiteralStep(element="location", value="loc-zurich")]))
    return Effect(timing=EffectTiming.IMMEDIATE, type="portal", action="set_destination",
                  refs=refs)


def test_the_arrival_effect_sets_the_board():
    """The end-to-end shape: refs in, board out.

    This is the test that would have caught a *silent* half-fix. The portal is an
    edge, and `resolve_refs` extracts a resolved value's id — if an edge's handle
    did not survive that, the effect would report "no portal named" and the board
    would stay empty while every unit test of the store passed.
    """
    with use_campaign(A):
        result = apply_effects(_subject(), [_effect()], FakeRepo())

    assert get_portal_destination(PORTAL, A) == "loc-zurich"
    assert [a.summary for a in result.applied] == [f"portal {PORTAL} now goes to Zurich"]


def test_the_board_is_edge_scoped_not_place_scoped():
    """Two portals at one airport are two boards — the human's first decision."""
    other = "edge:loc-air:loc-cape-town:transversal"
    with use_campaign(A):
        apply_effects(_subject(), [_effect()], FakeRepo())
        second = _effect()
        second.refs["portal"] = TargetRef(spec=TargetSpec(
            steps=[LiteralStep(element="relationship", value=other)]))
        apply_effects(_subject(), [second], FakeRepo(
            edge={"id": other, "type": "transversal", "owner_id": "loc-air",
                  "contact_id": "loc-cape-town", "contact_name": "Cape Town"}))

    assert get_portal_destination(PORTAL, A) == "loc-zurich"
    assert get_portal_destination(other, A) == "loc-zurich"


def test_the_effect_reports_when_it_names_no_portal():
    with use_campaign(A):
        result = apply_effects(_subject(), [_effect(portal=None)], FakeRepo())
    assert get_portal_destination(PORTAL, A) is None
    assert "no portal named" in result.applied[0].summary


def test_the_effect_reports_when_it_names_no_destination():
    with use_campaign(A):
        result = apply_effects(_subject(), [_effect(destination=None)], FakeRepo())
    assert get_portal_destination(PORTAL, A) is None
    assert "no destination" in result.applied[0].summary


def test_the_effect_reports_when_no_campaign_is_named():
    """Applied, but honestly: the board a background task would set belongs to
    nobody, so it says so instead of writing to a bucket nothing reads."""
    result = apply_effects(_subject(), [_effect()], FakeRepo())
    assert "no campaign scope" in result.applied[0].summary
    assert get_portal_destination(PORTAL, "") is None


# ── Authoring ────────────────────────────────────────

def test_the_action_is_authorable_and_reads_on_a_card():
    """A new action is three tables: the meta, its refs, and its card.

    The card matters because the *portal* is the half an author cannot infer —
    "set the portal to X" must not collapse to "set" — and the registry's guard
    tests read the same three tables.
    """
    from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY
    from transversal.services.effects_registry.cards import EFFECT_ACTION_CARDS

    meta = next(m for m in EFFECT_ACTION_REGISTRY
                if m.action_id == "set_portal_destination")
    assert (meta.effect_type, meta.effect_action) == ("portal", "set_destination")
    assert meta.group == "Travel"
    assert {r.name for r in meta.refs} == {"portal", "owner"}
    # The destination is an anchor: a board is one place, so a path that matched
    # three cities must not set three boards.
    owner = next(r for r in meta.refs if r.name == "owner")
    assert owner.anchor is True and owner.elements == ("location",)
    assert EFFECT_ACTION_CARDS[("portal", "set_destination")] == "set {target} to {owner}"
