#!/usr/bin/env python3
"""Regenerate the ticket board (docs/Process/Tickets.md) from the ticket notes.

The notes in docs/Process/Tickets/<ID>.md are the source of truth. This script
rewrites only the region between the BEGIN/END GENERATED INDEX markers: the head
(frontmatter + how-to) and the tail (the hand-maintained Deferred section) are
preserved verbatim.

Run it after minting or editing tickets:  python3 scripts/gen-ticket-board.py
"""
import json, os, re, sys, glob, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, "docs/Process/Tickets.md")
NOTES = os.path.join(ROOT, "docs/Process/Tickets")

BEGIN = "<!-- BEGIN GENERATED INDEX"
END = "<!-- END GENERATED INDEX"

# Board section order. Notes are matched to a section by prefix, so a note whose
# `phase` is "Backlog" or "Backlog — reconciled from `to-do.md`" lands the same.
SECTION_ORDER = [
    "Phase 1 — Keystone: effect targeting & application",
    "Phase 2 — Play spine: tests & contests resolve",
    "Phase 3 — Stakes & consequences",
    "Phase 4 — Character sheet: traits as first-class",
    "Phase 5 — Prep & content",
    "Phase 6 — Movement & projections",
    "Phase 7 — Polish & backlog",
    "Backlog — reconciled from `to-do.md`",
    "Troupe play (support cast & spotlight)",
]


def parse_frontmatter(text):
    """Minimal YAML reader for the flat scalars this vault writes."""
    if not text.startswith("---"):
        return {}
    end = text.index("\n---", 3)
    fm = {}
    for line in text[3:end].split("\n"):
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith('"'):
            try:
                fm[key] = json.loads(raw)
            except Exception:
                fm[key] = raw.strip('"')
        elif raw:
            fm[key] = raw
    return fm


def section_for(phase):
    if not phase:
        return SECTION_ORDER[-1]
    for s in SECTION_ORDER:
        if s.startswith(phase) or phase.startswith(s.split(" — ")[0]):
            return s
    return phase


def main():
    board = open(BOARD, encoding="utf8").read()
    b = board.index(BEGIN)
    e = board.index(END)
    head = board[: board.index("\n", b) + 1]   # keep the BEGIN marker line
    tail = board[e:]

    by_section = collections.OrderedDict((s, []) for s in SECTION_ORDER)
    for path in sorted(glob.glob(os.path.join(NOTES, "*.md"))):
        name = os.path.basename(path)
        if name.startswith("_"):
            continue
        fm = parse_frontmatter(open(path, encoding="utf8").read())
        tid, title = fm.get("id"), fm.get("title")
        if not tid:
            print(f"  ! skipping {name}: no id in frontmatter", file=sys.stderr)
            continue
        short = title.split(" — ", 1)[1] if title and " — " in title else (title or tid)
        by_section.setdefault(section_for(fm.get("phase")), []).append(
            (tid, short, fm.get("status", "pending"), fm.get("owner"), fm.get("priority"))
        )

    def note_key(item):
        """Numeric order: P2.2 before P2.10; B49 between B48 and B68."""
        tid = item[0]
        m = re.match(r"^([A-Za-z]+)(\d+)(?:\.(\d+)(\w*))?$", tid)
        if not m:
            return (9, 0, 0, "", tid)
        return (
            0 if m.group(1) == "B" else 1,
            int(m.group(2)),
            int(m.group(3) or 0),
            m.group(4) or "",
        )

    out = [head.rstrip("\n"), ""]
    total = 0
    for sec, items in by_section.items():
        if not items:
            continue
        out += ["## " + sec, ""]
        for tid, short, status, owner, prio in sorted(items, key=note_key):
            bits = [f"[[{tid}]] — {short}", f"*{status}*"]
            if owner:
                bits.append(owner)
            if prio:
                bits.append(f"`#{prio}`")
            out.append("- " + " · ".join(bits))
            total += 1
        out.append("")
    out.append(f"*{total} tickets, generated from `docs/Process/Tickets/`.*")
    out.append("")
    out.append(tail)
    open(BOARD, "w", encoding="utf8").write("\n".join(out))
    print(f"board regenerated: {total} tickets across {sum(1 for v in by_section.values() if v)} sections")


if __name__ == "__main__":
    main()
