"""A bucket-sourced rule lives in its bucket, because it may live nowhere else.

The author, 2026-10-09: *"I want SFX's that I author as `source = GM` or
`source = table` to automatically add them to the correct bucket."* — and that is
what the declaration already implies: `owner_surfaces_for` says a `gm` rule may be
attached to `gm` and to nothing else, so a rule that is in no bucket is a
contradiction with its own declaration, not an author's oversight to catch.

The other half is the move: changing the source changes the only surface the rule
may live on, so a stale membership must go rather than linger invisibly. A rule
with **no** source kind keeps its freedom — a bucket is one of its options, not its
only home — and nothing here touches it.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

from transversal.domain import SFX
from transversal.services.sfx_owner import sync_bucket_membership


class _Repo:
    """Buckets in a dict, enough for the attach/detach helpers."""

    def __init__(self, **buckets):
        self.owners = {name: NS(id=name, sfx_ids=list(ids)) for name, ids in buckets.items()}
        self.sfxs: dict[str, SFX] = {}
        self.owner_writes = 0

    def get_sfx_owner(self, owner_id):
        return self.owners.get(owner_id)

    def update_sfx_owner(self, owner):
        self.owner_writes += 1
        self.owners[owner.id] = owner

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)


def _rule(sfx_id="sfx-roll-table", source_kind="gm") -> SFX:
    return SFX(id=sfx_id, name="Roll Table", trigger="manual", source_kind=source_kind, effects=[])


def _bucket(repo, name) -> list[str]:
    return list(repo.owners[name].sfx_ids)


def test_a_bucket_sourced_rule_lands_in_its_bucket():
    repo = _Repo(table=["sfx-a"], gm=[])
    rule = _rule(source_kind="gm")
    repo.sfxs[rule.id] = rule

    assert sync_bucket_membership(repo, rule) == [("gm", "added")]
    assert _bucket(repo, "gm") == ["sfx-roll-table"]
    assert _bucket(repo, "table") == ["sfx-a"], "the other bucket is not a home"


def test_a_table_sourced_rule_lands_in_the_table_bucket():
    repo = _Repo(table=[], gm=[])
    rule = _rule(source_kind="table")
    repo.sfxs[rule.id] = rule

    assert sync_bucket_membership(repo, rule) == [("table", "added")]
    assert _bucket(repo, "table") == ["sfx-roll-table"]


def test_changing_the_source_moves_the_rule_out_of_the_old_bucket():
    """`gm` → `table` is not an addition: the rule may no longer be in `gm`."""
    repo = _Repo(table=[], gm=["sfx-roll-table"])
    rule = _rule(source_kind="table")
    repo.sfxs[rule.id] = rule

    assert sync_bucket_membership(repo, rule) == [("table", "added"), ("gm", "removed")]
    assert _bucket(repo, "table") == ["sfx-roll-table"]
    assert _bucket(repo, "gm") == []


def test_a_rule_restricted_to_another_surface_is_dropped_from_the_buckets():
    """An entity rule in the table bucket contradicts its own declaration."""
    repo = _Repo(table=["sfx-roll-table"], gm=[])
    rule = _rule(source_kind="entity")
    repo.sfxs[rule.id] = rule

    assert sync_bucket_membership(repo, rule) == [("table", "removed")]
    assert _bucket(repo, "table") == []


def test_a_rule_with_no_source_kind_is_left_alone():
    """No declaration = unrestricted: a bucket is one of its options, so a
    membership there is the author's choice rather than a contradiction."""
    repo = _Repo(table=["sfx-unrestricted"], gm=[])
    rule = _rule(sfx_id="sfx-unrestricted", source_kind="")
    repo.sfxs[rule.id] = rule

    assert sync_bucket_membership(repo, rule) == []
    assert _bucket(repo, "table") == ["sfx-unrestricted"]
    assert repo.owner_writes == 0, "nothing to write, so nothing written"


def test_an_unknown_source_kind_reads_as_unrestricted_and_is_left_alone():
    repo = _Repo(table=[], gm=[])
    rule = _rule(source_kind="not_a_kind")
    repo.sfxs[rule.id] = rule

    assert sync_bucket_membership(repo, rule) == []
    assert _bucket(repo, "table") == [] and _bucket(repo, "gm") == []


def test_syncing_twice_changes_nothing_the_second_time():
    """Idempotent: this runs on every rule write, including the ones that touch
    nothing about the source."""
    repo = _Repo(table=["sfx-a"], gm=[])
    rule = _rule(source_kind="gm")
    repo.sfxs[rule.id] = rule

    assert sync_bucket_membership(repo, rule) == [("gm", "added")]
    assert sync_bucket_membership(repo, rule) == []
    assert _bucket(repo, "gm") == ["sfx-roll-table"]
    assert _bucket(repo, "table") == ["sfx-a"]
