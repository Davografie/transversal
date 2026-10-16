"""What every campaign database needs beyond its schema (B255/B88).

``get_db()`` gives a campaign its 20 collections and their indexes. This is the other
half: the SFX provisioning and the idempotent backfills that must also be present. It
runs at startup for the default database — and, via ``tenancy_cli provision``, for
every fork.

**Why it is a function and not just startup code.** A fork is a *verbatim clone*, so
it has everything that existed when it was made and **nothing added since**. The
moment a new ``ensure_*`` or ``backfill_*`` lands, every fork created before it
diverges silently — [[Tenancy Rollout Plan]]'s *"one forgotten database is a silent
divergence"*, arriving through the back door rather than through a migration script.
Making the pass callable is what lets an operator bring a fork up to date, and lets a
fork be created without anyone having to remember the ordering.

Everything here is idempotent; re-running it **is** the intended use.
"""

from __future__ import annotations

from transversal.services.roll_table import backfill_rolltable_anchor_paths
from transversal.services.sfx_owner import (
    backfill_play_as_rating_targets,
    backfill_source_kinds,
    backfill_support_default_sfx,
    backfill_trait_default_sfx,
    ensure_base_move_sfxs,
    ensure_contest_complication_sfx,
    ensure_give_in_sfx,
    ensure_gmc_base_difficulty,
    ensure_hitch_gain_complication_sfx,
    ensure_offer_negative_sfx,
    ensure_opportunity_sfx,
    ensure_prevent_taken_out_sfx,
    ensure_sfx_owners,
    ensure_starter_location_sfx,
    ensure_support_cast_sfx,
    ensure_targeting_ban_sfx,
    ensure_teleport_to_main_sfx,
    remove_legacy_buy_hitch_sfx,
    remove_legacy_contest_complication_sfx,
)


def provision_campaign(repo) -> None:
    """Provision one campaign database. **Idempotent** — safe to re-run.

    ``repo`` is an :class:`~transversal.db.repository.EntityRepository` bound to the
    database to provision; the caller scopes it (``get_db()`` honours
    ``use_database()``, so a request-scoped or explicitly scoped repo both work).
    """
    ensure_sfx_owners(repo)
    ensure_give_in_sfx(repo)
    ensure_targeting_ban_sfx(repo)
    ensure_contest_complication_sfx(repo)
    ensure_prevent_taken_out_sfx(repo)
    ensure_hitch_gain_complication_sfx(repo)
    ensure_opportunity_sfx(repo)
    ensure_offer_negative_sfx(repo)
    ensure_starter_location_sfx(repo)
    ensure_support_cast_sfx(repo)
    ensure_teleport_to_main_sfx(repo)
    ensure_base_move_sfxs(repo)
    ensure_gmc_base_difficulty(repo)
    remove_legacy_contest_complication_sfx(repo)
    remove_legacy_buy_hitch_sfx(repo)
    backfill_trait_default_sfx(repo)
    # The support character's way home ([[B61]]). Wired on the author's call
    # (2026-09-24): the live 7 support characters are player-owned, so provisioning
    # them was a decision rather than a migration — with it made, a rule exists on
    # every SC whether it was created through the flow or before the rule did.
    backfill_support_default_sfx(repo)
    backfill_source_kinds(repo)
    backfill_play_as_rating_targets(repo)
    # Roll-table tie anchors move off the legacy context pair onto the owner path
    # ([[B164]]). Idempotent; the one `{term_faction}` rule in the shared tables is
    # skipped and logged, since a runtime token is not a literal filter.
    backfill_rolltable_anchor_paths(repo)
    repo.collapse_legacy_personal_relationship_types()
