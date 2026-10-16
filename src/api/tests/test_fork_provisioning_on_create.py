"""B88/B305 — a fork is provisioned when it is created, not when someone remembers.

The pass itself is old (`services/campaign_provisioning.provision_campaign`) and
idempotent. What these assert is the *wiring*: creating a fork runs it, and a failure in
it does not take the fork down with it — a campaign that exists but lags is recoverable
with one CLI command, while a campaign nobody can open is not.
"""

from types import SimpleNamespace


class _FakeDB:
    """Stands in for a StandardDatabase: EntityRepository binds 19 collections."""

    def collection(self, name):
        return SimpleNamespace()


def test_a_new_fork_is_provisioned_immediately(monkeypatch):
    from transversal.services import campaign_provisioning, provisioner

    seen = []
    monkeypatch.setattr(
        campaign_provisioning, "provision_campaign", lambda repo: seen.append(repo)
    )

    provisioner.provision_new_fork(_FakeDB(), "tv2_fork_probe")

    assert len(seen) == 1, "the pass must run for the database that was just cloned"


def test_a_failed_pass_does_not_lose_the_fork(monkeypatch, caplog):
    from transversal.services import campaign_provisioning, provisioner

    def _boom(repo):
        raise RuntimeError("a backfill exploded")

    monkeypatch.setattr(campaign_provisioning, "provision_campaign", _boom)

    with caplog.at_level("ERROR"):
        provisioner.provision_new_fork(_FakeDB(), "tv2_fork_probe")  # must not raise

    assert any("provisioning pass failed" in r.message for r in caplog.records)
