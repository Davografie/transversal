"""Transversal CLI — management commands.

Usage:
    python -m transversal seed    (disabled — use migration scripts)
"""

import sys


def cmd_seed() -> None:
    """Seed data is DEPRECATED. Use migration scripts instead.

    All data is now migrated from the old Transversal database.
    Do not run this — it will overwrite migrated data with outdated defaults.
    """
    print(
        "ERROR: Seed command is disabled. "
        "Data is managed via migration scripts (migrate_traitsets, migrate_traits, etc.). "
        "Run `python -m transversal.migrate_entities` to migrate remaining data."
    )
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m transversal <command>")
        print("Commands:")
        print("  seed    (disabled)")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "seed":
        cmd_seed()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
