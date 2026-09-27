"""Transversal CLI — management commands.

There are no commands. Data is managed entirely by the migration scripts
(`python -m transversal.migrate_entities`, `migrate_traits`, …). The old
`python -m transversal seed` command and its module (`db/seed.py`) were removed
on 2026-09-27: the content they described had been superseded twice over, and
reading them taught trait and table ids that no longer exist.
"""

import sys


def main() -> None:
    print(
        "No commands. Data is managed via migration scripts, e.g.:\n"
        "  python -m transversal.migrate_entities\n"
        "  python -m transversal.migrate_traits\n"
        "The `seed` command and `db/seed.py` were removed (2026-09-27)."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
