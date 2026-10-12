#!/bin/bash
set -u

CONFIG_DIR=/config
STATE_ROOT=/state
FOLDERS=/app/folders.py
# A handover in progress may wait up to ~2.5 min for provenance (bridge).
STOP_WAIT=170
SCAN_INTERVAL="${SCAN_INTERVAL:?set by compose}"
SUPERVISOR_INTERVAL=5
# An account's getmail that exits within this many seconds of its start is
# started again only after as long (a refused login is not retried every 5 s).
RESTART_PAUSE=60

declare -A PIDS STARTED NEXT_START

log() {
    printf '%s\n' "$*"
}

account_from_config() {
    basename "$1" .conf
}

start_getmail() {
    local account="$1"
    local config="$2"
    local state="$STATE_ROOT/$account"

    mkdir -p "$state"
    chmod 700 "$state"

    # Only with the provider's folder list applied (folders.py: explicit
    # mailboxes, no all-mail view, roles known). The generated config says
    # `mailboxes = ALL` and is never run as it is.
    if [ ! -f "$state/getmail.rc" ]; then
        log "GETMAIL WAIT account=$account: no folder list yet; fetching starts after a successful scan"
        return 0
    fi

    log "GETMAIL START account=$account"

    getmail \
        --getmaildir="$state" \
        --rcfile="$state/getmail.rc" \
        --idle=INBOX \
        --to-oldmail-on-each-mail &

    PIDS["$account"]=$!
    STARTED["$account"]=$SECONDS
}

stop_getmail() {
    local account="$1"
    local pid="${PIDS[$account]:-}"

    [ -n "$pid" ] || return 0

    if kill -0 "$pid" 2>/dev/null; then
        log "GETMAIL STOP account=$account pid=$pid"
        kill "$pid"
        wait "$pid" 2>/dev/null || true
    fi

    unset 'PIDS[$account]'
}

restart_getmail() {
    local account="$1"
    local config="$2"

    stop_getmail "$account"
    start_getmail "$account" "$config"
}

scan_folders() {
    local account="$1"
    local config="$2"
    local state="$STATE_ROOT/$account"
    local old="$state/folders.list"
    local raw="$state/folders.list.raw"
    local new="$state/folders.list.new"

    rm -f "$raw" "$new"

    # The provider's address and login: <account>.curl, written by
    # generate-config (never on curl's command line).
    if ! curl --config "${config%.conf}.curl" \
        --silent \
        --show-error \
        --fail \
        --connect-timeout 30 \
        --max-time 120 \
        > "$raw"
    then
        rm -f "$raw" "$new"
        log "FOLDER ERROR account=$account scan failed"
        return 2
    fi

    LC_ALL=C sort "$raw" > "$new"
    rm -f "$raw"

    if [ ! -f "$old" ]; then
        mv "$new" "$old"
        log "FOLDER BASELINE account=$account"
        # A first list (after a failed or unused one): 10 makes the
        # supervisor apply it and (re)start getmail.
        return 10
    fi

    if cmp -s "$old" "$new"; then
        rm -f "$new"
        log "FOLDER UNCHANGED account=$account"
        return 0
    fi

    mv "$new" "$old"
    log "FOLDER CHANGED account=$account"
    return 10
}

# folders.py: the provider's folder list -> folders.json (for the handoff)
# and getmail.rc (for getmail). On failure nothing is written and the list
# is forgotten, so the next scan is a baseline and tries again; a running
# getmail keeps its previous list meanwhile. Returns non-zero on failure.
update_folders() {
    local account="$1"
    local config="$2"
    if ! python3 "$FOLDERS" "$STATE_ROOT/$account" "$config"; then
        rm -f "$STATE_ROOT/$account/folders.list"
        log "FOLDER ERROR account=$account folder list not used; tried again at the next scan"
        return 1
    fi
}

# getmail turns SIGTERM into an abort wherever it is; in the middle of a
# handover that can leave a mail delivered but not recorded (fetched again,
# a duplicate). So: no new handovers (the handoff sees .stopping and defers),
# wait for the running ones, then stop getmail.
handovers_running() {
    local marker pid
    for marker in "$STATE_ROOT"/.handoff-*; do
        [ -e "$marker" ] || continue
        pid=${marker##*-}
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$marker"
    done
    return 1
}

shutdown() {
    log "SHUTDOWN"
    touch "$STATE_ROOT/.stopping"
    local waited=0
    while handovers_running && [ "$waited" -lt "$STOP_WAIT" ]; do
        sleep 1
        waited=$((waited + 1))
    done
    log "SHUTDOWN handovers finished after ${waited}s"

    for account in "${!PIDS[@]}"; do
        stop_getmail "$account"
    done

    exit 0
}

trap shutdown TERM INT

configs=("$CONFIG_DIR"/*.conf)

if [ ! -e "${configs[0]}" ]; then
    log "ERROR: no generated getmail configurations"
    exit 1
fi

rm -f "$STATE_ROOT/.stopping" "$STATE_ROOT"/.handoff-*

for config in "${configs[@]}"; do
    account=$(account_from_config "$config")
    mkdir -p "$STATE_ROOT/$account"
    chmod 700 "$STATE_ROOT/$account"
    # Scan before the first fetch, so getmail never sees an all-mail view;
    # a failed scan leaves the last applied list (none: getmail waits).
    scan_folders "$account" "$config"
    if [ -f "$STATE_ROOT/$account/folders.list" ]; then
        update_folders "$account" "$config"
    fi
    start_getmail "$account" "$config"
done

log "READY accounts=${#configs[@]} scan_interval=${SCAN_INTERVAL}s"

scan_elapsed=0

while true; do
    sleep "$SUPERVISOR_INTERVAL"
    scan_elapsed=$((scan_elapsed + SUPERVISOR_INTERVAL))

    for config in "${configs[@]}"; do
        account=$(account_from_config "$config")
        pid="${PIDS[$account]:-}"

        if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
            wait "$pid" 2>/dev/null
            rc=$?
            ran=$((SECONDS - ${STARTED[$account]:-0}))
            unset 'PIDS[$account]'
            pause=0
            [ "$ran" -lt "$RESTART_PAUSE" ] && pause=$RESTART_PAUSE
            NEXT_START["$account"]=$((SECONDS + pause))
            log "GETMAIL EXITED account=$account rc=$rc after ${ran}s; started again in ${pause}s"
        elif [ -z "$pid" ] && [ -f "$STATE_ROOT/$account/getmail.rc" ] \
             && [ "$SECONDS" -ge "${NEXT_START[$account]:-0}" ]; then
            start_getmail "$account" "$config"
        fi
    done

    if [ "$scan_elapsed" -lt "$SCAN_INTERVAL" ]; then
        continue
    fi
    scan_elapsed=0

    for config in "${configs[@]}"; do
        account=$(account_from_config "$config")

        scan_folders "$account" "$config"
        rc=$?

        case "$rc" in
            0)
                ;;
            10)
                if update_folders "$account" "$config"; then
                    log "TOPOLOGY RESTART account=$account"
                    restart_getmail "$account" "$config"
                fi
                ;;
            *)
                log "FOLDER WARNING account=$account rc=$rc; getmail left running"
                ;;
        esac
    done
done
