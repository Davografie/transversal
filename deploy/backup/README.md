# Backups

Daily, unattended, and rehearsed. This exists because the recovery story for inviting other
people in is a dump that runs whether or not anyone remembers — and because the global
multiverse is now the single source every new campaign is cloned from.

## What a snapshot contains

Under `.backups/<YYYYmmdd_HHMMSS>/`:

| path | is |
|---|---|
| `db/<database>/` | an `arangodump` of **every** database, discovered from the server (the registry and each campaign; `_system` is skipped) |
| `redis.rdb` | live session state |
| `manifest.txt` | per-collection document counts, so a restore can be checked without opening a database |

Plus one **rolling mirror** at `.backups/media-mirror/`, shared by all snapshots.

A snapshot is ~3 MB, because the media store is **content-addressed**: a file is named by the
digest of its bytes, so a blob is never rewritten — only added, or removed once no record
references it. Copying 645 MB per run would buy almost nothing (measured: a hardlink snapshot
still cost 0.6 GB, since linking needs identical mtime and attributes).

**The trade-off, stated rather than hidden:** a blob deleted *after* a snapshot is gone from
the mirror, so restoring that dump could miss an image whose record it still holds. Deletion is
refcounted and rare, and the alternative is a full copy of the store per run.

## Installed how

User units, so no sudo is needed:

```bash
loginctl enable-linger dave                 # so the timer runs while nobody is logged in
ln -sf /home/dave/dev/transversal2/deploy/backup/tv2-backup.service ~/.config/systemd/user/
ln -sf /home/dave/dev/transversal2/deploy/backup/tv2-backup.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tv2-backup.timer
```

Check it:

```bash
systemctl --user list-timers tv2-backup.timer     # when it next runs
systemctl --user start tv2-backup.service         # run one now
systemctl --user status tv2-backup.service        # how the last run went
journalctl --user -u tv2-backup.service -n 40     # what it said
```

If the tree moves away from `/home/dave/dev/transversal2`, relink the two units — the paths in
them are absolute.

## Restoring one database

Rehearsed on 2026-10-17 against the registry: the restored counts matched live exactly
(2 accounts, 2 campaigns, 41 account tokens, 4,904 blob references).

```bash
SNAP=.backups/20261017_160557          # pick a snapshot
DB=transversal_global                  # pick a database

docker exec tv2_arango sh -c 'rm -rf /tmp/rd && mkdir -p /tmp/rd'
docker cp "$SNAP/db/$DB" tv2_arango:/tmp/rd/$DB
docker exec tv2_arango sh -c "arangorestore --server.endpoint tcp://127.0.0.1:8529 \
  --server.username root --server.password \"\$ARANGO_ROOT_PASSWORD\" \
  --server.database $DB --input-directory /tmp/rd/$DB --overwrite true"
docker exec tv2_arango rm -rf /tmp/rd
```

**Restore into a probe database first** — add `--server.database tv2_restore_probe
--create-database true`, compare `manifest.txt` against it, then drop it. That is exactly how
the rehearsal above was done, and it is the difference between having a backup and hoping.

Restoring the *media* is `rsync -a .backups/media-mirror/ ./media/`. Restoring Redis is
`docker cp "$SNAP/redis.rdb" tv2_redis:/data/dump.rdb` and restarting the container.

## Retention

`--keep 7` (a week of dailies). The script prunes **only directories matching its own
timestamp shape**, so a manual backup kept in `.backups/` — such as the 2026-10-17
`pre-sanitize` dump — is never deleted.
