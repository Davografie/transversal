#!/usr/bin/env bash
# Back up everything the deployment would be sorry to lose: every ArangoDB database,
# the media store, and Redis. Part of the B305 pre-invitation readiness work.
#
#   scripts/backup-databases.sh              # snapshot now, under .backups/<stamp>/
#   scripts/backup-databases.sh --keep 14    # keep the newest 14 snapshots
#   scripts/backup-databases.sh --dry-run    # say what it would do
#
# Design notes, each from something that has already bitten this project:
#
# * **Every database, discovered not listed.** The registry and each campaign are separate
#   databases, and a new fork appears by itself — a hand-written list is the "one forgotten
#   database is a silent divergence" trap. `_system` is skipped (it holds no app data).
# * **Media is a rolling mirror, not a copy per snapshot.** The store is content-addressed
#   (a file is named by the digest of its bytes), so a blob is never rewritten — only added
#   or, once nothing references it, removed. Copying 645 MB per run buys almost nothing: a
#   hardlink snapshot still cost 0.6 GB measured, because linking needs identical mtime and
#   attributes. One mirror holds every blob any snapshot can reference; the trade-off (a blob
#   deleted after a snapshot is not in the mirror) is stated in the media section below.
# * **Redis is dumped**, because sessions are live state that a restore wants back.
# * **A manifest of per-collection counts** is written beside the dump, so a restore can be
#   checked without opening a database and "did we get everything" is answerable.
# * **The dump happens inside the Arango container**, because `arangodump` lives there and
#   the API image does not have it.
#
# It never deletes a snapshot it did not create: pruned directories must match this
# script's own `<YYYYmmdd_HHMMSS>` shape, so a manual backup kept in `.backups/` (such as
# the 2026-10-17 pre-sanitize dump) is left alone.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP="${TV2_BACKUP_KEEP:-7}"
DRY_RUN=0
ARANGO="${TV2_ARANGO_CONTAINER:-tv2_arango}"
API="${TV2_API_CONTAINER:-tv2_api}"
REDIS="${TV2_REDIS_CONTAINER:-tv2_redis}"

while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$ROOT/.backups/$STAMP"

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then say "  would run: $*"; else "$@"; fi; }

say "backup → $DEST"
[ "$DRY_RUN" = 1 ] && say "(dry run: nothing is written)"

# ── Which databases? Ask the server, never a list in this file. ──────────────
DATABASES="$(
  docker exec -i "$API" python - <<'PY'
import os
from arango import ArangoClient
client = ArangoClient(hosts=os.environ["ARANGO_URL"])
sys = client.db("_system", username="root", password=os.environ["ARANGO_ROOT_PASSWORD"])
for name in sorted(sys.databases()):
    if not name.startswith("_"):
        print(name)
PY
)"
[ -n "$DATABASES" ] || { echo "no databases found — refusing to write an empty backup" >&2; exit 1; }
say "databases: $(echo "$DATABASES" | tr '\n' ' ')"

run mkdir -p "$DEST/db"

# ── The dumps ────────────────────────────────────────────────────────────────
for db in $DATABASES; do
  say "  dumping $db"
  if [ "$DRY_RUN" = 1 ]; then continue; fi
  docker exec "$ARANGO" sh -c "rm -rf /tmp/tv2dump && mkdir -p /tmp/tv2dump/$db && \
    arangodump --server.endpoint tcp://127.0.0.1:8529 --server.username root \
      --server.password \"\$ARANGO_ROOT_PASSWORD\" --server.database '$db' \
      --output-directory /tmp/tv2dump/$db --overwrite true --compress-output true" >/dev/null
  docker cp "$ARANGO:/tmp/tv2dump/$db" "$DEST/db/$db" >/dev/null
  docker exec "$ARANGO" rm -rf /tmp/tv2dump
done

# ── Media: one rolling mirror, not a copy per snapshot ───────────────────────
# The store is content-addressed — a file is named by the digest of its bytes — so a blob is
# never rewritten, only added, or removed once no record references it any more. A copy of
# 645 MB per snapshot therefore buys almost nothing (measured: a hardlink snapshot still cost
# 0.6 GB, because linking needs identical mtime and attributes and most files differ). One
# mirror holds every blob any snapshot can reference.
#
# The trade-off, stated rather than hidden: a blob deleted *after* a snapshot is gone from the
# mirror, so restoring that dump could miss an image whose record it still holds. Deletion is
# refcounted and rare; the alternative is a full copy per run.
MIRROR="$ROOT/.backups/media-mirror"
if [ -d "$ROOT/media" ]; then
  say "  media → rolling mirror at .backups/media-mirror"
  run mkdir -p "$MIRROR"
  run rsync -a --delete "$ROOT/media/" "$MIRROR/"
fi

# ── Redis ────────────────────────────────────────────────────────────────────
if [ "$DRY_RUN" = 0 ]; then
  say "  redis → dump.rdb"
  docker exec "$REDIS" redis-cli SAVE >/dev/null 2>&1 || say "    (redis SAVE failed; continuing)"
  docker cp "$REDIS:/data/dump.rdb" "$DEST/redis.rdb" >/dev/null 2>&1 || say "    (no dump.rdb; continuing)"
fi

# ── Manifest: what a restore should add up to ────────────────────────────────
if [ "$DRY_RUN" = 0 ]; then
  say "  manifest"
  {
    echo "# backup $STAMP"
    echo "# created $(date -Is)"
    echo
    for db in $DATABASES; do
      echo "## $db"
      docker exec -i "$API" python - "$db" <<'PY'
import os, sys
from arango import ArangoClient
name = sys.argv[1]
client = ArangoClient(hosts=os.environ["ARANGO_URL"])
db = client.db(name, username="root", password=os.environ["ARANGO_ROOT_PASSWORD"])
total = 0
for col in sorted(db.collections(), key=lambda c: c["name"]):
    if col["name"].startswith("_"):
        continue
    n = db.collection(col["name"]).count()
    total += n
    print(f"{n:>8}  {col['name']}")
print(f"{total:>8}  (total)")
PY
    done
  } > "$DEST/manifest.txt"
  du -sh "$DEST" | sed 's/^/  size: /'
fi

# ── Prune, but only our own snapshots ────────────────────────────────────────
if [ "$DRY_RUN" = 0 ]; then
  mapfile -t MINE < <(ls -1d "$ROOT"/.backups/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9] 2>/dev/null | sort)
  if [ "${#MINE[@]}" -gt "$KEEP" ]; then
    for old in "${MINE[@]:0:$((${#MINE[@]} - KEEP))}"; do
      say "  pruning $(basename "$old")"
      rm -rf "$old"
    done
  fi
fi

say "done: $DEST"
