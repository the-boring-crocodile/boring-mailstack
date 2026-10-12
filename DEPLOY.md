# Deploying boring-mailstack

One host, one operator, releases as artifacts, no Git on the host
(DECISIONS.md). Commands that change the installation run as root (`sudo`).
What changed in each release, and what an upgrade needs: CHANGELOG.md.
Tested by `tests/first-install/run.sh` (this page's first installation, step
by step) and `tests/deploy/run.sh` (upgrades, refusals, rollback).

## Assumptions

boring-mailstack is made for a **small office or home office server**: one
machine on a network you trust, a handful of people with accounts. Hence:

- You, the operator (root on this machine), are trusted completely: you
  hold every provider password (`accounts.yaml`) and can read every
  mailbox, as the administrator of any mail server can. Tell your users
  so. The stack protects these secrets from everyone else on the machine.
- Webmail and Stalwart's admin page listen on the machine's LAN address by
  default, so the other computers in the house or office can open them.
  Both are **plain HTTP** on the LAN, and the admin page is protected only
  by its password. Anyone on that network can watch unencrypted traffic; on
  a network you do not trust (or from the Internet) use a TLS reverse proxy
  and bind to `127.0.0.1` (`tools/setup --bind 127.0.0.1`, or edit
  `etc/.env`).
- Everyone with an account is trusted: webmail connects to the CardDAV and
  Nextcloud addresses users type in. Roundcube runs on its own network, so
  those connections cannot reach the stack's internal services, but they
  can reach your LAN and the Internet.
- Your providers keep all mail: getmail never deletes there. That is what
  makes a lost local copy recoverable.

## The home

```
/opt/docker/boring-mailstack/    (any path; this one in the examples)
  accounts.yaml       your mailboxes and their providers
  folders.yaml        which provider folder is Sent, Junk, ... (for providers that do not say)
  compose.yaml        the stack for `docker compose` here (written by the first deploy; yours)
  compose.override.yaml   optional: your own changes, merged by Compose
  .env                which release runs (written by every deploy)
  release/            installed release (replaced whole by tools/deploy)
  release.previous/   the one before (rollback)
  etc/                secrets and settings — yours; deploy never writes here
    .env                where webmail and admin page listen; Stalwart's admin password
    bridge.env          the password of the bridge's Stalwart account (generated)
    roundcube/config.inc.php   your Roundcube settings
  data/               all state — written only by the services
  DEPLOYED            one line per deployment
  PROJECT             the Compose project this home owns
```

`accounts.yaml`, `folders.yaml` and `etc/` hold passwords and must be
private: owned by the user who deploys (root, with sudo) and nothing for
other users. Deploy refuses otherwise and prints the fix. Edit them with
`sudoedit` (or as root). The home itself is open (0755, as setup makes
it), so you can `cd` into it and run `sudo docker compose` there; what
others can read at the top is `compose.yaml`, `.env`, `PROJECT` and
`DEPLOYED`, none of them secret. `data/` is 0700.

## Start, stop, apply a change

In the home, plain Docker Compose:

```bash
cd /opt/docker/boring-mailstack
sudo docker compose down          # stop everything
sudo docker compose up -d         # start everything
sudo docker compose logs -f mail-getmail
```

`up -d` runs init first, which applies `accounts.yaml` and `folders.yaml`
(accounts, passwords, folders, filters). So after editing them: `down`,
then `up -d`; `up -d` alone leaves the running services as they are, with
what they read at their start. Data stays in `data/`; a `down` loses no
mail.

`compose.yaml` only includes the installed release (`release/compose.yaml`)
and never changes with a release. Your own changes go into
`compose.override.yaml` next to it, Compose's usual place: paths in it
start at the home (release files are `./release/...`), and it sees the
variables of the home's `.env`.

New releases go through `tools/deploy` (below): it verifies and builds the
images that `up -d` then uses.

## First installation

Needs Docker with Compose and `python3`. The first deploy builds the images
and fetches from the Internet: Docker images (pinned by digest), Composer
packages (the versions in `roundcube/composer.lock`), npm (`less`, for the
calendar's styles) and Kolab's git (git.kolab.org, the calendar plugins at
a pinned commit).

1. **Check and unpack the release** as root into a fresh, empty directory
   (deploy refuses files that are not in the release's manifest; unpacked
   by root, no other user can change the files root will run):

   ```bash
   sha256sum -c boring-mailstack-v2026.10.14.tar.gz.sha256
   R=$(sudo mktemp -d)
   sudo tar -xzf boring-mailstack-v2026.10.14.tar.gz -C "$R"
   R=$R/boring-mailstack-v2026.10.14
   ```

2. **Write the home:**

   ```bash
   sudo $R/tools/setup /opt/docker/boring-mailstack --mail-domain example.org
   ```

   Generates every secret into `etc/` (private), and copies
   `accounts.example.yaml` and `folders.example.yaml` as your
   `accounts.yaml` and `folders.yaml`. Webmail and admin page
   listen on this machine's LAN address (8801 and 8800); with no or several
   network interfaces, or only a public address, setup lists what it found
   and asks for `--bind ADDRESS`.
   `--bind 127.0.0.1` keeps both on this machine (behind a reverse proxy).
   Setup refuses if `etc/` exists.

3. **Put your mailboxes into `accounts.yaml`** (`sudoedit`): one entry per address,
   with the provider logins for fetching (`inbound`) and sending
   (`outbound`). The example entry explains every setting. Deploy refuses
   while a `CHANGE-ME` is left.

   **Providers that do not mark their folders:** say in
   `folders.yaml` which folder is Sent, Drafts, Junk and Trash, and
   which ones not to fetch at all (`skip`). The file explains itself and
   already holds a mapping for Hetzner mailboxes. Gmail and most others
   need nothing.
   After the first deploy the folder scan logs what it found
   (in the home: `sudo docker compose logs mail-getmail | grep FOLDERS`).

4. **Deploy:**

   ```bash
   sudo $R/tools/deploy /opt/docker/boring-mailstack
   ```

   It ends with `DEPLOYED v…`. The first fetch brings each account's whole
   history from the provider; large mailboxes take a while.

5. **Log in** at the address setup printed (`http://<LAN address>:8801/`)
   with an account's **address** and its provider password (the `inbound`
   password; set in Stalwart at every start). Users find what
   happens to their mail in `docs/USING.md`.

Stalwart's admin page is at `http://<LAN address>:8800/`: user `admin`,
password `STALWART_ADMIN_PASSWORD` from `etc/.env` (set at every start, so
to change it, edit `etc/.env`, then `down` and `up -d`). Use it for looking:
accounts, passwords and the settings the stack needs are written again at
every start, so changes made there may not last. Port 8800 is Stalwart's
whole web listener, also JMAP for every account (logins are the mail
logins); plain HTTP like the webmail, so keep it on an address only you
reach.

## Upgrade

Read the release's CHANGELOG.md entry first (some upgrades want a setting
or a backup). Then steps 1 and 4 with the new release.

Deploy: verifies the release against its manifest (nothing missing, changed
or extra); builds images tagged with the version; checks `etc/`, `accounts.yaml` and `folders.yaml` (complete,
private, valid) and the compose rendering; stops the stack and swaps `release/`; starts;
smoke-tests (webmail answers, Roundcube schema current, Stalwart speaks
IMAPS, Roundcube's plugins enabled and ManageSieve answering, Roundcube
reaching nothing but Stalwart, calendar tables present, provenance
bootstrapped, nothing restarting); appends to `DEPLOYED`.

A failure before the switch changes nothing. After it, deploy says how to go
back; nothing is rolled back automatically. Mail waits at the providers
while the stack is down.

**Configuration change** (e.g. a new account in `accounts.yaml`): `docker
compose down` and `up -d` in the home (above). Or redeploy the installed
release, `sudo /opt/docker/boring-mailstack/release/tools/deploy
/opt/docker/boring-mailstack`, which also checks `accounts.yaml` first and
smoke-tests afterwards; it switches nothing but restarts the stack.

The home owns its Compose project (`PROJECT`, written at the first deploy:
`boring-mailstack`, or `MAILSTACK_PROJECT=<name>` then). Deploy refuses a
project that belongs to another home, so a second installation on the same
host (a trial) needs its own name.

## Rollback

```bash
sudo /opt/docker/boring-mailstack/release.previous/tools/deploy /opt/docker/boring-mailstack
```

The previous release installs itself again (`release/` and
`release.previous/` swap). Deploy prints this command after every upgrade
that can be undone this way. Going back to a release before
v2026.10.14-rc.9 needs `env MAILSTACK_HOME=...` in front (deploy prints
the whole command); such a release reads `etc/accounts.yaml` and
`etc/folders.yaml`, which rc.9 left as links to the files in the home.
Afterwards, deploy rather than `docker compose up -d`: the home's `.env`
still names the newer release until the next deploy.

Some upgrades change `data/` for good (v2026.10.14: the accounts became
their real addresses). Deploy then prints **no rollback** instead, and
refuses to put an older release on that data. The way back is the backup
you took before the upgrade: take one before every upgrade whose CHANGELOG
entry says "no rollback".

**Do not run `release.previous/tools/deploy` after such an upgrade** when
`release.previous/` holds a release from before v2026.10.14: that one does
not know the check yet and would switch back onto data it cannot use.

## Backups

Backups are yours: deploy neither takes nor needs one. Whatever backs up the
host should cover the whole home (`accounts.yaml`, `folders.yaml`,
`etc/`, `data/`). Stalwart and Roundcube keep databases
open, so a consistent copy needs the stack stopped (or a filesystem
snapshot), e.g.:

```bash
cd /opt/docker/boring-mailstack && sudo docker compose stop
sudo tar --numeric-owner -cpf /root/mailstack-$(date +%F).tar -C /opt/docker boring-mailstack
sudo docker compose start
```

(tar skips Postfix's sockets in `data/relay-spool`; Postfix makes them
again.) Mail that arrives between a backup and a restore is not lost: the
providers keep it and getmail fetches it again.

## Removing it

```bash
sudo /opt/docker/boring-mailstack/release/tools/uninstall /opt/docker/boring-mailstack
```

stops and removes the stack. `--delete-home` also deletes what deploy and
setup made there (`release*/`, `etc/`, `data/` — all mail —,
`accounts.yaml`, `folders.yaml`, `compose.yaml`, `compose.override.yaml`,
`.env`, `DEPLOYED`, `PROJECT`; the directory itself only if nothing else is in it), `--images`
the images. It ends with a check of what is left.

## Building a release

From a clone, after the tests in DEVELOPMENT.md passed on the commit:

```bash
git tag -a v2026.10.14 -m "…"
tools/make-release v2026.10.14        # -> dist/boring-mailstack-v2026.10.14.tar.gz (+ .sha256)
```

The artifact holds the tag's files plus `VERSION`, `COMMIT` and
`MANIFEST.sha256`; its entries belong to root. The tarball's checksum
differs between builders (pack time); the checksum of `MANIFEST.sha256` does
not, so a build from another clone can be compared with the published one.
