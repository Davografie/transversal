"""The content migration's selection logic ([[B261]]).

The migration itself is a script; what can be tested is *what it will touch*,
which is the part that matters — it holds back the class of effect whose
behaviour changes when it is folded, and it must not fold an effect twice.
"""

from __future__ import annotations

from transversal.domain import Effect, TargetRef
from transversal.migrate_effect_refs import fold_effects, holds_back
from transversal.domain.effects import TargetSpec

SET_TRAIT = {"type": "modify_trait", "action": "set"}
GAIN = {"type": "modify_trait", "action": "gain"}


def _spec(value: str) -> TargetSpec:
    return TargetSpec.model_validate({"steps": [{"kind": "literal", "value": value}]})


def test_the_two_classes_whose_behaviour_changes_are_held_back():
    """A subject path, and a die filter that has no reference yet.

    `roll_deferral._apply_armed` checks refs *before* the die filter, so an effect
    with no refs runs once per matching die and one carrying a ref never reaches
    that loop — folding it would turn "for each unchosen die" into "once". One
    live effect is in this state (`sfx-crimson-scars.effects[1]`), and it is why
    its card text changed wording: `sfx_text` derives `per_die` from the same two
    fields.
    """
    assert holds_back(Effect(**SET_TRAIT, target="ts-x")) is False
    assert holds_back(Effect(**SET_TRAIT, entity_spec=_spec("gmc-7"))) is True
    assert holds_back(Effect(**SET_TRAIT, target="ts-x", entity_spec=_spec("gmc-7"))) is True
    # Per-die today…
    assert holds_back(Effect(**SET_TRAIT, target="ts-x", die_filter={"role": None})) is True
    # …but an effect that already carries a ref was never in that loop.
    assert holds_back(Effect(**SET_TRAIT, target="ts-x", die_filter={"role": None},
                             refs={"trait": TargetRef(value="ts-x")})) is False


def test_a_target_path_is_folded():
    folded, held, unusable = fold_effects([Effect(**SET_TRAIT, target="ts-x")])
    assert held == 0 and unusable == 0
    assert folded[0].refs["trait"].value == "ts-x"
    assert folded[0].target == ""


def test_a_subject_path_is_left_alone_unless_asked_for():
    effect = Effect(**GAIN, target="trait-beast", entity_spec=_spec("gmc-7"))

    folded, held, _ = fold_effects([effect])
    assert held == 1
    assert folded[0] is effect, "held back means untouched"

    folded, held, _ = fold_effects([effect], include_subject_paths=True)
    assert held == 0
    assert folded[0].refs["recipient"].spec is not None
    assert folded[0].entity_spec is None


def test_an_effect_with_nothing_to_fold_keeps_its_identity():
    effect = Effect(**SET_TRAIT)
    folded, held, unusable = fold_effects([effect])
    assert folded[0] is effect
    assert (held, unusable) == (0, 0)


def test_folding_twice_changes_nothing_the_second_time():
    """The migration is idempotent, so a re-run is a no-op."""
    once, _, _ = fold_effects([Effect(**SET_TRAIT, target="ts-x")])
    twice, _, _ = fold_effects(once)
    assert twice[0] is once[0]


def test_a_list_is_never_reordered_or_dropped():
    effects = [Effect(**SET_TRAIT, target="ts-x"), Effect(**SET_TRAIT),
               Effect(**GAIN, entity_spec=_spec("gmc-7"))]
    folded, held, _ = fold_effects(effects)
    assert len(folded) == len(effects)
    assert held == 1
    assert folded[1] is effects[1]


# --- the backup comes first, and a backup that fails stops the run ------------

class _FakeRepo:
    """One SFX that would change, and a call log, so ordering is observable."""

    def __init__(self):
        from transversal.domain import SFX
        self.written = []
        self._sfx = SFX(id="sfx-x", name="X", trigger="manual",
                        effects=[Effect(**SET_TRAIT, target="ts-x")])

    def get_all_sfxs(self):
        return [self._sfx]

    def list_roll_tables(self):
        return []

    def update_sfx(self, sfx):
        self.written.append(sfx)
        return sfx

    def update_roll_table(self, table):
        self.written.append(table)
        return table


def test_an_unwritable_backup_aborts_without_changing_anything(monkeypatch, tmp_path):
    """The whole point of writing the backup first: no change without a record."""
    import transversal.main as main_mod
    from transversal import migrate_effect_refs as mig

    repo = _FakeRepo()
    monkeypatch.setattr(main_mod, "_get_repo", lambda: repo, raising=False)
    unwritable = tmp_path / "not-a-dir"
    unwritable.write_text("a file, so it cannot be a directory")

    code = mig.main(["--apply", "--backup-dir", str(unwritable)])
    assert code == 1, "the run must report failure"
    assert repo.written == [], "and must not have written a single document"


def test_applying_writes_a_backup_before_the_change(monkeypatch, tmp_path):
    import transversal.main as main_mod
    from transversal import migrate_effect_refs as mig
    import json, os

    repo = _FakeRepo()
    monkeypatch.setattr(main_mod, "_get_repo", lambda: repo, raising=False)

    assert mig.main(["--apply", "--backup-dir", str(tmp_path)]) == 0
    assert len(repo.written) == 1

    backups = [f for f in os.listdir(tmp_path) if f.startswith("effect-refs-backup-")]
    assert len(backups) == 1, "exactly one backup"
    with open(tmp_path / backups[0]) as fh:
        payload = json.load(fh)
    doc = payload["documents"][0]
    assert doc["kind"] == "sfx" and doc["id"] == "sfx-x"
    before = doc["before"]["effects"][0]
    assert before["target"] == "ts-x" and before["refs"] == {}, "the OLD row is recorded"
