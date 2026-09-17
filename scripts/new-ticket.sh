#!/usr/bin/env bash
# Mint a new ticket note and regenerate the board.
#
#   scripts/new-ticket.sh "Canvas: inspect a relationship trait from an edge"
#
# Allocates the next free B-number (never invents one by hand — two sessions
# minting at once is how you get two B125s), writes the note in
# docs/Process/Tickets/, and regenerates the board index.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: scripts/new-ticket.sh <title>" >&2
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
DIR="docs/Process/Tickets"
TITLE="$*"

LAST="$(ls "$DIR"/B[0-9]*.md 2>/dev/null | sed -E 's#.*/B([0-9]+)\.md#\1#' | sort -n | tail -1 || true)"
NEXT=$(( ${LAST:-0} + 1 ))
ID="B$NEXT"
FILE="$DIR/$ID.md"

if [ -e "$FILE" ]; then
  echo "refusing: $FILE already exists" >&2
  exit 1
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
