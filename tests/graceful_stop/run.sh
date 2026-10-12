#!/bin/bash
# Graceful-stop test for mail bridge and mail-provenance (no mail, no Stalwart).
#
#   tests/graceful_stop/run.sh [SOURCE_TREE] [LABEL]
#
# Builds both images from SOURCE_TREE (default: this checkout), then checks:
#   1. bridge:     `docker stop` returns well inside the timeout, exit 0
#   2. provenance: same
#   3. provenance: a webhook whose body is still arriving when SIGTERM comes
#                  is answered 200 and its row is in SQLite; then exit 0
# Exit status 0 only if every check passes. Needs a Docker daemon
# (DOCKER_HOST), python3 and bc on the host.
set -euo pipefail

SRC=$(cd "${1:-$(dirname "$0")/../..}" && pwd)
LABEL=${2:-working}
STOP_TIMEOUT=10
FAST=5   # seconds; a clean stop must return before this
P="graceful-stop-$LABEL"
# Bind-mount sources must be visible to the Docker daemon. A private /tmp
# (e.g. a sandboxed job runner) is not, and the daemon then silently mounts
# an empty directory instead (observed 2026-10-06). Hence $HOME by default.
T=$(mktemp -d -p "${GRACEFUL_STOP_TMP:-$HOME}" graceful-stop.XXXXXX)
FAILED=0

cleanup() {
    docker rm -f "$P-bridge" "$P-prov" "$P-prov2" >/dev/null 2>&1 || true
    rm -rf "$T"
}
trap cleanup EXIT

check() { # name result detail
    if [ "$2" = ok ]; then echo "PASS $1 ($3)"; else echo "FAIL $1 ($3)"; FAILED=1; fi
}

wait_log() { # container pattern
    for _ in $(seq 1 50); do
        docker logs "$1" 2>&1 | grep -q "$2" && return 0
        sleep 0.2
    done
    echo "ERROR: $1 never logged '$2'" >&2; docker logs "$1" >&2; return 1
}

timed_stop() { # container -> prints "seconds exitcode"
    local t0 t1
    t0=$(date +%s.%N)
    docker stop -t "$STOP_TIMEOUT" "$1" >/dev/null
    t1=$(date +%s.%N)
    printf '%.1f %s\n' "$(echo "$t1 - $t0" | bc)" "$(docker inspect -f '{{.State.ExitCode}}' "$1")"
}

echo '{}' > "$T/routes.json"
echo '[]' > "$T/accounts.json"
mkdir "$T/data"

docker build -q -t "$P-bridge:test" "$SRC/bridge" >/dev/null
docker build -q -t "$P-prov:test" "$SRC/mail-provenance" >/dev/null

# 1. bridge
docker run -d --name "$P-bridge" --env-file "$SRC/stack.env" \
    -e JMAP_SESSION=https://stalwart.invalid/jmap/session -e JMAP_USER=u -e JMAP_PASSWORD=p \
    -e PROVENANCE_URL=http://provenance.invalid \
    -v "$T/routes.json:/config/bridge-routes.json:ro" "$P-bridge:test" >/dev/null
wait_log "$P-bridge" "listening"
read -r secs code < <(timed_stop "$P-bridge")
[ "$code" = 0 ] && [ "$(echo "$secs < $FAST" | bc)" = 1 ] && r=ok || r=no
check "bridge stop" "$r" "${secs}s exit $code"

# 2. provenance, plain stop
docker run -d --name "$P-prov" -e RESIEVE_WATCH_URL=http://resieve-watch.invalid/resort \
    -v "$T/accounts.json:/config/stalwart-accounts.json:ro" \
    -v "$T/data:/data" "$P-prov:test" >/dev/null
wait_log "$P-prov" "bootstrap complete"
read -r secs code < <(timed_stop "$P-prov")
[ "$code" = 0 ] && [ "$(echo "$secs < $FAST" | bc)" = 1 ] && r=ok || r=no
check "provenance stop" "$r" "${secs}s exit $code"

# 3. provenance, SIGTERM while a webhook body is still arriving
docker run -d --name "$P-prov2" -p 127.0.0.1::8080 -e RESIEVE_WATCH_URL=http://resieve-watch.invalid/resort \
    -v "$T/accounts.json:/config/stalwart-accounts.json:ro" \
    -v "$T/data:/data" "$P-prov:test" >/dev/null
wait_log "$P-prov2" "bootstrap complete"
PORT=$(docker port "$P-prov2" 8080/tcp | head -1 | sed 's/.*://')
reply=$(python3 - "$PORT" "$P-prov2" <<'EOF'
import json, socket, subprocess, sys, time
port, container = int(sys.argv[1]), sys.argv[2]
body = json.dumps({"account": "gs-account", "email_id": "gs-email", "reason": "graceful-stop-test"}).encode()
s = socket.create_connection(("127.0.0.1", port), timeout=15)
s.sendall(b"POST /protect HTTP/1.1\r\nHost: t\r\nContent-Type: application/json\r\n"
          b"Content-Length: %d\r\n\r\n" % len(body) + body[:10])
time.sleep(0.5)                      # handler is now blocked reading the body
subprocess.run(["docker", "kill", "-s", "TERM", container], check=True, capture_output=True)
time.sleep(1.0)                      # shutdown is in progress
try:
    s.sendall(body[10:])
    print(s.recv(200).split(b"\r\n", 1)[0].decode() or "no reply")
except OSError as exc:
    print(f"connection error: {exc}")
EOF
)
# A process that ignores SIGTERM keeps running; do not wait forever for it.
if timeout 15 docker wait "$P-prov2" >/dev/null; then
    code=$(docker inspect -f '{{.State.ExitCode}}' "$P-prov2")
else
    code="none, still running 15s after SIGTERM"
fi
row=$(python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute(\"select count(*) from protected_email where email_id='gs-email'\").fetchone()[0])" "$T/data/provenance.sqlite")
[ "$reply" = "HTTP/1.0 200 OK" ] && [ "$row" = 1 ] && [ "$code" = 0 ] && r=ok || r=no
check "provenance in-flight webhook" "$r" "reply '$reply', rows $row, exit $code"

exit "$FAILED"
