"""Themed name generation — offline, seedable, and authorable per universe.

Naming is **content**, so this module is a small registry of themes rather than a
dependency. Nothing name-shaped was installed or in ``requirements.lock``; a
real-world locale library (`faker` and friends) covers Chinese or Japanese names
but has nothing for *alien* or *fantasy*, which is half of what a multiverse
needs; and a public name API would put a network round-trip and a failure mode
into naming a character. So: two generator shapes, both seeded from the same
:func:`generate`, and a theme is whatever the universe says it is.

* a **syllable** theme builds a name from onsets/nuclei/codas — the shape that
  gives a world its phonology, which is what makes "alien" and "fantasy" feel
  like different places rather than two word lists;
* a **list** theme draws from curated given/family names, for the themes where
  authenticity is the point (Chinese and Japanese names are real names, not
  plausible syllables).

The generator is **deterministic for a given seed**, which is what lets a test
pin a name and what would let a birthday/motif repeat later; without a seed it
uses the module RNG, so two calls differ.

A universe sets its theme with ``Entity.naming_theme`` (the universe entity —
see [[Data Model]] §`entities`), and :func:`theme_for_universe` is the one place
that decides what a universe means when it names nothing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

#: What a universe names when it declares nothing, and what an unknown theme key
#: falls back to. Deliberately the plainest theme: a world nobody has described
#: should not invent a phonology for itself.
DEFAULT_THEME = "modern"


@dataclass(frozen=True)
class SyllableTheme:
    """A phonology: enough to sound like a *place* rather than a word list."""

    onsets: tuple[str, ...]
    nuclei: tuple[str, ...]
    codas: tuple[str, ...]
    syllables: tuple[int, ...] = (2, 2, 3)
    #: Chance a syllable takes an onset. Below 1 so a word can begin or continue
    #: on a vowel, which is most of what makes a name pronounceable.
    onset_chance: float = 0.85
    coda_chance: float = 0.45
    #: Chance a syllable break takes this instead of the plain joiner — a glottal
    #: stop or an apostrophe is most of what makes a name read as non-human.
    break_chance: float = 0.0
    joiner: str = ""
    break_mark: str = "'"
    #: Appended after the last syllable, chosen from here (e.g. fantasy `-iel`).
    suffixes: tuple[str, ...] = ()
    suffix_chance: float = 0.0


@dataclass(frozen=True)
class ListTheme:
    """Curated names, for themes where the names are real."""

    family: tuple[str, ...] = ()
    given: tuple[str, ...] = ()
    given_female: tuple[str, ...] = ()
    given_male: tuple[str, ...] = ()
    #: ``"family-given"`` (Chinese, Japanese, Korean) or ``"given-family"``.
    order: str = "given-family"
    separator: str = " "
    #: Patronymic endings, e.g. Norse ``-sson`` / ``-dottir``. When set, the
    #: family name is built from a given name plus the ending for the gender.
    patronymic: tuple[str, str, tuple[str, ...]] = ()  # (male_end, female_end, stems)


# ── Themes ────────────────────────────────────────────────
#
# Kept as data, in one place, because a new world should mean a new entry here
# and nothing else. Lists are short on purpose: a name is drawn, not enumerated,
# and a longer list would be false precision.

THEMES: dict[str, object] = {
    # ── Constructed phonologies ──
    "fantasy": SyllableTheme(
        onsets=("b", "br", "c", "d", "dr", "f", "g", "gl", "h", "k", "l", "m",
                "n", "r", "s", "sh", "t", "th", "v", "w", "y"),
        nuclei=("a", "e", "i", "o", "u", "ae", "ei", "ia", "io", "ea"),
        codas=("l", "m", "n", "r", "s", "th", "nd", "lm", "rn", "st"),
        syllables=(2, 2, 3, 3, 4),
        suffixes=("iel", "orn", "wen", "ric", "dor", "lith", "mere"),
        suffix_chance=0.3,
    ),
    "alien": SyllableTheme(
        onsets=("x", "z", "v", "kh", "vr", "tz", "q", "zh", "th", "sk", "gr",
                "n", "m", "ch", "dr", "kl"),
        nuclei=("a", "i", "u", "aa", "ii", "uu", "o", "e", "ai", "oa"),
        codas=("x", "z", "k", "th", "sh", "r", "n", "t", "ss", "q"),
        syllables=(2, 2, 3, 3),
        coda_chance=0.6,
        break_chance=0.35,
        break_mark="'",
        suffixes=("ax", "ix", "or", "un", "eth"),
        suffix_chance=0.2,
    ),
    "elvish": SyllableTheme(
        onsets=("a", "e", "el", "f", "g", "l", "m", "n", "r", "s", "th", "v",
                "y", "gl", "br", "c"),
        nuclei=("a", "e", "i", "o", "ae", "ia", "ie", "ea", "ui"),
        codas=("l", "r", "n", "s", "th", "ll", "nn", "lm"),
        syllables=(2, 3, 3, 4),
        coda_chance=0.35,
        suffixes=("iel", "wen", "las", "rion", "mir", "thil"),
        suffix_chance=0.35,
    ),
    "guttural": SyllableTheme(
        onsets=("b", "d", "g", "gr", "k", "kr", "m", "n", "r", "t", "th", "v",
                "z", "br", "dr", "kh"),
        nuclei=("a", "o", "u", "au", "oo", "aa"),
        codas=("k", "g", "rk", "rg", "m", "n", "z", "th", "sk"),
        syllables=(1, 2, 2, 3),
        coda_chance=0.7,
    ),
    # ── Real-world names ──
    "chinese": ListTheme(
        family=("Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao",
                "Wu", "Zhou", "Xu", "Sun", "Ma", "Zhu", "Hu", "Guo", "He",
                "Lin", "Gao", "Luo", "Zheng", "Liang", "Xie", "Song", "Tang"),
        given=("Wei", "Fang", "Min", "Jing", "Lei", "Yan", "Hui", "Qiang",
               "Xiu", "Jian", "Ling", "Bo", "Chen", "Dan", "Gang", "Hong",
               "Juan", "Kai", "Lan", "Ming", "Ning", "Peng", "Rui", "Shan",
               "Tao", "Wen", "Xia", "Yun", "Zhen", "Zhi"),
        given_female=("Xiu Ying", "Li Hua", "Mei Ling", "Yu Yan", "Fang",
                      "Jing", "Lan", "Yun", "Xia", "Zhen"),
        given_male=("Wei", "Jian", "Qiang", "Lei", "Ming", "Peng", "Tao",
                    "Bo", "Gang", "Kai"),
        order="family-given",
    ),
    "japanese": ListTheme(
        family=("Sato", "Suzuki", "Takahashi", "Tanaka", "Ito", "Watanabe",
                "Yamamoto", "Nakamura", "Kobayashi", "Kato", "Yoshida",
                "Yamada", "Sasaki", "Yamaguchi", "Matsumoto", "Inoue",
                "Kimura", "Hayashi", "Shimizu", "Saito"),
        given=("Akira", "Haruto", "Yuki", "Sora", "Ren", "Hina", "Sakura",
               "Yui", "Aoi", "Riku", "Kaito", "Mei", "Rin", "Sota", "Hana"),
        given_female=("Sakura", "Hina", "Yui", "Aoi", "Mei", "Rin", "Hana",
                      "Yuna", "Mio", "Akari"),
        given_male=("Haruto", "Ren", "Riku", "Kaito", "Sota", "Akira",
                    "Daiki", "Yuto", "Kenta", "Takumi"),
        order="family-given",
    ),
    "norse": ListTheme(
        given=("Astrid", "Bjorn", "Eirik", "Freya", "Gunnar", "Halvard",
               "Ingrid", "Jorunn", "Kettil", "Leif", "Ragnvald", "Sigrid",
               "Thorstein", "Ulf", "Vigdis", "Yrsa", "Hakon", "Solveig"),
        given_female=("Astrid", "Freya", "Ingrid", "Jorunn", "Sigrid",
                      "Vigdis", "Yrsa", "Solveig", "Runa", "Tove"),
        given_male=("Bjorn", "Eirik", "Gunnar", "Halvard", "Kettil", "Leif",
                    "Ragnvald", "Thorstein", "Ulf", "Hakon"),
        patronymic=("sson", "sdottir",
                    ("Bjorn", "Eirik", "Gunnar", "Halvard", "Leif", "Ragnvald",
                     "Thorstein", "Ulf", "Hakon", "Kettil")),
    ),
    "slavic": ListTheme(
        family=("Ivanov", "Petrov", "Smirnov", "Kuznetsov", "Volkov", "Sokolov",
                "Popov", "Lebedev", "Kozlov", "Novikov", "Morozov", "Orlov",
                "Kovalenko", "Bondarenko", "Shevchenko", "Tkachenko"),
        given=("Dmitri", "Anya", "Ivan", "Katya", "Nikolai", "Olga", "Pyotr",
               "Svetlana", "Viktor", "Yelena", "Alexei", "Irina", "Mikhail",
               "Natalia", "Sergei", "Tatiana"),
        given_female=("Anya", "Katya", "Olga", "Svetlana", "Yelena", "Irina",
                      "Natalia", "Tatiana", "Vera", "Zoya"),
        given_male=("Dmitri", "Ivan", "Nikolai", "Pyotr", "Viktor", "Alexei",
                    "Mikhail", "Sergei", "Boris", "Andrei"),
    ),
    "arabic": ListTheme(
        family=("Al-Hassan", "Al-Rashid", "Al-Najjar", "Al-Sayed", "Haddad",
                "Khalil", "Mansour", "Nasser", "Saleh", "Zahra", "Farouk",
                "Ibrahim", "Qasim", "Sabri"),
        given=("Amir", "Layla", "Omar", "Fatima", "Yusuf", "Noor", "Tariq",
               "Zahra", "Karim", "Amina", "Hassan", "Leila", "Samir", "Yasmin"),
        given_female=("Layla", "Fatima", "Noor", "Zahra", "Amina", "Leila",
                      "Yasmin", "Mariam", "Salma", "Rania"),
        given_male=("Amir", "Omar", "Yusuf", "Tariq", "Karim", "Hassan",
                    "Samir", "Khalid", "Rashid", "Ibrahim"),
    ),
    "modern": ListTheme(
        family=("Adams", "Bennett", "Carter", "Doyle", "Ellis", "Foster",
                "Grant", "Hayes", "Iverson", "Jensen", "Keller", "Lawson",
                "Mercer", "Nolan", "Osborne", "Parker", "Quinn", "Reeves",
                "Sinclair", "Turner", "Vance", "Whitaker"),
        given=("Alex", "Bailey", "Cameron", "Dana", "Elliot", "Frankie",
               "Gray", "Harper", "Indigo", "Jordan", "Kelly", "Logan",
               "Morgan", "Nova", "Oakley", "Peyton", "Quinn", "Riley",
               "Sasha", "Taylor"),
        given_female=("Alice", "Beth", "Clara", "Diana", "Elena", "Fiona",
                      "Grace", "Hannah", "Iris", "Julia", "Kate", "Laura",
                      "Maya", "Nora", "Olivia", "Rose"),
        given_male=("Adam", "Ben", "Carl", "David", "Edward", "Felix",
                    "George", "Henry", "Isaac", "Jack", "Karl", "Liam",
                    "Marcus", "Nathan", "Oliver", "Peter"),
    ),
}

#: Display order and labels for a picker. Keys match :data:`THEMES`.
THEME_LABELS: tuple[tuple[str, str], ...] = (
    ("modern", "Modern / Earth"),
    ("fantasy", "Fantasy"),
    ("alien", "Alien"),
    ("elvish", "Elvish"),
    ("guttural", "Guttural / Orcish"),
    ("chinese", "Chinese"),
    ("japanese", "Japanese"),
    ("norse", "Norse"),
    ("slavic", "Slavic"),
    ("arabic", "Arabic"),
)


def theme_keys() -> list[str]:
    """Every declared theme key, in picker order."""
    return [k for k, _ in THEME_LABELS if k in THEMES]


def theme_label(key: str) -> str:
    for k, label in THEME_LABELS:
        if k == key:
            return label
    return key


def _pick_given(rng: random.Random, theme: ListTheme, gender: str) -> str:
    """A given name for ``gender`` (``"male"`` / ``"female"`` / anything else).

    The gendered lists are consulted first and the general list is the fallback,
    so a theme that only carries a mixed list still answers a gendered request
    rather than refusing it.
    """
    if gender == "female" and theme.given_female:
        return rng.choice(theme.given_female)
    if gender == "male" and theme.given_male:
        return rng.choice(theme.given_male)
    if theme.given:
        return rng.choice(theme.given)
    return rng.choice(theme.given_female or theme.given_male)


def _syllable_name(rng: random.Random, theme: SyllableTheme) -> str:
    count = rng.choice(theme.syllables)
    parts: list[str] = []
    for i in range(count):
        syllable = ""
        if rng.random() < theme.onset_chance:
            syllable += rng.choice(theme.onsets)
        syllable += rng.choice(theme.nuclei)
        # A coda only ever **closes the word**. Letting every syllable carry one
        # collides it with the next onset and produces the unpronounceable clusters
        # that make a generator read as random rather than foreign — the first cut
        # of this produced "Dreiciostbriom" and "Tzith'nizzoass".
        if i == count - 1 and rng.random() < theme.coda_chance:
            syllable += rng.choice(theme.codas)
        parts.append(syllable)
    if theme.suffixes and rng.random() < theme.suffix_chance:
        parts.append(rng.choice(theme.suffixes))
    # At most **one** break, and only between syllables: two apostrophes in a name
    # is punctuation noise, not a phonology (the first cut allowed one per break).
    break_at = -1
    if theme.break_chance and len(parts) > 1 and rng.random() < theme.break_chance:
        break_at = rng.randrange(1, len(parts))
    out = theme.joiner.join(
        (theme.break_mark + part) if i == break_at else part
        for i, part in enumerate(parts)
    )
    # `capitalize` would lower the rest ("voz'Kren" → "Voz'kren"), which is right:
    # the name is one word and only its first letter is a capital.
    return out.capitalize()


def _list_name(rng: random.Random, theme: ListTheme, gender: str) -> str:
    given = _pick_given(rng, theme, gender)
    # An unset gender still has to be *internally* consistent: a female given name
    # with a male patronymic ("Vigdis Hakonsson") is worse than either alone, so
    # the ending follows the name that was actually drawn.
    effective = gender
    if effective not in ("male", "female"):
        if given in theme.given_female:
            effective = "female"
        elif given in theme.given_male:
            effective = "male"
    family = ""
    if theme.patronymic:
        male_end, female_end, stems = theme.patronymic
        end = female_end if effective == "female" else male_end
        family = rng.choice(stems) + end
    elif theme.family:
        family = rng.choice(theme.family)
    if not family:
        return given
    if theme.order == "family-given":
        return f"{family}{theme.separator}{given}"
    return f"{given}{theme.separator}{family}"


def generate(theme_key: str = DEFAULT_THEME, *, count: int = 1, gender: str = "",
             seed: Optional[int] = None) -> list[str]:
    """``count`` names in ``theme_key``.

    Unseeded calls use the module RNG, so two calls differ; a ``seed`` makes the
    result repeatable, which is what a test pins and what a caller who wants the
    same name twice would pass. An unknown theme falls back to
    :data:`DEFAULT_THEME` rather than failing — a universe is allowed to name a
    theme this build does not have yet.
    """
    theme = THEMES.get(theme_key) or THEMES[DEFAULT_THEME]
    rng = random.Random(seed) if seed is not None else random
    out: list[str] = []
    for _ in range(max(1, int(count))):
        if isinstance(theme, SyllableTheme):
            out.append(_syllable_name(rng, theme))
        else:
            out.append(_list_name(rng, theme, gender))
    return out


def theme_for_universe(repo, universe: str) -> str:
    """The theme a universe names, else :data:`DEFAULT_THEME`.

    ``universe`` is a universe **handle** (``earth``) — what an entity stores in
    ``current_universe`` — not the entity id (``universe-earth``), because that is
    what callers hold. One lookup, and a missing universe is not an error: a
    character mid-creation may name a world this repo cannot resolve yet.
    """
    if not universe or repo is None:
        return DEFAULT_THEME
    getter = getattr(repo, "get_entity", None)
    if not callable(getter):
        return DEFAULT_THEME
    entity = getter(f"universe-{universe}") or getter(universe)
    declared = (getattr(entity, "naming_theme", "") or "").strip()
    return declared if declared in THEMES else DEFAULT_THEME


# ── Public APIs (opt-in, always with a local fallback) ─────
#
# Public name APIs are supported, but they were **measured before being trusted**
# — from the API container itself, 2026-09-28:
#
#   behindthename.com  needs a free key, and is the only one that takes a
#                      ``usage=`` code (chinese, japanese, norse, arabic, slavic…)
#                      — i.e. the only public source for the themes asked for
#   randomuser.me      keyless, 0.43s, works — but its ``nat`` list is western
#                      (``nat=cn`` returns a *French* name; there is no Chinese)
#   namey.muffinlabs   keyless, 1.1s, works — western, no locale control
#   uinames.com        DEAD: TLS certificate expired
#   fakerapi.it        502 Bad Gateway
#   api.namefake.com   404
#
# Two consequences shape this seam. **Remote is opt-in** (`NAME_REMOTE=1`), because
# a game must name an NPC on a laptop with no uplink. And a **seeded** request is
# never remote: a seed means "give me that name again", which an API cannot honour.
#
# A key is read from ``BEHINDTHENAME_KEY``; with it set, the thematic themes gain a
# real source and everything else is unchanged if it is absent or the API is down.

BTN_USAGE: dict[str, str] = {
    "chinese": "chi",
    "japanese": "jap",
    "norse": "sca-anci",
    "slavic": "sla",
    "arabic": "ara",
    "modern": "eng",
}

#: Behind the Name's documented limits (`/api/help.php`): `number` is capped at 6,
#: and the key allows 2 requests/second, 400/hour, 4000/day. This seam makes one
#: call per name request, so a burst of GM clicking is inside the budget — but it
#: is the reason the seam must never be the only way to get a name.
BTN_MAX_NUMBER = 6

#: randomuser.me ``nat`` codes — the keyless path, for the themes it can serve.
RANDOMUSER_NAT: dict[str, str] = {
    "modern": "us,gb,au,ca,ie,nz",
    "slavic": "ua,rs",
}

_TIMEOUT = 4.0


def _get_json(url: str):
    import json
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "transversal/1.0"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _behind_the_name(theme_key: str, count: int, gender: str) -> Optional[list[str]]:
    """Behind the Name, when a key is configured. ``None`` on anything else."""
    import os
    import urllib.parse

    key = (os.environ.get("BEHINDTHENAME_KEY") or "").strip()
    usage = BTN_USAGE.get(theme_key)
    if not key or not usage:
        return None
    params = {"number": max(1, min(count, BTN_MAX_NUMBER)), "usage": usage, "key": key}
    if gender in ("male", "female"):
        params["gender"] = "m" if gender == "male" else "f"
    data = _get_json("https://www.behindthename.com/api/random.json?"
                     + urllib.parse.urlencode(params))
    names = data.get("names") if isinstance(data, dict) else None
    return [str(n) for n in names] if names else None


def _randomuser(theme_key: str, count: int, gender: str) -> Optional[list[str]]:
    """randomuser.me — keyless, and western-locale only."""
    import urllib.parse

    nat = RANDOMUSER_NAT.get(theme_key)
    if not nat:
        return None
    params = {"results": max(1, min(count, 20)), "nat": nat, "noinfo": ""}
    if gender in ("male", "female"):
        params["gender"] = gender
    data = _get_json("https://randomuser.me/api/?" + urllib.parse.urlencode(params))
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return None
    out = []
    for row in results:
        name = row.get("name") or {}
        first, last = name.get("first"), name.get("last")
        if first and last:
            out.append(f"{first} {last}")
        elif first:
            out.append(str(first))
    return out or None


def remote_names(theme_key: str, *, count: int = 1, gender: str = "") -> Optional[list[str]]:
    """Names from a public API, or ``None`` — **never raises**.

    Opt-in (``NAME_REMOTE=1``). Every failure — disabled, no provider for the
    theme, timeout, bad JSON, a dead certificate — returns ``None`` so the caller
    falls back to the local generator. Naming a character is not worth an error
    page, and the probed landscape above shows providers rot.
    """
    import os

    if (os.environ.get("NAME_REMOTE") or "").strip().lower() not in ("1", "true", "yes"):
        return None
    for provider in (_behind_the_name, _randomuser):
        try:
            names = provider(theme_key, count, gender)
        except Exception:
            names = None
        if names:
            return names
    return None


def generate_names(theme_key: str = DEFAULT_THEME, *, count: int = 1, gender: str = "",
                   seed: Optional[int] = None, remote: bool = True) -> list[str]:
    """The entry point callers should use: remote when asked for and possible,
    local otherwise.

    ``remote`` defaults to ``True`` and is still only a *preference* — the env
    switch and the provider map decide whether anything is attempted, and a seed
    turns it off entirely so a repeatable request stays repeatable.
    """
    if remote and seed is None:
        names = remote_names(theme_key, count=count, gender=gender)
        if names:
            return names
    return generate(theme_key, count=count, gender=gender, seed=seed)


def is_remote_enabled() -> bool:
    """Whether the remote seam is switched on — what a UI hint reads."""
    import os

    return (os.environ.get("NAME_REMOTE") or "").strip().lower() in ("1", "true", "yes")

