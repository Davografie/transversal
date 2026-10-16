"""B255 — accounts, forks and email links in the registry repository.

No Arango: the three collections are fakes. What is under test is the behaviour the
auth surface depends on — case-folded email identity, a verified-at that is written
once, epochs that move, and a link that can only be spent once.
"""

from transversal.db import registry
from transversal.db.registry_repository import (
    PURPOSE_SIGN_IN,
    PURPOSE_VERIFY,
    RegistryRepository,
    normalize_email,
)


class _Collection:
    def __init__(self):
        self.docs: dict[str, dict] = {}

    def insert(self, doc):
        self.docs[doc["_key"]] = dict(doc)

    def get(self, key):
        found = self.docs.get(key)
        return dict(found) if found else None

    def update(self, doc):
        self.docs[doc["_key"]] = dict(doc)

    def find(self, filters, limit=None):
        rows = [
            dict(doc)
            for doc in self.docs.values()
            if all(doc.get(k) == v for k, v in filters.items())
        ]
        return rows[:limit] if limit else rows

    def all(self):
        return [dict(doc) for doc in self.docs.values()]


class _FakeDB:
    def __init__(self):
        self._cols = {
            registry.ACCOUNTS: _Collection(),
            registry.CAMPAIGNS: _Collection(),
            registry.ACCOUNT_TOKENS: _Collection(),
        }
        self.touched: list[str] = []

    def collection(self, name):
        self.touched.append(name)
        return self._cols[name]


def _repo():
    return RegistryRepository(db=_FakeDB())


# ── Email identity ────────────────────────────────────────────────────


def test_email_is_trimmed_and_case_folded():
    assert normalize_email("  Dave@Example.COM ") == "dave@example.com"


def test_the_same_address_different_case_is_one_account():
    repo = _repo()
    first = repo.create_account("Dave@Example.com")
    second = repo.find_account_by_email("dave@example.com")

    assert second is not None
    assert second.id == first.id


def test_an_account_starts_unverified():
    repo = _repo()
    account = repo.get_account(repo.create_account("dave@example.com").id)

    assert account.email == "dave@example.com"
    assert account.verified_at is None
    assert account.epoch == 0
    assert account.global_editor is False


def test_verification_is_written_once():
    repo = _repo()
    account_id = repo.create_account("dave@example.com").id
    first = repo.mark_email_verified(account_id)
    second = repo.mark_email_verified(account_id)

    assert first.verified_at
    assert second.verified_at == first.verified_at


def test_verifying_an_unknown_account_is_not_a_crash():
    assert _repo().mark_email_verified("acct-ghost") is None


def test_an_epoch_bump_moves_the_counter():
    repo = _repo()
    account_id = repo.create_account("dave@example.com").id

    assert repo.bump_account_epoch(account_id) == 1
    assert repo.bump_account_epoch(account_id) == 2


# ── Forks ─────────────────────────────────────────────────────────────


def test_a_fork_records_the_database_it_routes_to():
    repo = _repo()
    fork_id = repo.create_fork("Dave's game", "tv2_fork_abc", "acct-1").id
    fork = repo.get_fork(fork_id)

    assert fork.database == "tv2_fork_abc"
    assert fork.owner_account == "acct-1"
    assert fork.kind == "fork"


def test_forks_are_listed_for_their_owner_only():
    repo = _repo()
    mine = repo.create_fork("mine", "tv2_fork_mine", "acct-1")
    repo.create_fork("theirs", "tv2_fork_theirs", "acct-2")

    assert [f.id for f in repo.list_forks_for("acct-1")] == [mine.id]


def test_a_fork_database_is_findable_for_routing():
    repo = _repo()
    repo.create_fork("mine", "tv2_fork_mine", "acct-1")

    assert repo.find_fork_by_database("tv2_fork_mine").name == "mine"
    assert repo.find_fork_by_database("nope") is None


# ── Email links ───────────────────────────────────────────────────────


def test_a_link_can_only_be_spent_once():
    repo = _repo()
    token_id = repo.create_account_token("acct-1", PURPOSE_VERIFY, "2099-01-01T00:00:00+00:00")

    assert repo.consume_account_token(token_id) is True
    assert repo.consume_account_token(token_id) is False


def test_a_consumed_link_keeps_its_purpose_for_audit():
    repo = _repo()
    token_id = repo.create_account_token("acct-1", PURPOSE_SIGN_IN, "2099-01-01T00:00:00+00:00")
    repo.consume_account_token(token_id)

    record = repo.get_account_token(token_id)
    assert record["purpose"] == PURPOSE_SIGN_IN
    assert record["consumed_at"]


def test_the_repository_binds_only_registry_collections():
    db = _FakeDB()
    RegistryRepository(db=db)

    assert set(db.touched) == set(registry.REGISTRY_COLLECTIONS)
