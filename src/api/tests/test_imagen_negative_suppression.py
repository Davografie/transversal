"""Watermark / text / caption suppression, and the way NOT to do it.

`AC0081AA` came back unusable as a background: a calligraphic inscription and two
red seal stamps baked into the top-right corner. The cause was a **style LoRA**,
not the prompt — `ChineseScrollPainting`, applied automatically to `three_realms`
locations from the universe's `LOCATION` lora config. A scroll-painting LoRA is
trained on images that carry inscriptions and seals, and it reproduced them over
an explicit `text, watermark, signature` negative.

Reproduced at the artefact's own seed with that LoRA at its real weight, then
fixed by widening the **negative** vocabulary alone (same seed, same LoRA).

The negative that produced *more* calligraphy than the baseline was a **positive**
clause reading "no text, no calligraphy, no seal stamps" — Flux/T5 does not
negate, so naming the thing summons it. That is why this only ever goes in the
negative, and why there is a test guarding the positive against it.
"""

import pytest

from transversal.domain import Entity, EntityType
from transversal.imagen import prompt_builder
from transversal.imagen.models import DEFAULT_NEGATIVE

UNIVERSE = "test_universe"

SUPPRESSION_TERMS = [
    "watermark",
    "signature",
    "text",
    "caption",
    "lettering",
    "writing",
    "calligraphy",
    "inscription",
    "seal",
    "seal stamp",
    "red seal",
    "logo",
    "title",
    "signage",
    "chinese characters",
    "kanji",
    "border",
    "frame",
]


class _StubTrait:
    def __init__(self, name):
        self.name = name


class _StubRepository:
    def get_trait(self, trait_id):
        return _StubTrait("appearance")


def _prompt_and_negative(entity_type=EntityType.LOCATION):
    entity = Entity(
        id="loc1", type=entity_type, name="Central Peak", current_universe=UNIVERSE
    )
    prompt, negative, _loras, _steps = prompt_builder._build_entity_prompt(
        entity, [], UNIVERSE
    )
    return prompt, negative


def test_default_negative_suppresses_captions_inscriptions_and_seals():
    missing = [term for term in SUPPRESSION_TERMS if term not in DEFAULT_NEGATIVE]

    assert not missing, f"default negative lost suppression vocabulary: {missing}"


def test_the_built_negative_carries_the_suppression(monkeypatch):
    monkeypatch.setattr(prompt_builder, "EntityRepository", lambda: _StubRepository())

    _prompt, negative = _prompt_and_negative()

    assert "caption" in negative
    assert "calligraphy" in negative
    assert "seal stamp" in negative


def test_the_positive_prompt_never_tries_to_negate_text(monkeypatch):
    """Naming these in the positive is how you get MORE of them.

    Measured against the real model at the artefact's seed with its LoRA: a
    positive clause reading "no text, no lettering, no calligraphy, no seal
    stamps" produced more calligraphy than the baseline did.
    """
    monkeypatch.setattr(prompt_builder, "EntityRepository", lambda: _StubRepository())

    prompt, _negative = _prompt_and_negative()

    for bad in ("no text", "no lettering", "no calligraphy", "no seal", "no watermark"):
        assert bad not in prompt.lower(), (
            f"'{bad}' is in the positive prompt — negation belongs in the negative only"
        )
