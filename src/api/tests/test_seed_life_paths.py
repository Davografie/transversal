"""Tests for the life path content seed (faction + linked roll tables)."""

from transversal.db.seed import seed_life_paths
from transversal.domain import (
    Entity,
    LifePath,
    RollTable,
)


class SeedRepo:
    """Minimal dict-backed repo for the life path seed."""

    def __init__(self):
        self.entities: dict[str, Entity] = {}
        self.lifepaths: dict[str, LifePath] = {}
        self.tables: dict[str, RollTable] = {}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def create_entity(self, e):
        self.entities[e.id] = e
        return e

    def update_entity(self, e):
        self.entities[e.id] = e
        return e

    def get_lifepath(self, lid):
        return self.lifepaths.get(lid)

    def create_lifepath(self, lp):
        self.lifepaths[lp.id] = lp
        return lp

    def update_lifepath(self, lp):
        self.lifepaths[lp.id] = lp
        return lp

    def get_roll_table(self, tid):
        return self.tables.get(tid)

    def create_roll_table(self, t):
        self.tables[t.id] = t
        return t

    def update_roll_table(self, t):
        self.tables[t.id] = t
        return t

    def delete_roll_table(self, tid):
        self.tables.pop(tid, None)
        return True


def test_seed_wires_verdant_path():
    repo = SeedRepo()
    seed_life_paths(repo)

    faction = repo.get_entity("fac-verdant-steps")
    assert faction is not None
    assert faction.active_universes == ["three_realms"]
    assert faction.suitable_life_path_ids == ["lp-verdant-disciple"]

    lp = repo.get_lifepath("lp-verdant-disciple")
    assert lp is not None
    assert lp.entry_table_id == "rt-verdant-qualify"

    # All six Verdant chain tables exist.
    expected_tables = {
        "rt-verdant-qualify",
        "rt-verdant-learn",
        "rt-verdant-mishap",
        "rt-verdant-advance",
        "rt-survive",
        "rt-continue",
    }
    assert expected_tables.issubset(set(repo.tables))


def test_seed_wires_drifter_path():
    repo = SeedRepo()
    seed_life_paths(repo)

    rogue = repo.get_entity("fac-rogue-cultivators")
    assert rogue is not None
    assert rogue.active_universes == ["three_realms"]
    assert rogue.suitable_life_path_ids == ["lp-drifter-three-realms"]

    lp = repo.get_lifepath("lp-drifter-three-realms")
    assert lp is not None
    assert lp.entry_table_id == "rt-drifter-3r-learn"

    drifter_tables = {
        "rt-drifter-3r-learn",
        "rt-drifter-3r-mishap",
        "rt-drifter-3r-advance",
        "rt-survive",
        "rt-continue",
    }
    assert drifter_tables.issubset(set(repo.tables))


def test_seed_table_links_are_coherent():
    repo = SeedRepo()
    seed_life_paths(repo)

    table_ids = set(repo.tables)

    for table in repo.tables.values():
        for entry in table.entries:
            for effect in entry.effects:
                if effect.type != "life_path" or effect.action not in ("next_step", "draft"):
                    continue
                target = effect.target or ""
                if target in ("", "{continue}"):
                    continue
                if target.startswith("{choose"):
                    continue
                if target.startswith("{return:"):
                    continue
                assert target in table_ids, (
                    f"{table.id} entry '{entry.label}' links to unknown table '{target}'"
                )


def test_seed_is_idempotent():
    repo = SeedRepo()
    seed_life_paths(repo)
    first_tables = dict(repo.tables)

    seed_life_paths(repo)
    assert set(repo.tables) == set(first_tables)
    assert repo.get_lifepath("lp-verdant-disciple").entry_table_id == "rt-verdant-qualify"


def test_shared_tables_use_named_exits():
    repo = SeedRepo()
    seed_life_paths(repo)

    survive = repo.get_roll_table("rt-survive")
    assert survive is not None
    assert survive.life_path is None
    assert survive.universe == ""  # fundamental (global, not universe-scoped)
    survive_exits = {
        effect.target
        for entry in survive.entries
        for effect in entry.effects
        if effect.action == "next_step"
    }
    assert survive_exits == {"{return:injured}", "{return:survived}"}

    cont = repo.get_roll_table("rt-continue")
    assert cont is not None
    assert cont.life_path is None
    assert cont.universe == ""  # fundamental (global, not universe-scoped)
    serve = next(e for e in cont.entries if e.label == "Serve another term")
    assert any(eff.target == "{return:next}" for eff in serve.effects)
    # Tenure targets the current term's faction, not a hardcoded one.
    assert any(eff.context.get("relationship") == "{term_faction}" for eff in serve.effects)


def test_a_demotion_targets_a_rating_die_not_a_trait():
    """A rating is a *list*, so "step down the rank" has to name which die.

    The trait-level verb (retired) stepped the smallest one silently, which no card
    could say; the seeded demotion therefore names the die through a path — the tie
    to this faction, the rank instance anchored to it, then the lowest of its dice.
    """
    repo = SeedRepo()
    seed_life_paths(repo)

    table = repo.get_roll_table("rt-verdant-mishap")
    assert table is not None
    demoted = next(e for e in table.entries if e.label == "Demoted")
    step = next(e for e in demoted.effects if e.action == "step_down_die")
    assert (step.type, step.target) == ("modify_roll", ""), "the target comes from the path"

    path = [s for s in step.target_spec.steps]
    assert [s.kind for s in path] == ["select", "navigate", "filter", "filter",
                                      "navigate", "filter", "navigate", "aggregate"]
    assert (path[2].field, path[2].value) == ("contact_id", "fac-verdant-steps")
    assert (path[3].field, path[3].value) == ("type", "membership")
    assert (path[5].field, path[5].value) == ("trait_id", "trait-rel-rank")
    assert path[6].edge == "rating_dice"
    assert (path[7].fn, path[7].field) == ("bottom", "rating"), "the lowest die, as before"
