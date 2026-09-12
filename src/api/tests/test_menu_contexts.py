"""Tests for the trigger/menu-context variable contract."""

from transversal.services.menu_contexts import (
    MENU_CONTEXT_IDS,
    TRIGGERS,
    menu_context_variables,
    trigger_variables,
)


def _names(vs):
    return [v.name for v in vs]


def test_menu_context_ids_declared():
    assert set(MENU_CONTEXT_IDS) == {
        "test_success", "simplified_roll", "contest_win", "contest_give_in", "hitch",
    }


def test_hitch_variables_are_typed():
    vs = menu_context_variables("hitch")
    assert {v.name: v.type for v in vs} == {
        "number_of_hitches": "number",
        "buying_entity": "entity",
        "hitch_entity": "entity",
    }


def test_contest_win_variables():
    vs = _names(menu_context_variables("contest_win"))
    assert "contest_entity_opponent" in vs
    assert "contest_projection_opponent" in vs
    assert "effect_die" in vs


def test_unknown_menu_context_is_empty():
    assert menu_context_variables("nope") == []


def test_trigger_variables_for_contests():
    assert "effect_die" in _names(trigger_variables("on_contest_win"))
    assert trigger_variables("on_roll") == []


def test_trigger_variables_for_state_events():
    vs = _names(trigger_variables("on_give_in"))
    assert "contest_entity_opponent" in vs
    assert "gave_in" in vs
    assert "pushed" in _names(trigger_variables("on_push"))
    assert "effect_die" in _names(trigger_variables("on_prevent_taken_out"))


def test_on_character_create_exposes_created_entity():
    vs = trigger_variables("on_character_create")
    assert {v.name: v.type for v in vs} == {"entity_created": "entity"}


def test_on_set_exposes_total_and_effect_die():
    vs = trigger_variables("on_set")
    assert {v.name: v.type for v in vs} == {"effect_die": "die", "total": "number"}


def test_on_result_exposes_total_and_effect_die():
    vs = trigger_variables("on_result")
    assert {v.name: v.type for v in vs} == {"effect_die": "die", "total": "number"}


def test_beat_and_scene_triggers_are_declared():
    by_value = {t.value: t for t in TRIGGERS}
    assert by_value["on_beat"].label == "On Beat Advance"
    assert by_value["on_beat"].group == "auto"
    assert list(by_value["on_beat"].variables) == []
    assert by_value["on_scene"].label == "On Scene Advance"
    assert by_value["on_scene"].group == "auto"
    assert list(by_value["on_scene"].variables) == []


def test_on_projection_create_exposes_projection_context():
    vs = trigger_variables("on_projection_create")
    assert {v.name: v.type for v in vs} == {
        "entity_created": "entity",
        "projection_created": "projection",
        "universe": "universe",
    }


def test_triggers_registry_declares_labels_and_variables():
    by_value = {t.value: t for t in TRIGGERS}
    # Every trigger the editor renders has a human label.
    assert all(t.label for t in TRIGGERS)
    # The auto-fire vocabulary matches the engine's matching rules.
    assert "on_character_create" in by_value
    assert by_value["on_character_create"].label == "On Character Created"
    assert _names(list(by_value["on_character_create"].variables)) == ["entity_created"]
    # Variables live beside their trigger in the same registry.
    assert "effect_die" in _names(list(by_value["on_contest_win"].variables))


def _fake_fire(monkeypatch, get_entity):
    """Patch the app singletons so ``fire_state_sfx``/``fire_contest_outcome_sfx``
    capture their GameEvent instead of mutating state."""
    from types import SimpleNamespace

    captured = []

    class FakeEngine:
        def process_event_outcome(self, event, sfx_ids, razmerit, repo=None):
            captured.append(event)
            return SimpleNamespace(applied=[], pending=[], structured=[])

    monkeypatch.setattr("transversal.main._get_engine", lambda: FakeEngine())
    monkeypatch.setattr("transversal.main._get_repo", lambda: SimpleNamespace(get_entity=get_entity))
    monkeypatch.setattr("transversal.services.sfx_owner.get_available_sfx_ids", lambda *a, **k: [])
    return captured


def test_state_fire_sites_populate_declared_variables(monkeypatch):
    """Every trigger variable a state trigger declares is actually populated."""
    from transversal.services import state_events

    # event_type → trigger string (mirrors EffectsEngine._trigger_matches).
    event_trigger = {
        "character_created": "on_character_create",
        "projection_created": "on_projection_create",
        "location_changed": "on_location_change",
        "trait_updated": "on_trait_change",
        "relationship_created": "on_relationship_create",
    }
    cases = {
        "character_created": {"entity_created": "c1"},
        "projection_created": {"entity_created": "c1", "projection_created": "c1:three_realms", "universe": "three_realms"},
        "location_changed": {"from_location": "a", "to_location": "b", "universe": "earth",
                                "arrival_kind": "move"},
        "trait_updated": {"trait": "t1", "traitset": "ts1"},
        "relationship_created": {"target_entity": "e2", "relationship_type": "ally"},
        "on_trait_learn": {"trait": "t1", "trait_setting": "s1", "owner": "o", "learner": "l"},
        "on_trait_offered": {"trait": "t1", "trait_setting": "s1", "owner": "o", "opponent": "p", "newly_revealed": "true"},
        "on_give_in": {"gave_in": True, "contest_entity_opponent": "x"},
        "on_push": {"pushed": True},
        "on_taken_out": {"taken_out": True, "contest_entity_opponent": "x"},
        "on_prevent_taken_out": {"prevented": True, "effect_die": "d6"},
        "on_set": {"effect_die": "d6", "total": 11},
    }

    from types import SimpleNamespace

    captured = _fake_fire(
        monkeypatch,
        lambda eid: SimpleNamespace(razmerit=0, current_universe="earth"),
    )
    for event_type, context in cases.items():
        captured.clear()
        state_events.fire_state_sfx("e1", "earth", event_type, context)
        assert len(captured) == 1, event_type
        trigger = event_trigger.get(event_type, event_type)
        declared = {v.name for v in trigger_variables(trigger)}
        missing = declared - set(captured[0].context)
        assert not missing, f"{trigger}: declared {sorted(missing)} but fire site did not populate them"


def test_contest_fire_site_populates_declared_variables(monkeypatch):
    """Contest triggers declare variables the contest fire site actually produces."""
    from types import SimpleNamespace

    from transversal.services import state_events

    captured = _fake_fire(
        monkeypatch,
        lambda eid: SimpleNamespace(razmerit=0, current_universe="earth", current_projection=None),
    )
    state_events.fire_contest_outcome_sfx(
        "winner", "loser", "earth", effect_die="d6", high_stakes=True, taken_out=False
    )

    declared = {v.name for v in trigger_variables("on_contest_win")}
    assert len(captured) == 2  # winner + loser
    for event in captured:
        missing = declared - set(event.context)
        assert not missing, f"contest: declared {sorted(missing)} but fire site did not populate them"


def test_fire_projection_created_populates_context(monkeypatch):
    """The shared projection-created fire site populates its declared variables."""
    from types import SimpleNamespace

    from transversal.services import state_events

    captured = _fake_fire(
        monkeypatch,
        lambda eid: SimpleNamespace(razmerit=0, current_universe="three_realms"),
    )
    state_events.fire_projection_created("e1", "three_realms", "e1:three_realms")
    assert len(captured) == 1
    assert captured[0].type == "projection_created"
    assert captured[0].context == {
        "entity_created": "e1",
        "projection_created": "e1:three_realms",
        "universe": "three_realms",
    }


def test_fire_challenge_completed_populates_context(monkeypatch):
    """The challenge-completed fire site populates its declared trigger variables."""
    from types import SimpleNamespace

    from transversal.domain import DieType, Polarity, RatingType, TraitSetting
    from transversal.services.challenge_pools import fire_challenge_completed

    captured = _fake_fire(
        monkeypatch,
        lambda eid: SimpleNamespace(razmerit=0, current_universe="three_realms"),
    )
    ts = TraitSetting(
        id="e1:trait-gate", entity_id="e1", trait_id="trait-gate",
        traitset_id="ts-location", rating_type=RatingType.CHALLENGE,
        dice=[DieType.D6, DieType.D6, DieType.D6],
        capacity=[DieType.D6, DieType.D6, DieType.D6],
        polarity=Polarity.POSITIVE,
    )
    assert fire_challenge_completed(ts, "three_realms") is True
    assert len(captured) == 1
    assert captured[0].type == "challenge_completed"
    assert captured[0].context == {
        "entity_id": "e1",
        "trait_setting_id": "e1:trait-gate",
        "trait_id": "trait-gate",
        "capacity": ["d6", "d6", "d6"],
    }


# ── Arrival triggers: the rule is spent as its audience walks in ──────

def test_arrival_is_declared_in_the_catalogue_not_guessed():
    """One declaration site: the sheet's place-rules strip reads this to decide
    what a place is still lending you (see [[Place-Owned Rules]])."""
    from transversal.services.menu_contexts import trigger_fires_on_arrival

    assert trigger_fires_on_arrival("on_location_change") is True
    assert trigger_fires_on_arrival("manual") is False
    assert trigger_fires_on_arrival("on_roll") is False
    assert trigger_fires_on_arrival("on_scene") is False


def test_the_arrival_flag_is_an_amendment_not_a_deletion():
    """The trigger is still authored, still offered, still carries its variables —
    it is only *flagged*, so nothing else that walks TRIGGERS changes meaning."""
    from transversal.services.menu_contexts import trigger_fires_on_arrival

    arrival = [t for t in TRIGGERS if t.fires_on_arrival]
    assert [t.value for t in arrival] == ["on_location_change"]
    assert [v.name for v in trigger_variables("on_location_change")] == [
        "from_location", "to_location", "universe", "arrival_kind",
    ]


def test_an_unmodelled_trigger_is_never_called_arrival():
    """The catalogue forbids, it never claims to prove: an unknown trigger keeps
    its rule visible rather than silently dropping it from the strip."""
    from transversal.services.menu_contexts import trigger_fires_on_arrival

    assert trigger_fires_on_arrival("on_something_new") is False
    assert trigger_fires_on_arrival("") is False


def test_menu_is_a_trigger_because_a_placement_could_disagree_with_it():
    """`menu` is the post-roll menu offered as a trigger. It is grouped under
    Manual (a person still picks it), it isn't an arrival rule, and it carries no
    `on_` prefix — which is what makes `derive_placement` read it as the menu
    without a special case."""
    from transversal.services.menu_contexts import trigger_fires_on_arrival

    menu = [t for t in TRIGGERS if t.value == "menu"]
    assert len(menu) == 1
    assert menu[0].group == "manual"
    assert trigger_fires_on_arrival("menu") is False


def test_a_menu_rule_reads_the_menu_context_keys():
    """Conditions on a menu rule are evaluated against the menu's context (the
    outcome keys), whether the rule says `trigger="menu"` or carries the legacy
    `placement="menu"` — one map, both spellings."""
    from transversal.services.conditions import context_keys_for

    new = context_keys_for("menu", "", None)
    legacy = context_keys_for("manual", "", "menu")
    assert new is not None and new == legacy
    assert "role" in new


def test_an_ordinary_trigger_is_still_unrestricted_by_this():
    from transversal.services.conditions import context_keys_for

    assert context_keys_for("", "", None) is None
