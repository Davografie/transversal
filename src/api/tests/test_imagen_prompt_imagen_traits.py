"""The imagen traits, and the active-body fallback that gets them into a prompt.

Two defects, both filed by [[mcp-architect]] and both silent:

1. Creating a trait setting through the API anchors it to the active body
   (``from_type='projection'``), but the prompt path had no ``current_projection``
   fallback while ``Entity.image()`` did — so generating without naming a
   projection dropped every morph-anchored trait. 19 locations' appearances and
   the 27 entities mcp-architect authored were invisible to the generator.
2. ``negative imagen`` and ``positive imagen`` gated on ``statement`` alone while
   most live settings keep their text in ``notes`` — 231 of 423 ``negative
   imagen`` settings never reached the generator.
"""

import pytest

from transversal.domain import Entity, EntityType
from transversal.domain.traits import TraitSetting
from transversal.imagen import prompt_builder

UNIVERSE = "test_universe"  # not in UNIVERSE_STYLE_GUIDE


class _StubTrait:
    def __init__(self, name: str):
        self.name = name


class _StubProjection:
    def __init__(self, universe: str):
        self.universe = universe
        self.origin_universe = universe


class _StubRepository:
    """Records the (entity, universes, projection) each lookup is asked for."""

    def __init__(self, names=None, settings=None):
        self._names = names or {}
        self._settings = settings or []
        self.calls = []

    def get_trait(self, trait_id):
        name = self._names.get(trait_id)
        return _StubTrait(name) if name else None

    def get_prompt_traitsettings(self, entity_id, universes, projection_id=None):
        self.calls.append((entity_id, projection_id))
        return self._settings

    def get_projection(self, projection_id):
        return _StubProjection(UNIVERSE)


def _setting(trait_id: str, statement: str = "", notes: str = "") -> TraitSetting:
    return TraitSetting(
        id=f"ts-{trait_id}",
        entity_id="e1",
        trait_id=trait_id,
        statement=statement,
        notes=notes,
    )


def _entity(current_projection=None) -> Entity:
    return Entity(
        id="e1",
        type=EntityType.CHARACTER,
        name="Kael",
        current_universe=UNIVERSE,
        current_projection=current_projection,
    )


def _build(settings, names, monkeypatch):
    monkeypatch.setattr(prompt_builder, "EntityRepository", lambda: _StubRepository(names))
    return prompt_builder._build_entity_prompt(_entity(), settings, UNIVERSE)


# ── negative / positive imagen ───────────────────────────────


def test_notes_only_negative_imagen_reaches_the_negative_prompt(monkeypatch):
    prompt, negative, _loras, _steps = _build(
        [_setting("t-neg", notes="blurry, extra fingers")],
        {"t-neg": "negative imagen"},
        monkeypatch,
    )

    assert "blurry, extra fingers" in negative


def test_statement_negative_imagen_still_reaches_the_negative_prompt(monkeypatch):
    _prompt, negative, _loras, _steps = _build(
        [_setting("t-neg", statement="watermark")], {"t-neg": "negative imagen"}, monkeypatch
    )

    assert "watermark" in negative


def test_negative_imagen_merges_statement_and_notes(monkeypatch):
    _prompt, negative, _loras, _steps = _build(
        [_setting("t-neg", "watermark", "extra fingers")],
        {"t-neg": "negative imagen"},
        monkeypatch,
    )

    assert "watermark, extra fingers" in negative


def test_notes_only_positive_imagen_reaches_the_prompt(monkeypatch):
    prompt, _negative, _loras, _steps = _build(
        [_setting("t-pos", notes="god rays, volumetric lighting")],
        {"t-pos": "positive imagen"},
        monkeypatch,
    )

    assert "(god rays, volumetric lighting:0.8)" in prompt


def test_lora_value_is_never_merged_with_notes(monkeypatch):
    """It becomes a filename (`flux/{name}.safetensors`) — notes would corrupt it."""
    _prompt, _negative, loras, _steps = _build(
        [_setting("t-lora", "FluxRealism", "some unrelated free text")],
        {"t-lora": "LoRA 1"},
        monkeypatch,
    )

    assert loras == ["FluxRealism"]


# ── the active-body fallback ─────────────────────────────────


def test_no_projection_falls_back_to_the_active_body():
    repo = _StubRepository()

    prompt_builder.build_imagen_prompt(_entity("e1:earth"), UNIVERSE, repo)

    assert repo.calls == [("e1", "e1:earth")], (
        "an unnamed projection must resolve to current_projection, as Entity.image() does"
    )


def test_an_explicit_projection_wins_over_the_active_body():
    repo = _StubRepository()

    prompt_builder.build_imagen_prompt(_entity("e1:earth"), UNIVERSE, repo, "e1:three_realms")

    assert repo.calls == [("e1", "e1:three_realms")]


def test_a_bodyless_entity_still_uses_entity_traits_only():
    repo = _StubRepository()

    prompt_builder.build_imagen_prompt(_entity(None), UNIVERSE, repo)

    assert repo.calls == [("e1", None)]
