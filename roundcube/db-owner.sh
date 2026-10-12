#!/bin/sh
# Post-setup task (run by the image's entrypoint after its setup, before
# Apache starts). The image's own setup runs as root and so creates the
# SQLite database root's; Apache must own it. Give it (and Roundcube's WAL
# companions) to www-data, private, on every start. The database is the one
# ROUNDCUBEMAIL_DSNW names (compose.yaml).
set -eu
[ "${ROUNDCUBEMAIL_DB_TYPE:-sqlite}" = sqlite ] || exit 0
db=${ROUNDCUBEMAIL_DSNW#sqlite:///}
db=${db%%\?*}
if [ ! -f "$db" ]; then
    echo "mailstack: $db (from ROUNDCUBEMAIL_DSNW) does not exist after setup" >&2
    exit 1
fi
for f in "$db" "$db-wal" "$db-shm"; do
    [ -e "$f" ] || continue
    chown www-data:www-data "$f"
    chmod 0600 "$f"
done
echo "mailstack: $db (and WAL files) www-data's, mode 0600"
