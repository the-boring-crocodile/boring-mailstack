#!/bin/sh
set -eu

STALWART_BIN=/usr/local/bin/stalwart
STALWART_CONFIG=/etc/stalwart/config.json

start_stalwart() {
    "$STALWART_BIN" --config "$STALWART_CONFIG" &
    STALWART_PID=$!
}

stop_stalwart() {
    kill -TERM "$STALWART_PID"
    wait "$STALWART_PID" || true
}

# Already configured: recovery/bootstrap credential must not survive
# into normal operation.
if [ -f /etc/stalwart/config.json ]; then
    unset STALWART_RECOVERY_ADMIN
    exec "$STALWART_BIN" --config "$STALWART_CONFIG"
fi

echo "mailstack: starting Stalwart bootstrap phase"

start_stalwart

# Wait until the bootstrap operation performed by mailstack-init has
# produced the persistent configuration.
while [ ! -f /etc/stalwart/config.json ]; do
    if ! kill -0 "$STALWART_PID" 2>/dev/null; then
        wait "$STALWART_PID"
        exit $?
    fi
    sleep 1
done

echo "mailstack: bootstrap complete; restarting Stalwart normally"

stop_stalwart

unset STALWART_RECOVERY_ADMIN

exec "$STALWART_BIN" --config "$STALWART_CONFIG"
