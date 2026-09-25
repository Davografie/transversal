"""The appearance trait's freeform `notes` must reach the image prompt.

A trait setting carries a short `statement` (the distinction, e.g. "lithe") and
longer freeform `notes`. For the `appearance` trait both are authored appearance
description, so prompt building must inject both — an appearance clause built
from the statement alone silently discards most of what a GM writes about how a
character looks.

`EntityRepository` is stubbed out: the point under test is prompt assembly, not
trait lookup, and this keeps the test off Arango.
"""

import pytest

from transversal.domain import Entity, EntityType, TraitSetting
from transversal.imagen import prompt_builder

# Not in UNIVERSE_STYLE_GUIDE, so the positive prompt carries only the entity
# base clause and the trait clauses under test.
UNIVERSE = "test_universe"


class _StubTrait:
    def __init__(self, name: str):
        self.name = name


class _StubRepository:
    """Minimal stand-in for EntityRepository.get_trait."""

    def __init__(self, names: dict[str, str]):
        self._names = names

    def get_trait(self, trait_id: str):
        name = self._names.get(trait_id)
        return _StubTrait(name) if name else None


@pytest.fixture
def build_prompt(monkeypatch):
    """``build_prompt(settings, names)`` → the positive prompt for Kael."""

    def _build(settings, names):
        monkeypatch.setattr(
            prompt_builder, "EntityRepository", lambda: _StubRepository(names)
        )
        entity = Entity(
            id="e1",
            type=EntityType.CHARACTER,
            name="Kael",
            current_universe=UNIVERSE,
        )
        prompt, _negative, _loras, _steps = prompt_builder._build_entity_prompt(
            entity, settings, UNIVERSE
        )
        return prompt

    return _build


def _appearance(statement: str = "", notes: str = "") -> TraitSetting:
    return TraitSetting(
        id="ts1",
        entity_id="e1",
        trait_id="t-appearance",
        statement=statement,
        notes=notes,
    )


def test_appearance_statement_and_notes_share_one_emphasised_clause(build_prompt):
    prompt = build_prompt(
        [_appearance("lithe", "a tall woman with a silver scar over one eye")],
        {"t-appearance": "appearance"},
    )

    assert "(lithe, a tall woman with a silver scar over one eye:1.4)" in prompt


def test_appearance_notes_alone_still_reach_the_prompt(build_prompt):
    prompt = build_prompt(
        [_appearance("", "shaved head, mechanical left arm")],
        {"t-appearance": "appearance"},
    )

    assert "(shaved head, mechanical left arm:1.4)" in prompt


def test_appearance_clause_is_omitted_when_both_fields_are_empty(build_prompt):
    prompt = build_prompt(
        [_appearance("", "")], {"t-appearance": "appearance"}
    )

    assert ":1.4)" not in prompt


def test_whitespace_only_notes_do_not_add_an_empty_clause(build_prompt):
    prompt = build_prompt(
        [_appearance("lithe", "   \n  ")], {"t-appearance": "appearance"}
    )

    assert "(lithe:1.4)" in prompt


def test_notes_are_sanitised_like_the_statement(build_prompt):
    # `clean_text` drops parenthetical asides and unusual punctuation, and the
    # assembled prompt collapses whitespace at the end.
    prompt = build_prompt(
        [_appearance("lithe", "wears a (faded) red coat — torn at the hem")],
        {"t-appearance": "appearance"},
    )

    assert "(lithe, wears a red coat torn at the hem:1.4)" in prompt


def test_notes_on_other_traits_are_not_injected(build_prompt):
    """Scope guard: only the appearance trait's notes feed the prompt."""
    setting = TraitSetting(
        id="ts2",
        entity_id="e1",
        trait_id="t-asset",
        statement="a battered compass",
        notes="SECRET-NOTES-TEXT",
    )
    prompt = build_prompt([setting], {"t-asset": "asset"})

    assert "SECRET-NOTES-TEXT" not in prompt
    assert "a battered compass" in prompt
