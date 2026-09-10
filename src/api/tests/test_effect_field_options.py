"""Effect-action field options.

The editor's dropdowns come from the registry ([[effects_registry]]), but some
fields hold *content* rather than an enum — a Target Universe is a universe that
exists in the database, not a fixed pair of keys. Those declare an
``options_from`` source that the GraphQL layer resolves. These tests keep that
seam honest.
"""

from transversal.api.graphql.schema import _OPTION_SOURCES, _universe_options
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY


class _Universe:
    def __init__(self, id, name, current_universe):
        self.id = id
        self.name = name
        self.current_universe = current_universe
        self.type = "universe"


class _Entity:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.current_universe = ""
        self.type = "character"


class _Repo:
    def __init__(self, entities):
        self._entities = entities

    def list_all_entities(self):
        return list(self._entities)


def _universes_in_registry():
    return [
        (meta.action_id, fdef)
        for meta in EFFECT_ACTION_REGISTRY
        for fdef in [*meta.fields, *meta.context_fields]
        if fdef.options_from
    ]


def test_every_declared_option_source_is_resolvable():
    """A typo in ``options_from`` would silently fall back and empty the dropdown."""
    unknown = {fdef.options_from for _aid, fdef in _universes_in_registry()} - set(_OPTION_SOURCES)
    assert not unknown, f"unresolvable option sources: {sorted(unknown)}"


def test_attune_offers_the_universes_in_the_database():
    """The Target Universe field is content-driven, not a hardcoded pair."""
    attune = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "attune")
    field = next(f for f in attune.fields if f.name == "result")
    assert field.options_from == "universes"
    assert len(field.options or []) == 2, "static pair survives only as a fallback"


def test_universe_options_use_the_content_key_with_the_name_as_label():
    repo = _Repo([
        _Universe("universe-earth", "Earth", "earth"),
        _Universe("universe-three_realms", "Three Realms", "three_realms"),
        _Universe("universe-cyberpunk--93f1e911", "Cyberpunk", ""),
        _Entity("char-1", "Someone"),
    ])
    values, labels = _universe_options(repo)
    # ``current_universe`` is the handle an attune effect stores; the entity id
    # (its ``_key``) is the fallback when a universe has no handle — the same
    # convention ``prompt_builder`` uses.
    assert values == ["universe-cyberpunk--93f1e911", "earth", "three_realms"]
    assert labels == ["Cyberpunk", "Earth", "Three Realms"]


def test_fallback_to_static_options_when_the_source_is_empty():
    attune = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "attune")
    field = next(f for f in attune.fields if f.name == "result")
    from transversal.api.graphql.schema import _field_options

    values, labels = _field_options(field, _Repo([]))
    assert values == ["three_realms", "earth"]
    assert labels == []


def test_attune_declares_its_scope():
    """`scope` decides whether an attunement stays on the carrier or radiates."""
    attune = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "attune")
    scope = next(f for f in attune.context_fields if f.name == "scope")
    assert scope.options == ["self", "domain"]
    assert scope.default == "self"


def test_entity_targeted_actions_offer_a_targeting_path():
    """`target_kind` is what puts the path builder on an action's target field."""
    transfer = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "transfer_razmerit")
    assert transfer.target_kind == "entity"
