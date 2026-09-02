#!/usr/bin/env bash
# Serve a role worktree's frontend on a throwaway port for local testing.
#
# :3000 is RESERVED for the canonical tv2_frontend (release-build). This script
# never uses it, so a worktree can never shadow the integration tree.
set -euo pipefail

IMAGE="${FRONTEND_IMAGE:-transversal2-frontend:latest}"
NETWORK="${FRONTEND_NETWORK:-transversal2_default}"
BASE_PORT="${FRONTEND_BASE_PORT:-3002}"

die() { echo "error: $*" >&2; exit 1; }

if [[ $# -lt 1 ]]; then
  cat >&2 <<'EOF'
Usage: scripts/dev-worktree.sh <worktree-path> [container-name]

Mount a git worktree's frontend over the dev image and serve it on a free
port starting at 3002 (:3000 is reserved for release-build and never used).

Examples:
  scripts/dev-worktree.sh /home/dave/dev/transversal2-gm-panels
  scripts/dev-worktree.sh /home/dave/dev/transversal2-effects wt-effects
EOF
  exit 1
fi

WT_ROOT="$(cd "$1" && pwd)"
NAME="${2:-wt-$(basename "$WT_ROOT")}"
NAME="${NAME//[^a-zA-Z0-9_.-]/-}"

SRC="$WT_ROOT/src/frontend/src"
PUBLIC="$WT_ROOT/src/frontend/public"
VITE="$WT_ROOT/src/frontend/vite.config.js"
for p in "$SRC" "$PUBLIC" "$VITE"; do
  [[ -e "$p" ]] || die "missing frontend path: $p"
done

# Pick a free host port, never 3000.
port="$BASE_PORT"
while :; do
  if ! ss -ltn 2>/dev/null | grep -qE ":$port[[:space:]]"; then break; fi
  port=$((port + 1))
done
[[ "$port" == 3000 ]] && port=3002 # hard guard (unreachable when BASE_PORT>=3002)

if [[ -n "$(docker ps -a --filter "name=^/${NAME}$" -q)" ]]; then
  die "container '$NAME' already exists — 'docker rm -f $NAME' first (or pass another name)"
fi

echo "Serving $WT_ROOT"
echo "  container: $NAME"
echo "  url:       http://localhost:$port"

docker run -d --name "$NAME" -p "${port}:3000" \
  --network "$NETWORK" \
  -v "$SRC:/app/src" \
  -v "$PUBLIC:/app/public" \
  -v "$VITE:/app/vite.config.js" \
  "$IMAGE" npm run dev
