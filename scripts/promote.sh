#!/usr/bin/env bash
# Promote staging to production.
#
#   staging     release-build   where work integrates and is verified
#   production  production      what is deployed
#
# production is a **promotion branch**: it only ever fast-forwards to
# release-build, so it stays an ancestor of it. That invariant is the point —
# it makes `git log production..release-build` mean exactly *"staged but not yet
# live"*, which is the question you actually ask before a deploy.
#
# The record of a promotion is the **tag**, not a merge commit. A merge commit
# would break that linearity, and the tag is what you deploy and roll back to.
#
#   scripts/promote.sh          fast-forward production to release-build, tag it
#   scripts/promote.sh --check  report what is staged but not live; change nothing
#
# Run with `bash` — this repo has core.fileMode = false, so the executable bit is
# not tracked reliably across checkouts.
#
# This does NOT push. Publishing is a separate, deliberate act (see AGENTS.md):
# `git push origin production --follow-tags`.
set -euo pipefail

STAGING=release-build
PROD=production
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
if [ "$(git branch --show-current)" != "$STAGING" ]; then
  echo "note: run this from $STAGING (you are on $(git branch --show-current)) — continuing anyway" >&2
fi

staging="$(git rev-parse "$STAGING")"
if ! prod="$(git rev-parse --verify --quiet "$PROD")"; then
  echo "error: no '$PROD' branch. Create it: git branch $PROD $STAGING" >&2
  exit 1
fi

if [ "$staging" = "$prod" ]; then
  echo "level: $PROD == $STAGING at $(git rev-parse --short "$staging") — nothing staged"
  exit 0
fi

# A promotion is only a promotion if production has not moved on its own.
if ! git merge-base --is-ancestor "$prod" "$staging"; then
  echo "REFUSING: '$PROD' is not an ancestor of '$STAGING' — they have diverged." >&2
  echo "Something was committed to $PROD directly. That breaks the invariant that" >&2
  echo "makes 'staged but not live' readable, so resolve it before promoting." >&2
  exit 1
fi

echo "staged but not live — $PROD..$STAGING:"
git log --oneline "$PROD..$STAGING" | sed 's/^/  /'
echo

if [ "$CHECK" = "1" ]; then
  echo "--check: nothing changed"
  exit 0
fi

# Fast-forward the branch ref WITHOUT checking it out, so the shared working tree
# (which serves :3000 from release-build) is not disturbed.
git fetch --quiet . "$STAGING:$PROD"
tag="production-$(date +%Y.%m.%d)"
if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
  tag="$tag.$(git rev-parse --short "$staging")"
fi
git tag -a "$tag" -m "promote $STAGING -> $PROD at $(git rev-parse --short "$staging")"

echo "promoted: $PROD is now $(git rev-parse --short "$PROD"), tagged $tag"
echo "next: verify the app, then publish with"
echo "  git push origin $PROD --follow-tags"
