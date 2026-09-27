#!/usr/bin/env bash
# Point git at the committed hooks in scripts/git-hooks/.
#
# Hooks do not live in version control and `.git/hooks` is not shared in a useful
# way, so the hook itself is committed under scripts/git-hooks/ and git is told
# where to find it. `core.hooksPath` lives in the repo's *common* config, so a
# single run covers every worktree of this checkout — all role sessions included.
#
# Safe to re-run. Note that setting core.hooksPath makes git ignore `.git/hooks`
# entirely; there are no bespoke hooks there today, so nothing is displaced.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

chmod +x scripts/git-hooks/*
git config core.hooksPath scripts/git-hooks

echo "core.hooksPath = $(git config core.hooksPath)"
echo "hooks:"
ls -1 scripts/git-hooks/
