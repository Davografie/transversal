"""A location can be **carried** by an entity, not only contained by one.

One `super` edge says two things, and the endpoints' kinds are what tell them apart:

* **child location → parent location** — *a sub-place of*. The location tree.
* **child location → parent non-location** — ***carried by***. A cultivator's inner
  world; a formation anchored to its caster.

The second shape already existed live and already *worked*: the edge validator never
asked what kind the parent was, and `get_location_ancestors` / `navigate_from` both
walked it. What was wrong was everything downstream of it:

* `location_tree()` gap-filled an endpoint it had not scanned as
  ``{name: <the id>, universe: ""}``, so a carrier appeared as a **top-level node
  beside the universes, named by its key** — measured 2026-09-29, `character-20809`
  listed next to "Earth" and "Three Realms";
* nothing could answer *what does this entity carry?* or *who holds this place?*;
* and the validator, while it accepted a non-location parent, would equally have
  accepted a non-location **child** — the same corruption from the other side.

So this file pins the asymmetry, the two reads, and the tree's honesty about what a
carrier is. Live-ArangoDB tests build an isolated fixture and tear it down (never a
player character — the only live carrier is one), and skip when ArangoDB is
unavailable.
"""

from types import SimpleNamespace

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import EntityType

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:  # pragma: no cover - the whole class skips
    _repo = None
    HAVE_DB = False


# ── The rule, without a database ─────────────────────────────────────────────


def _entity(entity_id, name, entity_type):
    return SimpleNamespace(id=entity_id, name=name, type=entity_type)


class _FakeRepo:
    """Enough of a repository to ask `validate_relationship` one question."""

    def __init__(self, entities, ancestors=None):
        self._entities = entities
        self._ancestors = ancestors or {}

    def get_entity(self, entity_id):
        return self._entities.get(entity_id)

    def get_location_ancestors(self, location_id):
        return self._ancestors.get(location_id, [])


def _validate(entities, from_id, to_id, ancestors=None):
    from transversal.db.repository_mixins.relationships import RepositoryRelationships

    repo = _FakeRepo(entities, ancestors)
    return RepositoryRelationships.validate_relationship(repo, from_id, to_id, "super")


def test_a_location_may_be_carried_by_a_non_location():
    """The whole point: the parent need not be a place."""
    entities = {
        "char-1": _entity("char-1", "Phaos Tyish", EntityType.CHARACTER),
        "loc-1": _entity("loc-1", "Qihai", EntityType.LOCATION),
    }
    assert _validate(entities, "loc-1", "char-1") is None


def test_a_non_location_may_not_be_a_child_in_the_location_tree():
    """The other direction is corruption, not carrying — a character rendered as a
    leaf inside the location tree, which is the same mislabelling from the far side."""
    entities = {
        "char-1": _entity("char-1", "Phaos Tyish", EntityType.CHARACTER),
        "loc-1": _entity("loc-1", "Qihai", EntityType.LOCATION),
    }
    refusal = _validate(entities, "char-1", "loc-1")
    assert refusal is not None
    assert "not a location" in refusal
    assert "carried" in refusal, "the refusal should say what *is* allowed"


def test_an_asset_is_refused_as_a_child_too():
    entities = {
        "asset-1": _entity("asset-1", "The Jian", EntityType.ASSET),
        "loc-1": _entity("loc-1", "Qihai", EntityType.LOCATION),
    }
    assert _validate(entities, "asset-1", "loc-1") is not None


def test_the_loop_guards_still_hold():
    entities = {
        "loc-1": _entity("loc-1", "A", EntityType.LOCATION),
        "loc-2": _entity("loc-2", "B", EntityType.LOCATION),
    }
    assert _validate(entities, "loc-1", "loc-1") is not None, "self-parent"
    assert (
        _validate(entities, "loc-1", "loc-2", {"loc-2": ["loc-1"]}) is not None
    ), "re-parented under its own descendant"


def test_a_missing_child_is_not_refused_for_its_type():
    """An unknown id is the caller's problem, not a type error — and the type check
    must not swallow the loop guards that follow it."""
    assert _validate({}, "ghost", "loc-1") is None


# ── The reads, against live ArangoDB ─────────────────────────────────────────


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
class TestAgainstLiveArango:
    @pytest.fixture
    def world(self):
        """A carrier with an inner world, and a plain sub-location for control."""
        from transversal.services.entity_manager import EntityManager

        repo = _repo
        em = EntityManager(repository=repo)
        carrier = em.create(
            name="Carrier Probe", entity_type=EntityType.GMC, universe="earth"
        )
        inner = em.create(
            name="Carrier Probe Qihai", entity_type=EntityType.LOCATION, universe="earth"
        )
        outer = em.create(
            name="Carrier Probe Outer", entity_type=EntityType.LOCATION, universe="earth"
        )
        sub = em.create(
            name="Carrier Probe Sub", entity_type=EntityType.LOCATION, universe="earth"
        )
        # carried: location → non-location.  contained: location → location.
        repo.create_relationship(inner.id, carrier.id, "super")
        repo.create_relationship(sub.id, outer.id, "super")
        try:
            yield SimpleNamespace(
                carrier=carrier, inner=inner, outer=outer, sub=sub
            )
        finally:
            for child, parent in ((inner, carrier), (sub, outer)):
                repo.delete_relationship(child.id, parent.id, "super")
                repo.delete_entity(child.id)
                repo.delete_entity(parent.id)

    def test_the_carrier_end_is_readable(self, world):
        grouped = _repo.get_locations_carried_by([world.carrier.id])
        assert [e.id for e in grouped.get(world.carrier.id, [])] == [world.inner.id]
        assert [e.name for e in grouped[world.carrier.id]] == ["Carrier Probe Qihai"]

    def test_the_location_end_is_readable(self, world):
        carriers = _repo.get_location_carriers([world.inner.id])
        assert carriers[world.inner.id].id == world.carrier.id

    def test_containment_is_not_carrying(self, world):
        """Both are `super` edges, so the reads must tell them apart by the parent's
        kind — else every sub-place in the world would read as carried."""
        assert _repo.get_location_carriers([world.sub.id]) == {}
        assert _repo.get_locations_carried_by([world.outer.id]) == {}
        # The containing parent is a location, so it carries nothing.
        assert _repo.get_location_carriers([world.outer.id]) == {}

    def test_a_carrier_carries_nothing_when_it_carries_nothing(self, world):
        assert _repo.get_location_carriers([world.carrier.id]) == {}

    def test_the_validator_permits_the_live_arrangement(self, world):
        assert _repo.validate_relationship(world.inner.id, world.carrier.id, "super") is None

    def test_the_validator_refuses_the_reverse_arrangement(self, world):
        refusal = _repo.validate_relationship(world.carrier.id, world.inner.id, "super")
        assert refusal is not None and "not a location" in refusal

    def test_the_tree_names_a_carrier_and_marks_what_it_carries(self, world):
        """The defect this fixes: a carrier was gap-filled as `{name: <id>,
        universe: ""}`, so it appeared as a top-level node beside the universes
        **named by its key**, with `node_type: "location"`."""
        tree = _repo.location_tree()

        def find(nodes, wanted):
            for node in nodes:
                if node["id"] == wanted:
                    return node
                hit = find(node.get("children", []), wanted)
                if hit:
                    return hit
            return None

        node = find(tree, world.carrier.id)
        assert node is not None, "the carrier is missing from the tree entirely"
        assert node["node_type"] == "carrier"
        assert node["name"] == "Carrier Probe", "the carrier is named by its key"
        children = {c["id"]: c for c in node["children"]}
        assert world.inner.id in children
        assert children[world.inner.id]["node_type"] == "location"
        assert children[world.inner.id]["carried"] is True
        assert children[world.inner.id]["name"] == "Carrier Probe Qihai"

    def test_a_carrier_is_not_filed_among_a_universes_places(self, world):
        """A carrier is not a place in a universe, and the location it carries need
        not share its universe — so filing by the carrier's universe would silently
        re-home the world it carries."""
        tree = _repo.location_tree()

        def find(nodes, wanted):
            for node in nodes:
                if node["id"] == wanted:
                    return node
                hit = find(node.get("children", []), wanted)
                if hit:
                    return hit
            return None

        for universe in (n for n in tree if n["node_type"] == "universe"):
            assert find([universe], world.carrier.id) is None, (
                f"the carrier was filed into {universe['name']}'s hierarchy"
            )
            assert find([universe], world.inner.id) is None

    def test_an_ordinary_sub_location_still_carries_and_is_not_carried(self, world):
        """Control: the tree's new fields say nothing false about a plain place."""
        tree = _repo.location_tree()

        def find(nodes, wanted):
            for node in nodes:
                if node["id"] == wanted:
                    return node
                hit = find(node.get("children", []), wanted)
                if hit:
                    return hit
            return None

        sub = find(tree, world.sub.id)
        assert sub is not None and sub["node_type"] == "location"
        assert sub["carried"] is False


# ── The GraphQL surface ──────────────────────────────────────────────────────


def _info(em):
    """A minimal `strawberry.Info` — these two fields need `context["loaders"]`."""
    from transversal.api.graphql.loaders import build_loaders

    return SimpleNamespace(context={"loaders": build_loaders(em), "entity_manager": em})


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
class TestGraphQL:
    async def test_carried_locations_and_carrier_resolve(self):
        """`Entity.carriedLocations` and `Entity.carrier` are the two ends of one
        edge, and a panel needs both."""
        from transversal.api.graphql.type_defs.entities import Entity as GqlEntity
        from transversal.services.entity_manager import EntityManager

        repo = _repo
        em = EntityManager(repository=repo)
        carrier = em.create(
            name="GQL Carrier Probe", entity_type=EntityType.GMC, universe="earth"
        )
        inner = em.create(
            name="GQL Carrier Probe Qihai",
            entity_type=EntityType.LOCATION,
            universe="earth",
        )
        repo.create_relationship(inner.id, carrier.id, "super")
        try:
            info = _info(em)
            carried = await GqlEntity(
                id=carrier.id, type=carrier.type, name=carrier.name,
                razmerit=0, current_universe="earth",
            ).carried_locations(info)
            assert [e.id for e in carried] == [inner.id]
            assert carried[0].name == "GQL Carrier Probe Qihai"

            back = await GqlEntity(
                id=inner.id, type=inner.type, name=inner.name,
                razmerit=0, current_universe="earth",
            ).carrier(info)
            assert back is not None and back.id == carrier.id
        finally:
            repo.delete_relationship(inner.id, carrier.id, "super")
            repo.delete_entity(inner.id)
            repo.delete_entity(carrier.id)

    async def test_a_placed_location_has_no_carrier_field_value(self):
        from transversal.api.graphql.type_defs.entities import Entity as GqlEntity
        from transversal.services.entity_manager import EntityManager

        repo = _repo
        em = EntityManager(repository=repo)
        lone = em.create(
            name="GQL Lone Probe", entity_type=EntityType.LOCATION, universe="earth"
        )
        try:
            info = _info(em)
            lone_gql = GqlEntity(
                id=lone.id, type=lone.type, name=lone.name,
                razmerit=0, current_universe="earth",
            )
            assert await lone_gql.carrier(info) is None
            assert await lone_gql.carried_locations(info) == []
        finally:
            repo.delete_entity(lone.id)
