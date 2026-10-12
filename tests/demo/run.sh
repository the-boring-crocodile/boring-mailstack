#!/bin/bash
# Acceptance test: the full demo, from nothing, and back to nothing.
#
#   tests/demo/run.sh
#
#   1. tools/demo up in a fresh directory (story check, seeding, first import)
#   2. verify_import.py until the first import is complete: every story mail
#      in exactly its owner's folder, no duplicates, provenance for every
#      mail imported outside the Inbox
#   3. roundtrip.py: send and receive through relay and provider; webmail
#      login, Filters (ManageSieve) and Contacts settings; a human
#      move recorded by provenance; Contacts, Calendar and cloud files
#      from the demo's Pond Cloud; no Internet from the mail network
#   3b. inbound.py: provider Junk through the filter, provider moves and
#      labels, filter changes, the re-sort chute, "not spam"
#   3b2. labels.py: a provider with labels like Gmail
#   3c. vacation.py: a vacation reply from the real address
#   4. browser checks (tests/browser; BROWSER=0 skips them): Kolab's
#      invitation box with Roundav; accepting a fresh invitation with a
#      login that differs from the Nextcloud user, reply copied to Sent;
#      the Sent-copy preference saved and reloaded; HTML mail in dark mode
#   5. tools/demo down (also on failure, unless KEEP=1)
#
# Needs Docker with Compose (DOCKER_HOST honoured), python3, openssl.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
DIR=$(mktemp -d -u -p "${DEMO_TEST_TMP:-$HOME}" demo-acceptance.XXXXXX)
# A separate Compose project, so a demo someone is reading stays untouched.
export DEMO_PROJECT=boring-mailstack-acceptance
NET=${DEMO_PROJECT}_mail-internal
# Roundcube and the demo cloud are on their own network (with Stalwart).
WEB=${DEMO_PROJECT}_webmail
STATUS=1

cleanup() {
    if [ "${KEEP:-0}" = 1 ]; then
        echo "KEEP=1: demo left running in $DIR"
    else
        "$ROOT/tools/demo" --dir "$DIR" down --yes >/dev/null 2>&1 || echo "WARNING: teardown failed; inspect $DIR"
    fi
}
trap cleanup EXIT

in_demo() {
    docker run --rm --network "$NET" --network "$WEB" \
        -v "$ROOT/demo:/demo:ro" -v "$ROOT/tests/demo:/t:ro" \
        -v "$DIR/seed-accounts.json:/a.json:ro" -v "$DIR/data/mail-provenance:/prov:ro" \
        -v "$DIR/accounts.yaml:/accounts.yaml:ro" -v "$DIR/provider/ca.crt:/provider-ca.crt:ro" \
        -e DEMO_ACCOUNTS=/a.json -e PROVENANCE_DB=/prov/provenance.sqlite \
        -e DEMO_ACCOUNTS_YAML=/accounts.yaml -e DEMO_CA_FILE=/provider-ca.crt \
        --entrypoint python3 "boring-mailstack-init:${DEMO_RELEASE:-demo}" "$@"
}

echo "== 1. demo up ($DIR)"
"$ROOT/tools/demo" --dir "$DIR" up --port "${DEMO_TEST_PORT:-18740}" >/dev/null || exit 1

echo "== 2. first import"
for i in $(seq 1 60); do
    if out=$(in_demo /t/verify_import.py 2>&1); then
        echo "$out"; break
    fi
    [ "$i" = 60 ] && { echo "$out"; echo "FAIL first import incomplete after 10 minutes"; exit 1; }
    sleep 10
done

echo "== 3. live checks"
in_demo /t/roundtrip.py && STATUS=0

echo "== 3b. inbound paths"
in_demo /t/inbound.py || STATUS=1

echo "== 3b2. a provider with labels (Gmail)"
in_demo /t/labels.py || STATUS=1

echo "== 3c. mail Stalwart writes itself"
in_demo /t/vacation.py || STATUS=1

if [ "${BROWSER:-1}" = 1 ]; then
    echo "== 4. browser checks"
    docker build -q -t boring-mailstack-browser "$ROOT/tests/browser" >/dev/null || { echo "FAIL browser image"; STATUS=1; }
    mkdir -p "$DIR/browser"
    browser() {
        docker run --rm --network "$WEB" -v "$ROOT/tests/browser:/t:ro" \
            -v "$DIR/seed-accounts.json:/a.json:ro" -v "$DIR/browser:/out" \
            --entrypoint python3 boring-mailstack-browser "$@"
    }
    check() {   # check NAME cmd...
        local name=$1; shift
        if out=$("$@" 2>&1); then echo "PASS $name"; else echo "$out" | tail -5; echo "FAIL $name"; STATUS=1; fi
    }
    check "invitation box with Roundav" browser /t/ics_invitation.py otter 1 "Management/Calendar (not attended)" /out/invitation.jpg
    if uid=$(browser /t/inject_invite.py otter); then
        check "accept with login otter@pond.test, reply in Sent" \
            browser /t/ics_accept.py otter otter@pond.test "$uid" INBOX /out/accept.jpg reply
    else
        echo "FAIL injecting an invitation"; STATUS=1
    fi
    check "Sent-copy preference off" browser /t/itip_save_sent_pref.py otter off /out/pref-off.jpg
    check "Sent-copy preference on" browser /t/itip_save_sent_pref.py otter on /out/pref-on.jpg
    check "HTML mail in dark mode (darkened, designed, invert, light)" browser /t/darkmail.py tim /out
fi

[ "$STATUS" = 0 ] && echo "== ACCEPTANCE PASSED" || echo "== ACCEPTANCE FAILED"
exit "$STATUS"
