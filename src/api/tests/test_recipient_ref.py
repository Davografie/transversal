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
        assert "entity" in ref.elements, meta.action_id
        assert ref.role == "entity", "the stored strings must keep resolving"
        field = next(f for f in meta.fields if f.name == "entity")
        assert field.hidden_when_ref == "recipient", (
            "once the ref is authored the fallback field must stop rendering"
        )


def test_every_action_with_a_recipient_field_declares_the_ref():
    """The invariant that keeps the fallback field and the reference in step.

    The ref is derived from the field's `hidden_when_ref` marker, so this can only
    fail by someone marking a field without the registry pass running — or by a
    new action adding an `entity` field that never opts in.

    **`elements` is a floor, not an equality.** It used to assert exactly
    ``("entity",)``, which was true while every recipient was a character or a
    thing like one. `Grant SFX` accepts the other owner surfaces too — a place, a
    body, a trait definition, a trait or trait-set instance ([[B326]]) — and the
    invariant that matters is the one this test is named for: the fallback field
    is still something the reference can name. Asserting equality would have
    forced either a second reference for the same question or a recipient that
    lies about what it takes.
    """
    from transversal.services.effects_registry.registry import EFFECT_ACTION_REGISTRY

    seen = 0
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.retired:
            continue
        has_field = any(f.name == "entity" for f in meta.fields)
        has_ref = any(r.name == "recipient" for r in meta.refs)
        assert has_field == has_ref, f"{meta.action_id}: field={has_field} ref={has_ref}"
        if not has_ref:
            continue
        seen += 1
        ref = next(r for r in meta.refs if r.name == "recipient")
        assert "entity" in ref.elements, meta.action_id
        assert ref.role == "entity"
        field = next(f for f in meta.fields if f.name == "entity")
        assert ref.label == field.label, (
            f"{meta.action_id}: the ref must read in the field's own words"
        )
        assert field.hidden_when_ref == "recipient", meta.action_id
    assert seen >= 17, "the whole recipient field set should have opted in"


def test_the_trait_ref_is_still_declared_first():
    """The declared order is the panel's order — and the engine's, now."""
    for action in RECIPIENT_ACTIONS:
        names = [d.name for d in get_action_meta_for("modify_trait", action).refs]
        assert names == ["trait", "recipient"]


def test_a_stored_entity_string_folds_into_the_recipient_ref():
    effect = Effect(type="modify_trait", action="move", entity="gmc-7")
    assert effective_refs(effect)["recipient"].value == "gmc-7"


def test_declaring_a_ref_for_a_field_does_not_author_it():
    """The routing gate reads *authored* refs, the resolver reads *effective* ones.

    That distinction is what keeps this migration inert: declaring a ref for a
    positional field must not move stored content off its subject/target path and
    onto the references branch. `effective_refs` sees the fold; `effect.refs` —
    which the engine, the roll path and the resume path all gate on — does not.
    """
    effect = Effect(type="modify_trait", action="move", entity="gmc-7")
    assert effective_refs(effect)["recipient"].value == "gmc-7"
    assert effect.refs == {}, "the gate must not see a ref nobody authored"


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


# --- pointing an effect at a reference, from the builder's side ----------------

def test_with_ref_sets_the_reference_the_action_declares_for_the_role():
    from transversal.services.effect_refs import with_ref

    effect = with_ref(Effect(type="modify_trait", action="move"), "entity", "gmc-7")
    assert effect.refs["recipient"].value == "gmc-7"
    assert effect.entity == "", "the builder never touches the positional field"


def test_with_ref_can_set_a_path_instead_of_a_value():
    from transversal.services.effect_refs import with_ref
    from transversal.services.target_spec import SelectStep, TargetSpec

    spec = TargetSpec(steps=[SelectStep(collection="self")])
    effect = with_ref(Effect(type="modify_trait", action="move"), "entity", spec=spec)
    assert effect.refs["recipient"].spec is spec


def test_with_ref_refuses_a_role_the_action_does_not_declare():
    """A caller asking for the wrong reference would build an effect naming nobody."""
    import pytest
    from transversal.services.effect_refs import with_ref

    with pytest.raises(ValueError, match="declares no 'owner' reference"):
        with_ref(Effect(type="modify_pool", action="add_trait_rating"), "owner", "x")


def test_with_ref_is_declaration_driven_not_name_driven():
    """`set_die` calls its target `die`, `set` calls it `trait` — same call."""
    from transversal.services.effect_refs import with_ref

    a = with_ref(Effect(type="modify_roll", action="set_die"), "target", "die:pool:kael:0")
    b = with_ref(Effect(type="modify_trait", action="set"), "target", "ts-x")
    assert a.refs["die"].value == "die:pool:kael:0"
    assert b.refs["trait"].value == "ts-x"
