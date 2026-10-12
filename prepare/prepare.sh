#!/bin/sh
set -eu

echo "Preparing mailstack persistent storage"

# Stalwart runs as uid/gid 2000:2000.
install -d -m 0700 -o 2000 -g 2000 \
    /data/stalwart-data \
    /data/stalwart-etc

# Roundcube's database directory belongs to www-data (33:33).
install -d -m 0700 -o 33 -g 33 \
    /data/roundcube-db

# Postfix initializes and manages the contents of its spool itself.
install -d -m 0755 -o 0 -g 0 \
    /data/relay-spool

# getmail runs as root and keeps its retrieval state private.
install -d -m 0700 -o 0 -g 0 \
    /data/getmail-state

# Provenance is persistent operational state shared by the provenance
# sidecar and maintenance resieve runs.
install -d -m 0700 -o 0 -g 0 \
    /data/mail-provenance

# resieve-watch: which filter it last applied per account. Root-only.
install -d -m 0700 -o 0 -g 0 \
    /data/resieve-watch

# init's output and state: generated service config (contains secrets) and
# the Stalwart provisioner API key. Root-only.
install -d -m 0700 -o 0 -g 0 \
    /data/generated \
    /data/stalwart-provision

echo "Persistent storage ready"
