"""The recipient as a declared reference ([[B261]], step 3).

`modify_trait/copy` and `move` no longer name their recipient only through the
positional `entity` field: they declare a `recipient` ref whose `legacy_field` is
`entity`, so the stored strings keep resolving while the two vocabularies are
fused. These tests pin the declaration, the shim's fold, and the handler read —
the three places that have to agree for the migration to be invisible.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

from transversal.domain import Effect, TargetRef
from transversal.services.effect_refs import effective_refs
from transversal.services.effects_applier.datatypes import EffectsResult
from transversal.services.effects_applier.targeting import _effect_subject
from transversal.services.effects_registry.lookup import get_action_meta_for

RECIPIENT_ACTIONS = ("copy", "move")


def test_copy_and_move_declare_the_recipient_ref_over_the_entity_field():
    for action in RECIPIENT_ACTIONS:
        meta = get_action_meta_for("modify_trait", action)
        ref = next(d for d in meta.refs if d.name == "recipient")
        assert ref.element == "entity"
        assert ref.legacy_field == "entity", "the stored strings must keep resolving"
        field = next(f for f in meta.fields if f.name == "entity")
        assert field.hidden_when_ref == "recipient", (
            "once the ref is authored the fallback field must stop rendering"
        )


def test_the_trait_ref_is_still_declared_first():
    """The declared order is the panel's order — and the engine's, now."""
    for action in RECIPIENT_ACTIONS:
        names = [d.name for d in get_action_meta_for("modify_trait", action).refs]
        assert names == ["trait", "recipient"]


def test_a_stored_entity_string_folds_into_the_recipient_ref():
    effect = Effect(type="modify_trait", action="move", entity="gmc-7")
    assert effective_refs(effect)["recipient"].value == "gmc-7"


def test_an_authored_ref_wins_over_the_stored_string():
    effect = Effect(type="modify_trait", action="move", entity="gmc-old",
                    refs={"recipient": TargetRef(value="gmc-new")})
    assert effective_refs(effect)["recipient"].value == "gmc-new"


class _Repo:
    def __init__(self):
        self.entities = {"kael": NS(id="kael"), "gmc-7": NS(id="gmc-7"),
                         "gmc-old": NS(id="gmc-old"), "gmc-new": NS(id="gmc-new")}

    def get_entity(self, eid):
        return self.entities.get(eid)


def _subject(effect, acting="kael", repo=None):
    repo = repo or _Repo()
    return _effect_subject(repo.entities[acting], effect, EffectsResult(), repo)


def test_the_handler_reads_the_recipient_ref():
    effect = Effect(type="modify_trait", action="move",
                    refs={"recipient": TargetRef(value="gmc-7")})
    assert _subject(effect).id == "gmc-7"


def test_the_handler_prefers_the_ref_over_a_stale_entity_string():
    """The ref is what the resolver wrote; the field is only the fallback."""
    effect = Effect(type="modify_trait", action="move", entity="gmc-old",
                    refs={"recipient": TargetRef(value="gmc-new")})
    assert _subject(effect).id == "gmc-new"


def test_a_blank_recipient_is_still_the_acting_entity():
    for effect in (Effect(type="modify_trait", action="move"),
                   Effect(type="modify_trait", action="move", entity="self"),
                   Effect(type="modify_trait", action="move",
                          refs={"recipient": TargetRef(value="")})):
        assert _subject(effect).id == "kael", "no recipient named means the actor"


def test_a_self_dot_field_recipient_still_reads_its_own_id_field():
    class _Repo2(_Repo):
        def __init__(self):
            super().__init__()
            self.entities["kael"] = NS(id="kael", current_location="loc-9")
            self.entities["loc-9"] = NS(id="loc-9")

    effect = Effect(type="modify_trait", action="move",
                    refs={"recipient": TargetRef(value="self.location")})
    assert _subject(effect, repo=_Repo2()).id == "loc-9"
