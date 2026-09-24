"""The guided route: directions granted by an effect, and ended by arriving.

[[Guided Route]] splits the feature across two roles. Navigation's half (the
destination field, the route read, the viewer's next hop) is built; this is the
effects half: the `set_destination` action, its inverse, and the arrival that ends
the guidance.

The part worth pinning is the *comparison*: guidance ends when the character
stands on the destination, not when they move. A route runs through places and a
character with an objective may make a side trip, so "any location change clears
it" would retire the directions the first time they went anywhere.
"""

from types import SimpleNamespace as NS

from transversal.domain import Effect, EffectTiming, Entity, EntityType
from transversal.services.effects_commit import commit_effects
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY
from transversal.services.effects_registry.cards import EFFECT_ACTION_CARDS
from transversal.services.guided_route import clear_arrived_destination
from transversal.services.sfx_text import effect_text


class Repo:
    """Enough repository for the effect path (mirrors ``test_effects_commit``)."""

    def __init__(self, entities, graph=None):
        self.entities = {e.id: e for e in entities}
        # An undirected location graph: ``{location: [neighbours]}``.
        self.graph = {k: list(v) for k, v in (graph or {}).items()}
        self.updated = []

    def list_all_entities(self):
        return list(self.entities.values())

    def get_location_distances_from(self, origin, targets, exclude_hidden=False):
        """BFS over the fixture graph — the shape, not the implementation (the real
        graph and its weights are pinned in ``test_location_routes``)."""
        targets = {t for t in targets if t}
        dist = {origin: 0} if origin else {}
        frontier = [origin] if origin else []
        while frontier:
            nxt = []
            for node in frontier:
                for neighbour in self.graph.get(node, []):
                    if neighbour not in dist:
                        dist[neighbour] = dist[node] + 1
                        nxt.append(neighbour)
            frontier = nxt
        return {t: dist[t] for t in targets if t in dist}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def update_entity(self, entity):
        self.updated.append(entity.id)
        return entity

    def get_projection(self, pid):
        return None

    def list_all_scheduled_events(self):
        return []

    def list_scheduled_events(self, **kwargs):
        return []


def _entity(eid="kael", **overrides):
    kwargs = dict(id=eid, type=EntityType.CHARACTER, name="Kael",
                  current_universe="earth", current_location="loc-a")
    kwargs.update(overrides)
    return Entity(**kwargs)


def _directions(target="goblin-cave", entity="", **overrides):
    kwargs = dict(timing=EffectTiming.IMMEDIATE, type="set_destination", action="set",
                  target=target, entity=entity)
    kwargs.update(overrides)
    return Effect(**kwargs)


# ── The declaration ───────────────────────────────────────────

def test_the_action_is_declared_beside_travel_and_set_location():
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "set_destination")
    assert (meta.effect_type, meta.effect_action) == ("set_destination", "set")
    assert meta.target_kind == "location"
    # The destination is the *target*; who is being told is the subject — the same
    # shape travel and set_location already use, which is why they share the field.
    assert [f.name for f in meta.fields] == ["entity", "target"]
    assert meta.supports_duration is True
    assert meta.inverse == ("set_destination", "clear")
    assert meta.inverse_captures_prior is True


def test_clearing_is_an_inverse_and_not_a_verb_the_editor_offers():
    """`clear` is how directions end, never something an author reaches for."""
    assert not [m for m in EFFECT_ACTION_REGISTRY
                if m.effect_type == "set_destination" and m.effect_action == "clear"]


def test_the_card_says_what_it_grants():
    assert EFFECT_ACTION_CARDS[("set_destination", "set")] == "grant directions to {target}"
    # A realistic resolver: the real one answers None for an empty id, and a stub
    # that answers a name for *anything* invents a duplicate clause.
    names = {"goblin-cave": "the Goblin Cave"}
    assert effect_text(_directions(), resolve=lambda i: names.get(i)) == \
        "grant directions to the Goblin Cave"


# ── Applying ──────────────────────────────────────────────────

def test_directions_are_written_on_the_subject():
    kael = _entity()
    repo = Repo([kael])
    commit_effects(kael, [_directions()], repo)
    assert kael.destination_location == "goblin-cave"
    assert "kael" in repo.updated


def test_directions_can_be_granted_to_someone_else():
    """The party-wide brief is one effect over several subjects, so the subject is
    not necessarily the entity that applied it."""
    kael, mira = _entity(), _entity("mira", name="Mira")
    repo = Repo([kael, mira])
    commit_effects(kael, [_directions(entity="mira")], repo)
    assert mira.destination_location == "goblin-cave"
    assert kael.destination_location is None
    assert "mira" in repo.updated, "a cross-entity subject must be persisted"


def test_the_undo_restores_what_the_guidance_replaced():
    """Pointing someone somewhere new and then ending *that* guidance leaves the
    earlier objective standing — which is what expiring the second rule means."""
    kael = _entity(destination_location="old-ruin")
    repo = Repo([kael])
    commit_effects(kael, [_directions()], repo)
    assert kael.destination_location == "goblin-cave"

    from transversal.services.scheduled_events import build_revert

    revert = build_revert(_directions(), prior_result="old-ruin")
    assert (revert.type, revert.action) == ("set_destination", "clear")
    assert revert.result == "old-ruin", "the declared `inverse_captures_prior`"
    commit_effects(kael, [revert], repo)
    assert kael.destination_location == "old-ruin"


def test_an_expiry_with_nothing_before_it_clears_outright():
    kael = _entity()
    repo = Repo([kael])
    commit_effects(kael, [_directions()], repo)
    from transversal.services.scheduled_events import build_revert

    commit_effects(kael, [build_revert(_directions(), prior_result="")], repo)
    assert kael.destination_location is None


# ── Arriving ──────────────────────────────────────────────────

def test_arriving_on_the_destination_ends_the_guidance():
    kael = _entity(destination_location="goblin-cave")
    repo = Repo([kael])
    assert clear_arrived_destination(repo, "kael", "goblin-cave") is True
    assert kael.destination_location is None


def test_arriving_somewhere_else_leaves_the_guidance_standing():
    """The whole point of comparing against *the destination*: a route runs
    through places, and a side trip is not an arrival."""
    kael = _entity(destination_location="goblin-cave")
    repo = Repo([kael])
    assert clear_arrived_destination(repo, "kael", "the-crossroads") is False
    assert kael.destination_location == "goblin-cave"


def test_an_arrival_with_nothing_to_do_with_guidance_is_a_quiet_no_op():
    """Most arrivals are unremarkable — no destination, no entity, no location."""
    kael = _entity()
    repo = Repo([kael])
    assert clear_arrived_destination(repo, "kael", "loc-a") is False
    assert clear_arrived_destination(repo, "kael", None) is False
    assert clear_arrived_destination(repo, "nobody", "loc-a") is False
    assert clear_arrived_destination(repo, None, "loc-a") is False


def test_the_arrival_hook_runs_on_the_dispatch_every_move_passes_through():
    """Clearing rides `location_changed` rather than a new event, so it happens
    however the character got there — a portal, a GM placement, an effect. This
    exercises the one dispatch path, not the helper directly."""
    from transversal.services.scheduled_events import dispatch_event

    kael = _entity(destination_location="goblin-cave")
    repo = Repo([kael])
    dispatch_event(repo, "location_changed", entity_id="kael", universe="earth",
                   context={"from_location": "loc-a", "to_location": "goblin-cave",
                            "universe": "earth", "arrival_kind": "move"})
    assert kael.destination_location is None, "arriving ends the guidance"

    # ...and passing through somewhere else does not.
    mira = _entity("mira", name="Mira", destination_location="goblin-cave")
    repo2 = Repo([mira])
    dispatch_event(repo2, "location_changed", entity_id="mira", universe="earth",
                   context={"from_location": "loc-a", "to_location": "the-crossroads",
                            "universe": "earth", "arrival_kind": "move"})
    assert mira.destination_location == "goblin-cave"


# ── Directions that lead nowhere ──────────────────────────────
#
# The refusal fires at the **attach**, because that is the moment the origin
# exists: a rule is authored and then given a home, and "the mayor tells you the
# way" is only meaningful once we know which place the mayor speaks from.

def _place(eid, name, sfx_ids=None, **overrides):
    kwargs = dict(id=eid, type=EntityType.LOCATION, name=name,
                  current_universe="earth", current_location=None,
                  sfx_ids=list(sfx_ids or []))
    kwargs.update(overrides)
    return Entity(**kwargs)


AZURE, CROSSROADS, CAVE, ISLE = ("azure-dawn", "the-crossroads", "goblin-cave", "lost-isle")


def _route_world(sfx_ids=("sfx-guide",)):
    """Azure Dawn → the Crossroads → the Goblin Cave; Lost Isle connects to nothing."""
    repo = Repo(
        [_place(AZURE, "Azure Dawn", sfx_ids), _place(CROSSROADS, "the Crossroads"),
         _place(CAVE, "the Goblin Cave"), _place(ISLE, "Lost Isle")],
        graph={AZURE: [CROSSROADS], CROSSROADS: [AZURE, CAVE], CAVE: [CROSSROADS]},
    )
    return repo


def _guide(target, source_kind="location", **overrides):
    from transversal.domain import SFX

    kwargs = dict(id="sfx-guide", name="Ask the Mayor", trigger="manual",
                  source_kind=source_kind, effects=[_directions(target=target)])
    kwargs.update(overrides)
    return SFX(**kwargs)


def test_a_reachable_destination_attaches():
    from transversal.services.sfx_owner import attach_refusal

    assert attach_refusal(_guide(CAVE), "location", AZURE, _route_world()) is None


def test_an_unreachable_destination_is_refused_at_the_attach():
    """The GM must not be able to author "ask the mayor for the way" that leads
    nowhere — the map would light nothing and the rule would look fine."""
    from transversal.services.sfx_owner import attach_refusal

    reason = attach_refusal(_guide(ISLE), "location", AZURE, _route_world())
    assert reason, "directions to a place with no route must be refused"
    assert "Azure Dawn" in reason and "Lost Isle" in reason


def test_the_refusal_names_the_place_the_guidance_starts_from():
    """Measuring from the owner is the point: the same destination is fine from a
    place that can reach it."""
    from transversal.services.sfx_owner import attach_refusal

    repo = _route_world()
    assert attach_refusal(_guide(ISLE), "location", AZURE, repo)
    assert attach_refusal(_guide(CAVE), "location", CROSSROADS, repo) is None


def test_a_path_destination_is_not_checked():
    """Which place a path resolves to is the world's answer at fire time, so there
    is nothing to refuse while authoring."""
    from transversal.domain import TargetSpec
    from transversal.services.sfx_owner import attach_refusal

    effect = _directions(target="").model_copy(update={
        "target_spec": TargetSpec(steps=[{"kind": "select", "collection": "locations"}])})
    sfx = _guide(CAVE)
    sfx.effects = [effect]
    assert attach_refusal(sfx, "location", AZURE, _route_world()) is None


def test_a_non_location_owner_is_not_measured():
    """An entity moves, so what it could tell you depends on when the rule fires;
    refusing on a snapshot of that would be a guess."""
    from transversal.services.sfx_owner import attach_refusal

    assert attach_refusal(_guide(ISLE, source_kind="entity"), "entity", "kael",
                          _route_world()) is None


def test_a_rule_that_grants_no_directions_is_never_measured():
    from transversal.services.guided_route import declares_literal_directions
    from transversal.services.sfx_owner import attach_refusal

    plain = _guide("")            # a token-free, path-free, empty target
    plain.effects = [Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                            action="gain", target="iron-will", result="d6")]
    assert declares_literal_directions(plain) is False
    assert attach_refusal(plain, "location", AZURE, _route_world()) is None


def test_validate_reports_it_once_the_rule_lives_there():
    from transversal.services.sfx_validation import unreachable_directions

    sfx = _guide(ISLE)
    assert unreachable_directions(sfx, _route_world(sfx_ids=[])) == [], "no owner, no origin"
    assert unreachable_directions(sfx, _route_world())            # owned by Azure Dawn
    assert unreachable_directions(_guide(CAVE), _route_world()) == []
