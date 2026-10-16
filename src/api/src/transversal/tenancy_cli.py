"""Operator CLI for the tenancy tier (B255/B88).

Run inside the API container::

    docker compose exec api python -m transversal.tenancy_cli --help

**Why a CLI as well as the API.** The mechanism is built, but using it needs an
account, and accounts are verified by email — which is not configured yet. The
operator holds the server, so creating a **verified** account is a legitimate
operator act: it is the same trust as holding ``ARCHITECT_TOKEN``, and it is what
makes the tier usable today. It is also the cheapest way to run the owner's first
migration — two instances of the current database, one to keep and one to clean —
which is otherwise a bare function call.

This is the *operator* path, not the product one: the account UI is [[B256]]'s and
the fork routes already exist for whoever builds it. The commands here call exactly
the same services, so there is one implementation and no second behaviour to keep
in step.
"""

from __future__ import annotations

import argparse
import sys

from transversal.api.tenancy import base_domain
from transversal.db.registry_repository import RegistryRepository, normalize_email
from transversal.services.provisioner import (
    campaign_databases,
    drop_fork,
    fork_slug,
    provision_fork,
)


def _registry() -> RegistryRepository:
    return RegistryRepository()


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _fork_line(fork) -> str:
    base = base_domain()
    where = f"https://{fork.slug}.{base}" if fork.slug and base else fork.database
    return f"{fork.id}  {fork.name}  [{fork.kind}]  {where}"


# ── Commands ──────────────────────────────────────────────────────────


def _bootstrap_account(args) -> int:
    """Create a **verified** account. The operator's word is the verification.

    Idempotent: an address that already has an account is returned as it is, and an
    unverified one is verified rather than duplicated.
    """
    email = normalize_email(args.email)
    if not email or "@" not in email:
        return _fail("a valid email address is required")

    registry = _registry()
    account = registry.find_account_by_email(email)
    if account is None:
        account = registry.create_account(email)
    verified = registry.mark_email_verified(account.id)
    print(f"{verified.id}  {verified.email}  verified={bool(verified.verified_at)}")
    return 0


def _create_fork(args) -> int:
    registry = _registry()
    owner = registry.find_account_by_email(args.owner)
    if owner is None:
        return _fail(f"no account for {args.owner!r} — bootstrap it first")
    if not owner.verified_at:
        return _fail(f"{owner.email!r} is not verified")

    slug = fork_slug(args.slug or args.name)
    if registry.find_fork_by_slug(slug):
        return _fail(f"the address {slug!r} is already taken")

    source = args.source or None
    if source is None:
        import os

        source = os.getenv("GLOBAL_DATABASE", "transversal")

    fork = provision_fork(
        registry,
        source_database=source,
        name=args.name,
        owner_account=owner.id,
        database=args.database,
        slug=slug,
        include_play=args.include_play,
    )
    print(_fork_line(fork))
    if args.include_play:
        print(
            "note: this copied the play state too (players, messages, history, "
            "join tokens) — that is the first migration, and the source still "
            "needs cleaning if it is to become the global multiverse.",
            file=sys.stderr,
        )
    return 0


def _list_forks(args) -> int:
    forks = _registry().list_forks()
    if not forks:
        print("no forks")
        return 0
    for fork in forks:
        print(_fork_line(fork))
    return 0


def _drop_fork(args) -> int:
    registry = _registry()
    fork = registry.get_fork(args.fork_id)
    if fork is None:
        return _fail(f"no fork {args.fork_id!r}")

    if not args.yes:
        # Irreversible, and there is no archive: say exactly what would go.
        print(
            f"would drop fork {fork.id} ({fork.name}) and its database "
            f"{fork.database!r}, and forget the routing row.\n"
            f"re-run with --yes to do it.",
            file=sys.stderr,
        )
        return 1

    if drop_fork(registry, fork.id):
        print(f"dropped {fork.id} ({fork.database})")
        return 0
    return _fail(f"could not drop {args.fork_id!r}")


def _databases(args) -> int:
    for name in campaign_databases(_registry(), global_database=args.global_database):
        print(name)
    return 0


# ── Entry point ───────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m transversal.tenancy_cli",
        description="Operator commands for the tenancy tier (accounts and forks).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser(
        "bootstrap-account",
        help="create a verified account (the operator's word is the verification)",
    )
    bootstrap.add_argument("email")
    bootstrap.set_defaults(handler=_bootstrap_account)

    create = sub.add_parser("create-fork", help="clone a database into a new fork")
    create.add_argument("name")
    create.add_argument("--owner", required=True, help="the owner's account email")
    create.add_argument("--slug", help="the DNS label (default: derived from the name)")
    create.add_argument("--database", help="the database name (default: derived)")
    create.add_argument("--source", help="what to clone from (default: GLOBAL_DATABASE)")
    create.add_argument(
        "--include-play",
        action="store_true",
        help="copy the play state too — the owner's first migration",
    )
    create.set_defaults(handler=_create_fork)

    listing = sub.add_parser("list-forks", help="every fork, newest first")
    listing.set_defaults(handler=_list_forks)

    drop = sub.add_parser("drop-fork", help="delete a fork's database and routing row")
    drop.add_argument("fork_id")
    drop.add_argument("--yes", action="store_true", help="actually do it")
    drop.set_defaults(handler=_drop_fork)

    databases = sub.add_parser(
        "databases", help="every database a schema change must reach"
    )
    databases.add_argument("--global", dest="global_database", help="the global's name")
    databases.set_defaults(handler=_databases)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover - thin wrapper
    sys.exit(main())
