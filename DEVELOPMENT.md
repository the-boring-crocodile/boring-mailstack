# Development

Everything runs on Docker with Compose; rootless Docker works (set
`DOCKER_HOST`, e.g. `unix:///run/user/$(id -u)/docker.sock`). Besides Docker
the scripts need `python3` (with PyYAML and pyflakes for the unit tests;
Debian/Ubuntu: `python3-yaml`, `python3-pyflakes`), `git`, `curl`, `openssl`
and `bc`. No Rust or PHP toolchain on the host: images build their own.

## Test tiers

| Command | What it proves |
|---|---|
| `tests/unit/run.sh` | Python unittest (bridge, getmail tools, provenance, resieve-watch, accounts and config tools) and pyflakes, the cloud-files plugin (PHP, in the Roundcube image) and resieve (`cargo test` in a container); also on GitHub at every push (`.github/workflows/unit-tests.yml`) |
| `tests/graceful_stop/run.sh` | bridge and provenance stop cleanly on SIGTERM, a webhook in flight is still recorded |
| `tests/demo/run.sh` | **acceptance:** the whole demo from nothing back to nothing — first import with provenance, round trip through relay and provider, mail to oneself, webmail with Filters, Contacts, Calendar and cloud files, inbound paths (provider Junk through the filter, provider moves and labels, filter changes, the re-sort chute, "not spam"), a provider with labels like Gmail (label, spam, not spam, trash, restore; handed to the bridge directly), HTML mail in dark mode, a vacation reply from the real address, browser checks (`BROWSER=0` skips them), no Internet from the mail network |
| `tests/first-install/run.sh` | DEPLOY.md's first installation, step by step (without sudo, on 127.0.0.1): artifact check, `tools/setup`, placeholder refused, deploy, webmail and login, uninstall |
| `tests/deploy/run.sh` | release artifacts and `tools/deploy`: first install, upgrade, refusals (accounts, extra files, open etc/ or accounts.yaml, older data generation, a broken or misplaced compose override), rollback, plain `docker compose` in the home, upgrade from an rc.8 home |
| `tests/trial/run.sh` | a release installed against the demo provider, checked and uninstalled, twice: nothing left behind |

Run the acceptance and deploy tests on the commit to be released (DEPLOY.md,
"Building a release"). Each test uses its own Compose project, so a demo someone is
reading is not touched; `KEEP=1` leaves the acceptance demo running for a
look (tear it down with `DEMO_PROJECT=boring-mailstack-acceptance tools/demo
--dir DIR down --yes`).

Run one heavy job at a time: a parallel Rust build beside two suites once
exhausted a rootless daemon's per-user process limit.

## Where things are

- `bridge/`, `getmail/`, `init/`, `mail-provenance/`, `prepare/`, `relay/`,
  `resieve/`, `stalwart/`, `roundcube/`: the services and their images.
- `compose.yaml`: the production stack; `demo/compose.demo.yaml` overlays
  the simulated provider and Pond Cloud.
- `tools/`: `demo`, `make-release`, `deploy`, `uninstall`, `resieve` and the
  configuration helpers.
- `stack.env`: values several components share (junk port, message size
  limit, bridge port); compose hands it to the services that need them.
- `roundcube/README.md`: Roundcube image, pinned Composer lock, patches.
- `demo/README.md`: the demo; `demo/story/BIBLE.md`: its story (spoilers).
- `DECISIONS.md`: why things are the way they are; `CHANGELOG.md`: what
  changed in each release.
- `tests/resieve/README.md`: benchmarking resieve on a real mailbox.

## Changing dependencies

Images are pinned by digest; Roundcube's PHP packages by
`roundcube/composer.lock` (see `roundcube/README.md`); Kolab's plugins by
commit; patches in `roundcube/patches/` are applied exactly, so upstream
drift fails the build instead of dropping a patch.
