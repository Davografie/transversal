"""Tests for SFX ownership resolution (`services/sfx_owner.py`).

Uses an in-memory repository double so the resolver is exercised standalone
without a live ArangoDB.
"""

from types import SimpleNamespace

from transversal.domain import Condition, ConditionType, EntityType, Timer
from transversal.services.sfx_owner import (
    backfill_trait_default_sfx,
    ensure_give_in_sfx,
    ensure_sfx_owners,
    ensure_targeting_ban_sfx,
    get_available_sfx_ids,
    list_owner_refs,
    propagate_trait_default_sfx,
    resolve_sfx_source,
)


class Repo:
    """Minimal in-memory double covering every owner surface the resolver reads."""

    def __init__(self):
        self.entity = None
        self.projection = None
        self.owners = {}                # owner_id -> SimpleNamespace(sfx_ids=[...])
        self.trait_settings = []        # SimpleNamespace(sfx_ids=[...], trait_id=...)
        self.traits = {}                # trait_id -> SimpleNamespace(default_sfx_ids=[...])
        self.traitset_settings = []     # SimpleNamespace(sfx_ids=[...])
        self.locations = {}             # location_id -> SimpleNamespace(sfx_ids=[...])
        self.location_parents = {}      # location_id -> parent location_id
        self.nested = {}                # parent_traitsetting_id -> [sub-instances]

    def get_sub_traitsettings_for_parents(self, parent_ids):
        """Mirror the real batch read: sub-instances grouped by parent.

        Availability and ownership walk *into* sub-traits (a portent, an
        elemental root), so every double needs this — an absent method would be
        an AttributeError, but a silently empty one would hide the walk.
        """
        return {pid: list(self.nested.get(pid, [])) for pid in parent_ids}

    def list_ancestor_locations_with_sfx(self, location_id, max_depth=8):
        """Mirror the real scope query: the location and its parents, filtered
        to the ones that actually own rules."""
        out, seen, cur = [], set(), location_id
        while cur and cur not in seen and len(seen) < max_depth:
            seen.add(cur)
            loc = self.locations.get(cur)
            if loc is not None and (loc.sfx_ids or []):
                out.append(loc)
            cur = self.location_parents.get(cur)
        return out

    def get_entity(self, entity_id):
        return self.entity

    def get_projection(self, projection_id):
        return self.projection

    def get_sfx_owner(self, owner_id):
        return self.owners.get(owner_id)

    def get_effective_traitsettings(self, entity_id, universes):
        return self.trait_settings

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_effective_traitsetsettings(self, entity_id, universes):
        return self.traitset_settings

    def get_sfx(self, sfx_id):
        return None


def _entity(sfx_ids=None, current_projection=None, current_location=None):
    return SimpleNamespace(sfx_ids=sfx_ids or [], current_projection=current_projection,
                           current_location=current_location)


# ── Rules on a *sub*-trait ───────────────────────────
#
# A rule can live on an instance nested under another instance — an agenda's
# portent, an elemental root. Both availability and ownership read
# `get_effective_traitsettings`, which returns only `from_type == 'entity'` rows,
# so before the walk these rules were authored, attached and *silently dead*.

def _nested_world(nested, effective):
    repo = Repo()
    repo.entity = _entity()
    repo.trait_settings = effective
    repo.nested = nested
    return repo


def test_a_rule_on_a_sub_trait_is_offered_and_is_its_own_source():
    """The portent agenda's shape: the container is the parent, the rule is on a
    portent, and the portent — not the container — is the activation source."""
    parent = SimpleNamespace(id="e1:portents", sfx_ids=[], trait_id="portents")
    child = SimpleNamespace(id="e1:portent-1", sfx_ids=["sfx-advance"],
                            trait_id="portent", enabled=True)
    repo = _nested_world({"e1:portents": [child]}, [parent])

    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-advance"]
    resolved = resolve_sfx_source(repo, "e1", "earth", "sfx-advance", "trait_setting")
    assert resolved is not None
    assert resolved[0].id == "e1:portent-1"
    assert resolved[1] == "traitsetting"


def test_a_disabled_sub_trait_grants_nothing():
    """`enabled` is a fact about the owner, so a landed portent takes its rule
    dark with it — the same rule that applies to a top-level instance."""
    parent = SimpleNamespace(id="e1:portents", sfx_ids=[], trait_id="portents")
    child = SimpleNamespace(id="e1:portent-1", sfx_ids=["sfx-advance"],
                            trait_id="portent", enabled=False)
    repo = _nested_world({"e1:portents": [child]}, [parent])

    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_a_sub_trait_under_an_inactive_parent_grants_nothing():
    """Effectiveness is *inherited*: the walk starts only from instances that are
    themselves in play, so a subtree under nothing is dark."""
    orphan_parent = SimpleNamespace(id="e1:gone", sfx_ids=[], trait_id="portents")
    child = SimpleNamespace(id="e1:portent-1", sfx_ids=["sfx-advance"],
                            trait_id="portent", enabled=True)
    # `e1:gone` is not in the effective list — the walk never reaches its child.
    repo = _nested_world({"e1:gone": [child]}, [])

    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_the_walk_recurses_so_a_root_under_a_root_still_grants():
    parent = SimpleNamespace(id="e1:power", sfx_ids=[], trait_id="power")
    mid = SimpleNamespace(id="e1:root", sfx_ids=[], trait_id="root", enabled=True)
    deep = SimpleNamespace(id="e1:root:leaf", sfx_ids=["sfx-leaf"],
                           trait_id="leaf", enabled=True)
    repo = _nested_world({"e1:power": [mid], "e1:root": [deep]}, [parent])

    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-leaf"]


def test_empty_repo_returns_empty():
    repo = Repo()
    repo.entity = _entity()
    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_direct_entity_ownership():
    repo = Repo()
    repo.entity = _entity(sfx_ids=["sfx-a", "sfx-b"])
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-a", "sfx-b"]


def test_active_projection_ownership():
    repo = Repo()
    repo.entity = _entity(current_projection="proj-1")
    repo.projection = SimpleNamespace(sfx_ids=["sfx-proj"])
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-proj"]


def test_table_owner_included():
    repo = Repo()
    repo.entity = _entity()
    repo.owners = {"table": SimpleNamespace(sfx_ids=["sfx-table"])}
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-table"]


def test_players_bucket_is_ignored():
    # The players bucket was folded into table + an entity_type condition.
    repo = Repo()
    repo.entity = _entity()
    repo.owners = {"players": SimpleNamespace(sfx_ids=["sfx-arrival"])}
    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_gm_owner_is_excluded():
    repo = Repo()
    repo.entity = _entity()
    repo.owners = {"gm": SimpleNamespace(sfx_ids=["sfx-buy-hitch"])}
    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_trait_level_grants():
    # Defaults are provisioned onto the instance at grant time, so availability
    # reads the instance's materialized sfx_ids (no read-time default union).
    repo = Repo()
    repo.entity = _entity()
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-flashback"], trait_id="origin")]
    repo.traits = {"origin": SimpleNamespace(default_sfx_ids=["sfx-default"])}
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-flashback"]


def test_a_disabled_instance_offers_nothing():
    """A disabled ("landed", suppressed) instance grants nothing.

    The rule it carries is a fact about the *owner*, so this is implicit — there
    is no condition to author, and `HAS_EFFECTIVE_TRAIT` cannot stand in: it
    matches by registry trait and returns the first match's `enabled`, so several
    instances of one generic trait (an agenda's steps) answer arbitrarily.
    """
    repo = Repo()
    repo.entity = _entity()
    repo.trait_settings = [
        SimpleNamespace(sfx_ids=["sfx-spent-step"], trait_id="portent", enabled=False),
        SimpleNamespace(sfx_ids=["sfx-live-step"], trait_id="portent", enabled=True),
    ]
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-live-step"]


def test_an_instance_without_an_enabled_flag_still_grants():
    """`enabled` is read as *absent means enabled*, so older data and every other
    owner surface are unaffected."""
    repo = Repo()
    repo.entity = _entity()
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-old"], trait_id="legacy")]
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-old"]


def test_source_rating_filters_trait_grant():
    class R(Repo):
        def get_sfx(self, sfx_id):
            return SimpleNamespace(conditions=[Condition(type=ConditionType.SOURCE_RATING, value="d6")])

    repo = R()
    repo.entity = _entity()
    repo.trait_settings = [SimpleNamespace(
        sfx_ids=["sfx-breakthrough"], trait_id="cultivation-stage",
        dice=[SimpleNamespace(max_value=6)],
    )]
    repo.traits = {"cultivation-stage": SimpleNamespace(default_sfx_ids=[])}
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-breakthrough"]

    # Below the threshold -> filtered out.
    repo.trait_settings = [SimpleNamespace(
        sfx_ids=["sfx-breakthrough"], trait_id="cultivation-stage",
        dice=[SimpleNamespace(max_value=4)],
    )]
    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_traitset_as_unit_grants():
    repo = Repo()
    repo.entity = _entity()
    repo.traitset_settings = [SimpleNamespace(sfx_ids=["sfx-set"])]
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-set"]


def test_union_is_sorted_and_deduplicated():
    repo = Repo()
    repo.entity = _entity(sfx_ids=["sfx-a"])
    repo.owners = {"table": SimpleNamespace(sfx_ids=["sfx-a", "sfx-b"])}
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-c"], trait_id="t1")]
    repo.traits = {"t1": SimpleNamespace(default_sfx_ids=[])}
    repo.traitset_settings = [SimpleNamespace(sfx_ids=["sfx-b"])]
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-a", "sfx-b", "sfx-c"]


def test_missing_entity_still_collects_other_surfaces():
    repo = Repo()
    repo.entity = None
    repo.owners = {"table": SimpleNamespace(sfx_ids=["sfx-table"])}
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-trait"], trait_id="t1")]
    repo.traits = {"t1": SimpleNamespace(default_sfx_ids=[])}
    assert get_available_sfx_ids("ghost", "earth", repo) == ["sfx-table", "sfx-trait"]


class PrefetchRepo(Repo):
    """Double exposing the bulk read paths the prefetch builder uses."""

    def __init__(self):
        super().__init__()
        self.get_entity_calls = 0

    def get_entity(self, entity_id):
        self.get_entity_calls += 1
        return self.entity

    def get_projections_for_entities(self, entity_ids):
        out = {eid: [] for eid in entity_ids}
        if self.projection is not None:
            for eid in entity_ids:
                out[eid] = [self.projection]
        return out

    def get_effective_traitsettings_bulk(self, entity_ids, universes):
        return {eid: list(self.trait_settings) for eid in entity_ids}

    def get_effective_traitsetsettings_bulk(self, entity_ids, universes):
        return {eid: list(self.traitset_settings) for eid in entity_ids}

    def get_all_sfxs(self):
        return []


def test_prefetch_matches_per_entity_resolution():
    """The bulk path resolves the same SFX set as the per-entity path."""
    from transversal.services.sfx_owner import build_sfx_availability_prefetch

    repo = PrefetchRepo()
    repo.entity = SimpleNamespace(sfx_ids=["sfx-a"], current_projection="proj-1")
    repo.projection = SimpleNamespace(id="proj-1", sfx_ids=["sfx-proj"])
    repo.owners["table"] = SimpleNamespace(sfx_ids=["sfx-table"])
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-trait"])]
    repo.traitset_settings = [SimpleNamespace(sfx_ids=["sfx-set"])]

    without = get_available_sfx_ids("e1", "earth", repo)

    entity = SimpleNamespace(
        id="e1", current_universe="earth",
        sfx_ids=["sfx-a"], current_projection="proj-1",
    )
    prefetch = build_sfx_availability_prefetch(repo, [entity])
    calls_before = repo.get_entity_calls
    with_prefetch = get_available_sfx_ids("e1", "earth", repo, prefetch=prefetch)

    assert with_prefetch == without
    assert with_prefetch == ["sfx-a", "sfx-proj", "sfx-set", "sfx-table", "sfx-trait"]
    # The prefetch path must not fall back to per-entity fetches.
    assert repo.get_entity_calls == calls_before


class SetupRepo:
    """Minimal in-memory double for the owner/SFX setup functions."""

    def __init__(self):
        self.owners = {}
        self.sfxs = {}

    def get_sfx_owner(self, owner_id):
        return self.owners.get(owner_id)

    def create_sfx_owner(self, owner):
        self.owners[owner.id] = owner
        return owner

    def update_sfx_owner(self, owner):
        self.owners[owner.id] = owner
        return owner

    def delete_sfx_owner(self, owner_id):
        self.owners.pop(owner_id, None)
        return True

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)

    def create_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx
        return sfx

    def update_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx
        return sfx

    def delete_sfx(self, sfx_id):
        if sfx_id in self.sfxs:
            del self.sfxs[sfx_id]
            return True
        return False


def test_ensure_sfx_owners_creates_buckets_and_table_reward():
    repo = SetupRepo()
    ensure_sfx_owners(repo)
    assert set(repo.owners.keys()) == {"table", "gm"}
    assert set(repo.owners["table"].sfx_ids) == {
        "sfx-give-in-get-razmerit",
        "sfx-give-in-targeting-ban",
        "apply-complication",
        "take-complication",
        "prevent-taken-out",
        "sfx-offer-negative-trait",
        "sfx-starter-location",
        "opportunity-step-down-complication",
    }
    assert repo.owners["gm"].sfx_ids == ["hitch-gain-complication"]


def test_ensure_sfx_owners_merges_into_existing_table():
    repo = SetupRepo()
    repo.owners["table"] = SimpleNamespace(id="table", sfx_ids=["sfx-other"])
    ensure_sfx_owners(repo)
    assert "sfx-give-in-get-razmerit" in repo.owners["table"].sfx_ids
    assert "sfx-give-in-targeting-ban" in repo.owners["table"].sfx_ids
    assert "sfx-other" in repo.owners["table"].sfx_ids


def test_ensure_give_in_sfx_creates_once():
    repo = SetupRepo()
    ensure_give_in_sfx(repo)
    sfx = repo.sfxs["sfx-give-in-get-razmerit"]
    assert sfx.trigger == "on_give_in"
    assert sfx.effects[0].type == "transfer_razmerit"
    assert sfx.effects[0].action == "earn"
    assert sfx.effects[0].result == "1"
    ensure_give_in_sfx(repo)
    assert len(repo.sfxs) == 1


def test_ensure_targeting_ban_sfx_creates_once():
    repo = SetupRepo()
    ensure_targeting_ban_sfx(repo)
    sfx = repo.sfxs["sfx-give-in-targeting-ban"]
    assert sfx.trigger == "on_give_in"
    assert sfx.effects[0].type == "entity"
    assert sfx.effects[0].action == "targeting_ban"
    assert sfx.effects[0].result is None
    assert sfx.effects[0].duration is not None
    assert sfx.effects[0].duration.timers == [Timer(event="scene", remaining=1)]
    ensure_targeting_ban_sfx(repo)
    assert len(repo.sfxs) == 1


def test_ensure_targeting_ban_sfx_migrates_legacy_result():
    from transversal.domain import Effect, EffectTiming, SFX
    from transversal.services.sfx_owner import ensure_targeting_ban_sfx

    repo = SetupRepo()
    repo.sfxs["sfx-give-in-targeting-ban"] = SFX(
        id="sfx-give-in-targeting-ban",
        name="Give In — Keep Your Distance",
        trigger="on_give_in",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="entity", action="targeting_ban", target="", result="1")],
    )
    ensure_targeting_ban_sfx(repo)
    sfx = repo.sfxs["sfx-give-in-targeting-ban"]
    assert sfx.effects[0].result is None
    assert sfx.effects[0].duration is not None
    assert sfx.effects[0].duration.timers == [Timer(event="scene", remaining=1)]


def test_ensure_sfx_owners_table_defaults():
    # The table bucket carries the give-in SFX, the two contest-complication
    # menu SFX (winner applies / conceder takes), and the player opportunity SFX.
    repo = SetupRepo()
    ensure_sfx_owners(repo)
    assert set(repo.owners["table"].sfx_ids) == {
        "sfx-give-in-get-razmerit",
        "sfx-give-in-targeting-ban",
        "apply-complication",
        "take-complication",
        "prevent-taken-out",
        "sfx-offer-negative-trait",
        "sfx-starter-location",
        "opportunity-step-down-complication",
    }


def _path(effect):
    """The effect's target, as the compact path it is.

    The built-ins compose a spec (the declared scope path plus a terminal
    choose/random step) rather than the flat ``{choose_kind}`` spelling, so what a
    seeded rule and a migrated one look like is the same thing.
    """
    return [
        (step.kind,
         getattr(step, "collection", None) or getattr(step, "field", None)
         or getattr(step, "edge", None) or getattr(step, "fn", None)
         or getattr(step, "value", None))
        for step in (effect.target_spec.steps if effect.target_spec else [])
    ]


def test_ensure_starter_location_sfx_creates_once():
    from transversal.services.sfx_owner import ensure_starter_location_sfx

    repo = SetupRepo()
    ensure_starter_location_sfx(repo)
    sfx = repo.sfxs["sfx-starter-location"]
    assert sfx.trigger == "on_character_create"
    assert {c.type.value for c in sfx.conditions} == {"unplaced", "in_universe"}
    in_universe = [c for c in sfx.conditions if c.type.value == "in_universe"][0]
    assert in_universe.target == "earth"
    assert sfx.effects[0].type == "location"
    assert sfx.effects[0].action == "set"
    effect = sfx.effects[0]
    assert effect.target == ""
    assert _path(effect) == [("select", "locations"), ("filter", "universe"),
                             ("filter", "starter_location"), ("aggregate", "random")]
    assert effect.target_spec.steps[1].value == "earth"
    assert effect.target_spec.steps[2].value is True
    ensure_starter_location_sfx(repo)
    assert len(repo.sfxs) == 1


def test_ensure_starter_location_sfx_migrates_travel_shape():
    from transversal.domain import Effect, EffectTiming, SFX
    from transversal.services.sfx_owner import ensure_starter_location_sfx

    repo = SetupRepo()
    repo.sfxs["sfx-starter-location"] = SFX(
        id="sfx-starter-location",
        name="Scatter to Starter Location",
        trigger="on_character_create",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE,
            type="travel", action="move",
            target="{random_starter_location}", target_scope="universe:earth",
            context={"transversal_type": "inapposite"},
        )],
    )
    ensure_starter_location_sfx(repo)
    eff = repo.sfxs["sfx-starter-location"].effects[0]
    assert eff.type == "location"
    assert eff.action == "set"
    assert _path(eff) == [("select", "locations"), ("filter", "universe"),
                          ("filter", "starter_location"), ("aggregate", "random")]
    assert eff.context == {}  # inapposite context dropped


def test_ensure_offer_negative_sfx_creates_once():
    from transversal.services.sfx_owner import ensure_offer_negative_sfx

    repo = SetupRepo()
    ensure_offer_negative_sfx(repo)
    sfx = repo.sfxs["sfx-offer-negative-trait"]
    assert sfx.trigger == "on_trait_offered"
    assert sfx.effects[0].type == "transfer_razmerit"
    assert sfx.effects[0].action == "earn"
    assert sfx.effects[0].result == "1"
    ensure_offer_negative_sfx(repo)
    assert len(repo.sfxs) == 1


def test_ensure_contest_complication_sfx_creates_once():
    from transversal.services.sfx_owner import ensure_contest_complication_sfx

    repo = SetupRepo()
    ensure_contest_complication_sfx(repo)
    apply_sfx = repo.sfxs["apply-complication"]
    take_sfx = repo.sfxs["take-complication"]
    assert apply_sfx.trigger == "menu"
    assert take_sfx.trigger == "menu"
    # The menu is the trigger now, not a placement override.
    assert apply_sfx.placement is None
    assert take_sfx.placement is None
    assert [c.target for c in apply_sfx.conditions if c.type.value == "contest_outcome"] == ["player"]
    assert [c.target for c in take_sfx.conditions if c.type.value == "contest_outcome"] == ["give_in"]
    assert apply_sfx.name == "Apply a complication"
    assert take_sfx.name == "Take a complication"
    # Identical effect, different label.
    assert apply_sfx.effects[0].action == "cortex_gain"
    assert take_sfx.effects[0].action == "cortex_gain"
    assert apply_sfx.effects[0].negative is True
    assert take_sfx.effects[0].negative is True
    assert _path(apply_sfx.effects[0]) == [("literal", "ts-complications-a190"),
                                          ("navigate", "traits"), ("choose", None)]
    assert _path(take_sfx.effects[0]) == _path(apply_sfx.effects[0])
    ensure_contest_complication_sfx(repo)
    assert len(repo.sfxs) == 2


def test_ensure_contest_complication_sfx_migrates_stale_effect():
    from transversal.domain import Effect, EffectTiming, SFX
    from transversal.services.sfx_owner import ensure_contest_complication_sfx

    repo = SetupRepo()
    repo.create_sfx(SFX(
        id="apply-complication", name="Apply a complication",
        description="", trigger="on_consequence",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait",
            action="gain_complication", target="{choose_trait}",
            target_scope="traitset:ts-complications-a190", result="{effect_die}",
        )],
    ))

    ensure_contest_complication_sfx(repo)

    apply_sfx = repo.sfxs["apply-complication"]
    assert apply_sfx.effects[0].action == "cortex_gain"
    assert apply_sfx.effects[0].negative is True
    # The stale flat shape is replaced by the path it meant.
    assert _path(apply_sfx.effects[0]) == [("literal", "ts-complications-a190"),
                                          ("navigate", "traits"), ("choose", None)]
    assert apply_sfx.effects[0].target == ""
    assert apply_sfx.trigger == "menu"
    assert apply_sfx.placement is None
    assert [c.target for c in apply_sfx.conditions if c.type.value == "contest_outcome"] == ["player"]


def test_ensure_prevent_taken_out_sfx_creates_once():
    from transversal.services.sfx_owner import ensure_prevent_taken_out_sfx

    repo = SetupRepo()
    ensure_prevent_taken_out_sfx(repo)
    sfx = repo.sfxs["prevent-taken-out"]
    assert sfx.trigger == "on_prevent_taken_out"
    assert len(sfx.effects) == 1
    assert sfx.effects[0].type == "transfer_razmerit"
    assert sfx.effects[0].action == "spend"
    assert sfx.effects[0].result == "1"
    ensure_prevent_taken_out_sfx(repo)
    assert len(repo.sfxs) == 1


def test_ensure_hitch_gain_complication_sfx_creates_once():
    from transversal.services.sfx_owner import ensure_hitch_gain_complication_sfx

    repo = SetupRepo()
    ensure_hitch_gain_complication_sfx(repo)
    sfx = repo.sfxs["hitch-gain-complication"]
    assert sfx.trigger == "menu"
    assert sfx.placement is None
    assert [c.type.value for c in sfx.conditions] == ["hitch"]
    assert len(sfx.effects) == 2
    assert sfx.effects[0].type == "modify_trait"
    assert sfx.effects[0].action == "gain_or_step_up"
    assert sfx.effects[0].entity == "{hitch_entity}"
    assert sfx.effects[0].negative is True
    assert sfx.effects[0].result == "d4"
    assert sfx.effects[0].context == {"steps": "{number_of_hitches}"}
    assert _path(sfx.effects[0]) == [("literal", "ts-complications-a190"),
                                     ("navigate", "traits"), ("choose", None)]
    assert sfx.effects[1].type == "transfer_razmerit"
    assert sfx.effects[1].action == "earn"
    assert sfx.effects[1].entity == "{hitch_entity}"
    assert sfx.effects[1].result == "1"
    ensure_hitch_gain_complication_sfx(repo)
    assert len(repo.sfxs) == 1


def test_ensure_opportunity_sfx_creates_once():
    from transversal.services.sfx_owner import ensure_opportunity_sfx

    repo = SetupRepo()
    ensure_opportunity_sfx(repo)
    sfx = repo.sfxs["opportunity-step-down-complication"]
    assert sfx.trigger == "menu"
    assert sfx.placement is None
    assert {c.type.value for c in sfx.conditions} == {"hitch", "entity_type"}
    assert len(sfx.effects) == 2
    assert sfx.effects[0].type == "transfer_razmerit"
    assert sfx.effects[0].action == "spend"
    assert sfx.effects[0].entity == "{buying_entity}"
    assert sfx.effects[0].result == "1"
    assert sfx.effects[1].type == "modify_trait"
    assert sfx.effects[1].action == "step_down"
    assert sfx.effects[1].entity == "{buying_entity}"
    assert _path(sfx.effects[1]) == [("literal", "ts-complications-a190"),
                                     ("navigate", "traits"), ("choose", None)]
    ensure_opportunity_sfx(repo)
    assert len(repo.sfxs) == 1


def test_remove_legacy_contest_complication_sfx_is_idempotent():
    from transversal.domain import SFX
    from transversal.services.sfx_owner import remove_legacy_contest_complication_sfx

    repo = SetupRepo()
    repo.sfxs["sfx-contest-loss-complication"] = SFX(
        id="sfx-contest-loss-complication", name="stale", trigger="on_contest_loss", effects=[]
    )
    repo.owners["table"] = SimpleNamespace(
        id="table",
        sfx_ids=["sfx-give-in-get-razmerit", "sfx-give-in-targeting-ban", "sfx-contest-loss-complication"],
    )

    remove_legacy_contest_complication_sfx(repo)
    assert "sfx-contest-loss-complication" not in repo.sfxs
    assert "sfx-contest-loss-complication" not in repo.owners["table"].sfx_ids

    # Idempotent: a second pass is a no-op.
    remove_legacy_contest_complication_sfx(repo)
    assert "sfx-contest-loss-complication" not in repo.sfxs
    assert "sfx-contest-loss-complication" not in repo.owners["table"].sfx_ids


class DispatchRepo:
    """In-memory double for the owner-index + add/remove dispatcher.

    Each owner type maps to a SimpleNamespace with the attribute the dispatcher
    reads/writes (``sfx_ids`` everywhere except trait, which uses
    ``default_sfx_ids``).
    """

    def __init__(self):
        self.owners = {}
        self.entities = {}
        self.projections = {}
        self.traits = {}
        self.traitsettings = {}
        self.traitsetsettings = {}

    def get_sfx_owner(self, oid): return self.owners.get(oid)
    def update_sfx_owner(self, o): self.owners[o.id] = o
    def get_entity(self, eid): return self.entities.get(eid)
    def update_entity(self, e): self.entities[e.id] = e
    def get_projection(self, pid): return self.projections.get(pid)
    def update_projection(self, p): self.projections[p.id] = p
    def get_trait(self, tid): return self.traits.get(tid)
    def update_trait(self, t): self.traits[t.id] = t
    def get_traitsetting(self, sid): return self.traitsettings.get(sid)
    def update_traitsetting(self, s): self.traitsettings[s.id] = s
    def get_traitsettings_by_trait(self, tid):
        return [s for s in self.traitsettings.values() if getattr(s, "trait_id", None) == tid]
    def get_traitsetsetting(self, sid): return self.traitsetsettings.get(sid)
    def update_traitsetsetting(self, s): self.traitsetsettings[s.id] = s


def test_add_remove_dispatcher_across_surfaces():
    from transversal.services.sfx_owner import add_sfx_to_owner, remove_sfx_from_owner

    repo = DispatchRepo()
    repo.owners["table"] = SimpleNamespace(id="table", sfx_ids=[])
    repo.entities["char-1"] = SimpleNamespace(id="char-1", sfx_ids=[])
    repo.projections["proj-1"] = SimpleNamespace(id="proj-1", sfx_ids=[])
    repo.traits["trait-1"] = SimpleNamespace(id="trait-1", default_sfx_ids=[])
    repo.traitsettings["ts-1"] = SimpleNamespace(id="ts-1", sfx_ids=[])
    repo.traitsetsettings["tss-1"] = SimpleNamespace(id="tss-1", sfx_ids=[])

    for owner_type, owner_id in [
        ("table", "table"),
        ("entity", "char-1"),
        ("projection", "proj-1"),
        ("trait", "trait-1"),
        ("trait_instance", "ts-1"),
        ("trait_set", "tss-1"),
    ]:
        assert add_sfx_to_owner(repo, owner_type, owner_id, "sfx-x") is True

    assert repo.owners["table"].sfx_ids == ["sfx-x"]
    assert repo.entities["char-1"].sfx_ids == ["sfx-x"]
    assert repo.projections["proj-1"].sfx_ids == ["sfx-x"]
    assert repo.traits["trait-1"].default_sfx_ids == ["sfx-x"]
    assert repo.traitsettings["ts-1"].sfx_ids == ["sfx-x"]
    assert repo.traitsetsettings["tss-1"].sfx_ids == ["sfx-x"]

    # Idempotent add + remove.
    assert add_sfx_to_owner(repo, "entity", "char-1", "sfx-x") is True
    assert repo.entities["char-1"].sfx_ids == ["sfx-x"]
    assert remove_sfx_from_owner(repo, "entity", "char-1", "sfx-x") is True
    assert repo.entities["char-1"].sfx_ids == []

    # Missing owner returns False without error.
    assert add_sfx_to_owner(repo, "entity", "ghost", "sfx-x") is False
    assert remove_sfx_from_owner(repo, "entity", "ghost", "sfx-x") is False


def test_add_sfx_to_owner_enforces_source_kind():
    from transversal.services.sfx_owner import add_sfx_to_owner
    from transversal.domain import SFX

    repo = DispatchRepo()
    repo.traitsettings["ts-1"] = SimpleNamespace(id="ts-1", sfx_ids=[])
    repo.entities["char-1"] = SimpleNamespace(id="char-1", sfx_ids=[])

    # A trait-setting SFX may attach to trait_instance, but not to entity.
    repo.sfxs = {"sfx-x": SFX(id="sfx-x", name="X", trigger="manual", source_kind="trait_setting")}
    def get_sfx(sid):
        return repo.sfxs.get(sid)
    repo.get_sfx = get_sfx

    assert add_sfx_to_owner(repo, "trait_instance", "ts-1", "sfx-x") is True
    assert add_sfx_to_owner(repo, "entity", "char-1", "sfx-x") is False

    # Buckets are origin-less: a source-kind SFX can't attach to them either.
    repo.owners["table"] = SimpleNamespace(id="table", sfx_ids=[])
    assert add_sfx_to_owner(repo, "table", "table", "sfx-x") is False

    # A source-kind-less SFX is unrestricted.
    repo.sfxs["sfx-y"] = SFX(id="sfx-y", name="Y", trigger="manual")
    assert add_sfx_to_owner(repo, "entity", "char-1", "sfx-y") is True


# ── Default-SFX provisioning (#218) and propagation (#49) ──────

class _PropRepo:
    """Minimal double for default-SFX propagation/backfill."""

    def __init__(self):
        self.traits = {}          # trait_id -> SimpleNamespace(id=..., default_sfx_ids=[...])
        self.settings = {}        # ts_id -> SimpleNamespace(id=..., trait_id=..., sfx_ids=[...])

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitsettings_by_trait(self, trait_id):
        return [ts for ts in self.settings.values() if ts.trait_id == trait_id]

    def update_traitsetting(self, ts):
        self.settings[ts.id] = ts

    def get_all_traits(self):
        return list(self.traits.values())


def test_propagate_trait_default_sfx_adds_missing():
    repo = _PropRepo()
    repo.traits["t1"] = SimpleNamespace(id="t1", default_sfx_ids=["sfx-a", "sfx-b"])
    repo.settings["e1:t1"] = SimpleNamespace(id="e1:t1", trait_id="t1", sfx_ids=["sfx-a"])
    assert propagate_trait_default_sfx(repo, "t1") == 1
    assert repo.settings["e1:t1"].sfx_ids == ["sfx-a", "sfx-b"]


def test_propagate_trait_default_sfx_noop_when_present():
    repo = _PropRepo()
    repo.traits["t1"] = SimpleNamespace(id="t1", default_sfx_ids=["sfx-a", "sfx-b"])
    repo.settings["e1:t1"] = SimpleNamespace(id="e1:t1", trait_id="t1", sfx_ids=["sfx-a", "sfx-b"])
    assert propagate_trait_default_sfx(repo, "t1") == 0
    assert repo.settings["e1:t1"].sfx_ids == ["sfx-a", "sfx-b"]


def test_propagate_trait_default_sfx_no_defaults():
    repo = _PropRepo()
    repo.traits["t1"] = SimpleNamespace(id="t1", default_sfx_ids=[])
    repo.settings["e1:t1"] = SimpleNamespace(id="e1:t1", trait_id="t1", sfx_ids=[])
    assert propagate_trait_default_sfx(repo, "t1") == 0


def test_backfill_trait_default_sfx_across_traits():
    repo = _PropRepo()
    repo.traits["t1"] = SimpleNamespace(id="t1", default_sfx_ids=["sfx-a"])
    repo.traits["t2"] = SimpleNamespace(id="t2", default_sfx_ids=["sfx-b"])
    repo.settings["e1:t1"] = SimpleNamespace(id="e1:t1", trait_id="t1", sfx_ids=[])
    repo.settings["e2:t2"] = SimpleNamespace(id="e2:t2", trait_id="t2", sfx_ids=["sfx-b"])
    assert backfill_trait_default_sfx(repo) == 1  # only t1's instance was updated
    assert repo.settings["e1:t1"].sfx_ids == ["sfx-a"]
    assert repo.settings["e2:t2"].sfx_ids == ["sfx-b"]


def test_create_traitsetting_provisions_defaults():
    from transversal.db.repository import EntityRepository
    from transversal.domain import DieType, TraitSetting

    class R(EntityRepository):
        def __init__(self, trait):
            self._trait = trait

        def get_trait(self, trait_id):
            return self._trait

    trait = SimpleNamespace(default_sfx_ids=["sfx-a", "sfx-b"])
    repo = R(trait)
    ts = TraitSetting(
        id="e1:t1", entity_id="e1", trait_id="t1", traitset_id="ts-x",
        dice=[DieType.D6], sfx_ids=["sfx-c"],
    )
    out = repo._provision_trait_default_sfx(ts)
    assert out.sfx_ids == ["sfx-a", "sfx-b", "sfx-c"]
    # No-op when the trait has no defaults.
    repo._trait = SimpleNamespace(default_sfx_ids=[])
    assert repo._provision_trait_default_sfx(ts).sfx_ids == ["sfx-c"]


# ── Automatic-trigger source resolution ──────────────────────

def test_resolve_sfx_source_traitsetting():
    repo = Repo()
    repo.trait_settings = [
        SimpleNamespace(id="e1:cultivation", sfx_ids=["sfx-qi"], trait_id="cultivation", entity_id="e1"),
    ]
    out = resolve_sfx_source(repo, "e1", "earth", "sfx-qi", "trait_setting")
    assert out is not None
    obj, element = out
    assert element == "traitsetting"
    assert obj.id == "e1:cultivation"


def test_resolve_sfx_source_none_when_not_granting():
    repo = Repo()
    repo.trait_settings = [
        SimpleNamespace(id="e1:other", sfx_ids=["sfx-other"], trait_id="other", entity_id="e1"),
    ]
    assert resolve_sfx_source(repo, "e1", "earth", "sfx-qi", "trait_setting") is None


def test_resolve_sfx_source_entity():
    repo = Repo()
    repo.entity = _entity(sfx_ids=["sfx-entity"])
    out = resolve_sfx_source(repo, "e1", "earth", "sfx-entity", "entity")
    assert out is not None
    obj, element = out
    assert element == "entity"
    assert obj is repo.entity


def test_owned_surfaces_collects_across_surfaces(monkeypatch):
    import transversal.services.sfx_owner as sfo

    def fake_list_owner_refs(repo, owner_type):
        if owner_type == "table":
            return [{"sfx_ids": ["sfx-x"]}]
        if owner_type == "entity":
            return [{"sfx_ids": ["sfx-y"]}]
        return []

    monkeypatch.setattr(sfo, "list_owner_refs", fake_list_owner_refs)
    assert sfo.owned_surfaces(None, "sfx-x") == {"table"}
    assert sfo.owned_surfaces(None, "sfx-y") == {"entity"}
    assert sfo.owned_surfaces(None, "sfx-z") == set()


def test_backfill_source_kinds_folds_buckets_and_traits(monkeypatch):
    from types import SimpleNamespace
    import transversal.services.sfx_owner as sfo

    repo = SimpleNamespace()
    repo._sfxs = {
        "sfx-table": SimpleNamespace(id="sfx-table", trigger="manual", source_kind=None, arming_scope=None),
        "sfx-gm": SimpleNamespace(id="sfx-gm", trigger="manual", source_kind=None, arming_scope=None),
        "sfx-trait": SimpleNamespace(id="sfx-trait", trigger="manual", source_kind=None, arming_scope=None),
        "sfx-orphan": SimpleNamespace(id="sfx-orphan", trigger="manual", source_kind=None, arming_scope=None),
        "sfx-session": SimpleNamespace(id="sfx-session", trigger="on_session_start", source_kind=None, arming_scope=None),
        "sfx-done": SimpleNamespace(id="sfx-done", trigger="manual", source_kind="entity", arming_scope=None),
    }
    repo._owners = {
        "table": SimpleNamespace(sfx_ids=["sfx-table", "sfx-session"]),
        "gm": SimpleNamespace(sfx_ids=["sfx-gm"]),
    }
    repo.get_sfx_owner = lambda oid: repo._owners.get(oid)
    repo.get_sfx = lambda sid: repo._sfxs.get(sid)
    repo.update_sfx = lambda sfx: repo._sfxs.__setitem__(sfx.id, sfx)
    repo.get_all_sfxs = lambda: list(repo._sfxs.values())

    def fake_owned_surfaces(_repo, sid):
        return {"trait_instance"} if sid == "sfx-trait" else ({"entity"} if sid == "sfx-done" else set())
    monkeypatch.setattr(sfo, "owned_surfaces", fake_owned_surfaces)

    changed = sfo.backfill_source_kinds(repo)
    assert changed == 5  # table, gm, session(source), session(scope), trait
    assert repo._sfxs["sfx-table"].source_kind == "table"
    assert repo._sfxs["sfx-gm"].source_kind == "gm"
    assert repo._sfxs["sfx-trait"].source_kind == "trait_setting"
    assert repo._sfxs["sfx-session"].source_kind == "table"
    assert repo._sfxs["sfx-session"].arming_scope == "global"
    assert repo._sfxs["sfx-orphan"].source_kind is None  # orphan skipped
    assert repo._sfxs["sfx-done"].source_kind == "entity"  # already set, untouched

    # Idempotent: second pass changes nothing.
    assert sfo.backfill_source_kinds(repo) == 0


def test_backfill_play_as_rating_moves_the_dead_token_onto_a_path():
    """`implicit_target="{source_trait}"` was never bound by any firing path, so a
    stored Play as Rating effect passed a literal string as its target and did
    nothing (sfx-hinder is the live case). The pass rewrites exactly those."""
    from types import SimpleNamespace
    from transversal.domain import Effect, EffectTiming

    import transversal.services.sfx_owner as sfo

    dead = Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                  action="play_as_rating", target="{source_trait}", result="d4")
    already = Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                     action="play_as_rating", target="kael:distinction", result="d4")
    other = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                   action="gain", target="{source_trait}", result="d6")
    repo = SimpleNamespace()
    repo._sfxs = {
        "sfx-hinder": SimpleNamespace(id="sfx-hinder", effects=[dead]),
        "sfx-authored": SimpleNamespace(id="sfx-authored", effects=[already]),
        "sfx-other": SimpleNamespace(id="sfx-other", effects=[other]),
    }
    repo.get_all_sfxs = lambda: list(repo._sfxs.values())
    repo.update_sfx = lambda sfx: repo._sfxs.__setitem__(sfx.id, sfx)

    assert sfo.backfill_play_as_rating_targets(repo) == 1
    assert dead.target == ""
    assert dead.target_spec is not None
    assert [s.kind for s in dead.target_spec.steps] == ["select"]
    assert dead.target_spec.steps[0].collection == "source"
    # An author's own path and another action's token are left alone.
    assert already.target == "kael:distinction" and already.target_spec is None
    assert other.target == "{source_trait}"

    # Idempotent.
    assert sfo.backfill_play_as_rating_targets(repo) == 0


# ── Availability narrowing + record cache ─────────────────────
#
# Availability runs on every state event, every roll and every "what can I do"
# query, and reads each candidate's record. These pin the two things that keep
# its cost proportional to the *candidates that matter* rather than the whole
# catalogue.

class CountingRepo(Repo):
    """The same double, counting `get_sfx` reads and serving real records."""

    def __init__(self, sfxs=None):
        super().__init__()
        self.sfxs = {s.id: s for s in (sfxs or [])}
        self.reads = 0

    def get_sfx(self, sfx_id):
        self.reads += 1
        return self.sfxs.get(sfx_id)


def _sfx(sfx_id, trigger="manual"):
    return SimpleNamespace(id=sfx_id, name=sfx_id, trigger=trigger, conditions=[],
                           source_kind=None)


def _cache_state():
    from transversal.services import sfx_owner

    return sfx_owner._SFX_CACHE


def test_records_are_cached_across_calls():
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-a")])
    repo.entity = _entity(sfx_ids=["sfx-a"])

    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-a"]
    first = repo.reads
    assert first == 1
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-a"]
    assert repo.reads == first, "a warm cache must not re-read the record"

    invalidate_sfx_cache()
    get_available_sfx_ids("e1", "earth", repo)
    assert repo.reads > first, "an explicit invalidation forces a re-read"


def test_a_missing_record_is_not_remembered_as_missing():
    """A miss means "not created yet" — caching it would hide a new SFX."""
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([])
    repo.entity = _entity(sfx_ids=["sfx-new"])
    get_available_sfx_ids("e1", "earth", repo)  # resolves to nothing (still listed)

    repo.sfxs["sfx-new"] = _sfx("sfx-new")      # the SFX now exists
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-new"]


def test_trigger_narrowing_drops_candidates_before_reading_them():
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-roll", "on_roll"), _sfx("sfx-manual", "manual")])
    repo.entity = _entity(sfx_ids=["sfx-roll", "sfx-manual"])
    # Warm the cache so the narrowing is what we measure, not the first read.
    get_available_sfx_ids("e1", "earth", repo)
    repo.reads = 0

    out = get_available_sfx_ids("e1", "earth", repo, triggers=frozenset({"on_roll"}))
    assert out == ["sfx-roll"]
    assert repo.reads == 0, "a narrowed-away candidate must not be read at all"


def test_no_narrowing_lists_everything():
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-roll", "on_roll"), _sfx("sfx-manual", "manual")])
    repo.entity = _entity(sfx_ids=["sfx-roll", "sfx-manual"])
    # The sheet's listing passes no triggers: a manual activation has no event.
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-manual", "sfx-roll"]


# ── Location scope: a place's rules reach the people in it ────
#
# Read-time only: nothing is written onto the occupant, so walking out ends the
# rule by itself. These pin both the reaching and the *not* reaching.

def _place(repo, loc_id, sfx_ids, parent=None):
    repo.locations[loc_id] = SimpleNamespace(id=loc_id, sfx_ids=list(sfx_ids))
    if parent:
        repo.location_parents[loc_id] = parent


def test_a_place_rule_reaches_its_occupants():
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-hall")])
    _place(repo, "hall", ["sfx-hall"])
    repo.entity = _entity(current_location="hall")

    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-hall"]


def test_a_place_rule_reaches_the_rooms_inside_it():
    """A rule on the sect applies in its cellar: the scope walks up."""
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-sect")])
    _place(repo, "sect", ["sfx-sect"])
    _place(repo, "cellar", [], parent="sect")
    repo.entity = _entity(current_location="cellar")

    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-sect"]


def test_a_place_the_entity_is_not_in_does_not_reach_them():
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-elsewhere")])
    _place(repo, "elsewhere", ["sfx-elsewhere"])
    _place(repo, "hall", [])
    repo.entity = _entity(current_location="hall")

    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_an_entity_with_no_location_gets_no_place_rules():
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-hall")])
    _place(repo, "hall", ["sfx-hall"])
    repo.entity = _entity()  # unplaced

    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_place_rules_are_attributed_to_the_place_that_lends_them():
    """The strip needs a heading, so the contribution is kept apart and named."""
    from transversal.services.sfx_owner import get_place_sfx_rules, invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-sect")])
    _place(repo, "sect", ["sfx-sect"])
    repo.locations["sect"].name = "Azure Dawn"
    repo.entity = _entity(current_location="sect")

    assert get_place_sfx_rules("e1", "earth", repo) == [
        {"location_id": "sect", "location_name": "Azure Dawn", "sfx_ids": ["sfx-sect"]},
    ]


def test_a_room_rule_is_credited_to_the_room_not_its_parent():
    """A rule both the room and its ancestor carry shows once, under the nearer
    place — the one the entity is actually standing in."""
    from transversal.services.sfx_owner import get_place_sfx_rules, invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-shared")])
    _place(repo, "sect", ["sfx-shared"])
    _place(repo, "cellar", ["sfx-shared"], parent="sect")
    repo.locations["sect"].name = "Azure Dawn"
    repo.locations["cellar"].name = "The Cellar"
    repo.entity = _entity(current_location="cellar")

    groups = get_place_sfx_rules("e1", "earth", repo)
    assert [(g["location_id"], g["sfx_ids"]) for g in groups] == [("cellar", ["sfx-shared"])]


def test_a_place_rule_that_conditions_exclude_is_not_offered_as_a_button():
    """The strip reads the *same* availability the activation path does, so it
    can never show a button the fire path would refuse. Here the rule is
    restricted to GMCs and the entity is a character."""
    from transversal.domain import Condition, ConditionType
    from transversal.services.sfx_owner import get_place_sfx_rules, invalidate_sfx_cache

    invalidate_sfx_cache()
    gated = _sfx("sfx-gmc-only")
    gated.conditions = [Condition(type=ConditionType.ENTITY_TYPE, target="gmc")]
    repo = CountingRepo([gated])
    _place(repo, "hall", ["sfx-gmc-only"])
    repo.entity = SimpleNamespace(id="e1", type=EntityType.CHARACTER, sfx_ids=[],
                                  current_projection=None, current_location="hall")

    assert get_available_sfx_ids("e1", "earth", repo) == []
    assert get_place_sfx_rules("e1", "earth", repo) == []


def test_an_unplaced_entity_is_lent_nothing():
    from transversal.services.sfx_owner import get_place_sfx_rules, invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-hall")])
    _place(repo, "hall", ["sfx-hall"])
    repo.entity = _entity()

    assert get_place_sfx_rules("e1", "earth", repo) == []


def test_a_standing_place_rule_is_held_up_and_an_arrival_one_is_not():
    """The MtG line the author drew: an arrival rule is an instant — it has fired
    by the time you are standing there — while activated and recurring rules are
    permanents you keep track of. Both stay *available*; only the shelf differs.
    """
    from transversal.services.sfx_owner import get_place_sfx_rules, invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([
        _sfx("sfx-sect-initiation", "on_location_change"),
        _sfx("sfx-use-the-forge", "manual"),
        _sfx("sfx-sect-blessing", "on_roll"),
    ])
    _place(repo, "sect", ["sfx-sect-initiation", "sfx-use-the-forge", "sfx-sect-blessing"])
    repo.entity = _entity(current_location="sect")

    assert "sfx-sect-initiation" in get_available_sfx_ids("e1", "earth", repo), \
        "arriving there still teaches you"
    groups = get_place_sfx_rules("e1", "earth", repo)
    assert [g["sfx_ids"] for g in groups] == [["sfx-sect-blessing", "sfx-use-the-forge"]]


def test_a_place_whose_only_rule_is_an_arrival_rule_shows_no_group():
    """No empty heading for a place that has nothing to hold up."""
    from transversal.services.sfx_owner import get_place_sfx_rules, invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-sect-initiation", "on_location_change")])
    _place(repo, "sect", ["sfx-sect-initiation"])
    repo.entity = _entity(current_location="sect")

    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-sect-initiation"]
    assert get_place_sfx_rules("e1", "earth", repo) == []


def test_the_strip_never_offers_what_availability_would_refuse():
    """One rule, two views: every id the strip groups is in `availableSfxIds`,
    so a button on the sheet can't be one the activation path rejects."""
    from transversal.services.sfx_owner import get_place_sfx_rules, invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-sect"), _sfx("sfx-mine")])
    _place(repo, "sect", ["sfx-sect"])
    repo.entity = _entity(sfx_ids=["sfx-mine"], current_location="sect")

    available = set(get_available_sfx_ids("e1", "earth", repo))
    grouped = {sid for g in get_place_sfx_rules("e1", "earth", repo) for sid in g["sfx_ids"]}
    assert grouped == {"sfx-sect"}
    assert grouped <= available


def test_place_rules_and_carried_rules_combine():
    from transversal.services.sfx_owner import invalidate_sfx_cache

    invalidate_sfx_cache()
    repo = CountingRepo([_sfx("sfx-own", "manual"), _sfx("sfx-hall", "manual")])
    _place(repo, "hall", ["sfx-hall"])
    repo.entity = _entity(sfx_ids=["sfx-own"], current_location="hall")

    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-hall", "sfx-own"]


def test_the_bulk_path_agrees_about_place_rules():
    """The session-start fan-out resolves the scope once per location; it must
    reach the same answer as the per-entity path."""
    from transversal.services.sfx_owner import (
        build_sfx_availability_prefetch,
        invalidate_sfx_cache,
    )

    invalidate_sfx_cache()
    repo = PrefetchRepo()
    repo.sfxs = {"sfx-sect": _sfx("sfx-sect", "manual")}
    repo.get_sfx = lambda sid: repo.sfxs.get(sid)
    _place(repo, "sect", ["sfx-sect"])
    _place(repo, "cellar", [], parent="sect")
    kael = SimpleNamespace(id="e1", current_universe="earth", sfx_ids=[],
                           current_projection=None, current_location="cellar")
    other = SimpleNamespace(id="e2", current_universe="earth", sfx_ids=[],
                            current_projection=None, current_location="outside")

    repo.entity = kael  # the per-entity path loads it by id
    per_entity = get_available_sfx_ids("e1", "earth", repo)
    prefetch = build_sfx_availability_prefetch(repo, [kael, other])
    bulk = get_available_sfx_ids("e1", "earth", repo, prefetch=prefetch)

    assert per_entity == bulk == ["sfx-sect"]
    assert get_available_sfx_ids("e2", "earth", repo, prefetch=prefetch) == []


# ── The place-owned worked example ────────────────────────────
#
# Seeded by hand (never from startup), so the risks are: attaching it twice, and
# seeding into a world that has neither the place nor the life path.

class _WorldDouble:
    """Just enough repository for the example seeder."""

    def __init__(self, location=None, life_path=None):
        from transversal.domain import EntityType

        self.sfxs = {}
        self.entities = []
        if location:
            self.entities.append(SimpleNamespace(id=location, name="Azure Dawn",
                                                type=EntityType.LOCATION, sfx_ids=[]))
        self.lifepaths = ([SimpleNamespace(id=life_path, name="Azure Dawn")] if life_path else [])
        self.owner_lists = {}

    def list_all_entities(self):
        return self.entities

    def list_all_lifepaths(self):
        return self.lifepaths

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)

    def create_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx
        return sfx

    def update_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx
        return sfx

    # owner surface (the `entity` bucket is the entity's own list)
    def get_entity(self, entity_id):
        return next((e for e in self.entities if e.id == entity_id), None)

    def update_entity(self, entity):
        return entity


def test_the_place_rule_example_lands_on_the_location():
    from transversal.services.sfx_owner import PLACE_RULE_EXAMPLE_ID, ensure_place_rule_example

    repo = _WorldDouble(location="azur-dawn", life_path="lp-azure")
    ensure_place_rule_example(repo)

    sfx = repo.sfxs[PLACE_RULE_EXAMPLE_ID]
    assert sfx.trigger == "on_location_change"
    assert [e.type for e in sfx.effects] == ["life_path"]
    assert repo.get_entity("azur-dawn").sfx_ids == [PLACE_RULE_EXAMPLE_ID]


def test_the_place_rule_example_is_idempotent():
    from transversal.services.sfx_owner import PLACE_RULE_EXAMPLE_ID, ensure_place_rule_example

    repo = _WorldDouble(location="azur-dawn", life_path="lp-azure")
    ensure_place_rule_example(repo)
    ensure_place_rule_example(repo)

    assert repo.get_entity("azur-dawn").sfx_ids == [PLACE_RULE_EXAMPLE_ID]
    assert len(repo.sfxs) == 1


def test_the_place_rule_example_no_ops_without_its_data():
    from transversal.services.sfx_owner import ensure_place_rule_example

    for keyword in ({}, {"location": "azur-dawn"}, {"life_path": "lp-azure"}):
        repo = _WorldDouble(**keyword)
        ensure_place_rule_example(repo)
        assert repo.sfxs == {}, keyword


# ── A place as an owner *and* as a source ─────────────────────
#
# `location` is its own owner surface: a place-owned rule resolves its source to
# the place, not to the entity standing in it.

def test_locations_are_their_own_owner_surface():
    from transversal.domain import EntityType
    from transversal.services.sfx_owner import list_owner_refs

    repo = Repo()
    repo.entities = [
        SimpleNamespace(id="loc-1", name="Azure Dawn", type=EntityType.LOCATION, sfx_ids=["sfx-a"]),
        SimpleNamespace(id="char-1", name="Kael", type=EntityType.CHARACTER, sfx_ids=[]),
    ]
    repo.list_all_entities = lambda: repo.entities

    assert [r["owner_id"] for r in list_owner_refs(repo, "location")] == ["loc-1"]
    assert [r["owner_id"] for r in list_owner_refs(repo, "entity")] == ["char-1"]


def test_a_location_writes_its_rules_to_the_same_field():
    from transversal.domain import EntityType
    from transversal.services.sfx_owner import _get_owner_sfx_ids, _set_owner_sfx_ids

    repo = Repo()
    repo.entities = [SimpleNamespace(id="loc-1", name="Azure Dawn", type=EntityType.LOCATION, sfx_ids=[])]
    repo.get_entity = lambda eid: next((e for e in repo.entities if e.id == eid), None)
    repo.update_entity = lambda e: e

    assert _get_owner_sfx_ids(repo, "location", "loc-1") == []
    assert _set_owner_sfx_ids(repo, "location", "loc-1", ["sfx-a"]) is True
    assert repo.entities[0].sfx_ids == ["sfx-a"]


def test_a_place_source_resolves_to_the_place_not_the_occupant():
    from transversal.domain import EntityType
    from transversal.services.sfx_owner import resolve_sfx_source

    kael = SimpleNamespace(id="char-1", type=EntityType.CHARACTER, current_location="loc-1")
    elsewhere = SimpleNamespace(id="char-2", type=EntityType.CHARACTER, current_location="loc-9")
    repo = Repo()
    repo.entities = {"char-1": kael, "char-2": elsewhere}
    repo.get_entity = lambda eid: repo.entities.get(eid)
    _place(repo, "loc-1", ["sfx-sect"])
    _place(repo, "loc-9", [])

    source, element = resolve_sfx_source(repo, "char-1", "earth", "sfx-sect", "location")
    assert element == "location"
    assert source.id == "loc-1", "the source is the place, not the character"

    # A character who is not in a place that owns it has no location source.
    assert resolve_sfx_source(repo, "char-2", "earth", "sfx-sect", "location") is None


def test_owner_refs_say_what_kind_of_entity_they_are():
    """A flat list of 462 names is unusable — each row carries its entity type,
    as the *value* ("faction"), never the enum's repr ("EntityType.FACTION")."""
    from transversal.domain import EntityType
    from transversal.services.sfx_owner import list_owner_refs

    repo = Repo()
    repo.entities = [
        SimpleNamespace(id="char-1", name="Kael", type=EntityType.CHARACTER, sfx_ids=[]),
        SimpleNamespace(id="faction-1", name="Azure Dawn", type=EntityType.FACTION, sfx_ids=[]),
    ]
    repo.list_all_entities = lambda: repo.entities

    rows = list_owner_refs(repo, "entity")
    assert {r["entity_type"] for r in rows} == {"character", "faction"}


# ── One rule decides where a rule may live ────────────────────

def test_a_declared_source_restricts_where_a_rule_can_attach():
    """The same rule drives the attach guard, the picker's filter and validation,
    so a mismatch is refused for the reason it isn't offered."""
    from transversal.services.sfx_owner import (
        attach_refusal,
        can_attach,
        owner_surfaces_for,
    )

    trait_sfx = _sfx("sfx-on-trait")
    trait_sfx.source_kind = "trait_setting"
    # Both homes: the instance it fires from, and the *definition* that provisions
    # its instances (`Trait.possible_sfx_ids` / `default_sfx_ids`).
    assert owner_surfaces_for(trait_sfx) == {"trait_instance", "trait"}
    assert can_attach(trait_sfx, "trait_instance") is True
    assert can_attach(trait_sfx, "trait") is True
    assert can_attach(trait_sfx, "location") is False
    assert attach_refusal(trait_sfx, "location") == (
        "belongs on a trait definition or a trait instance")
    assert attach_refusal(trait_sfx, "trait_instance") is None
    assert attach_refusal(trait_sfx, "trait") is None

    place_sfx = _sfx("sfx-on-place")
    place_sfx.source_kind = "location"
    assert can_attach(place_sfx, "location") is True
    assert can_attach(place_sfx, "entity") is False, "a place rule is not an entity rule"


def test_an_undeclared_source_is_unrestricted():
    from transversal.services.sfx_owner import can_attach, owner_surfaces_for

    free = _sfx("sfx-anywhere")  # _sfx() leaves source_kind unset
    assert can_attach(free, "table") and can_attach(free, "location")
    assert "location" in owner_surfaces_for(free) and "trait_instance" in owner_surfaces_for(free)


# ── A gate on acquiring (not on using) ────────────────────────
#
# The author's case: learnable at Azure Dawn, attached to a trait instance, and
# usable afterwards. So the gate is enforced where the *grant* happens, and it is
# a path seeded at the owner itself.

def _gated_rule(target_location: str, source_kind: str = "trait_setting"):
    from transversal.services.target_spec import FilterStep, NavigateStep, SelectStep, TargetSpec

    sfx = _sfx("sfx-azure-technique")
    sfx.source_kind = source_kind
    sfx.acquire_spec = TargetSpec(steps=[
        SelectStep(collection="source"),
        NavigateStep(edge="entity"),
        FilterStep(field="current_location", operator="==", value=target_location),
    ])
    return sfx


def _world_at(location: str):
    from transversal.domain import EntityType

    repo = Repo()
    repo.entities = {
        "char-1": SimpleNamespace(id="char-1", type=EntityType.CHARACTER, current_location=location),
        "loc-1": SimpleNamespace(id="loc-1", name="Azure Dawn", type=EntityType.LOCATION),
        "loc-9": SimpleNamespace(id="loc-9", name="Elsewhere", type=EntityType.LOCATION),
        "ts-1": SimpleNamespace(id="ts-1", trait_id="trait-technique", entity_id="char-1", sfx_ids=[]),
    }
    repo.get_entity = lambda eid: repo.entities.get(eid)
    repo.get_traitsetting = lambda tid: repo.entities.get(tid)
    repo.update_entity = lambda e: e
    repo.update_traitsetting = lambda ts: ts
    # `traitsetting → entity` and `entity → location` are resolver edges, not
    # repo calls, so no more surface is needed here.
    return repo


def test_a_rule_can_be_gated_to_a_place_of_acquisition():
    from transversal.services.sfx_owner import acquire_gate_holds

    gated = _gated_rule("loc-1")
    assert acquire_gate_holds(gated, "trait_instance", "ts-1", _world_at("loc-1")) is True
    assert acquire_gate_holds(gated, "trait_instance", "ts-1", _world_at("loc-9")) is False


def test_an_ungated_rule_is_acquirable_anywhere():
    from transversal.services.sfx_owner import acquire_gate_holds

    plain = _sfx("sfx-plain")
    plain.source_kind = "trait_setting"
    assert acquire_gate_holds(plain, "trait_instance", "ts-1", _world_at("loc-9")) is True


def test_the_gate_is_enforced_on_attach_not_just_offered():
    """A UI filter is a suggestion; the attach refuses for the same reason."""
    from transversal.services.sfx_owner import add_sfx_to_owner, attach_refusal

    gated = _gated_rule("loc-1")
    away = _world_at("loc-9")
    away.get_sfx = lambda sid: gated
    assert attach_refusal(gated, "trait_instance", "ts-1", away) == "can't be acquired here"
    assert add_sfx_to_owner(away, "trait_instance", "ts-1", gated.id) is False
    assert away.entities["ts-1"].sfx_ids == [], "nothing is attached when the gate refuses"

    here = _world_at("loc-1")
    here.get_sfx = lambda sid: gated
    assert attach_refusal(gated, "trait_instance", "ts-1", here) is None
    assert add_sfx_to_owner(here, "trait_instance", "ts-1", gated.id) is True
    assert here.entities["ts-1"].sfx_ids == [gated.id]


# ── The ownership panel lists holders first (B72) ─────────────
#
# The panel exists to manage what is *attached*: a flat list of hundreds buries
# the handful of entities that actually hold a rule. Sorted in one place, so every
# consumer agrees, and *stable* within a count so the repository's own order is
# not disturbed for owners the change is not about.

class _OwnerRepo:
    def __init__(self, entities):
        # (id, name, sfx_ids) triples, in the order the repository would give.
        self._entities = entities

    def list_all_entities(self):
        return [
            SimpleNamespace(id=i, name=n, sfx_ids=list(s),
                            type=SimpleNamespace(value="character"))
            for i, n, s in self._entities
        ]


def test_owners_that_hold_rules_come_first():
    repo = _OwnerRepo([
        ("e-nothing", "Nothing", []),
        ("e-two", "Two", ["sfx-a", "sfx-b"]),
        ("e-one", "One", ["sfx-c"]),
        ("e-also-nothing", "Also Nothing", []),
    ])
    refs = list_owner_refs(repo, "entity")
    assert [r["owner_id"] for r in refs] == ["e-two", "e-one", "e-nothing", "e-also-nothing"]
    assert [len(r["sfx_ids"]) for r in refs] == [2, 1, 0, 0]


def test_the_order_is_stable_for_owners_holding_the_same_count():
    """Ties keep the repository's order — this change is about floating the
    holders up, not about re-sorting the world."""
    repo = _OwnerRepo([
        ("e-b", "B", ["sfx-a"]),
        ("e-a", "A", ["sfx-b"]),
        ("e-c", "C", ["sfx-c"]),
    ])
    assert [r["owner_id"] for r in list_owner_refs(repo, "entity")] == ["e-b", "e-a", "e-c"]


# ── The support character's way home (B61) ────────────

class _SfxRepo:
    """The reads/writes the teleport-to-main provisioning touches."""

    def __init__(self, entities=None, edges=None, sfxs=None):
        self._entities = {e.id: e for e in (entities or [])}
        self._edges = edges or []
        self._sfxs = sfxs or {}

    def get_sfx(self, sfx_id):
        return self._sfxs.get(sfx_id)

    def create_sfx(self, sfx):
        self._sfxs[sfx.id] = sfx
        return sfx

    def get_entity(self, entity_id):
        return self._entities.get(entity_id)

    def list_entities_with_relationship_type(self, rel_type):
        return [e["from"] for e in self._edges if e["type"] == rel_type]

    def get_sfx_owner(self, owner_id):
        return None

    def update_entity(self, entity):
        self._entities[entity.id] = entity
        return entity


def test_the_support_rule_is_a_manual_entity_rule_with_a_guarded_path():
    """The rule says *how* it is used, and the same-universe guard is the filter
    on the contact — without it `location/set` would also write the destination's
    universe, i.e. perform a transversal."""
    from transversal.services.sfx_owner import ensure_teleport_to_main_sfx

    class Creating(_SfxRepo):
        def __init__(self):
            super().__init__()
            self.created = []

        def create_sfx(self, sfx):
            self.created.append(sfx)
            self._sfxs[sfx.id] = sfx
            return sfx

    repo = Creating()
    ensure_teleport_to_main_sfx(repo)
    sfx = repo.created[0]
    assert sfx.id == "sfx-teleport-to-main"
    assert sfx.trigger == "manual" and sfx.source_kind == "entity"
    assert [bv.name for bv in sfx.bound_variables] == ["world"]
    steps = sfx.effects[0].target_spec.steps
    assert [getattr(s, "kind") for s in steps] == \
        ["select", "navigate", "filter", "navigate", "filter", "navigate"]
    # The guard compares the contact's universe to the *bound* name, not a literal.
    guard = steps[4]
    assert (guard.field, guard.value) == ("current_universe", "{world}")
    assert steps[2].value == "support"

    # Idempotent: a second call creates nothing.
    ensure_teleport_to_main_sfx(repo)
    assert len(repo.created) == 1


def test_the_backfill_gives_the_rule_to_support_holders_only():
    """Only the holders of a `support` edge — an SC is a relationship, so that
    edge is the whole test for who gets the rule."""
    from transversal.domain import Entity, EntityType
    from transversal.services.sfx_owner import (
        backfill_support_default_sfx,
        ensure_teleport_to_main_sfx,
    )

    sc = Entity(id="sc-1", type=EntityType.CHARACTER, name="Hanger-on",
                current_universe="earth")
    main = Entity(id="main-1", type=EntityType.CHARACTER, name="Kael",
                  current_universe="earth")
    other = Entity(id="char-9", type=EntityType.CHARACTER, name="Bystander",
                   current_universe="earth")
    repo = _SfxRepo(entities=[sc, main, other],
                    edges=[{"from": "sc-1", "type": "support"},
                           {"from": "main-1", "type": "agency"}])
    ensure_teleport_to_main_sfx(repo)

    assert backfill_support_default_sfx(repo) == 1
    assert repo.get_entity("sc-1").sfx_ids == ["sfx-teleport-to-main"]
    assert repo.get_entity("main-1").sfx_ids == []
    assert repo.get_entity("char-9").sfx_ids == []
    # Idempotent: the second restart changes nothing.
    assert backfill_support_default_sfx(repo) == 0
    assert repo.get_entity("sc-1").sfx_ids == ["sfx-teleport-to-main"]
