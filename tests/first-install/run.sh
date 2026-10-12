#!/bin/bash
# First installation as DEPLOY.md describes it, step by step, from a release
# artifact of HEAD into an empty home:
#
#   1  check the artifact (sha256sum -c), unpack into a fresh directory
#   2  tools/setup HOME --mail-domain ... --bind ...: HOME, etc/,
#      accounts.yaml and folders.yaml private, secrets generated; a second
#      setup is refused
#   3  deploy refuses while accounts.yaml still says CHANGE-ME
#   4  fill in the account (here: a provider that does not exist), deploy
#   5  webmail answers; the address logs in to IMAP with its password;
#      the admin page takes admin / STALWART_ADMIN_PASSWORD
#   6  in HOME, plain `docker compose down` and `up -d` stop and start it
#   7  uninstall --delete-home leaves nothing
#
# Separate Compose project; everything is removed at the end (KEEP=1 keeps it).
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d -p "${FIRST_INSTALL_TMP:-$HOME}" first-install.XXXXXX)
H=$T/home
export MAILSTACK_PROJECT=boring-mailstack-firstinstall
PORT=${FIRST_INSTALL_PORT:-18820}
FAILED=0
ok()  { echo "PASS $*"; }
bad() { echo "FAIL $*"; FAILED=1; }
quiet() { grep -v -E '^ *(Container|Network|Volume) '; }

cleanup() {
    if [ "${KEEP:-0}" = 1 ]; then echo "KEEP=1: left in $T"; return; fi
    if [ -f "$H/release/VERSION" ]; then
        (cd "$H" && docker compose down -v --remove-orphans >/dev/null 2>&1)
        [ -d "$H/data" ] && docker run --rm -v "$H/data:/data" --entrypoint sh "boring-mailstack-init:vfirst.1" \
            -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null; true' >/dev/null 2>&1
    fi
    rm -rf "$T"
}
trap cleanup EXIT

echo "== 1. artifact"
git clone -q "$ROOT" "$T/repo" && cd "$T/repo" || exit 1
git -c user.name=t -c user.email=t@example.test tag -a vfirst.1 -m test
tools/make-release vfirst.1 --out "$T/dist" | head -1
cd "$T/dist" && sha256sum -c boring-mailstack-vfirst.1.tar.gz.sha256 >/dev/null \
    && ok "artifact checksum" || bad "artifact checksum"
U=$(mktemp -d -p "$T" unpack.XXXXXX)
tar --no-same-owner -xzf "$T/dist/boring-mailstack-vfirst.1.tar.gz" -C "$U"
R=$U/boring-mailstack-vfirst.1
cd /

echo "== 2. setup"
"$R/tools/setup" "$H" --mail-domain example.test --bind 127.0.0.1 \
    --webmail-port "$PORT" --admin-port $((PORT + 1)) | head -1
modes=$(cd "$H" && find . -not -path './data/*' -printf '%m %P\n' | LC_ALL=C sort | tr '\n' ';')
want="600 accounts.yaml;600 etc/.env;600 etc/bridge.env;600 etc/roundcube/config.inc.php;600 folders.yaml;700 data;700 etc;700 etc/roundcube;755 ;"
[ "$modes" = "$want" ] && ok "secrets private, home 0755: $modes" || bad "home modes: $modes"
grep -q 'address: alice@example.test' "$H/accounts.yaml" && ok "example account on the mail domain" || bad "accounts.yaml"
out=$("$R/tools/setup" "$H" --mail-domain example.test --bind 127.0.0.1 2>&1)
if [ $? != 0 ] && echo "$out" | grep -q "exists"; then
    ok "second setup refused"; else bad "second setup"; fi
[ -z "$(find "$R" -name __pycache__)" ] && ok "release tree unchanged by setup" || bad "setup left bytecode in the release"

echo "== 3. deploy refuses the example as it is"
out=$("$R/tools/deploy" "$H" 2>&1)
if echo "$out" | grep -q "FAILED at step 3 check" && echo "$out" | grep -q "placeholder" && [ ! -e "$H/release" ]; then
    ok "CHANGE-ME refused; nothing installed"; else bad "placeholder"; echo "$out" | tail -3; fi

echo "== 4. fill in the account, deploy"
PW=first-install-$(date +%s%N)
sed -i "s/CHANGE-ME/$PW/; s/CHANGE-ME/$PW/; s/imap.example.org/imap.provider.invalid/; s/smtp.example.org/smtp.provider.invalid/" "$H/accounts.yaml"
if "$R/tools/deploy" "$H" 2>&1 | quiet; [ "${PIPESTATUS[0]}" = 0 ] && [ "$(cat "$H/release/VERSION")" = vfirst.1 ]; then
    ok "first deploy"; else bad "first deploy"; fi

echo "== 5. webmail and login"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")
[ "$code" = 200 ] && ok "webmail answers on 127.0.0.1:$PORT" || bad "webmail HTTP $code"
login=$(docker run --rm --network "${MAILSTACK_PROJECT}_mail-internal" -e PW="$PW" --entrypoint python3 \
    boring-mailstack-init:vfirst.1 -c "
import imaplib, os, ssl
c = imaplib.IMAP4_SSL('stalwart.mailstack.local', 993, ssl_context=ssl._create_unverified_context())
print(c.login('alice@example.test', os.environ['PW'])[0])" 2>&1)
[ "$login" = OK ] && ok "alice@example.test logs in" || bad "login: $login"
ADMIN_PW=$(sed -n 's/^STALWART_ADMIN_PASSWORD=//p' "$H/etc/.env")
code=$(curl -s -o /dev/null -w '%{http_code}' -u "admin:$ADMIN_PW" "http://127.0.0.1:$((PORT + 1))/jmap/session")
[ "$code" = 200 ] && ok "admin logs in on the admin port" || bad "admin login HTTP $code"
code=$(curl -s -o /dev/null -w '%{http_code}' -u "admin:wrong-$ADMIN_PW" "http://127.0.0.1:$((PORT + 1))/jmap/session")
[ "$code" = 401 ] && ok "admin with a wrong password refused" || bad "wrong admin password: HTTP $code"
domains=$(docker run --rm --network "${MAILSTACK_PROJECT}_mail-internal" -e STALWART_URL=http://stalwart:8080 -e STALWART_USER=admin -e STALWART_PASSWORD="$ADMIN_PW" \
    boring-mailstack-init:vfirst.1 stalwart-cli query Domain 2>&1)
grep -q example.test <<<"$domains" && ok "admin has admin rights (lists domains)" || bad "admin query: $domains"

echo "== 6. plain docker compose in HOME"
count() { docker ps --filter "label=com.docker.compose.project=$MAILSTACK_PROJECT" -q | wc -l; }
n0=$(count)
(cd "$H" && docker compose down 2>&1 | quiet)
n1=$(count)
(cd "$H" && docker compose up -d 2>&1 | quiet)
for i in $(seq 60); do [ "$(count)" = "$n0" ] && break; sleep 3; done
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")
if [ "$n1" = 0 ] && [ "$(count)" = "$n0" ] && [ "$code" = 200 ]; then
    ok "down: $n0 -> 0 running; up -d: $n0 again, webmail answers"
else bad "plain compose: $n0 / $n1 / $(count), webmail $code"; fi

echo "== 7. uninstall"
if "$H/release/tools/uninstall" "$H" --delete-home --images 2>&1 | quiet | tail -8; [ "${PIPESTATUS[0]}" = 0 ] && [ ! -e "$H" ]; then
    ok "uninstall: home gone, nothing left"; else bad "uninstall"; fi

[ "$FAILED" = 0 ] && echo "== FIRST INSTALL PASSED" || echo "== FIRST INSTALL FAILED"
exit "$FAILED"
