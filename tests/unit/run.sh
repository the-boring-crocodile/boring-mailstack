#!/bin/bash
# Fast tier: unit tests without a running stack.
#
#   tests/unit/run.sh
#
#   python   python3 -m unittest and pyflakes (host Python 3.10+ with PyYAML, pyflakes)
#   cloudfiles  php in the pinned Roundcube base image, no network
#   resieve  cargo test in resieve/Dockerfile's pinned Rust image, two build jobs and a pids limit
#            (a rootless daemon under a per-user pids limit can fall over
#            when a parallel Rust build spawns too many threads; observed
#            2026-10-07). Cargo's registry and target dir live in named
#            volumes (resieve-test-cargo, resieve-test-target).
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATUS=0

echo "== python"
# The stack's shared fixed values, as compose gives them to the services.
(set -a; . "$ROOT/stack.env"; python3 -m unittest discover -s "$ROOT/tests/unit") || STATUS=1
# Names used but never defined, imports never used: what a run of the
# tools would find only on the path that hits them.
(cd "$ROOT" && python3 -m pyflakes tools/deploy tools/uninstall tools/setup tools/demo tools/*.py \
    bridge/*.py getmail/*.py mail-provenance/*.py resieve/watch.py demo/seed/*.py demo/story/*.py) || STATUS=1

echo "== resieve"
RUST_IMAGE=$(sed -n 's/^FROM \(rust:[^ ]*\) AS builder$/\1/p' "$ROOT/resieve/Dockerfile")
[ -n "$RUST_IMAGE" ] || { echo "no rust image in resieve/Dockerfile" >&2; exit 2; }
docker run --rm --pids-limit 200 --network bridge \
    -v "$ROOT/resieve:/src:ro" -v resieve-test-target:/target -v resieve-test-cargo:/usr/local/cargo/registry \
    -e CARGO_TARGET_DIR=/target -e CARGO_BUILD_JOBS=2 -e RUST_TEST_THREADS=2 -w /src \
    "$RUST_IMAGE" cargo test --locked --quiet || STATUS=1

echo "== cloudfiles (PHP, in the pinned Roundcube base image, no network)"
RC_IMAGE=$(sed -n 's/^ARG ROUNDCUBE_IMAGE=\(.*\)$/\1/p' "$ROOT/roundcube/Dockerfile")
docker run --rm --network none -v "$ROOT:/src:ro" --entrypoint php "$RC_IMAGE" \
    /src/tests/unit/test_cloudfiles.php || STATUS=1

[ "$STATUS" = 0 ] && echo "== UNIT TESTS PASSED" || echo "== UNIT TESTS FAILED"
exit "$STATUS"
