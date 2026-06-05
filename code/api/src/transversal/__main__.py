"""Transversal CLI — management commands.

Usage:
    python -m transversal seed    Run one-time database initialization.
"""

import sys

from transversal.db.repository import EntityRepository
from transversal.services.effects_applier import _register_core_handlers
from transversal.services.effects_engine import EffectsEngine
from transversal.services.entity_manager import EntityManager
from transversal.services.razmerit import RazmeritService
from transversal.services.session_manager import session_manager


def cmd_seed() -> None:
    """Initialize database with seed data. Idempotent — safe to run multiple times."""
    print("Connecting to ArangoDB...")
    repo = EntityRepository()
    em = EntityManager(repository=repo)
    raz = RazmeritService(repository=repo)
    engine = EffectsEngine()

    print("Seeding universes...")
    from transversal.db.seed import seed_universes

    seed_universes(em)

    print("Seeding trait registry...")
    from transversal.db.seed import seed_trait_registry

    seed_trait_registry(repo)

    print("Registering core effect handlers...")
    _register_core_handlers(em, raz)

    print("Seeding SFX registry...")
    from transversal.db.seed import seed_sfx_registry

    seed_sfx_registry(repo, engine=engine)

    print("Creating default characters...")
    from transversal.db.seed import seed_default_character, seed_elena

    seed_default_character(em)
    seed_elena(em)

    print("Creating locations...")
    from transversal.db.seed import seed_locations

    seed_locations(em)

    print("Creating default session...")
    s = session_manager.create(
        name="Krasnoyarsk-45 Extraction", gm_id="gm", universe="earth"
    )
    session_manager.join(s.id, "kael-1")
    session_manager.join(s.id, "elena-1")

    print("Seed complete.")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m transversal <command>")
        print("Commands:")
        print("  seed    Run one-time database initialization")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "seed":
        cmd_seed()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
