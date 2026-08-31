"""Tests for SFX ownership resolution (`services/sfx_owner.py`).

Uses an in-memory repository double so the resolver is exercised standalone
without a live ArangoDB.
"""

from types import SimpleNamespace

from transversal.domain import Condition, ConditionType, Timer
from transversal.services.sfx_owner import (
    backfill_trait_default_sfx,
    ensure_give_in_sfx,
    ensure_sfx_owners,
    ensure_targeting_ban_sfx,
    get_available_sfx_ids,
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


def _entity(sfx_ids=None, current_projection=None):
    return SimpleNamespace(sfx_ids=sfx_ids or [], current_projection=current_projection)


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
    assert sfx.effects[0].target == "{random:location}"
    assert sfx.effects[0].target_scope == "universe:earth"
    assert sfx.effects[0].target_filter == {"starter_location": True}
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
    assert eff.target == "{random:location}"
    assert eff.target_filter == {"starter_location": True}
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
    assert apply_sfx.trigger == "contest_win"
    assert take_sfx.trigger == "contest_give_in"
    assert apply_sfx.name == "Apply a complication"
    assert take_sfx.name == "Take a complication"
    # Identical effect, different label.
    assert apply_sfx.effects[0].action == "cortex_gain"
    assert take_sfx.effects[0].action == "cortex_gain"
    assert apply_sfx.effects[0].negative is True
    assert take_sfx.effects[0].negative is True
    assert apply_sfx.effects[0].target == "{choose_trait}"
    assert take_sfx.effects[0].target_scope == "traitset:ts-complications-a190"
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
    assert apply_sfx.effects[0].target_scope == "traitset:ts-complications-a190"
    assert apply_sfx.trigger == "contest_win"


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
    assert sfx.trigger == "hitch"
    assert len(sfx.effects) == 2
    assert sfx.effects[0].type == "modify_trait"
    assert sfx.effects[0].action == "gain_or_step_up"
    assert sfx.effects[0].entity == "{hitch_entity}"
    assert sfx.effects[0].negative is True
    assert sfx.effects[0].result == "d4"
    assert sfx.effects[0].context == {"steps": "{number_of_hitches}"}
    assert sfx.effects[0].target_scope == "traitset:ts-complications-a190"
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
    assert sfx.trigger == "hitch"
    assert len(sfx.effects) == 2
    assert sfx.effects[0].type == "transfer_razmerit"
    assert sfx.effects[0].action == "spend"
    assert sfx.effects[0].entity == "{buying_entity}"
    assert sfx.effects[0].result == "1"
    assert sfx.effects[1].type == "modify_trait"
    assert sfx.effects[1].action == "step_down"
    assert sfx.effects[1].entity == "{buying_entity}"
    assert sfx.effects[1].target == "{choose_trait}"
    assert sfx.effects[1].target_scope == "traitset:ts-complications-a190"
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
