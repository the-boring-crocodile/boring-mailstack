#!/bin/bash
# Deploy test: first install, upgrade, a refused upgrade, rollback.
#
#   tests/deploy/run.sh            # tests the committed HEAD
#
# In a throwaway clone of HEAD it tags vtest.1 and vtest.2, builds both
# release artifacts with tools/make-release, prepares a home (etc/ as
# tools/demo would write it) and then, with each release's own tools/deploy:
#
#   A  first install of vtest.1
#   B  upgrade to vtest.2 (an old etc/deploy-backup hook is ignored; a root:root 0646
#      Roundcube database, as older installations had it, must be corrected;
#      v2's own plugin list without carddav must not switch off Contacts,
#      and Filters must answer - deploy's smoke step checks both)
#   C  an upgrade refused in preflight (invalid accounts.yaml):
#      nothing may change, vtest.2 keeps running
#   D  rollback: release.previous/tools/deploy -> vtest.1 again
#   E  redeploy of the installed release (config change): services restarted
#   F  the installed version again from its artifact: no switch
#   G  a release that never passed smoke is not kept in release.previous/
#   H  HOME/PROJECT: a second home with the same project, and another
#      MAILSTACK_PROJECT for this home, are refused
#   I  an unpacked release with a file not in its manifest (and one with a
#      symlink) is refused before anything changes
#   J  an etc/ open to other users is refused before anything changes
#   K  DATA_GENERATION: an install from before generation 2 must go through
#      v2026.10.14-rc.6; an older generation over a newer one is refused
#   L  the installed version again, but built from other files: refused
#   M  plain Compose in HOME: `docker compose down` stops everything,
#      `docker compose up -d` starts it again and init applies accounts.yaml
#   O  compose overrides: a broken HOME/compose.override.yaml and an old
#      etc/compose.override.yaml are refused before anything changes
#   N  a home of v2026.10.14-rc.8 (accounts.yaml and folders.yaml in etc/):
#      the upgrade moves them up (links in etc/), writes compose.yaml and
#      .env; rc.8 again with the printed rollback command; forward again
# Also: the artifact's entries are owned by root:root.
#
# Separate Compose project; everything is removed at the end (KEEP=1 keeps it).
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d -p "${DEPLOY_TEST_TMP:-$HOME}" deploy-test.XXXXXX)
H=$T/home
export MAILSTACK_PROJECT=boring-mailstack-deploytest
PORT=${DEPLOY_TEST_PORT:-18700}
FAILED=0
G="git -c user.name=test -c user.email=test@pond.test"

ok()   { echo "PASS $*"; }
bad()  { echo "FAIL $*"; FAILED=1; }
quiet() { grep -v -E '^ *(Container|Network|Volume) '; }

cleanup() {
    if [ "${KEEP:-0}" = 1 ]; then echo "KEEP=1: left in $T"; return; fi
    for d in "$H" "$T/home3"; do
        [ -f "$d/compose.yaml" ] && (cd "$d" && env -u MAILSTACK_PROJECT docker compose down -v --remove-orphans >/dev/null 2>&1)
        [ -f "$d/release/VERSION" ] && MAILSTACK_HOME=$d MAILSTACK_ETC=$d/etc MAILSTACK_DATA=$d/data \
            MAILSTACK_RELEASE=$(cat "$d/release/VERSION") docker compose -p "$(cat "$d/PROJECT" 2>/dev/null || echo x)" \
            --project-directory "$d/release" -f "$d/release/compose.yaml" --env-file "$d/etc/.env" \
            down -v --remove-orphans >/dev/null 2>&1
    done
    for d in "$H" "$T/home2" "$T/home3"; do
        [ -d "$d/data" ] && docker run --rm -v "$d/data:/data" --entrypoint sh "boring-mailstack-init:vtest.1" \
            -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null; true' >/dev/null 2>&1
    done
    rm -rf "$T"
    # The test releases' images (vtest.*); the build cache stays.
    docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^boring-mailstack-[a-z-]+:vtest\.' \
        | xargs -r docker rmi >/dev/null 2>&1
}
trap cleanup EXIT

echo "== releases"
git clone -q "$ROOT" "$T/repo" && cd "$T/repo" || exit 1
$G tag -a vtest.1 -m test
echo "second test release" > RELEASE_NOTE_TEST
git add RELEASE_NOTE_TEST && $G commit -q -m "test change" && $G tag -a vtest.2 -m test
for v in vtest.1 vtest.2; do
    tools/make-release $v --out "$T/dist" | head -1
    tar xzf "$T/dist/boring-mailstack-$v.tar.gz" -C "$T/dist"
done
R1=$T/dist/boring-mailstack-vtest.1
R2=$T/dist/boring-mailstack-vtest.2
owners=$(tar tvzf "$T/dist/boring-mailstack-vtest.1.tar.gz" | awk '{print $2}' | sort -u | tr '\n' ' ')
[ "$owners" = "root/root " ] && ok "artifact entries owned by root:root" || bad "artifact owners: $owners"

echo "== home"
python3 -c "
import runpy; from pathlib import Path
m = runpy.run_path('$ROOT/tools/demo'); m['create'](Path('$H'), '127.0.0.1', $PORT, 'Europe/London')" || exit 1
# A hook from older releases: deploy no longer runs it (backups are the host's).
printf '#!/bin/sh\necho "$(date -Is) $MAILSTACK_PROJECT" >> "$MAILSTACK_HOME/backup-hook.log"\n' > "$H/etc/deploy-backup"
chmod 0700 "$H/etc/deploy-backup"

version() { cat "$H/$1/VERSION" 2>/dev/null || echo none; }

echo "== A: first install vtest.1"
if "$R1/tools/deploy" "$H" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ] && [ "$(version release)" = vtest.1 ]; then
    ok "first install"; else bad "first install"; fi

echo "== B: upgrade to vtest.2 (database made root:root 0646 and an older plugin list first, as older installations had)"
echo "\$config['plugins'] = ['managesieve', 'archive', 'zipdownload'];" >> "$H/etc/roundcube/config.inc.php"
docker run --rm -v "$H/data/roundcube-db:/d" --entrypoint sh boring-mailstack-init:vtest.1 \
    -c 'chown 0:0 /d/sqlite.db && chmod 0646 /d/sqlite.db'
if "$R2/tools/deploy" "$H" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ] \
   && [ "$(version release)" = vtest.2 ] && [ "$(version release.previous)" = vtest.1 ] \
   && [ ! -e "$H/backup-hook.log" ]; then
    ok "upgrade (old backup hook left alone)"; else bad "upgrade"; fi

echo "== C: refused upgrade (invalid accounts.yaml)"
cp -p "$H/accounts.yaml" "$T/accounts.good"
python3 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d['accounts']['croc']['colour']='green'; json.dump(d, open(p,'w'))" "$H/accounts.yaml"
before=$(docker ps -q --filter "label=com.docker.compose.project=$MAILSTACK_PROJECT" | sort | tr '\n' ' ')
out=$("$R1/tools/deploy" "$H" 2>&1)
after=$(docker ps -q --filter "label=com.docker.compose.project=$MAILSTACK_PROJECT" | sort | tr '\n' ' ')
if echo "$out" | grep -q "FAILED at step 3 check" && echo "$out" | grep -q "Nothing was changed" \
   && [ "$(version release)" = vtest.2 ] && [ "$before" = "$after" ]; then
    ok "refused in preflight; vtest.2 untouched and still running"; else bad "refused upgrade"; echo "$out" | tail -5; fi
cp -p "$T/accounts.good" "$H/accounts.yaml"
cp -p "$H/folders.yaml" "$T/folders.good"
printf 'version: 1\nproviders:\n  "*":\n    Spam: spam\n' > "$H/folders.yaml"
out=$("$R1/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 3 check" && echo "$out" | grep -q "unknown role 'spam'" \
   && [ "$(version release)" = vtest.2 ]; then
    ok "folders.yaml with an unknown role refused in preflight"; else bad "folders.yaml refusal"; echo "$out" | tail -5; fi
rm "$H/folders.yaml"
out=$("$R1/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "folders.yaml is missing" && echo "$out" | grep -q "folders.example.yaml" \
   && [ "$(version release)" = vtest.2 ]; then
    ok "missing folders.yaml refused, with the copy command"; else bad "missing folders.yaml"; echo "$out" | tail -5; fi
cp -p "$T/folders.good" "$H/folders.yaml"

echo "== D: rollback to vtest.1"
if "$H/release.previous/tools/deploy" "$H" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ] \
   && [ "$(version release)" = vtest.1 ] && [ "$(version release.previous)" = vtest.2 ]; then
    ok "rollback"; else bad "rollback"; fi

started() { docker inspect -f '{{.State.StartedAt}}' "$MAILSTACK_PROJECT-mail-bridge-1" 2>/dev/null; }

echo "== E: configuration-only redeploy restarts the services"
t0=$(started)
if "$H/release/tools/deploy" "$H" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ] \
   && [ "$(version release)" = vtest.1 ] && [ "$(version release.previous)" = vtest.2 ] && [ "$(started)" != "$t0" ]; then
    ok "redeploy of the installed release: services restarted, releases unchanged"; else bad "configuration redeploy"; fi

echo "== F: the installed version again from its unpacked artifact"
if "$R1/tools/deploy" "$H" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ] \
   && [ "$(version release)" = vtest.1 ] && [ "$(version release.previous)" = vtest.2 ]; then
    ok "same version: no switch, release.previous/ kept"; else bad "same-version redeploy"; fi

echo "== G: a release that never passed smoke is not kept for rollback"
"$R2/tools/deploy" "$H" 2>&1 | quiet
sed -i '$d' "$H/DEPLOYED"          # as if vtest.2 had failed its smoke test
if "$R1/tools/deploy" "$H" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ] \
   && [ "$(version release)" = vtest.1 ] && [ "$(version release.previous)" = vtest.1 ]; then
    ok "failed vtest.2 dropped; release.previous/ is the last good one"; else bad "failed release kept"; fi

echo "== H: the home owns its project"
H2=$T/home2
python3 -c "
import runpy; from pathlib import Path
m = runpy.run_path('$ROOT/tools/demo'); m['create'](Path('$H2'), '127.0.0.1', $((PORT + 10)), 'Europe/London')" >/dev/null
before=$(docker ps -q --filter "label=com.docker.compose.project=$MAILSTACK_PROJECT" | sort | tr '\n' ' ')
out=$("$R1/tools/deploy" "$H2" 2>&1)
after=$(docker ps -q --filter "label=com.docker.compose.project=$MAILSTACK_PROJECT" | sort | tr '\n' ' ')
if echo "$out" | grep -q "belongs to another installation" && [ ! -e "$H2/release" ] && [ "$before" = "$after" ]; then
    ok "second home with the same project refused; first untouched"; else bad "foreign project"; echo "$out" | tail -3; fi
out=$(MAILSTACK_PROJECT=somethingelse "$H/release/tools/deploy" "$H" 2>&1)
if [ "$(cat "$H/PROJECT")" = "$MAILSTACK_PROJECT" ] && echo "$out" | grep -q "belongs to project $MAILSTACK_PROJECT"; then
    ok "HOME/PROJECT recorded; another MAILSTACK_PROJECT refused"; else bad "project record"; echo "$out" | tail -3; fi

echo "== I: files beyond the manifest are refused"
for kind in file symlink; do
    X=$T/dist/extra-$kind; rm -rf "$X"; cp -a "$R2" "$X"
    if [ $kind = file ]; then echo "services: {}" > "$X/compose.override.yaml"
    else ln -s /etc/hostname "$X/roundcube/linked"; fi
    out=$("$X/tools/deploy" "$H" 2>&1)
    if echo "$out" | grep -q "FAILED at step 1 verify" && echo "$out" | grep -q "not in the manifest" \
       && [ "$(version release)" = vtest.1 ]; then
        ok "extra $kind refused; nothing changed"; else bad "extra $kind"; echo "$out" | tail -3; fi
done

echo "== J: etc/ must be private"
chmod o+r "$H/etc/roundcube/config.inc.php"
out=$("$R2/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 3 check" && echo "$out" | grep -q "etc/, accounts.yaml and folders.yaml must be private" \
   && echo "$out" | grep -q "chmod -R o-rwx" && [ "$(version release)" = vtest.1 ]; then
    ok "open etc/ refused with the fix; nothing changed"; else bad "open etc/"; echo "$out" | tail -3; fi
chmod o-r "$H/etc/roundcube/config.inc.php"
chmod o+r "$H/accounts.yaml"
out=$("$R2/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "must be private" && echo "$out" | grep -q "$H/accounts.yaml" && [ "$(version release)" = vtest.1 ]; then
    ok "open accounts.yaml refused; nothing changed"; else bad "open accounts.yaml"; echo "$out" | tail -3; fi
chmod o-r "$H/accounts.yaml"

echo "== K: data generations"
echo 1 > "$H/release/DATA_GENERATION"          # installed vtest.1 as if from before the renaming
out=$("$R2/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 1 verify" && echo "$out" | grep -q "deploy v2026.10.14-rc.6 first" \
   && [ "$(version release)" = vtest.1 ]; then
    ok "too old to upgrade directly: refused, via rc.6"; else bad "too-old upgrade"; echo "$out" | tail -4; fi
cp "$R1/DATA_GENERATION" "$H/release/DATA_GENERATION"
"$R2/tools/deploy" "$H" 2>&1 | quiet
echo 3 > "$H/release/DATA_GENERATION"          # installed vtest.2 as if newer than vtest.1
out=$("$R1/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 1 verify" && echo "$out" | grep -q "cannot read" \
   && [ "$(version release)" = vtest.2 ]; then
    ok "older data generation refused; nothing changed"; else bad "older generation"; echo "$out" | tail -3; fi
cp "$R2/DATA_GENERATION" "$H/release/DATA_GENERATION"

echo "== L: same version, other files"
(cd "$T/repo" && echo "changed" >> RELEASE_NOTE_TEST && git add RELEASE_NOTE_TEST \
    && $G commit -q -m "same version, other files" && $G tag -f -a vtest.2 -m test >/dev/null \
    && tools/make-release vtest.2 --out "$T/dist2" >/dev/null)
mkdir -p "$T/dist2/x" && tar xzf "$T/dist2/boring-mailstack-vtest.2.tar.gz" -C "$T/dist2/x"
out=$("$T/dist2/x/boring-mailstack-vtest.2/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 1 verify" && echo "$out" | grep -q "other files" \
   && [ "$(version release)" = vtest.2 ]; then
    ok "same version from other files refused"; else bad "same version, other files"; echo "$out" | tail -3; fi

echo "== O: compose overrides are checked before the switch"
printf 'services:\n  mail-bridge:\n    environment: [broken\n' > "$H/compose.override.yaml"
out=$("$R1/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 3 check" && echo "$out" | grep -q "Nothing was changed" \
   && [ "$(version release)" = vtest.2 ]; then
    ok "broken compose.override.yaml refused before the switch"; else bad "broken override"; echo "$out" | tail -4; fi
rm "$H/compose.override.yaml"
printf 'services: {}\n' > "$H/etc/compose.override.yaml"
out=$("$R1/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 3 check" && echo "$out" | grep -q "Compose's own place" \
   && [ "$(version release)" = vtest.2 ]; then
    ok "etc/compose.override.yaml refused with the move hint"; else bad "old override place"; echo "$out" | tail -4; fi
rm "$H/etc/compose.override.yaml"

running() { docker ps --filter "label=com.docker.compose.project=$1" --format '{{.Names}}' | grep -vc -- -init- ; }
init_exit() { docker inspect -f '{{.State.ExitCode}} {{.State.Status}}' "$1-init-1" 2>/dev/null; }

echo "== M: plain docker compose in HOME"
n0=$(running "$MAILSTACK_PROJECT")
grep -q "^name: $MAILSTACK_PROJECT\$" "$H/compose.yaml" && grep -q "^MAILSTACK_RELEASE=vtest.2\$" "$H/.env" \
    && ok "compose.yaml names the project; .env names the release" || bad "compose.yaml/.env"
(cd "$H" && env -u MAILSTACK_PROJECT docker compose down 2>&1 | quiet)
n1=$(running "$MAILSTACK_PROJECT")
python3 -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d['accounts']['croc']['resieve']={'enabled': False}; json.dump(d, open(p,'w'))" "$H/accounts.yaml"
croc_resieve() { python3 -c "import json,sys; print([a['resieve_enabled'] for a in json.load(open(sys.argv[1])) if a['id']=='croc'])" "$H/data/generated/stalwart-accounts.json" 2>/dev/null; }
(cd "$H" && env -u MAILSTACK_PROJECT docker compose up -d 2>&1 | quiet)
for i in $(seq 60); do [ "$(running "$MAILSTACK_PROJECT")" = "$n0" ] && [ "$(init_exit "$MAILSTACK_PROJECT")" = "0 exited" ] && break; sleep 3; done
if [ "$n1" = 0 ] && [ "$(running "$MAILSTACK_PROJECT")" = "$n0" ] && [ "$(init_exit "$MAILSTACK_PROJECT")" = "0 exited" ] \
   && [ "$(croc_resieve)" = "[False]" ]; then
    ok "down stops all ($n0 -> 0); up -d starts all again, init applied accounts.yaml"
else bad "plain compose: before $n0, after down $n1, after up $(running "$MAILSTACK_PROJECT"), init $(init_exit "$MAILSTACK_PROJECT")"; fi
cp -p "$T/accounts.good" "$H/accounts.yaml"
(cd "$H" && env -u MAILSTACK_PROJECT docker compose down 2>&1 | quiet)

echo "== N: upgrade from a v2026.10.14-rc.8 home (accounts.yaml and folders.yaml in etc/)"
H3=$T/home3
P3=boring-mailstack-deploytest-old
# Built from the rc.8 commit under a test tag, so no image named like the
# real release is created or replaced.
(cd "$T/repo" && $G tag -a vtest.rc8 -m test 'v2026.10.14-rc.8^{commit}' \
    && tools/make-release vtest.rc8 --out "$T/dist" >/dev/null) \
    && tar xzf "$T/dist/boring-mailstack-vtest.rc8.tar.gz" -C "$T/dist"
R8=$T/dist/boring-mailstack-vtest.rc8
python3 -c "
import runpy; from pathlib import Path
m = runpy.run_path('$ROOT/tools/demo'); m['create'](Path('$H3'), '127.0.0.1', $((PORT + 20)), 'Europe/London')" >/dev/null
mv "$H3/accounts.yaml" "$H3/folders.yaml" "$H3/etc/"
if MAILSTACK_PROJECT=$P3 "$R8/tools/deploy" "$H3" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ]; then
    ok "rc.8 installed (old layout)"; else bad "rc.8 install"; fi
out=$(MAILSTACK_PROJECT=$P3 "$R2/tools/deploy" "$H3" 2>&1)
echo "$out" | quiet | grep -E "moved|wrote|DEPLOYED|FAILED"
if echo "$out" | grep -q "DEPLOYED vtest.2" && [ -f "$H3/accounts.yaml" ] && [ ! -L "$H3/accounts.yaml" ] \
   && [ "$(readlink "$H3/etc/accounts.yaml")" = ../accounts.yaml ] && [ "$(readlink "$H3/etc/folders.yaml")" = ../folders.yaml ] \
   && grep -q "^name: $P3\$" "$H3/compose.yaml" && grep -q "^MAILSTACK_RELEASE=vtest.2\$" "$H3/.env"; then
    ok "upgrade moved accounts.yaml and folders.yaml up (links in etc/), wrote compose.yaml and .env"
else bad "migration"; echo "$out" | tail -5; fi
back=$(echo "$out" | sed -n 's/^ *sudo \(env MAILSTACK_HOME=[^ ]* [^ ]*\/tools\/deploy [^ ]*\)$/\1/p')
if [ -n "$back" ] && MAILSTACK_PROJECT=$P3 $back 2>&1 | quiet | grep -q "DEPLOYED vtest.rc8"; then
    ok "back to rc.8 with the printed command ($back)"; else bad "rollback to rc.8: '${back:-no command printed}'"; fi
out=$(MAILSTACK_PROJECT=$P3 "$R2/tools/deploy" "$H3" 2>&1)
if echo "$out" | grep -q "DEPLOYED vtest.2" && [ "$(cat "$H3/release/VERSION")" = vtest.2 ]; then
    ok "forward to vtest.2 again"; else bad "forward again"; echo "$out" | tail -5; fi
(cd "$H3" && env -u MAILSTACK_PROJECT docker compose down 2>&1 | quiet)
[ "$(running "$P3")" = 0 ] && ok "migrated home stops with docker compose down" || bad "migrated home still running"

echo "== DEPLOYED"
cat "$H/DEPLOYED"
[ "$(wc -l < "$H/DEPLOYED")" = 7 ] && ok "seven deployments recorded" || bad "DEPLOYED has $(wc -l < "$H/DEPLOYED") lines"

[ "$FAILED" = 0 ] && echo "== DEPLOY TEST PASSED" || echo "== DEPLOY TEST FAILED"
exit "$FAILED"
