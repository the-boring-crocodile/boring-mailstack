# Sourced by the shell tools of an installed release (stalwart-cli,
# resieve): where the home's parts are. The home's layout itself is
# DEPLOY.md, "The home".
#
# <home> is derived from where this file lives (<home>/release/tools/), e.g.
# /opt/docker/boring-mailstack.

MAILSTACK_RELEASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAILSTACK_HOME="$(dirname "$MAILSTACK_RELEASE_DIR")"
MAILSTACK_DATA="$MAILSTACK_HOME/data"

if [[ ! -f "$MAILSTACK_RELEASE_DIR/VERSION" ]]; then
    echo "ERROR: $MAILSTACK_RELEASE_DIR/VERSION missing: not an installed release" >&2
    exit 1
fi
MAILSTACK_RELEASE="$(< "$MAILSTACK_RELEASE_DIR/VERSION")"

# The home's Compose project (HOME/PROJECT, written by tools/deploy) and its
# internal network, as Compose names it.
if [[ ! -f "$MAILSTACK_HOME/PROJECT" ]]; then
    echo "ERROR: $MAILSTACK_HOME/PROJECT missing: deploy this release first" >&2
    exit 1
fi
MAILSTACK_PROJECT="$(< "$MAILSTACK_HOME/PROJECT")"
MAILSTACK_NETWORK="${MAILSTACK_PROJECT}_mail-internal"

# The stack as the operator runs it: docker compose in <home> (its .env says
# which release runs).
mailstack_compose() {
    (cd "$MAILSTACK_HOME" && env -u MAILSTACK_RELEASE -u MAILSTACK_HOME docker compose "$@")
}
