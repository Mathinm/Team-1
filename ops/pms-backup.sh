#!/bin/sh
# NFR-13 (TC-REL-03): daily PostgreSQL backup, and restore, for PMS.
#
# Runs inside the "backup" service of docker-compose.yml (image postgres:16-alpine, which
# already contains pg_dump and pg_restore). Which database to use comes from the standard
# PostgreSQL variables PGHOST, PGUSER, PGPASSWORD and PGDATABASE, set in docker-compose.yml.
#
#   sh /scripts/pms-backup.sh loop             run forever: one backup a day at BACKUP_TIME
#   sh /scripts/pms-backup.sh now              take one backup right now
#   sh /scripts/pms-backup.sh list             show the backups
#   sh /scripts/pms-backup.sh restore FILE     replace the database with FILE (stop backend first)
#
# From your computer, put "docker compose exec backup" in front, for example:
#   docker compose exec backup sh /scripts/pms-backup.sh list
set -eu

DIR=${BACKUP_DIR:-/backups}           # ./backups on your computer (see docker-compose.yml)
TIME=${BACKUP_TIME:-02:00}            # store time (TZ) of the daily backup, HH:MM
KEEP_DAYS=${BACKUP_KEEP_DAYS:-7}      # backups older than this many days are deleted
CHECK_SECONDS=${BACKUP_CHECK_SECONDS:-60}

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') backup: $*"; }

backup_now() {
    mkdir -p "$DIR"
    name="pms_$(date +%Y-%m-%d_%H%M%S).dump"
    # pg_dump writes to a temporary name; it gets the real name only if pg_dump succeeded,
    # so a half-written file (disk full, database down) never looks like a good backup.
    if pg_dump --format=custom --file="$DIR/.$name.part"; then
        mv "$DIR/.$name.part" "$DIR/$name"
        date +%Y%m%d > "$DIR/.last_success"   # the health check looks at this file
        log "saved $name ($(du -h "$DIR/$name" | cut -f1))"
        find "$DIR" -name 'pms_*.dump' -mtime +"$KEEP_DAYS" | while read -r old; do
            rm -f "$old" && log "deleted old backup $(basename "$old")"
        done
    else
        rm -f "$DIR/.$name.part"
        log "FAILED, will try again in $CHECK_SECONDS s"
        return 1
    fi
}

# Is a backup due? Yes when there has never been one, when the newest is from before
# yesterday (the computer was off at BACKUP_TIME), or when today's is missing and
# BACKUP_TIME has passed. Dates and times are compared as numbers: 20261101, 0200.
backup_due() {
    last=$(cat "$DIR/.last_success" 2>/dev/null || echo 0)
    today=$(date +%Y%m%d)
    yesterday=$(date -d "@$(( $(date +%s) - 86400 ))" +%Y%m%d)
    now=$(date +%H%M)
    at=$(echo "$TIME" | tr -d :)
    [ "$last" -lt "$yesterday" ] && return 0
    [ "$last" -lt "$today" ] && [ "$now" -ge "$at" ] && return 0
    return 1
}

loop() {
    log "daily backup at $TIME (${TZ:-UTC}), keeping $KEEP_DAYS days, into $DIR"
    while true; do
        if backup_due; then
            backup_now || true   # a failure is logged; the next round tries again
        fi
        sleep "$CHECK_SECONDS"
    done
}

list() {
    ls -lh "$DIR"/pms_*.dump 2>/dev/null || echo "No backups in $DIR yet."
}

restore() {
    file=${1:-}
    [ -n "$file" ] || { echo "Usage: restore FILE   (a name from: list)"; exit 2; }
    [ -f "$file" ] || file="$DIR/$file"   # a bare name like pms_2026-11-01_020000.dump
    [ -f "$file" ] || { echo "No such backup: $1"; list; exit 2; }

    # Restoring under a running backend could mix old and new data, so refuse.
    others=$(psql -tAc "SELECT count(*) FROM pg_stat_activity
                        WHERE datname = current_database() AND pid <> pg_backend_pid()
                          AND backend_type = 'client backend'")
    if [ "$others" != 0 ]; then
        echo "$others other connection(s) to $PGDATABASE. Stop the backend first:"
        echo "  docker compose stop backend"
        exit 3
    fi

    log "restoring $(basename "$file") into database $PGDATABASE"
    # --clean --if-exists: drop each table before recreating it from the backup.
    # --single-transaction: all or nothing; on any error the database stays as it was.
    # --no-owner: don't insist the tables belong to the user who made the backup.
    pg_restore --clean --if-exists --no-owner --single-transaction \
        --dbname="$PGDATABASE" "$file"
    log "restore finished. Start the backend again: docker compose start backend"
}

case "${1:-loop}" in
    loop) loop ;;
    now) backup_now ;;
    list) list ;;
    restore) restore "${2:-}" ;;
    *) echo "Usage: $0 loop|now|list|restore FILE"; exit 2 ;;
esac
