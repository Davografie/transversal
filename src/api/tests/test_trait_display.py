"""`dice_with_trait_display` — the trait behind a rolled pool die ([[B289]]).

The difficulty splash draws each die's trait as the map's own chip, which wants the
trait's navdot picture and the instance's statement. Neither is on the wire, and the
client cannot get them (nothing is keyed by a *setting* id), so the server attaches
them. This pins the four outcomes that matter, with a repository double — no DB, and
no dependence on which trait happens to carry a picture today.
"""

from types import SimpleNamespace

import transversal.services.trait_display as trait_display
from transversal.services.trait_display import dice_with_trait_display


class _Setting:
    def __init__(self, id, trait_id, statement=""):
        self.id = id
        self.trait_id = trait_id
        self.statement = statement
        self.picked_image_id = ""


class _Repo:
    """Just the three reads the helper makes."""

    db = object()

    def __init__(self, settings, images):
        self._settings = settings
        self._images = images

    def get_traitsetting(self, ts_id):
        return self._settings.get(ts_id)

    def get_images_for_owners(self, ids):
        return {i: self._images.get(i, []) for i in ids}

    def role_image_url(self, image, role):
        return f"/media/imagen/{{x}}/{role}-{image.name}.webp"


def _repo():
    return _Repo(
        settings={
            "ts-sword": _Setting("ts-sword", "trait-sword", "the blade remembers"),
            "ts-bare": _Setting("ts-bare", "trait-bare", "no picture on this one"),
        },
        images={"trait-sword": [SimpleNamespace(name="sword", transparent=True)]},
    )


def test_a_die_gains_its_trait_statement_and_picture(monkeypatch):
    monkeypatch.setattr(trait_display, "pick_role_image", lambda images, role, variant_id=None, picked_id="": (images[0] if images else None))
    dice = [{"die": "d8", "label": "Sword", "ts_id": "ts-sword", "result": 6}]
    [die] = dice_with_trait_display(dice, repo=_repo())
    assert die["statement"] == "the blade remembers"
    assert die["navdot_image"].endswith("navdot-sword.webp")
    assert die["navdot_transparent"] is True
    assert die["result"] == 6, "nothing else about the die changes"


def test_a_trait_with_no_picture_still_gets_its_statement(monkeypatch):
    monkeypatch.setattr(trait_display, "pick_role_image", lambda images, role, variant_id=None, picked_id="": (images[0] if images else None))
    [die] = dice_with_trait_display([{"die": "d6", "label": "Bare", "ts_id": "ts-bare", "result": 3}], repo=_repo())
    assert die["statement"] == "no picture on this one"
    assert "navdot_image" not in die, "an entry with no picture keeps exactly the keys it had"


def test_a_die_with_no_setting_or_an_unknown_one_is_untouched(monkeypatch):
    monkeypatch.setattr(trait_display, "pick_role_image", lambda *a, **k: None)
    dice = [
        {"die": "d6", "label": "manual", "result": 2},
        {"die": "d8", "label": "gone", "ts_id": "ts-removed", "result": 5},
    ]
    out = dice_with_trait_display(dice, repo=_repo())
    assert out == dice
    for die in out:
        assert "statement" not in die and "navdot_image" not in die


def test_the_stored_pool_is_not_mutated(monkeypatch):
    monkeypatch.setattr(trait_display, "pick_role_image", lambda images, role, variant_id=None, picked_id="": (images[0] if images else None))
    stored = {"die": "d8", "label": "Sword", "ts_id": "ts-sword", "result": 6}
    dice_with_trait_display([stored], repo=_repo())
    assert stored == {"die": "d8", "label": "Sword", "ts_id": "ts-sword", "result": 6}, \
        "the pool the server keeps is not the wire's copy"


def test_no_repo_and_no_db_are_both_quiet(monkeypatch):
    monkeypatch.setattr(trait_display, "_repo_or_none", lambda: None)
    dice = [{"die": "d8", "ts_id": "ts-sword", "result": 6}]
    assert dice_with_trait_display(dice) == dice

    class _NoDb:
        db = None
    assert dice_with_trait_display(dice, repo=_NoDb()) == dice
