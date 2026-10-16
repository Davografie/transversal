#!/usr/bin/env bash
# Point a worktree's coordination paths at the ONE shared copy.
#
# Why: `docs/sessions/`, `docs/Process/`, `docs/to-do.md` and the security
# register are **gitignored** so they never reach the public repo. But git was also
# the only thing that carried a session doc from a role's worktree to the main
# checkout — so ignoring them left **20 private copies** drifting apart, in both
# directions (agent tools resolve RELATIVE paths against the main checkout, so
# sessions write to different copies depending on how they name the path).
#
# The result was measured on 2026-10-16: 11 of 18 role docs differed, and 11
# `[[Overseer]]` asks sat in worktrees where the main checkout could not see them.
#
# Symlinking every worktree at these paths fixes it at the root: relative and
# absolute paths both resolve to the same file, so there is nothing to propagate.
#
#   scripts/link-coordination.sh          # the current worktree
#   scripts/link-coordination.sh --all    # every worktree of this repo
#
# Nothing is deleted: a real path is MOVED into the shared archive first.
set -euo pipefail

INTERNAL="${TV2_INTERNAL:-/home/dave/dev/transversal2-internal}"
[ -d "$INTERNAL" ] || { echo "no shared coordination dir at $INTERNAL" >&2; exit 1; }

PAIRS=(
  "docs/sessions:sessions"
  "docs/Process:Process"
  "docs/to-do.md:to-do.md"
  "docs/Technical/Security Posture.md:Technical/Security Posture.md"
)

relpath() { python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$1" "$2"; }

link_one() {
  local wt="$1" path="$2" target="$3"
  local full="$wt/$path" dest="$INTERNAL/$target"
  local rel; rel="$(relpath "$dest" "$(dirname "$full")")"

  if [ -L "$full" ]; then
    if [ "$(readlink "$full")" = "$rel" ]; then
      echo "  ok       $path"
    else
      rm "$full"; ln -s "$rel" "$full"; echo "  relinked $path"
    fi
  elif [ -e "$full" ]; then
    # Never destroy: move the real copy into the archive first.
    local keep="$INTERNAL/.archive/migrated/$(basename "$wt")"
    mkdir -p "$keep/$(dirname "$path")"
    mv "$full" "$keep/$path"
    mkdir -p "$(dirname "$full")"
    ln -s "$rel" "$full"
    echo "  migrated $path  (real copy -> .archive/migrated/$(basename "$wt")/$path)"
  else
    mkdir -p "$(dirname "$full")"
    ln -s "$rel" "$full"
    echo "  created  $path"
  fi
}

do_worktree() {
  local wt="$1"
  echo "=== $(basename "$wt")"
  for pair in "${PAIRS[@]}"; do
    link_one "$wt" "${pair%%:*}" "${pair##*:}"
  done
}

if [ "${1:-}" = "--all" ]; then
  while read -r wt; do do_worktree "$wt"; done < <(git worktree list | awk '{print $1}')
else
  do_worktree "$(git rev-parse --show-toplevel)"
fi

echo
echo "done. Verify: read a file through the link, and 'git status' must stay clean."
