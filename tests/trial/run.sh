#!/bin/bash
# Trial installation from a release of HEAD against the demo provider,
# twice (install, check, uninstall; again): install and removal leave
# nothing behind that a fresh install trips over.
#
#   tests/trial/run.sh
#
# Uses a separate project and port; leaves nothing behind.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d -p "${TRIAL_TEST_TMP:-$HOME}" trial-test.XXXXXX)
export MAILSTACK_PROJECT=boring-mailstack-trialtest
H=$T/opt/docker/boring-mailstack
FAILED=0
step() { echo "== $*"; }
ok()   { echo "PASS $*"; }
bad()  { echo "FAIL $*"; FAILED=1; }
trap 'rm -rf "$T"' EXIT

git clone -q "$ROOT" "$T/repo" && cd "$T/repo" || exit 1
git -c user.name=t -c user.email=t@pond.test tag -a vtrial.1 -m test
tools/make-release vtrial.1 --out "$T/dist" | head -1
tar xzf "$T/dist/boring-mailstack-vtrial.1.tar.gz" -C "$T"
R=$T/boring-mailstack-vtrial.1
mkdir -p "$(dirname "$H")"

for round in 1 2; do
    step "round $round: prepare"
    "$R/tools/demo" --dir "$H" prepare --bind 127.0.0.1 --port "${TRIAL_TEST_PORT:-18800}" >/dev/null || { bad prepare; break; }
    step "round $round: deploy"
    "$R/tools/deploy" "$H" 2>&1 | grep -E '^\[|FAILED'
    [ "${PIPESTATUS[0]}" = 0 ] && ok "deploy" || { bad deploy; break; }
    step "round $round: check"
    "$R/tools/demo" --dir "$H" check 2>&1 | grep -E 'PASS|FAIL|CHECK'
    [ "${PIPESTATUS[0]}" = 0 ] && ok "check" || bad check
    step "round $round: uninstall"
    echo "not boring-mailstack's" > "$H/keep-me.txt"
    "$H/release/tools/uninstall" "$H" --delete-home --images 2>&1 | grep -v -E '^ *(Container|Network|Volume) '
    [ "${PIPESTATUS[0]}" = 0 ] && ok "uninstall, nothing left" || bad uninstall
    # --delete-home removes what deploy and setup made (uninstall's OURS);
    # the demo's other files and ours stay (and go here, by hand).
    if [ -f "$H/keep-me.txt" ] && ! ls -d "$H"/release* "$H/etc" "$H/data" "$H/DEPLOYED" "$H/PROJECT" \
            "$H/compose.yaml" "$H/compose.override.yaml" "$H/.env" "$H/accounts.yaml" "$H/folders.yaml" >/dev/null 2>&1; then
        ok "home: deploy's files gone, others kept"; else bad "home after uninstall: $(ls -A "$H" 2>&1 | tr '\n' ' ')"; fi
    rm -rf "$H"
done
[ "$FAILED" = 0 ] && echo "== TRIAL REHEARSAL PASSED" || echo "== TRIAL REHEARSAL FAILED"
exit "$FAILED"
