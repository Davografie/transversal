#!/usr/bin/env bash
# Mint a new ticket note and regenerate the board.
#
#   scripts/new-ticket.sh "Canvas: inspect a relationship trait from an edge"
#
# Allocates the next free B-number (never invents one by hand — two sessions
# minting at once is how you get two B125s), writes the note in
# docs/Process/Tickets/, and regenerates the board index.
#
# Allocation reads the highest B-number visible ANYWHERE, not just in this
# checkout. A role worktree that has not been rebased onto the integration branch
# sees a stale ticket directory, so scanning it alone hands out an id another
# session already used — and the "already exists" guard below does not catch it,
# because the file is not in *this* tree. See "Allocation".
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: scripts/new-ticket.sh <title>" >&2
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
DIR="docs/Process/Tickets"
TITLE="$*"

# One lock shared by every worktree (they share one .git dir), so two sessions
# cannot pick the same id in the same instant. Best-effort: without flock the
# scan below still makes a collision very unlikely.
if command -v flock >/dev/null 2>&1; then
  LOCK="$(git rev-parse --git-common-dir)/new-ticket.lock"
  exec 9>"$LOCK"
  flock 9
fi

# ── Allocation ────────────────────────────────────────────────────────────────
# Highest id among: the files in this worktree, the files in every other worktree
# (a ticket minted but not yet committed), and every branch (tickets that exist
# but are not merged here yet).
ids() { sed -E 's#.*/B([0-9]+)\.md#\1#' | grep -E '^[0-9]+$' | sort -n | tail -1; }

LOCAL_MAX="$(ls "$DIR"/B[0-9]*.md 2>/dev/null | ids || true)"
REFS_MAX="$(git log --all --pretty=format: --name-only --diff-filter=A -- "$DIR/B*.md" 2>/dev/null | ids || true)"
WT_MAX="$(
  git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2}' \
    | while read -r w; do ls "$w/$DIR"/B[0-9]*.md 2>/dev/null || true; done \
    | ids || true
)"

LAST=0
for n in "$LOCAL_MAX" "$REFS_MAX" "$WT_MAX"; do
  if [ -n "$n" ] && [ "$n" -gt "$LAST" ]; then LAST="$n"; fi
done

NEXT=$(( LAST + 1 ))
ID="B$NEXT"
FILE="$DIR/$ID.md"

# The scan above should make this impossible; keep it as a backstop, extended to
# an id that exists on another branch but not in this checkout.
if [ -e "$FILE" ] \
   || git log --all --pretty=format: --name-only --diff-filter=A -- "$FILE" 2>/dev/null | grep -q .; then
  echo "refusing: $ID already exists (here or on another branch) — rebase and retry" >&2
  exit 1
fi

if [ -n "$LOCAL_MAX" ] && [ "$LAST" -gt "$LOCAL_MAX" ]; then
  echo "note: this checkout's highest is B$LOCAL_MAX; the newest ticket elsewhere is B$LAST" >&2
  echo "      allocating $ID — this worktree looks behind, rebase when convenient" >&2
fi

cat > "$FILE" <<EOF
---
title: "$ID — $TITLE"
id: $ID
status: "pending"
owner: ""
phase: "Backlog — reconciled from \`to-do.md\`"
tags:
  - transversal
  - ticket
  - backlog
aliases:
  - $ID
---

### $ID — $TITLE
- **Owner:** 
- **Status:** pending #$ID
- **What:** 
- **Done:** 
- **Depends:** —
EOF

python3 scripts/gen-ticket-board.py
echo "minted $ID -> $FILE"
echo "fill in owner/what/done, then commit the note AND the regenerated board."
