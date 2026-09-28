"""What a roll is *for*, derived from the tags its traits carry.

The author's ruling, 2026-09-28: **"roll purpose can be derived from trait tags."**
So a roll does not carry an authored intent. A pool die knows the trait instance it
came from (``ts_id``), the instance knows its registry trait, and the trait carries
whatever labels an author put on it — so the purpose is read off the dice rather
than asserted by the client, which is what keeps it a *rule* rather than a claim.

**Why derive it instead of walking a path.** The same question is expressible today
as a targeting path (``pool → dice → traitsetting → filter tags contains …``), and
that is what an author had to write before this. Two reasons it is worth naming
instead: the walk asks a *structural* question (*"does a die in this pool own a
trait carrying this label"*) where the rule means a *semantic* one (*"is this roll
an attack"*), and every rule paid for the same four hops. One derivation, one
place, and a condition that reads as what it means.

**Instance tags come too** ([[B116]]): a particular blade being a weapon is a fact
about the instance, not about the definition it was made from.
"""

from __future__ import annotations

from typing import Iterable, Optional


def _ts_id(roll) -> str:
    """The trait-setting id a pool die came from, from either shape of a roll.

    The live roll path yields enriched dicts and the legacy resolver yields
    ``DieRoll`` models; both carry ``ts_id``.
    """
    if isinstance(roll, dict):
        return str(roll.get("ts_id") or "").strip()
    return str(getattr(roll, "ts_id", None) or "").strip()


def roll_purpose(rolls: Optional[Iterable], repo) -> list[str]:
    """The tags the traits in this pool carry, deduped, in pool order.

    Not every die resolves — a manual die, a difficulty die, or an instance whose
    trait was deleted has no tags and contributes nothing. **An empty list is a
    real answer**, not an unknown: "no trait in this pool is tagged". A
    ``not contains`` gate on it passes, which is the honest reading of *"this roll
    is not an attack"*.
    """
    if repo is None:
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for roll in rolls or []:
        ts_id = _ts_id(roll)
        if not ts_id or ts_id in seen:
            continue
        seen.add(ts_id)
        instance = repo.get_traitsetting(ts_id)
        if instance is None:
            continue
        for tag in (getattr(instance, "tags", None) or []):
            tag = str(tag).strip()
            if tag and tag not in tags:
                tags.append(tag)
        trait = repo.get_trait(getattr(instance, "trait_id", "") or "")
        for tag in (getattr(trait, "tags", None) or []):
            tag = str(tag).strip()
            if tag and tag not in tags:
                tags.append(tag)
    return tags
