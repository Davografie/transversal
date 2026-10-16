"""Content bundles — the export half ([[B301]]).

A bundle is a file of whole documents, exported in two phases: a **plan** that
reports what a selection would carry and what it would leave behind, and an
**emit** that writes it. The design calls are in the module docstring
(`services/content_bundle.py`); what is pinned here is the behaviour that is easy
to get quietly wrong:

* **the reference map matches the data.** The map declares meaning by document
  path, and the walker reports the keys a document actually has — so a wildcard
  rule (`refs.*.value`) must match `refs.trait.value`, and a path a future session
  adds must fail the completeness guard rather than vanish from the closure;
* **nothing references itself.** `_key` and `id` are the key and are id-shaped;
* **an anchor is a handle, not an id** (`entities/x`), and existence is a question
  about `x`;
* **the report is about what leaves the bundle**, never about internal edges;
* **an edge is carried iff both endpoints are** — following one end would walk the
  whole world.

Live-ArangoDB tests skip when ArangoDB is unavailable.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from transversal.services.content_bundle import (
    ANCHOR,
    BUNDLE_FORMAT,
    COLLECTIONS,
    CONDITIONS,
    CONTEXT_KINDS,
    EFFECTS,
    ELEMENT_KINDS,
    INCIDENTAL,
    KIND_BY_COLLECTION,
    KINDS,
    LITERAL_STEP,
    REQUIRED,
    RESOLVE,
    RULE_TRIES,
    RULES,
    SKIP,
    SPEC,
    ContentBundleService,
    _candidate_keys,
    _iter_strings,
    _path_str,
    _rule_for,
)

MARKERS = {RESOLVE, LITERAL_STEP, SPEC, EFFECTS, CONDITIONS, ANCHOR, SKIP}


# ── A world small enough to argue about ──────────────────────────────────────


class FakeRepo:
    """An in-memory stand-in for the document reads a bundle makes."""

    def __init__(self, store):
        self.store = store

    def raw_documents(self, collection, keys):
        wanted = set(keys)
        return {
            k: v for k, v in self.store.get(collection, {}).items() if k in wanted
        }

    def locate_documents(self, collections, keys):
        out = {}
        for collection in collections:
            for key in keys:
                if key in self.store.get(collection, {}):
                    out.setdefault(key, collection)
        return out

    def raw_edges_by_anchor(self, collection, handles):
        wanted = set(handles)
        return [
            d for d in self.store.get(collection, {}).values() if d.get("_from") in wanted
        ]

    def raw_traitsettings_by_anchor(self, handles):
        return self.raw_edges_by_anchor("traitsettings", handles)

    def raw_traitsetsettings_by_anchor(self, handles):
        return self.raw_edges_by_anchor("traitsetsettings", handles)

    def raw_relationships_touching(self, handles):
        wanted = set(handles)
        return [
            d
            for d in self.store.get("relationships", {}).values()
            if d.get("_from") in wanted or d.get("_to") in wanted
        ]

    def raw_traits_for_traitsets(self, traitset_ids):
        wanted = set(traitset_ids)
        return [
            d
            for d in self.store.get("traits", {}).values()
            if d.get("traitset_id") in wanted
        ]


WORLD = {
    "traitsets": {
        "ts-skills": {
            "_key": "ts-skills",
            "name": "skills",
            "universes": ["earth"],
            "entity_types": ["character"],
        }
    },
    "traits": {
        "trait-shooting": {
            "_key": "trait-shooting",
            "name": "Shooting",
            "universes": ["earth"],
            "traitset_id": "ts-skills",
            "possible_sfx_ids": [],
        }
    },
    "entities": {
        "gmc-1": {
            "_key": "gmc-1",
            "type": "gmc",
            "name": "Sheriff",
            "current_universe": "earth",
            "current_location": "loc-far",
            "sfx_ids": [],
        },
        "gmc-2": {
            "_key": "gmc-2",
            "type": "gmc",
            "name": "Deputy",
            "current_universe": "earth",
            "sfx_ids": [],
        },
    },
    "traitsettings": {
        "gmc-1:trait-shooting": {
            "_key": "gmc-1:trait-shooting",
            "_from": "entities/gmc-1",
            "_to": "traits/trait-shooting",
            "entity_id": "gmc-1",
            "trait_id": "trait-shooting",
            "from_type": "entity",
            "sfx_ids": [],
        }
    },
    "relationships": {
        "edge:gmc-1:gmc-2:relation": {
            "_key": "edge:gmc-1:gmc-2:relation",
            "_from": "entities/gmc-1",
            "_to": "entities/gmc-2",
            "type": "relation",
        }
    },
}


def service(store=None):
    return ContentBundleService(repository=FakeRepo(store if store is not None else WORLD))


# ── The map against the data it describes ────────────────────────────────────


def test_every_declared_target_is_a_kind_a_context_or_a_marker():
    """A typo in the map would silently become an 'external' reference and never
    be followed, so every declared target must be something the exporter knows."""
    known = set(KINDS) | set(CONTEXT_KINDS) | MARKERS | {
        "player",
        "image",
        "message",
        "historical_record",
        "scheduled_event",
        "plan_entity",
        "sfx_owner",
        "join_token",
    }
    for collection, table in RULES.items():
        for path, rule in table.items():
            assert rule.target in known, f"{collection}:{path} → {rule.target}"
            assert rule.klass in (REQUIRED, INCIDENTAL, "invited")


def test_every_declared_collection_is_a_carried_kind():
    assert set(RULES) == set(COLLECTIONS)
    assert set(RULES) <= set(KIND_BY_COLLECTION)


def test_a_wildcard_rule_matches_the_literal_key_the_walker_reports():
    """The walker reports `refs.trait.value`, never `refs.*.value` — a flat lookup
    would miss every wildcard rule, which is how `effects[].refs.*.spec.steps[]`
    silently stopped being walked."""
    root = RULE_TRIES["roll_tables"]
    literal = ("entries", "[]", "effects", "[]", "refs", "trait", "value")
    assert _rule_for(root, literal) is not None
    assert _rule_for(root, literal).target == RESOLVE
    # …and an exact rule still beats the wildcard.
    spec_step = ("entries", "[]", "effects", "[]", "refs", "trait", "spec", "steps", "[]", "value")
    assert _rule_for(root, spec_step).target == LITERAL_STEP
    # A path with no rule matches nothing rather than something.
    assert _rule_for(root, ("entries", "[]", "made_up", "value")) is None


def test_cost_effects_is_walked_exactly_like_effects():
    """`cost_effects` is on 169 live rows and in no Data Model table. A row's cost
    is part of what the row means, so its references have to be followed."""
    root = RULE_TRIES["roll_tables"]
    for field in ("effects", "cost_effects"):
        rule = _rule_for(root, ("entries", "[]", field, "[]", "target"))
        assert rule is not None and rule.target == RESOLVE


def test_the_identity_of_a_document_is_not_a_reference_to_itself():
    for collection in COLLECTIONS:
        root = RULE_TRIES[collection]
        for identity in ("_key", "id"):
            rule = _rule_for(root, (identity,))
            assert rule is not None, f"{collection}:{identity} has no rule"
            assert rule.target == SKIP, f"{collection}:{identity} is treated as a reference"


def test_paths_render_the_way_a_reader_reads_them():
    assert _path_str(("entries", "[]", "effects", "[]", "target")) == "entries[].effects[].target"
    assert _path_str(("steps", "[]", "value")) == "steps[].value"
    assert _path_str(("_from",)) == "_from"


def test_candidate_keys_reads_a_handle_as_the_id_it_names():
    assert _candidate_keys("gmc-1") == ["gmc-1"]
    assert _candidate_keys("entities/gmc-1") == ["gmc-1"]
    assert _candidate_keys("projections/gmc-1:earth") == ["gmc-1:earth"]
    # `players` is not a carried collection, and a media path is not a key.
    assert _candidate_keys("players/player-abc") == []
    assert _candidate_keys("/media/loc-1.webp") == []


def test_the_walker_reports_a_step_with_its_own_container():
    doc = {"effects": [{"refs": {"trait": {"value": "trait-x"}}}]}
    found = {
        _path_str(path): (value, container is not None)
        for path, value, container in _iter_strings(doc)
    }
    assert found["effects[].refs.trait.value"] == ("trait-x", True)


# ── Planning ────────────────────────────────────────────────────────────────


def test_a_trait_carries_its_set_and_the_set_carries_its_traits():
    """A set's traits point *up* at the set, so the reach back down is a reverse
    read — without it a registry export ships an empty grouping."""
    plan = service().plan([{"kind": "traitset", "id": "ts-skills"}], depth=0)
    assert plan["counts"].get("traitset") == 1
    assert plan["counts"].get("trait") == 1
    assert plan["unruled"] == []


def test_an_entity_carries_its_trait_settings_and_their_traits():
    plan = service().plan([{"kind": "entity", "id": "gmc-1"}], depth=0)
    assert plan["counts"].get("entity") == 1
    assert plan["counts"].get("traitsetting") == 1
    assert plan["counts"].get("trait") == 1
    assert plan["counts"].get("traitset") == 1


def test_the_report_is_about_what_leaves_the_bundle():
    """A reference to something already in the bundle is not a decision for the
    chooser — a closed closure reports nothing required."""
    plan = service().plan([{"kind": "entity", "id": "gmc-1"}], depth=0)
    assert plan["required"] == []


def test_a_reference_outside_the_selection_is_reported_with_its_path():
    plan = service().plan([{"kind": "trait", "id": "trait-shooting"}], depth=1)
    required = {(r["kind"], r["value"]) for r in plan["required"]}
    assert ("traitset", "ts-skills") in required
    row = next(r for r in plan["required"] if r["value"] == "ts-skills")
    assert row["path"] == "traitset_id"
    assert row["exists"] is True
    assert row["carried"] is True


def test_placement_is_incidental_and_never_followed():
    """`current_location` is where an entity *stands*. Following it would walk the
    location tree, and the map, and the world."""
    plan = service().plan([{"kind": "entity", "id": "gmc-1"}], depth=0)
    incidental = {(r["kind"], r["value"]) for r in plan["incidental"]}
    assert ("entity", "loc-far") in incidental
    assert not any(r["value"] == "loc-far" for r in plan["required"])
    # The location it stands in is nowhere in the bundle.
    assert plan["counts"].get("entity") == 1


def test_an_edge_is_carried_when_both_of_its_ends_are_in():
    plan = service().plan(
        [{"kind": "entity", "id": "gmc-1"}, {"kind": "entity", "id": "gmc-2"}], depth=0
    )
    assert plan["counts"].get("relationship") == 1
    assert plan["invited"] == []


def test_an_edge_with_one_end_outside_is_invited_never_carried():
    plan = service().plan([{"kind": "entity", "id": "gmc-1"}], depth=0)
    assert "relationship" not in plan["counts"]
    invited = {(r["kind"], r["value"]) for r in plan["invited"]}
    assert ("entity", "gmc-2") in invited
    row = next(r for r in plan["invited"] if r["value"] == "gmc-2")
    assert row["class"] == "invited"
    assert row["fromId"] == "edge:gmc-1:gmc-2:relation"


def test_an_anchor_is_a_handle_and_is_reported_as_the_id_it_names():
    """`_from`/`_to` are `entities/x`; reporting them verbatim would make every
    anchor look like a missing reference, because no document is keyed by a
    handle."""
    plan = service().plan([{"kind": "entity", "id": "gmc-1"}], depth=0)
    for bucket in ("required", "invited", "incidental"):
        for row in plan[bucket]:
            assert "/" not in row["value"], f"{bucket}: {row}"


def test_a_targeting_step_names_its_own_element_so_an_absent_reference_has_a_kind():
    store = {
        "sfxs": {
            "sfx-gift": {
                "_key": "sfx-gift",
                "name": "Gift",
                "effects": [
                    {
                        "type": "modify_trait",
                        "action": "gain",
                        "target": "",
                        "entity": "",
                        "refs": {
                            "trait": {
                                "value": "",
                                "spec": {
                                    "steps": [
                                        {
                                            "kind": "literal",
                                            "element": "traitset",
                                            "value": "ts-complications-a190",
                                        }
                                    ]
                                },
                            }
                        },
                    }
                ],
            }
        }
    }
    plan = service(store).plan([{"kind": "sfx", "id": "sfx-gift"}], depth=1)
    assert plan["unruled"] == []
    row = plan["required"][0]
    assert row["kind"] == "traitset"
    assert row["value"] == "ts-complications-a190"
    assert row["exists"] is False
    assert row["path"] == "effects[].refs.trait.spec.steps[].value"


def test_an_id_shaped_value_on_an_unruled_path_is_reported_not_dropped():
    store = {
        "traits": {
            "trait-x": {
                "_key": "trait-x",
                "name": "X",
                "universes": [],
                "traitset_id": "ts-skills",
                "brand_new_field": "trait-ghost",
            }
        }
    }
    plan = service(store).plan([{"kind": "trait", "id": "trait-x"}], depth=1)
    assert [r["value"] for r in plan["unruled"]] == ["trait-ghost"]
    assert plan["unruled"][0]["path"] == "brand_new_field"


def test_a_non_id_string_on_an_unruled_path_is_not_a_reference():
    store = {
        "traits": {
            "trait-x": {
                "_key": "trait-x",
                "name": "A perfectly ordinary name",
                "universes": [],
                "traitset_id": "ts-skills",
            }
        }
    }
    plan = service(store).plan([{"kind": "trait", "id": "trait-x"}], depth=1)
    assert plan["unruled"] == []


def test_universe_handles_are_expected_not_missing():
    """A world handle is a string with no document, so it is an *expectation*: the
    target world may not have it, and that is a fact about the world, not a
    dangling reference."""
    plan = service().plan([{"kind": "traitset", "id": "ts-skills"}], depth=1)
    assert plan["expects"] == {"universes": ["earth"]}


def test_an_anchored_kind_cannot_be_asked_for_directly():
    assert service().plan([{"kind": "traitsetting", "id": "gmc-1:trait-shooting"}])["counts"] == {}


def test_an_unknown_kind_plans_nothing():
    assert service().plan([{"kind": "dragon", "id": "d-1"}])["counts"] == {}


# ── Emitting ────────────────────────────────────────────────────────────────


def test_emit_keeps_the_key_and_drops_the_volatile_bookkeeping():
    bundle = service().emit([{"kind": "traitset", "id": "ts-skills"}], depth=0)
    doc = next(d for d in bundle["documents"] if d["kind"] == "traitset")["document"]
    assert doc["_key"] == "ts-skills"
    assert "_id" not in doc and "_rev" not in doc
    # Everything else travels verbatim — a model-based export would drop this.
    assert doc["universes"] == ["earth"]
    assert doc["entity_types"] == ["character"]


def test_emit_embeds_what_it_could_not_find_and_what_it_left_behind():
    store = json.loads(json.dumps(WORLD))
    store["entities"]["gmc-1"]["current_location"] = None
    store["traits"]["trait-shooting"]["possible_sfx_ids"] = ["sfx-ghost"]
    bundle = service(store).emit([{"kind": "entity", "id": "gmc-1"}], depth=0)
    unresolved = {(r["kind"], r["value"]) for r in bundle["unresolved"]}
    assert ("sfx", "sfx-ghost") in unresolved
    assert bundle["format"] == BUNDLE_FORMAT
    assert bundle["bundleId"]


def test_emit_is_json_serialisable_and_states_the_format():
    bundle = service().emit([{"kind": "entity", "id": "gmc-1"}], depth=0)
    text = ContentBundleService.to_json(bundle)
    again = json.loads(text)
    assert again["format"] == BUNDLE_FORMAT
    assert again["source"]["depth"] == 0


def test_a_planned_bundle_and_an_emitted_one_agree_on_what_is_in_it():
    """The two phases are one walk; if they could disagree, the report would be
    describing a different bundle than the one that gets written."""
    svc = service()
    selection = [{"kind": "entity", "id": "gmc-1"}]
    plan = svc.plan(selection, depth=0)
    bundle = svc.emit(selection, depth=0)
    assert plan["counts"] == bundle["counts"]
    assert {r["value"] for r in plan["required"]} == {r["value"] for r in bundle["unresolved"]}


# ── Live ArangoDB ────────────────────────────────────────────────────────────

try:
    from transversal.db.repository import EntityRepository

    _repo = EntityRepository()
    HAVE_DB = True
except Exception:  # pragma: no cover - the whole class skips
    _repo = None
    HAVE_DB = False


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
class TestAgainstLiveArango:
    def test_every_id_shaped_value_live_sits_on_a_ruled_path(self):
        """The completeness guard, and the reason the map is testable at all.

        For every document of every carried collection: every id-shaped string must
        sit on a path the map declares. A field a future session adds belongs here
        first — otherwise it is silently absent from every closure, which is how
        [[B156]]'s 50 dangling targets arrived.
        """
        from transversal.services.content_bundle import _ID_SHAPED, _rule_for

        unruled: dict[tuple[str, str], str] = {}
        for spec in ELEMENT_KINDS:
            for doc in _repo.raw_documents(
                spec.collection,
                [d["_key"] for d in _repo.db.aql.execute(
                    f"FOR d IN {spec.collection} RETURN {{'_key': d._key}}"
                )],
            ).values():
                root = RULE_TRIES[spec.collection]
                for path, value, _ in _iter_strings(doc):
                    if not _ID_SHAPED.match(value):
                        continue
                    if _rule_for(root, path) is None:
                        unruled.setdefault(
                            (spec.collection, _path_str(path)), value
                        )
        assert unruled == {}, f"unruled id-shaped paths: {unruled}"

    def test_a_real_selection_plans_and_closes_without_unruled_values(self):
        svc = ContentBundleService(repository=_repo)
        plan = svc.plan([{"kind": "traitset", "id": "ts-3"}], depth=0)
        assert plan["unruled"] == []
        assert plan["counts"].get("trait", 0) > 0
        # A closed closure has nothing left outside it.
        assert plan["required"] == []

    def test_the_live_dangling_reference_is_reported_rather_than_laundered(self):
        """Three live SFX name a trait set that does not exist. A bundle must say
        so at export; an importer that only found out at the table is the failure
        mode this whole report exists to prevent."""
        svc = ContentBundleService(repository=_repo)
        sfx = next(
            (
                d["_key"]
                for d in _repo.db.aql.execute(
                    "FOR d IN sfxs SORT d._key RETURN {'_key': d._key, 'd': d}"
                )
                if "ts-complications-a190" in json.dumps(d["d"])
            ),
            None,
        )
        if sfx is None:
            pytest.skip("the dangling traitset reference is gone from the live data")
        plan = svc.plan([{"kind": "sfx", "id": sfx}], depth=1)
        missing = [
            r for r in plan["required"] if r["value"] == "ts-complications-a190"
        ]
        assert missing, plan["required"]
        assert missing[0]["exists"] is False
        assert missing[0]["kind"] == "traitset"


# ── The REST surface ────────────────────────────────────────────────────────

from transversal.api import auth  # noqa: E402
from transversal.api.rest import bundles as bundles_mod  # noqa: E402

GOOD_SECRET = "a" * 64


class _Request:
    def __init__(self, cookies=None):
        self.headers = {}
        self.cookies = cookies or {}


@pytest.fixture
def owner(monkeypatch):
    """An owner session, with the player lookup and the document reads stubbed.

    Ownership rides the **session**, not the role — the same shape every route test
    uses, and the separation that stops "take the owner's player" from being
    "become the owner".
    """
    monkeypatch.setenv("SESSION_SECRET", GOOD_SECRET)
    monkeypatch.setattr(bundles_mod, "_service", lambda: service())
    fake = SimpleNamespace(
        get=lambda pid: SimpleNamespace(id=pid, name="Dave", role="player", epoch=0)
    )
    monkeypatch.setattr(auth, "player_manager", fake)
    return _Request({auth.COOKIE_NAME: auth.mint_session("player-abc", 0, owner=True)})


@pytest.fixture
def player(monkeypatch, owner):
    """The same device, admitted but not the owner."""
    return _Request({auth.COOKIE_NAME: auth.mint_session("player-abc", 0, owner=False)})


async def test_the_vocabulary_is_served_not_documented_twice(owner):
    answer = await bundles_mod.bundle_kinds(owner)
    kinds = {k["kind"] for k in answer["kinds"]}
    assert kinds == {k.key for k in ELEMENT_KINDS if k.selectable}
    assert answer["format"] == BUNDLE_FORMAT
    # Anchored kinds are named too — a reader of an export should be able to learn
    # what arrives inside one element without reading the source.
    assert {a["kind"] for a in answer["anchored"]} == {
        k.key for k in ELEMENT_KINDS if k.anchored
    }


async def test_plan_answers_with_a_report_and_writes_nothing(owner):
    answer = await bundles_mod.plan_bundle(
        owner, bundles_mod.BundleRequest(selection=[{"kind": "entity", "id": "gmc-1"}], depth=0)
    )
    assert answer["counts"]["entity"] == 1
    assert "documents" not in answer


async def test_export_hands_back_a_file(owner):
    response = await bundles_mod.export_bundle(
        owner, bundles_mod.BundleRequest(selection=[{"kind": "entity", "id": "gmc-1"}], depth=0)
    )
    assert response.media_type == "application/json"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.json"')
    bundle = json.loads(response.body)
    assert bundle["format"] == BUNDLE_FORMAT
    assert bundle["counts"]["entity"] == 1


async def test_an_unknown_kind_is_an_error_not_an_empty_bundle(owner):
    """A bundle that silently exports nothing is indistinguishable from a bundle
    of nothing, and the caller cannot tell which it got."""
    with pytest.raises(HTTPException) as caught:
        await bundles_mod.plan_bundle(
            owner, bundles_mod.BundleRequest(selection=[{"kind": "dragon", "id": "d-1"}])
        )
    assert caught.value.status_code == 400
    assert "dragon" in caught.value.detail


async def test_an_empty_selection_is_refused(owner):
    with pytest.raises(HTTPException) as caught:
        await bundles_mod.plan_bundle(owner, bundles_mod.BundleRequest(selection=[]))
    assert caught.value.status_code == 400


async def test_a_depth_out_of_range_is_refused(owner):
    for depth in (-1, bundles_mod._MAX_DEPTH + 1):
        with pytest.raises(HTTPException) as caught:
            await bundles_mod.plan_bundle(
                owner,
                bundles_mod.BundleRequest(
                    selection=[{"kind": "entity", "id": "gmc-1"}], depth=depth
                ),
            )
        assert caught.value.status_code == 400


async def test_a_non_owner_may_not_export_the_campaign(player):
    """A bundle reaches the whole authored surface of the campaign — registry,
    SFX, life paths, entities — which is GM material, not player material."""
    with pytest.raises(HTTPException) as caught:
        await bundles_mod.plan_bundle(
            player, bundles_mod.BundleRequest(selection=[{"kind": "entity", "id": "gmc-1"}])
        )
    assert caught.value.status_code == 403
