# Deploying boring-mailstack

One host, one operator, releases as artifacts, no Git on the host
([decisions](DECISIONS.md)). Commands that change the installation run as root (`sudo`).
What changed in each release, and what an upgrade needs: [CHANGELOG.md](CHANGELOG.md).
The setup/deploy path is exercised by `tests/first-install/run.sh`;
`tests/deploy/run.sh` covers upgrades, refusals and rollback. The download
and reverse-proxy examples below are not exercised by those tests.


Start with **Assumptions** and **First installation** for a new host. For an
existing installation, use **Upgrade**, reading its compatibility notes before
running commands. **Mail retention** includes the fix for older releases.

Run shell commands in order and check each result. If a command fails, stop
and resolve the error before continuing.

## Assumptions

boring-mailstack is made for a **small office or home office server**: one
machine on a network you trust, a handful of people with accounts. Hence:

- You, the operator (root on this machine), are trusted completely: you
  hold every provider password (`accounts.yaml`) and can read every
  mailbox, as the administrator of any mail server can. Tell your users
  so. The stack protects these secrets from everyone else on the machine.
- **For everyday use, put webmail behind an HTTPS reverse proxy such as
  Caddy.** This protects mail and login credentials between the browser and
  your server. Direct LAN HTTP is available for a local trial; it remains
  the setup tool's default, not the recommended everyday arrangement.
  Choose the bind address for your proxy's network before running setup;
  see [Reverse proxy](#reverse-proxy). Keep Stalwart's admin endpoint private.
- Everyone with an account is trusted: webmail connects to the CardDAV and
  Nextcloud addresses users type in. Roundcube runs on its own network, so
  those connections cannot reach the stack's internal services, but they
  can reach your LAN and the Internet.
- getmail does not delete provider mail, but providers and other clients
  can. Imported archives and local filing may exist only here. Back up
  the installation; a provider copy is not a complete recovery plan.

## First installation

Needs Docker with Compose and `python3`. The first deploy builds the images
and fetches from the Internet: Docker images (pinned by digest), Composer
packages (the versions in `roundcube/composer.lock`), npm (`less`, for the
calendar's styles) and Kolab's git (git.kolab.org, the calendar plugins at
a pinned commit).

Releases are on the repository's releases page
(https://github.com/the-boring-crocodile/boring-mailstack/releases): the
tarball, its `.sha256`, and the checksum of its `MANIFEST.sha256`, which a
build of your own from the tag must match (below, "Building a release").

**Get the release onto the Linux host first.** Open
[GitHub Releases](https://github.com/the-boring-crocodile/boring-mailstack/releases),
choose a release and read its notes. Under **Assets**, download
`boring-mailstack-VERSION.tar.gz` and the matching `.tar.gz.sha256`.
Use the packaged release, not GitHub's automatically generated “Source code”
archive: the deploy tool expects the release manifest.

If downloading on your desktop, copy both files to the same directory on
the Linux host, for example with your SSH client's file-transfer pane.
Open a shell on that host and `cd` to that directory. No Git clone is needed.

Alternatively, copy each asset's download link from GitHub and download
directly on the host (requires curl). Replace both placeholder URLs:

```bash
mkdir -p "$HOME/mailstack-download"
cd "$HOME/mailstack-download"
curl --fail --location --remote-name 'PASTE_ARCHIVE_ASSET_URL_HERE'
curl --fail --location --remote-name 'PASTE_CHECKSUM_ASSET_URL_HERE'
```

The commands below use v2026.11.1 as an example artifact name, not a claim
that it is the newest release. Substitute your downloaded version in all
three places in step 1. Run the numbered steps in the same shell so that
`R`, the unpacked release directory, remains available.

1. **Check and unpack the release** as root into a fresh, empty directory
   (deploy refuses files that are not in the release's manifest; unpacked
   by root, no other user can change the files root will run):

   ```bash
   sha256sum -c boring-mailstack-v2026.11.1.tar.gz.sha256
   R=$(sudo mktemp -d)
   sudo tar -xzf boring-mailstack-v2026.11.1.tar.gz -C "$R"
   R=$R/boring-mailstack-v2026.11.1
   ```

2. **Write the home:**

   ```bash
   sudo "$R/tools/setup" /opt/docker/boring-mailstack --mail-domain example.org --bind 127.0.0.1
   ```

   Generates every secret into `etc/` (private), and copies
   `accounts.example.yaml` and `folders.example.yaml` as your
   `accounts.yaml` and `folders.yaml`. Replace `example.org` with your
   mail domain. This example binds webmail (8801) and Stalwart's web listener
   (8800) to host loopback for a proxy running on the host.
   For a containerised reverse proxy, choose the arrangement in
   [Reverse proxy](#reverse-proxy) first. Without `--bind`, setup selects a
   LAN address or asks you to choose one. Setup refuses if `etc/` exists.

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
   history from the provider; large mailboxes take a while. Before connecting
   real accounts, review active filters: initial delivery and later resieve
   are different paths. Do not assume that replaying old mail suppresses
   every sending side effect. See [arriving mail](docs/USING.md#arriving-mail).

5. **Connect the reverse proxy**, following the next section, then log in
   at your HTTPS webmail URL with an account's **address** and its provider
   password (the `inbound` password; set in Stalwart at every start).
   Check that the browser accepts the certificate before entering credentials.
   Users find what happens to their mail in [Using mailstack](docs/USING.md).

Stalwart's admin page is on the configured bind address at port 8800
(loopback in the example above): user `admin`,
password `STALWART_ADMIN_PASSWORD` from `etc/.env` (set at every start, so
to change it, edit `etc/.env`, then `down` and `up -d`). Use it for looking:
accounts, passwords and the settings the stack needs are written again at
every start, so changes made there may not last. Port 8800 is Stalwart's
whole web listener, also JMAP for every account (logins are the mail
logins); plain HTTP like the webmail, so keep it on an address only you
reach.

## Reverse proxy

Use whichever HTTPS reverse proxy you already run. Caddy, nginx and
Traefik are examples; mailstack does not require a particular proxy.
The recommendation is HTTPS for browser access, so mail and passwords
are protected in transit.

The example below uses Caddy because its configuration is short.
Adapt the upstream address to your proxy and network. Mailstack setup
does not install a proxy or configure DNS or certificates.
Only webmail needs the user-facing route; keep port 8800 private.

**Example: Caddy running on the Linux host.** Use the loopback setup command above.
Add a site to your Caddyfile, replacing the hostname with your own:

```caddyfile
webmail.example.org {
    reverse_proxy 127.0.0.1:8801
}
```

For Caddy's usual public-certificate setup, point the hostname's DNS at
your server and route ports 80 and 443 to Caddy. Caddy obtains and renews
the certificate. A LAN-only installation also needs a certificate the
clients trust; see Caddy's [automatic HTTPS documentation](https://caddyserver.com/docs/automatic-https)
for internal certificates and other certificate arrangements.
Validate and reload Caddy using your installation's normal procedure.

**If your proxy runs in Docker:** a container on a bridge network has its own
`127.0.0.1`; that address does not reach the host's published webmail port.
Choose one of these arrangements:

- On Linux, a proxy using host networking can reach the loopback address above.
- With bridge networking, bind mailstack to a specific host address reachable
  from the proxy and use that address as its upstream. In Caddy, for example:
  `reverse_proxy 192.168.1.10:8801`. Replace the example address with your
  host's address. Restrict direct access to the published ports to the
  intended clients/proxy, accounting for Docker's published-port firewall
  rules. Do not forward ports 8800 or 8801 from the router to the internet.

The bridge-network option leaves the proxy-to-webmail hop as HTTP on that
network; use a trusted path. Simply adding a host-name alias inside the proxy's
container does not make a service bound only to host loopback reachable.

After deployment, check the HTTPS login page, sign-in, message reading and
sending through the proxy. Confirm that the admin endpoint remains private.
The examples describe proxy wiring; mailstack's deployment smoke test does
not validate your external DNS, certificate or reverse-proxy configuration.

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

## Upgrade

Read the release's CHANGELOG.md entry first (some upgrades want a setting
or a backup). Then steps 1 and 4 with the new release.

Before step 4, `--check` shows what the deploy would refuse, all of it at
once, and changes nothing (it builds nothing and leaves the stack running):

```bash
sudo $R/tools/deploy --check /opt/docker/boring-mailstack
```

It ends with `checked:` or with a list of what to fix first. `accounts.yaml`
is validated by the new release's own image, so `--check` leaves that to the
deploy unless the images are already built.

Deploy: verifies the release against its manifest (nothing missing, changed
or extra); builds images tagged with the version; checks `etc/`, `accounts.yaml` and `folders.yaml` (complete,
private, valid) and the compose rendering; stops the stack and swaps `release/`; starts;
smoke-tests (webmail answers, Roundcube schema current, Stalwart speaks
IMAPS, Roundcube's plugins enabled and ManageSieve answering, Roundcube
reaching nothing but Stalwart, calendar tables present, stored mail without
an expiry, provenance bootstrapped, nothing restarting); appends to `DEPLOYED`.

A stack you stopped stays stopped: deploy installs the release, skips start
and smoke test, and says so (also in `DEPLOYED`). `docker compose up -d` in
the home starts it later; `deploy --start` starts it right away, with the
smoke test. A first installation always starts.

A failure before the switch leaves the installed release selected; preparation
may already have built images. After the switch, deploy says how to go back;
nothing is rolled back automatically. Providers continue receiving mail while
the stack is down, subject to their own quotas and retention policies.

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

## Mail retention

The stack retains stored messages until explicitly deleted. Provisioning sets
Stalwart's global `DataRetention.expungeTrashAfter` to `null` for all accounts,
including Junk and Trash. This is enforced each time init provisions the stack;
changing it in Stalwart's admin page is not a persistent override.

Releases through v2026.10.15 did not enforce this setting and left
Stalwart's default 30-day expiry active. For an existing installation, disable
it immediately from its home directory, without waiting for an upgrade:

```bash
cd /opt/docker/boring-mailstack
printf '%s\n' '{"expungeTrashAfter":null}' | sudo ./release/tools/stalwart-cli update DataRetention --stdin
sudo ./release/tools/stalwart-cli create Action/ReloadSettings
sudo ./release/tools/stalwart-cli get DataRetention
```

Verify `Trash/Junk: <none>`. This prevents future expiry; it does not restore
messages already removed. Compare retained import archives and backups with
live mail before restoring, to avoid duplicating surviving messages.

Other maintenance remains enabled: email-submission expiry removes delivery
tracking records, not Sent messages; blob cleanup reclaims unreferenced data.
Manual deletion and user-authored Sieve discard rules still apply. Provider
retention is independent, so provider copies alone are not a complete backup.

## Backups

Backups are yours: deploy does not take one. A data-changing upgrade can
require one for recovery; read its release notes first. Whatever backs up the
host should cover the whole home (`accounts.yaml`, `folders.yaml`,
`etc/`, `data/`). Stalwart and Roundcube keep databases
open, so stop the stack for a consistent copy. A snapshot is an alternative
only with a database-consistent backup procedure. For example:

```bash
cd /opt/docker/boring-mailstack && sudo docker compose stop
sudo tar --numeric-owner -cpf /root/mailstack-$(date +%F).tar -C /opt/docker boring-mailstack
sudo docker compose start
```

(tar skips Postfix's sockets in `data/relay-spool`; Postfix makes them
again.) After restoring a backup, getmail can fetch later mail that is still
available at the providers. It cannot recover provider-deleted mail or local
changes made after that backup. Keep original import archives as well.

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
git tag -a v2026.11.1 -m "…"
tools/make-release v2026.11.1         # -> dist/boring-mailstack-v2026.11.1.tar.gz (+ .sha256)
```

The artifact holds the tag's files plus `VERSION`, `COMMIT` and
`MANIFEST.sha256`; its entries belong to root. The tarball's checksum
differs between builders (pack time); the checksum of `MANIFEST.sha256` does
not, so a build from another clone can be compared with the published one.
