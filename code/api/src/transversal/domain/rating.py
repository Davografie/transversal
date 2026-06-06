"""Rating string parser — converts human-readable ratings to dice arrays.

Supported formats:
    "d10"          → [D10]
    "2d8"          → [D8, D8]
    "4d4+7d6"      → [D4, D4, D4, D4, D6, D6, D6, D6, D6, D6, D6]
    "2d4 + d6"     → [D4, D4, D6]
    "8d4+5d6"      → eight d4s + five d6s

Parsing is whitespace-tolerant.
"""

import re

from transversal.domain import DieType

_RATING_RE = re.compile(r"(?:(\d+)\s*)?([dD]\d+)")
"""Matches groups like '4d6', 'd8', '3d4'."""


def parse_rating(rating: str) -> list[DieType]:
    """Parse a human-readable rating string into a flat dice array.

    Args:
        rating: e.g. "4d4+7d6", "d10", "2d8"

    Returns:
        Flat list of DieType values, e.g. [D4, D4, D4, D4].

    Raises:
        ValueError: if the rating string cannot be parsed.
    """
    dice: list[DieType] = []

    for match in _RATING_RE.finditer(rating):
        count_str = match.group(1)
        die_str = match.group(2).lower()
        count = int(count_str) if count_str else 1
        die = DieType(die_str)
        dice.extend([die] * count)

    if not dice:
        raise ValueError(f"Could not parse rating: {rating!r}")

    return dice
