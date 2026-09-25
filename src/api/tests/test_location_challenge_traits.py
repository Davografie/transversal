"""[[B191]]: a zone inherits its location's challenge traits, nearest wins.

A zone is a pin to a child location, so the inheritance is a walk up the `super`
chain. The author's call (2026-09-25): inherit the **full pool**, and the child
keeps **no record** — it points at the parent's trait setting, so a die spent
anywhere is one pool being spent. The fold is where that rule lives, and the
`inherited` flag is what lets the viewer say where a pool comes from.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest import locations as locations_module
from transversal.api.rest.locations import router as locations_router
from transversal.db.repository_mixins.trait_settings import fold_challenge_traits, trait_visible_to
from transversal.domain import DieType, Polarity, RatingType, TraitSetting


def _ts(setting_id, owner, trait_id, rating=RatingType.CHALLENGE, dice=None, capacity=None,
        polarity=Polarity.POSITIVE):
    return TraitSetting(
        id=setting_id,
        entity_id=owner,
        trait_id=trait_id,
        traitset_id="set-1",
        rating_type=rating,
        polarity=polarity,
        dice=[DieType(d) for d in (dice or ["d8"])],
        capacity=[DieType(d) for d in capacity] if capacity else None,
    )


class TestTheInheritanceRule:
    def test_a_child_with_no_trait_of_its_own_inherits_the_parents_setting(self):
        parent = _ts("ts-parent", "district", "trait-curse", dice=["d10", "d6"])
        got = fold_challenge_traits(["room", "district"], {"district": [parent]})

        assert [t.id for t in got] == ["ts-parent"]
        # The inherited trait *is* the owner's edge: same id, same dice ledger,
        # and `entity_id` still names the parent. The child stores nothing.
        assert got[0].entity_id == "district"
        assert got[0].dice == [DieType.D10, DieType.D6]

    def test_the_childs_own_trait_replaces_the_parents_rather_than_stacking(self):
        own = _ts("ts-own", "room", "trait-curse", dice=["d6"])
        parent = _ts("ts-parent", "district", "trait-curse", dice=["d10"])
        got = fold_challenge_traits(["room", "district"], {"room": [own], "district": [parent]})

        assert [t.id for t in got] == ["ts-own"]
        assert [t.id for t in got] != ["ts-own", "ts-parent"]

    def test_a_chain_of_three_resolves_the_root_once(self):
        root = _ts("ts-root", "city", "trait-curse")
        got = fold_challenge_traits(["room", "district", "city"], {"city": [root]})
        assert [t.id for t in got] == ["ts-root"]

    def test_a_location_inherits_each_distinct_trait_from_wherever_it_is_defined(self):
        parent = _ts("ts-parent", "district", "trait-curse")
        root = _ts("ts-root", "city", "trait-fires")
        got = fold_challenge_traits(
            ["room", "district", "city"], {"district": [parent], "city": [root]}
        )
        assert sorted(t.id for t in got) == ["ts-parent", "ts-root"]

    def test_only_challenge_traits_are_inherited(self):
        static = _ts("ts-static", "district", "trait-smell", rating=RatingType.STATIC)
        resource = _ts("ts-res", "district", "trait-ammo", rating=RatingType.RESOURCE)
        challenge = _ts("ts-doom", "district", "trait-curse")
        got = fold_challenge_traits(
            ["room", "district"], {"district": [static, resource, challenge]}
        )
        assert [t.id for t in got] == ["ts-doom"]

    def test_a_location_with_no_ancestors_is_unchanged(self):
        own = _ts("ts-own", "room", "trait-curse")
        assert [t.id for t in fold_challenge_traits(["room"], {"room": [own]})] == ["ts-own"]
        assert fold_challenge_traits(["room"], {}) == []


class _Named:
    def __init__(self, name):
        self.name = name


class FakeRepo:
    def __init__(self, traits, hidden=None, known_to=None):
        self._traits = traits
        self._hidden = hidden or {}
        self._known_to = known_to or {}

    def get_location_challenge_traits(self, location_id):
        out = []
        for ts in self._traits:
            out.append(ts.model_copy(update={"known_to": self._known_to.get(ts.id, [])}))
        return out

    def get_trait(self, trait_id):
        return _Named({"trait-curse": "The Curse"}.get(trait_id, ""))

    def get_entity(self, entity_id):
        hidden = bool(self._hidden.get(entity_id, False))
        entity = _Named({"district": "Krasnoyarsk-45"}.get(entity_id, ""))
        entity.hidden = hidden
        return entity


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(locations_router)
    return TestClient(app)


def test_the_read_tells_the_viewer_where_an_inherited_pool_lives(client, monkeypatch):
    repo = FakeRepo([
        _ts("ts-own", "room", "trait-room", dice=["d6"]),
        _ts("ts-parent", "district", "trait-curse", dice=["d10"], capacity=["d12"],
            polarity=Polarity.NEGATIVE),
    ])
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)

    r = client.get("/api/v1/locations/room/challenge-traits")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["location_id"] == "room"
    own, inherited = data["traits"]

    assert own["inherited"] is False
    assert own["owner_location_id"] == "room" and own["owner_name"] == "room"

    # The point of the ticket: the child holds no setting of its own, so the
    # entry carries the *parent's* setting id — which is what a spend must use.
    assert inherited["inherited"] is True
    assert inherited["id"] == "ts-parent"
    assert inherited["owner_location_id"] == "district"
    assert inherited["owner_name"] == "Krasnoyarsk-45"
    assert inherited["name"] == "The Curse"
    assert inherited["dice"] == ["d10"] and inherited["capacity"] == ["d12"]
    assert inherited["polarity"] == "negative" and inherited["rating_type"] == "challenge"


def test_a_location_with_no_challenge_traits_reads_empty(client, monkeypatch):
    monkeypatch.setattr(locations_module, "_repo", lambda: FakeRepo([]))
    r = client.get("/api/v1/locations/room/challenge-traits")
    assert r.json() == {"location_id": "room", "viewer": None, "traits": []}


class TestVisibilityPerViewer:
    """[[B92]]: the human's fog-of-war rule, resolved in the payload."""

    def test_an_unhidden_owner_is_visible_to_everyone(self):
        assert trait_visible_to(False, [], "") is True
        assert trait_visible_to(False, [], "anyone") is True

    def test_a_hidden_owner_is_visible_only_to_those_known_to_it(self):
        assert trait_visible_to(True, ["kael"], "kael") is True
        assert trait_visible_to(True, ["kael"], "antonov") is False
        # A viewer that names nobody sees only the un-hidden set.
        assert trait_visible_to(True, ["kael"], "") is False

    def test_the_rule_is_the_owners_not_the_inheriting_zones(self, client, monkeypatch):
        # The inherited pool belongs to a hidden parent, so the zone cannot
        # un-hide it: a viewer outside `known_to` must not receive it.
        repo = FakeRepo(
            [_ts("ts-parent", "district", "trait-curse")],
            hidden={"district": True},
            known_to={"ts-parent": ["kael"]},
        )
        monkeypatch.setattr(locations_module, "_repo", lambda: repo)

        seen_by_kael = client.get("/api/v1/locations/room/challenge-traits?viewer=kael").json()
        assert [t["id"] for t in seen_by_kael["traits"]] == ["ts-parent"]
        assert seen_by_kael["traits"][0]["hidden"] is True
        assert seen_by_kael["traits"][0]["known_to"] == ["kael"]

        seen_by_antonov = client.get("/api/v1/locations/room/challenge-traits?viewer=antonov").json()
        assert seen_by_antonov["traits"] == []

    def test_omitting_the_viewer_returns_the_set_with_its_flags(self, client, monkeypatch):
        repo = FakeRepo([_ts("ts-parent", "district", "trait-curse")], hidden={"district": True})
        monkeypatch.setattr(locations_module, "_repo", lambda: repo)

        data = client.get("/api/v1/locations/room/challenge-traits").json()
        assert data["viewer"] is None
        assert len(data["traits"]) == 1
        assert data["traits"][0]["hidden"] is True
