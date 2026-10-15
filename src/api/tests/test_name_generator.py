"""Themed name generation ([[B82]]).

The generator is offline by default and **seedable**, which is what makes it
testable at all: a seed pins a name, so a regression in the phonology shows up as
a diff rather than as a vibe. The remote seam is opt-in and is tested for the one
property that matters — it must never be able to break naming.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.services import name_generator as ng


# ── The registry ─────────────────────────────────────────

def test_the_requested_themes_exist():
    """The human named these three explicitly: alien, fantasy, Chinese."""
    keys = ng.theme_keys()
    for key in ("alien", "fantasy", "chinese"):
        assert key in keys


def test_every_theme_key_has_a_label_and_a_definition():
    for key in ng.theme_keys():
        assert ng.theme_label(key) != key or key == "modern", key
        assert key in ng.THEMES
    assert ng.theme_label("chinese") == "Chinese"


# ── Generation ───────────────────────────────────────────

def test_a_seed_makes_a_name_repeatable():
    assert ng.generate("fantasy", count=3, seed=4) == ng.generate("fantasy", count=3, seed=4)


def test_unseeded_calls_differ():
    """Three tries, because two identical draws from a small space are possible."""
    draws = {tuple(ng.generate("alien", count=3)) for _ in range(3)}
    assert len(draws) > 1


def test_count_is_honoured_and_never_zero():
    assert len(ng.generate("modern", count=7, seed=1)) == 7
    assert len(ng.generate("modern", count=0, seed=1)) == 1
    assert len(ng.generate("modern", count=-3, seed=1)) == 1


def test_an_unknown_theme_falls_back_rather_than_failing():
    """A universe may name a theme a newer build carries; naming must not break."""
    assert ng.generate("klingon", count=2, seed=1) == ng.generate(ng.DEFAULT_THEME, count=2, seed=1)
    assert ng.generate("", count=2, seed=1) == ng.generate(ng.DEFAULT_THEME, count=2, seed=1)


def test_every_theme_produces_something_name_shaped():
    for key in ng.theme_keys():
        for name in ng.generate(key, count=6, seed=13):
            assert name and name.strip() == name, (key, name)
            assert name[0].isupper(), (key, name)
            assert "  " not in name, (key, name)


def test_gender_is_honoured_where_the_theme_carries_it():
    female = ng.generate("japanese", count=1, gender="female", seed=2)
    male = ng.generate("japanese", count=1, gender="male", seed=2)
    f_given = female[0].split(" ", 1)[1]
    m_given = male[0].split(" ", 1)[1]
    assert f_given in ng.THEMES["japanese"].given_female
    assert m_given in ng.THEMES["japanese"].given_male


def test_a_constructed_theme_ignores_gender_without_error():
    assert len(ng.generate("alien", count=2, gender="female", seed=5)) == 2


def test_a_patronymic_agrees_with_the_given_name():
    """`Vigdis Hakonsson` — a female given name with a male patronymic — is the bug
    this pins: with no gender asked for, the ending follows the name actually drawn."""
    for gender, expected in (("female", "sdottir"), ("male", "sson")):
        for name in ng.generate("norse", count=12, gender=gender, seed=8):
            assert name.endswith(expected), (gender, name)
    for name in ng.generate("norse", count=24, seed=8):
        given = name.split(" ", 1)[0]
        if given in ng.THEMES["norse"].given_female:
            assert name.endswith("sdottir"), name
        elif given in ng.THEMES["norse"].given_male:
            assert name.endswith("sson"), name


def test_a_name_is_pronounceable_enough_to_say_aloud():
    """The first cut of the syllable generator gave every syllable an onset *and* a
    coda, and produced "Dreiciostbriom" and "Tzith'nizzoass" — mush. Two guards: at
    most one break mark, and no long consonant pile-up."""
    import re

    for key in ("fantasy", "alien", "elvish", "guttural"):
        for name in ng.generate(key, count=40, seed=17):
            assert name.count("'") <= 1, (key, name)
            runs = [len(m) for m in re.findall(r"[bcdfghjklmnpqrstvwxz]+", name.lower())]
            assert max(runs, default=0) <= 3, (key, name)


# ── The universe's theme ─────────────────────────────────

def _repo(theme, entity_id="universe-earth"):
    return NS(get_entity=lambda eid: NS(id=entity_id, naming_theme=theme) if eid == entity_id else None)


def test_a_universe_supplies_the_default_theme():
    assert ng.theme_for_universe(_repo("chinese"), "earth") == "chinese"


def test_a_universe_handle_and_its_entity_id_both_resolve():
    repo = NS(get_entity=lambda eid: NS(naming_theme="alien") if eid in ("earth", "universe-earth") else None)
    assert ng.theme_for_universe(repo, "earth") == "alien"


def test_an_unknown_declared_theme_falls_back_to_the_default():
    assert ng.theme_for_universe(_repo("klingon"), "earth") == ng.DEFAULT_THEME


def test_no_universe_no_repo_and_no_theme_are_all_the_default():
    assert ng.theme_for_universe(_repo(""), "earth") == ng.DEFAULT_THEME
    assert ng.theme_for_universe(_repo("chinese"), "") == ng.DEFAULT_THEME
    assert ng.theme_for_universe(None, "earth") == ng.DEFAULT_THEME
    assert ng.theme_for_universe(NS(), "earth") == ng.DEFAULT_THEME
    assert ng.theme_for_universe(_repo("chinese"), "nowhere") == ng.DEFAULT_THEME


# ── The remote seam ──────────────────────────────────────

def test_remote_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("NAME_REMOTE", raising=False)
    assert ng.is_remote_enabled() is False
    assert ng.remote_names("modern", count=2) is None


def test_a_seeded_request_never_goes_remote(monkeypatch):
    """A seed means "give me that name again", which an API cannot honour."""
    monkeypatch.setattr(ng, "remote_names", lambda *a, **k: pytest.fail("remote was used"))
    assert ng.generate_names("modern", count=2, seed=3) == ng.generate("modern", count=2, seed=3)


def test_a_remote_failure_falls_back_to_the_local_generator(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("network down")

    monkeypatch.setattr(ng, "_behind_the_name", boom)
    monkeypatch.setattr(ng, "_randomuser", boom)
    monkeypatch.setenv("NAME_REMOTE", "1")
    assert ng.remote_names("modern", count=2) is None
    assert ng.generate_names("modern", count=2, seed=1) == ng.generate("modern", count=2, seed=1)


def test_no_provider_for_a_theme_means_no_remote_attempt(monkeypatch):
    """Alien and fantasy have no public source — no call is even attempted."""
    monkeypatch.setenv("NAME_REMOTE", "1")
    assert ng.remote_names("alien", count=2) is None
    assert ng.remote_names("fantasy", count=2) is None


def test_behind_the_name_needs_a_key(monkeypatch):
    """Measured live: without one it answers `invalid key`, so it must not be called."""
    monkeypatch.delenv("BEHINDTHENAME_KEY", raising=False)
    assert ng._behind_the_name("chinese", 2, "") is None


def test_randomuser_is_only_offered_the_locales_it_has():
    assert "modern" in ng.RANDOMUSER_NAT
    assert "chinese" not in ng.RANDOMUSER_NAT


def test_the_usage_codes_are_behind_the_names_documented_codes():
    """`usage` takes a code from `/api/appendix2.php`, **not** a display name.

    Passing "chinese" or "English" answers
    `{"error_code":60,"error":"name could not be generated"}` — which is what
    shipped first, and which the local fallback hid so completely that the result
    still looked like a working call. Probed live against the real key.
    """
    assert ng.BTN_USAGE["chinese"] == "chi"
    assert ng.BTN_USAGE["japanese"] == "jap"
    assert ng.BTN_USAGE["norse"] == "sca-anci"   # Old Norse, not "norse"
    assert ng.BTN_USAGE["slavic"] == "sla"
    for theme, code in ng.BTN_USAGE.items():
        assert code == code.lower() and code.isascii(), (theme, code)
        assert " " not in code, (theme, code)


def test_the_number_cap_matches_the_api_limit():
    """Behind the Name caps `number` at 6, and asking for more is not an error the
    caller can see — the fallback answers instead."""
    assert ng.BTN_MAX_NUMBER == 6


def test_every_declared_theme_is_offered_even_without_a_label(monkeypatch):
    """The frontend's dropdown is built from this read, so a theme that is declared
    but not offered is **invisible** — and that is what the old label-derived order
    did: it listed keys from `THEME_LABELS`, so declaring a theme without labelling
    it silently withheld it from every picker."""
    assert set(ng.THEMES) <= set(ng.theme_keys())
    monkeypatch.setitem(ng.THEMES, "playtest-theme", ng.THEMES["modern"])
    assert "playtest-theme" in ng.theme_keys()
    # Unlabelled, so it shows its own key rather than vanishing.
    assert ng.theme_label("playtest-theme") == "Playtest Theme"
