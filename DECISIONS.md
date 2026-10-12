# Decisions

Product decisions and the alternatives rejected. Newest last.

## 2026-10-05 — CardDAV addressbooks are added by each user, not configured by us

**Decision (for now):** Roundcube carries the RCMCardDAV plugin with a
static admin config and no presets. Each user adds their own Nextcloud
addressbook in Roundcube (Settings → CardDAV), ideally with a Nextcloud app
password. Mailstack configuration (`accounts.yaml`, `generated/`) holds no
CardDAV data or credentials.

**Intent / property that must hold:** a Roundcube user can see only the
addressbooks they configured themselves; no user's CardDAV credentials are
ever available to another user. Testable: log in as a second user and check
that Settings → CardDAV and the contacts list show none of the first user's
addressbooks.

**Why:** RCMCardDAV presets are global; the plugin adds every preset to every
user at first login, with no per-user restriction (upstream
`doc/ADMIN-SETTINGS.md`, plugin 5.1.4). The first design, one preset per mail
account with fixed Nextcloud credentials generated from `accounts.yaml`,
would have given every user every account's addressbook and credentials.
It was implemented on 2026-10-05, found before any use, and reverted.

**Cost:** one manual setup per user; a changed mail password means
re-entering the CardDAV password (`pwstore_scheme = encrypted`, the default).

**Rejected alternatives:**

- Per-account presets with fixed credentials — the leak above.
- Presets selected per logged-in user by our own PHP glue — relies on
  undocumented plugin load order and session behaviour; we would own policy
  that belongs to the plugin. Revisit only if hand setup proves unacceptable.
- Presets with `%u`/`%p` placeholders — work only when Nextcloud logins equal
  the mail logins, which is often not the case.

## 2026-10-06 — Install layout: code, host config and data apart; no Git

**Decision:** an installation (e.g. `/opt/docker/boring-mailstack`) has three
parts: `release/` (the code of exactly one release, replaced whole on each
deploy), `etc/` (host config and secrets, edited only by the operator) and `data/`
(all state). No Git on the host:
a release reaches it as an artifact built from a tag
(`git archive`), with a `VERSION` file and no repository.

**Why:** code, host config and data change for different reasons. With code
in its own directory, an update replaces it whole (no stale files, no risk
of overwriting config or data) and a rollback puts the previous one back.
Secrets and `accounts.yaml` live in `etc/`, never in code directories.
*(Changed 2026-10-11: `accounts.yaml` and `folders.yaml` sit at the home's
top, see "The home is a plain Compose project".)*

**Rejected:** a single tree with new code copied over the code
paths — simpler to look at, but stale files remain and rollback is less
clean. A Git checkout on the host — the host needs the files of one
release, not the repository.

## 2026-10-06 — Names come from the Compose project

**Decision:** the Compose project, containers, images and networks are named
`boring-mailstack` / `boring-mailstack-*`. Containers are named by Compose
from the project name (`boring-mailstack-<service>-1`), not by fixed
`container_name`s, so a demo or test project can run beside an installation
on one daemon. Services address each other only by Compose service name or a
declared alias, never by container name: a webhook that still pointed at an
old container name once delivered silently nowhere after a rename (found by
the demo; until v2026.10.14-rc.7 the provisioner also removed such legacy
webhooks).

## 2026-10-06 — Filters and Contacts are part of the product

**Decision:** every install has Roundcube Filters (ManageSieve) and
Contacts (RCMCardDAV, users add their own addressbooks) from the first
login. The image's release defaults add both plugins
after the operator's `etc/roundcube/config.inc.php`, so an own plugin list
there (e.g. an older one without carddav) cannot switch them off; Filters use the IMAP
host on 4190 unless set. Deploy's smoke step checks both.

## 2026-10-06 — Releases are checked by their manifest; built from a clone

A release artifact is `git archive` of a tag plus VERSION, COMMIT and
MANIFEST.sha256. The tarball's own checksum differs between builders (pack
time, owner); the checksum of `MANIFEST.sha256` does not, so an operator
building from their own clone compares that with the one published for the
release.

## 2026-10-06 — Calendar and files in Roundcube, from the user's Nextcloud via CardDAV

**Decision:** the calendar lives *in* Roundcube (Kolab's calendar, CalDAV driver), not as Nextcloud's page in a frame; Nextcloud files via Roundav. Both take the user's Nextcloud login from the CardDAV account they already set up (our plugin `mailstack_cloudfiles`); no second password, never the mail password. Kolab's plugins come from Kolab's git at a pinned commit (the Packagist release depends on a library version with a security advisory). Our libkolab patch caching folder rights is kept for the measured speed (0.1 s vs 0.3 s per click with four calendars; grows with the square of the number of calendars) and offered upstream.

**Rejected:** Nextcloud's calendar in an iframe (needs Nextcloud's frame-ancestors changed; looks like Nextcloud, not Roundcube); commercial plugins (proprietary); Roundav's own settings (unencrypted password, fallback to the mail password).


## 2026-10-07 — Nextcloud identity check per session; wrong password counts as a failed login

**Decision (for now):** `mailstack_cloudfiles` asks the user's Nextcloud once per Roundcube session who they are (`current-user-principal`), with the login from their CardDAV account. A wrong CardDAV password therefore counts as one failed login at the Nextcloud per session (its brute-force protection may slow further logins from the webmail's address), as RCMCardDAV's own sync already does. A Nextcloud that cannot be reached is asked again on the next request; nothing is cached as "not a Nextcloud" then. The note for users without a Nextcloud account stays as worded (en/de).

**To revisit:** if failed logins from a stale CardDAV password become a nuisance, remember the failure for the session or tell the user in Settings.

## 2026-10-07 — Inside the stack, TLS to Stalwart is not verified

**Decision (recorded 2026-10-07; was a code comment before):** the
stack's own clients talk to Stalwart over its private Docker network and do
**not** verify Stalwart's certificate, which is Stalwart's own self-signed
one for `stalwart.mailstack.local`:

- `resieve` and resieve-watch (JMAP over HTTPS): `.accept_invalid_certs(true)`, an unverified context;
- the bridge (JMAP over HTTPS, since v2026.10.14-rc.9; before: plain HTTP on 8080 with the
  session's URLs rewritten): an unverified context;
- `mail-provenance` (IMAPS): `CERT_NONE`, no host-name check;
- Roundcube (IMAPS, SMTPS, ManageSieve): `verify_peer` off in `etc/roundcube/config.inc.php`
  (the demo writes the same);
- deploy's IMAPS probe: the same.


**Trade-off, stated plainly:** this switches off *all* certificate checking
on those connections, not just the host-name check. Anyone who can join the
`mail-internal` network or impersonate `stalwart` on it can read the
passwords these clients send. We accept that because that network is
internal to one Compose project on one host: a process able to join it can
already read `etc/` and `data/`. Nothing outside the host talks to Stalwart
this way.

Connections to the **providers** are verified: the relay with
`smtp_tls_security_level = verify`, getmail with `ca_certs` (chain and host
name). getmail did **not** verify before v2026.10.8: without `ca_certs`
getmail 6 uses imaplib's default context, which checks nothing (found while
writing this entry, 2026-10-07).

**To revisit:** if any of these clients ever connects across a host
boundary, or if the network is shared with other projects. The fix then is
an internal CA (or Stalwart's certificate pinned) mounted into each client,
not a broader exception.

## 2026-10-08 — Stalwart request limits

**Decision:** the authenticated HTTP rate limit
goes from 60,000 to 600,000 requests per account per minute
(`tools/stalwart-provision.py`, applied by init at every start).

**Why, measured** on a real mailbox of 48,987 mails:
resieve with full messages makes about one request per mail (~1,300/s); a
run right after another within the minute hit the 60,000 limit and Stalwart
answered 429. resieve now waits and retries on 429 anyway, and evaluates
header-only scripts with about 100 requests, so the limit only matters for
scripts that need full messages on large mailboxes. With 600,000 back-to-back
runs saw no 429 at all.

**Not changed:** JMAP `maxConcurrentRequests` stays 4: it does not apply to
blob downloads (same throughput with 4 and 16, measured). Parallel downloads
over kept-open connections would give about 1.6x in full-message mode
(1,500 → 2,400/s in a probe); not built, header-only mode makes it moot for
our filters.

**Trade-off:** the limit no longer protects Stalwart from a runaway
authenticated client on our own networks; acceptable for a family-sized
stack where every authenticated client is ours.

## 2026-10-08 — Automatic resieve after a filter change

**Decision:** when a user's active Sieve filter changes, resieve runs
with `--apply` for that account by itself (a dry run would only report).
Service `resieve-watch`: Stalwart reports ManageSieve script changes by
webhook (the event carries no account); after 60 s without further changes
the watcher reads every enabled account's active script and runs resieve for
each account whose script differs from the one it last applied. Hourly the
same check runs without an event (lost events, a script activated another
way). One run at a time. The first start records the current scripts without
a run, so a deploy moves no mail by itself. Per account, `resieve:
{enabled: false}` in `accounts.yaml` switches it off (default on; was
`auto_resieve: false` until v2026.10.14-rc.5).

**What stays protected:** as in every resieve run, mail moved by hand and
mail the provider had filed into a folder (provenance).

**Accepted risk:** a wrong filter moves mail as fast as a right one; the cure
is fixing the filter (which starts the next run) or moving mail back by hand
(those moves are then protected).

**Measured** on the fixture: filter saved 01:33:47, run started 01:34:48,
done in 7.1 s, 2,420 moves, 0 errors.

## 2026-10-09 — resieve puts unprotected mail where the filter says; protection is for human placements

Replaces the earlier rule "resieve may move any mail that provenance has not
protected", which failed open: every placement provenance never heard of
(Roundcube's Sent and Drafts, copies, a lost webhook event) was free to move.

**Protected (resieve never touches the mail):** placements by a human — here
by IMAP MOVE, COPY or APPEND (reported by Stalwart's webhook), and elsewhere:
mail that sat in a provider folder other than the Inbox when it was fetched
(moved there in the provider's webmail, or by the user's filter there).
**Never protected:** deliveries (including the spam filter's Junk),
Sieve placements at delivery, resieve's own moves.

**What resieve does:** computes the filter's full placement as a set of
folders (`fileinto :copy`, several `fileinto`, keep) and puts every
unprotected mail exactly there: a folder the filter does not name is left.
A copy the filter made is removed when the filter changes. Human placements
are known from the start: the bridge records every mail it imports from a
provider folder other than the Inbox, and Stalwart's webhook every move,
copy and append since. Per account, `resieve.never_move_from`
(roles or paths; default Sent, Drafts, Trash, Junk): never out of these,
into them is allowed. Before writing it re-reads the protection and
fetches the mail's folders again, writing with `ifInState`. Provenance
entries are removed only for mail Stalwart reports gone, never in a dry run.

**Events:** provenance processes each event on its own (one failing event
no longer holds back the batch); new and renamed folders are learned from
their events; undelivered events wait up to 6 hours.

**Accepted:** a human move through JMAP produces no usable event, and
Stalwart drops a webhook event it could not deliver for 6 hours; such a
mail is unprotected. Copies and appends made before this release were not
recorded.

## 2026-10-09 — Three ways in

Stalwart has two ways to take a mail: delivery (its spam filter and the
user's Sieve filter run; Sieve's "keep" is always INBOX) and JMAP import
(nothing runs, the mail lands in the folder given). There is no way to skip
the filter on delivery and no way to give delivery another fallback folder.
So the bridge chooses per provider folder:

- **listed in `inbound_sieve.folders`** (default INBOX): delivery on port 25,
  spam filter off for the bridge (the provider filtered already; re-injected
  mail scores badly because sender checks see the bridge; measured and
  confirmed 2026-10-11, "No second spam filter on fetched mail");
- **the provider's Junk, if listed:** delivery on an internal second port
  (2525) with the spam filter on and a rule that makes mail carrying the
  bridge's provider-junk header spam. The user's filter still decides;
  Stalwart files what the filter leaves in INBOX into Junk. Forging the
  header can only make mail spam;
- **any other folder:** import into the same folder, recorded as placed by a
  human ("human, elsewhere").

Copies: Stalwart 0.16 cannot search Message-IDs (JMAP header filter and IMAP
SEARCH HEADER find nothing), so the bridge keeps a Message-ID index per
account with `Email/changes` and compares candidates exactly. A provider
move becomes a move here when the existing copy was placed by the filter;
a copy placed by a human gets the new folder added (labels).

**Rejected:** running the filter after an import (resieve per mail) — two
mechanisms pretending to be one; Stalwart's classify API for provider INBOX
mail — not needed while the provider's verdict is trusted.

## 2026-10-09 — Moving a mail into INBOX hands it back to the filter

A human move into INBOX (or into Junk, when the account's filter may sort
Junk) releases the mail: its "placed by a human" record goes and resieve
sorts exactly those mails, batched about a minute after the last move. A
rule that matches files the mail (and clears its junk flag: the user's rule
overrules every spam verdict); no rule means it stays where the human put
it. Read/unread state is left alone. This makes restructuring folders a
filter change plus a move into INBOX.

Spam on a normal re-sort follows Stalwart's delivery rule: spam the filter
leaves only in INBOX goes to Junk. "Spam" is the `$junk` keyword or the
spam verdict in `X-Spam-Score` (`X-Spam-Status` says "No" whenever Sieve
filed the mail elsewhere), unless `$notjunk` is set.

The release stands whatever the re-sort's outcome: the move handed the mail
to the filter, and a mail a failed run leaves in place is sorted by the
filter's next run (2026-10-11). Pending re-sorts are kept on disk by
resieve-watch; provenance retries the hand-back with the whole event.

**Accepted:** a move made by a JMAP client is not seen (Stalwart reports no
usable event), so it does not hand the mail back.

**Who owns what:** provenance owns the store of human placements (schema,
recording, `/protect` and `/protected` for the bridge); resieve and
resieve-watch read it and delete from it directly (releases, mail Stalwart
reports gone), the same file on the same volume. A human's spam verdict is
the `$junk`/`$notjunk` keyword pair, written by the bridge (provider moves)
and resieve (re-sorts) alike: change both together.

## 2026-10-09 — Each account is its real address

A Stalwart account's primary address is always name@domain. The accounts
were `<id>@mailstack.local` with the real address as an alias; Stalwart
sends vacation replies and Sieve redirects from the primary address, so they
went out as `<id>@mailstack.local` and the relay (which only accepts the
configured addresses) refused them. The internal account domain had no
recorded reason; the real domains were Stalwart domains anyway (for the
aliases).

Now the account is the real address (name = local part, the address's
domain); the same local part on two domains is fine (Stalwart requires
unique addresses, not names). The `accounts.yaml` key stays our internal
handle (provenance, state files, `tools/resieve <key>`). Users log in with
their address. Existing accounts were renamed in place by v2026.10.14-rc.1
to rc.6 (that code is gone since: older installs go through rc.6); their
mail belongs to the account and stays.

**Rejected:** a sender rewrite table in the relay — works, but one more
translation layer to look after ("boring, simple, less responsibility for
us").

## 2026-10-09 — Roundcube on its own network

Users type URLs into Roundcube (CardDAV, Nextcloud), and Roundcube connects
to them. On `mail-internal` that reached provenance, the bridge and
resieve-watch, which trust their network (no logins). Roundcube now sits on
a network with Stalwart only; deploy checks that it cannot resolve the other
services. It still reaches the LAN and the Internet: Nextclouds live there.
The docs say to give accounts only to people you trust.

**Rejected:** an allowlist of Nextcloud hosts — one more thing to configure
for every user's own server.

## 2026-10-09 — Every base image pinned by digest

All Dockerfiles name their base image by tag and digest; five did not
(bridge, provenance, resieve's builder and its two runtime stages), so a
rebuild of the same release could pull a different base. The bridge now
uses the same Python base as getmail and init, resieve the same Debian as
the relay. Updates come as proposals with tests (GitHub Dependabot, once the
repository is public), not by rebuilding.

Packages installed with apt/apk on top stay unpinned: Debian and Alpine
take versions out of their archives, so pins would break rebuilds, and the
security fixes are what we want. A release built twice may therefore differ
in those packages.

## 2026-10-09 — etc/ is private; uninstall deletes only its own

`etc/` holds every secret of the installation. Deploy now refuses when
anything in it is open to other users or owned by a third user, and names
the fix. Roundcube's config used to be mounted straight into
the container, so it had to be world-readable for Apache; a pre-setup task
now copies it as root (root:www-data 0640).

`uninstall --delete-home` used to delete HOME whole. HOME is the
operator's directory (it may be `/opt/docker`, or hold their own notes), so
now only what deploy and setup made goes (since 2026-10-11 also
accounts.yaml, folders.yaml, compose.yaml, compose.override.yaml and .env at
the top; DEPLOY.md, "Removing it"); HOME goes only if then empty, and the
rest is listed. The same privacy rule covers accounts.yaml and folders.yaml.

## 2026-10-09 — Nextcloud cookies encrypted in the session

The Nextcloud session cookies the webmail keeps (for speed, ~450 ms per
login saved) were stored in Roundcube's session table in the clear: a copy
of `data/` gave a working Nextcloud session. They are now encrypted with
Roundcube's `des_key`, as Roundcube does for the IMAP password.


## 2026-10-11 — The home is a plain Compose project; accounts.yaml at the top

**Decision:** in the home, `docker compose up -d` and `down` start and stop
the stack, as with any other Compose application. The home's `compose.yaml`
only includes `release/compose.yaml` (Compose `include`, project directory
`release/`, env files `etc/.env` then the home's `.env`); deploy writes it
once if missing and never again. Deploy writes the home's `.env` (the
installed release and the home's path) at every deploy. `accounts.yaml`
and `folders.yaml`, the files the operator edits, sit next to
`compose.yaml`; `etc/` keeps secrets and rarely touched settings. Own
Compose changes go into the home's `compose.override.yaml`, which Compose
merges by itself. Deploy stays the way to install a release (verify, build,
check, switch, smoke) and runs Compose exactly as the operator does.

The project name is recorded twice on purpose: `name:` in `compose.yaml` is
what Docker uses (every `docker compose` in the home), `PROJECT` is the
tools' record of which project the home belongs to (deploy, uninstall,
`layout.sh`, the demo). `compose.yaml` is the operator's file; deploy
refuses when its `name:` differs from `PROJECT`, so an edited name cannot
quietly start a second project beside the first one's containers.

**Why:** other Compose applications in `/opt/docker` work this way, and so
does Docker's own model (project = directory with `compose.yaml`, `.env`,
`compose.override.yaml`). Before, starting the stack by hand needed the
release directory, `etc/.env` and three variables on one command line, and
a password change in `accounts.yaml` needed a redeploy.

**Rejected:** copying `release/compose.yaml` into the home at each deploy (a
file the operator might edit, overwritten); symlinking it (relative paths
in it would start at the home); keeping `accounts.yaml` in `etc/` (the
operator edits it often; `etc/` is for what is set once).

## 2026-10-11 — Mirror what is there, as it is

**Decision:** the stack shows the provider's mailbox as it is and does not
tidy it up. A plain label that happens to be called "Sent" (left by an old
mail client at Gmail) stays an ordinary folder next to the real Sent; the
cure is at the provider (delete the label) or, if wanted, one line in
`folders.yaml`, never code. A mail's arrival date here is when the stack
fetched it, and Roundcube shows that when sorting by arrival; the mail's
own date is the "Sent date" column. No default changes either.

**Why (Wald):** "both things are based in reality and changing them would
lessen reality's weight … we want to lead reality." Bending what is shown
to look tidier makes the mirror less trustworthy. Whoever wants the
provider's arrival dates on an existing mailbox gets a one-time migration,
not a feature.

## 2026-10-11 — No second spam filter on fetched mail

**Decision:** Stalwart's spam filter stays off for the provider's INBOX
(as since 2026-10-09, "Three ways in"); it runs only on the junk port,
where our rule makes provider-Junk mail spam anyway. The spam verdict is the
provider's, plus what the user does (mark as spam / not spam, filters).
Nothing of "option 1" below is built.

**Measured** (a trial installation, 41 real mails of a Gmail test account
handed to Stalwart as the bridge does; the probe script is not part of the
release):

| | INBOX mail judged spam | Gmail-Junk mail judged spam |
|---|---|---|
| filter on, settings as they are | 20 of 25 | 4 of 16 |
| option 1: SPF, DMARC, reverse IP off; HELO, rDNS, Received-trail and DMARC_NA tags 0 | 16 of 25 | 0 of 16 |
| option 1, without what only the test adds (old dates, another recipient) | 7 of 25 | 0 of 16 |

Sender checks fail on every fetched mail because Stalwart sees the bridge,
not the sending machine (SPF, DMARC through SPF, HELO, reverse DNS: 4–6
points per mail). Option 1 removes that part, but the content rules alone,
with an empty Bayes, still put newsletters (5.2) and a real Google security
alert (6.4, `PHISHING`) into Junk. The link blocklists (URIBL, Spamhaus)
answer `…_BLOCKED`: they refuse queries from public resolvers.

**Why:** every mail was judged already, at arrival, by a provider that saw
the real connection and has far more data. A second judge here sees only
the leftovers with the weakest signals, and a filter that hides real mail
does more harm than one that lets a spam through. A third opinion next to
the provider's and the user's also contradicts the mirror (above).

**Rejected:** option 1 (sender checks off, see the table); option 2, the
real sending machine read from the `Received:` lines (the trust boundary
must be guessed without provider-specific code; a line too low lets a
spammer choose his IP; checks at fetch time are wrong for history).

**Revisit when** a provider measurably lets spam into the INBOX (one
provider's filter is the candidate): then Bayes alone, trained by the user's own
spam / not spam, as an opt-in per account, first checking how Stalwart 0.16
trains its classifier. Count before building.

## 2026-10-12 — No single sign-on into Nextcloud

**Decision:** the Files and Talk links open the user's Nextcloud with its
own browser login ("Stay logged in" keeps it). The webmail does not log
the browser into Nextcloud.

**Why:** the Nextcloud login the webmail holds is the server's (its
session cookies belong to the server's requests, not to the browser), and
handing it to the browser would mean either moving a session to another
client or putting the password into the page; the stored password is
usually an app password, not meant for the web login. The user's
Nextcloud owns how people log in to it. Real single sign-on needs an
identity provider both trust (OpenID Connect): a new component, too heavy
for this convenience (Wald).

## 2026-10-12 — Licence: AGPL-3.0-or-later

**Decision:** the whole repository is under the GNU AGPL, version 3 or
later (`LICENSE`; README "Licence"). `resieve` binaries are AGPL-3.0 only
(sieve-rs); our patches to Kolab and Roundav stay under their licences.
Copyright line: "Wald and the boring-mailstack contributors", saying that
much of the code was written by an AI and reviewed and tested by Wald.

**Why:** Wald supports the open source idea and uses it daily; the stack
is built from AGPL software (Stalwart, Kolab's calendar, Roundav,
sieve-rs), so one licence of the same family needs no per-directory map;
a changed version offered as a service shares its source. Permissive
(MIT/Apache) for our own code would have meant AGPL/GPL exceptions anyway
(resieve, the patches, mailstack_cloudfiles through RCMCardDAV).
