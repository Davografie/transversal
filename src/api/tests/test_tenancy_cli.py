"""B255/B88 — the operator CLI.

The commands are thin, so what is worth asserting is the *refusals*: an unknown or
unverified owner, a taken address, and a drop without ``--yes``. Those are the paths
that would otherwise do something irreversible or surprising.

No Arango: the registry is the real repository over fake collections, and the
provisioner is stubbed where the real one would clone.
"""

import pytest

from transversal.db import registry
from transversal.db.registry_repository import RegistryRepository
from transversal.tenancy_cli import main


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

    def delete(self, key):
        self.docs.pop(key, None)


class _FakeDB:
    def __init__(self):
        self._cols = {
            registry.ACCOUNTS: _Collection(),
            registry.CAMPAIGNS: _Collection(),
            registry.ACCOUNT_TOKENS: _Collection(),
        }

    def collection(self, name):
        return self._cols[name]


@pytest.fixture
def repo(monkeypatch):
    fake = RegistryRepository(db=_FakeDB())
    monkeypatch.setattr("transversal.tenancy_cli._registry", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _no_global_env(monkeypatch):
    monkeypatch.delenv("GLOBAL_DATABASE", raising=False)
    monkeypatch.delenv("FORKS_BASE_DOMAIN", raising=False)
    # The default database is the global's default name; pin it so the assertion
    # does not depend on the machine's env.
    monkeypatch.setenv("ARANGO_DATABASE", "transversal")


def _verified(repo, email="dave@example.com"):
    account = repo.create_account(email)
    return repo.mark_email_verified(account.id)


# ── bootstrap-account ─────────────────────────────────────────────────


def test_bootstrap_creates_a_verified_account(repo, capsys):
    assert main(["bootstrap-account", "Dave@Example.com"]) == 0

    out = capsys.readouterr().out
    account = repo.find_account_by_email("dave@example.com")
    assert account is not None
    assert account.verified_at
    assert account.id in out


def test_bootstrap_is_idempotent(repo):
    assert main(["bootstrap-account", "dave@example.com"]) == 0
    first = repo.find_account_by_email("dave@example.com").id

    assert main(["bootstrap-account", "dave@example.com"]) == 0

    assert repo.find_account_by_email("dave@example.com").id == first
    assert len(repo.db.collection(registry.ACCOUNTS).all()) == 1


def test_bootstrap_verifies_an_existing_unverified_account(repo):
    account = repo.create_account("dave@example.com")
    assert account.verified_at is None

    assert main(["bootstrap-account", "dave@example.com"]) == 0

    assert repo.get_account(account.id).verified_at


def test_bootstrap_refuses_a_bad_address(repo, capsys):
    assert main(["bootstrap-account", "not-an-address"]) == 1
    assert "valid email" in capsys.readouterr().err


# ── create-fork ───────────────────────────────────────────────────────


def test_create_refuses_an_unknown_owner(repo, capsys):
    assert main(["create-fork", "Probe", "--owner", "nobody@example.com"]) == 1
    assert "no account" in capsys.readouterr().err


def test_create_refuses_an_unverified_owner(repo, capsys):
    repo.create_account("dave@example.com")

    assert main(["create-fork", "Probe", "--owner", "dave@example.com"]) == 1
    assert "not verified" in capsys.readouterr().err


def test_create_refuses_a_taken_address(repo, capsys):
    owner = _verified(repo)
    repo.create_fork("Taken", "tv2_fork_taken", owner.id, slug="probe")

    assert main(["create-fork", "Probe", "--owner", "dave@example.com"]) == 1
    assert "already taken" in capsys.readouterr().err


def test_create_provisions_and_prints_the_fork(repo, monkeypatch, capsys):
    owner = _verified(repo)
    seen = {}

    def _stub(registry_repo, **kwargs):
        seen.update(kwargs)
        return registry_repo.create_fork(
            kwargs["name"],
            "tv2_fork_probe",
            kwargs["owner_account"],
            slug=kwargs["slug"],
        )

    monkeypatch.setattr("transversal.tenancy_cli.provision_fork", _stub)

    assert main(["create-fork", "Probe Game", "--owner", "dave@example.com"]) == 0

    assert seen["source_database"] == "transversal"
    assert seen["name"] == "Probe Game"
    assert seen["owner_account"] == owner.id
    assert seen["slug"] == "probe-game"
    assert seen["include_play"] is False
    assert "tv2_fork_probe" in capsys.readouterr().out


def test_create_takes_the_source_from_the_environment(repo, monkeypatch):
    _verified(repo)
    seen = {}
    monkeypatch.setenv("GLOBAL_DATABASE", "tv2_global")

    def _stub(registry_repo, **kwargs):
        seen.update(kwargs)
        return registry_repo.create_fork("P", "tv2_fork_p", kwargs["owner_account"])

    monkeypatch.setattr("transversal.tenancy_cli.provision_fork", _stub)

    main(["create-fork", "Probe", "--owner", "dave@example.com"])

    assert seen["source_database"] == "tv2_global"


def test_the_first_migration_is_a_flag_and_it_warns(repo, monkeypatch, capsys):
    _verified(repo)

    def _stub(registry_repo, **kwargs):
        return registry_repo.create_fork("P", "tv2_fork_p", kwargs["owner_account"])

    monkeypatch.setattr("transversal.tenancy_cli.provision_fork", _stub)

    main(["create-fork", "Probe", "--owner", "dave@example.com", "--include-play"])

    assert "play state" in capsys.readouterr().err


# ── list / drop / databases ───────────────────────────────────────────


def test_list_prints_every_fork(repo, capsys):
    owner = _verified(repo)
    repo.create_fork("One", "tv2_fork_one", owner.id, slug="one")
    repo.create_fork("Two", "tv2_fork_two", owner.id, slug="two")

    assert main(["list-forks"]) == 0

    out = capsys.readouterr().out
    assert "tv2_fork_one" in out and "tv2_fork_two" in out


def test_list_says_so_when_there_are_none(repo, capsys):
    assert main(["list-forks"]) == 0
    assert "no forks" in capsys.readouterr().out


def test_drop_without_yes_changes_nothing(repo, capsys):
    owner = _verified(repo)
    fork = repo.create_fork("One", "tv2_fork_one", owner.id, slug="one")

    assert main(["drop-fork", fork.id]) == 1

    assert "would drop" in capsys.readouterr().err
    assert repo.get_fork(fork.id) is not None


def test_drop_with_yes_removes_it(repo, monkeypatch, capsys):
    owner = _verified(repo)
    fork = repo.create_fork("One", "tv2_fork_one", owner.id, slug="one")
    monkeypatch.setattr(
        "transversal.tenancy_cli.drop_fork", lambda registry_repo, fork_id: True
    )

    assert main(["drop-fork", fork.id, "--yes"]) == 0
    assert "dropped" in capsys.readouterr().out


def test_drop_refuses_an_unknown_fork(repo, capsys):
    assert main(["drop-fork", "fork-ghost", "--yes"]) == 1
    assert "no fork" in capsys.readouterr().err


def test_databases_prints_the_global_and_every_fork(repo, capsys):
    owner = _verified(repo)
    repo.create_fork("One", "tv2_fork_one", owner.id, slug="one")

    assert main(["databases"]) == 0

    lines = capsys.readouterr().out.split()
    assert lines == ["transversal", "tv2_fork_one"]
