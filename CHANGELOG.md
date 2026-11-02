# Changelog

What changed in each release and what to know when upgrading to it, newest
first. Versions are `vYYYY.M.N`: year, month, and the release count in that
month. Every upgrade is `tools/deploy` of the new release (DEPLOY.md); a
rollback is a redeploy of `release.previous/`.

## v2026.11.3

Security update of the webmail's address book plugin (Dependabot's
proposal, checked by the acceptance test). Stalwart and the stored mail
are unchanged.

- **roundcube/carddav 5.1.5** with carddavclient 1.5.1 (security fixes):
  account credentials go only to the address book's own origin; error
  messages no longer show the bodies of HTTP responses; a contact photo
  given only as a URL is no longer downloaded by the webmail server, so
  such contacts show Roundcube's placeholder picture. Photos stored in the
  contact itself show as before.
- With it: guzzlehttp/guzzle 7.16.1, guzzlehttp/promises 2.6.0,
  guzzlehttp/psr7 2.13.2.
- Nothing to do when upgrading; a rollback to v2026.11.2 works as usual.

## v2026.11.2

Dependency updates (Dependabot's proposals, each checked by the acceptance
test). Stalwart, and with it the stored mail, is unchanged.

- **Base images:** the bridge, getmail and init on Python 3.15;
  stalwart-cli 1.0.14 in init; Alpine 3.24 and Node 26 rebuilt; the
  Roundcube build stage on alpine/git 2.54. The browser-check image moves
  to Playwright 1.64, pinned with its tag, and its Playwright package with
  it.
- **Roundcube's PHP packages:** masterminds/html5 2.12, lolli42/finediff
  1.1, league/commonmark 2.10.4.
- **resieve's Rust crates:** rustls 0.23.46 (security fixes), serde_json
  1.0.154, rusqlite 0.41.1.
- **Demo:** GreenMail 2.1.15.
- **Stays on Stalwart 0.16.23.** Stalwart 1.0 has a new database layout
  and cannot open a 0.16 data store; the move needs Stalwart's own
  migration tool from 0.16.27 and gets a release of its own. Dependabot no
  longer proposes the Stalwart server image (DECISIONS.md).
- Nothing to do when upgrading; the data is untouched and a rollback to
  v2026.11.1 works as usual.

## v2026.11.1

- **Stored mail must not expire:** provisioning explicitly sets Stalwart's
  global `DataRetention.expungeTrashAfter` to `null`. Previously it left the
  upstream 30-day Junk/Trash expiry unchanged. The new policy applies to all
  accounts on first installation and when init provisions an existing stack.
  An omitted setting is no longer treated as an explicit disabled value.
- This prevents future age-based deletion; it does not recover expired mail.
  Existing installations need the immediate mitigation in DEPLOY.md until
  they deploy this change. Delivery-tracking and storage housekeeping remain
  unchanged. Explicit user deletion and user-authored discard rules still work.
- **Base images and locks updated** (Dependabot's proposals,
  each checked by the acceptance test): the Python services on Python 3.14,
  Alpine 3.24, the Roundcube build stages on alpine/git 2.52 and Node 26;
  Roundcube's PHP packages (masterminds/html5 2.11, pear/crypt_gpg 2.0,
  pear/http_request2 2.8); resieve's Rust crates (sieve-rs 1.0.2,
  jmap-client 0.4.3, rusqlite 0.40.2). The browser-check image stays on
  Playwright 1.55, now pinned with its tag.
- **Authorship, truthfully:** README, CONTRIBUTING, DECISIONS and STORY say
  that all of it — code, tests, docs — was written by AI, and that Wald
  decided what to build, tested it, ran it and had the last word (they said
  "much of the code ... reviewed and tested by Wald").
- **Deploy:** `tools/deploy --check HOME` lists everything the deploy would
  refuse, at once, and changes nothing. The smoke test checks that Stalwart
  keeps stored mail without an expiry. A stack stopped before the deploy
  stays stopped (`--start` starts it); a first install always starts.
- **Docs:** USING.md says exactly when vacation replies go out (only to mail
  naming your address, never to group addresses, lists, bulk or automatic
  mail); the acceptance test proves the first two. README links to the
  pages it names; the diagrams have dark-mode twins. README rewritten for
  someone deciding whether the stack fits; the new
  docs/WORKING_WITH_MAILSTACK.md covers daily use (what travels where,
  reorganising old mail, Nextcloud, keeping history); DEPLOY.md recommends
  HTTPS through a reverse proxy, with a Caddy example.
- Nothing to do when upgrading besides the retention note above.

## v2026.10.15

Documentation only: the demo described in README.md and docs/STORY.md as
the story it is. Nothing to do when upgrading; no change in operation.

## v2026.10.14

Against v2026.10.13 (candidates rc.1 to rc.9).

- **Licence:** GNU AGPL-3.0-or-later (`LICENSE`, README "Licence").
- **Documentation:** `docs/DESIGN.md` (the decisions that shape it, with
  the code and tests behind each), `docs/STORY.md` (how it came to be and
  how it was built), `docs/USING.md` for the people who read mail with it,
  five diagrams in `docs/architecture/`; `SECURITY.md`, `CONTRIBUTING.md`.
- **Unit tests on GitHub** at every push and pull request
  (`.github/workflows/unit-tests.yml`).
- **Demo:** the story has more spam, one of it an HTML advert (`html:` in
  the story format), for a look at dark mode.

### Running it

- **Plain Docker Compose in the home:** in `/opt/docker/boring-mailstack`,
  `docker compose down` stops everything, `docker compose up -d` starts it
  and applies `accounts.yaml` and `folders.yaml`. The home's small
  `compose.yaml` includes `release/compose.yaml` (written once, then yours);
  `.env` names the installed release (written by every deploy); your own
  Compose changes go into `compose.override.yaml`. New releases still go
  through `tools/deploy`.
- **`accounts.yaml` and `folders.yaml` live in the home**, next to
  `compose.yaml`; `etc/` keeps the secrets and the Roundcube settings.
- **`tools/setup HOME --mail-domain example.org`** writes a new home
  (open to read, `etc/`, `data/` and the account files private, every
  secret generated, `accounts.yaml` and `folders.yaml` from the examples) and says what to do next; webmail and admin page listen on
  the LAN address (`--bind` to choose). Deploy refuses the example's
  `CHANGE-ME`.
- **Stalwart's admin page login works:** `STALWART_ADMIN_PASSWORD` from
  `etc/.env` is set at every start.
- **Deploy:** verifies the release against its manifest (no file more or
  less, no symlink), checks before it stops anything (`etc/`,
  `accounts.yaml` and `folders.yaml` private and valid, the home rendered as
  it will run, `compose.override.yaml` included), knows one-way upgrades
  (`DATA_GENERATION`: no rollback offered onto data an older release cannot
  read), never keeps a release that failed its smoke test for rollback, and
  owns its Compose project (`PROJECT`: a trial cannot take over an
  installation). It takes no backup (the host's business).
- **`tools/resieve ACCOUNT [--apply]`** runs in the running resieve-watch
  container; no password passes through the host.
- **`uninstall --delete-home`** deletes only what deploy and setup made in
  the home; a Docker command that fails is reported, never "CLEAN".
- Every base image pinned by digest; Roundcube on its own network with
  Stalwart only (a URL typed into Contacts cannot reach the stack's inner
  services); the Nextcloud session cookies encrypted with `des_key`.

### Mail

- **Folders by role, not by name:** Sent, Drafts, Junk, Trash and Archive
  come from the provider's special-use marks (RFC 6154) or from
  `folders.yaml`, per provider (inbound host) and per account; `skip` leaves
  a folder unfetched. A provider folder merely called "Junk" is an ordinary
  folder (`folders.example.yaml` holds a mapping for Hetzner mailboxes;
  GMX's outbox is skipped).
- **Gmail:** "All Mail", "Important" and "Starred" are not fetched; a mail
  in two labels is one mail in two folders; spam and trash are places (a
  mail marked as spam or deleted there moves here into Junk or Trash, "not
  spam" and restoring bring it back); INBOX is fetched first, so a new mail
  goes through the filter before any label copy. Archiving in Gmail is not
  mirrored (docs/USING.md).
- **Fetching:** nothing is fetched before the provider's folder list is
  applied; a mail moved at the provider moves here too; copies are compared
  exactly; a mail without Message-ID gets one from its content; the
  provider's Sent copy of a mail sent from webmail is not imported again; a
  mail to yourself arrives; a deploy or stop finishes the mail being handed
  over; no bounces for fetched mail.
- **Per-account filter settings** in `accounts.yaml` (`inbound_sieve`,
  `resieve`; `accounts.example.yaml` explains them). The provider's Junk can
  go through your filter (`inbound_sieve.folders: [INBOX, Junk]`): a rule
  files it, otherwise it stays spam (Stalwart gets an internal second SMTP
  port, 2525, for this).
- **resieve applies the filter's full result** to mail already here, never
  to mail you placed yourself or mail in `never_move_from` folders; spam it
  leaves in INBOX goes to Junk; it writes patiently on busy accounts and
  puts a notice into the INBOX when a filter change cannot be applied.
- **Re-sort chute:** moving mail into INBOX (or a re-sortable Junk) hands it
  back to your filter about a minute after the last move; a mail no rule
  matches stays where you put it. Junk to INBOX by hand means "not spam",
  into Junk means spam, and that sticks. Pending re-sorts survive a restart.
- **More placements recorded as yours:** IMAP moves, copies and appends
  (Roundcube's Sent and Drafts), in new and renamed folders too.
- **Each account is its real address** (vacation replies and filter
  redirects work); log in with the full address.
- **Webmail:** special folders are Stalwart's ("Sent Items", "Junk Mail",
  "Deleted Items", "Drafts") unless `etc/roundcube/config.inc.php` names
  others; HTML mail in dark mode (auto, invert, off; Settings > Preferences >
  Displaying Messages).
- **Stalwart's spam filter stays off for fetched INBOX mail** (measured;
  DECISIONS.md, "No second spam filter on fetched mail"): the provider judged it already.

### Upgrade from v2026.10.13

- **Take a backup first: no rollback** to v2026.10.13 once this release ran
  (the accounts become their real addresses). Releases before v2026.10.14
  that renamed nothing yet must go through v2026.10.14-rc.6; deploy says so.
- Make `etc/` private if deploy asks (`chown -R root HOME/etc && chmod -R
  o-rwx HOME/etc`).
- `folders.yaml` is required: copy `release/folders.example.yaml` to the
  home (or, before the upgrade, to `etc/`) and adapt it. Mail already
  fetched stays where it is (e.g. `INBOX/Sent`): move it in webmail once.
- The upgrade moves `etc/accounts.yaml` and `etc/folders.yaml` to the home
  and leaves links in `etc/` for going back to an older release (deploy
  prints that command); delete the links when you no longer need them.
  `etc/compose.override.yaml` is refused: move it to the home (its paths
  then start at the home).
- `accounts.yaml`: `auto_resieve` and `inbound.folders` are unknown keys now
  (`resieve: {enabled: false}`; folders to leave out: `skip` in
  `folders.yaml`). `etc/bridge.env` needs only `JMAP_PASSWORD`;
  `etc/deploy-backup` is ignored.
- The home itself may be open (`chmod 755 HOME`), so you can `cd` into it
  and run `sudo docker compose`; setup makes new homes so. What must stay
  private (`accounts.yaml`, `folders.yaml`, `etc/`) deploy still checks;
  `data/` stays 0700.
- The first start restarts Stalwart once (to open port 2525).
- Copies and appends made before the upgrade were not recorded as yours;
  resieve may move such mail.

## v2026.10.13

- Without a Nextcloud account in Contacts, Roundav's cloud buttons are
  hidden too ("From cloud" in the composer, "Save all" and "Save to cloud"
  for attachments); before they were shown and failed with an error.
- Nothing to configure; no data changes. Rollback to v2026.10.12 is a plain
  redeploy of `release.previous/`.

## v2026.10.12

- **Files and Talk in the left bar,** after Calendar: links into your
  Nextcloud (its Files and Talk apps), opened in a new tab. Shown only with a
  Nextcloud account in Contacts (like Calendar); Talk only when that
  Nextcloud has Talk installed.
- **Invitations go to Nextcloud's default calendar:** accepting an
  invitation preselects the calendar your Nextcloud marks as default
  (Nextcloud: Calendar settings, "Default calendar"); before, the last
  calendar in the list. A calendar chosen in Roundcube's own calendar
  settings still wins. Side effect: Roundcube no longer offers to delete
  that default calendar (Kolab treats a default calendar as not removable).
- Both are read once per webmail session: log out and in once after the
  deploy to see them.
- Nothing to configure; no data changes. Rollback to v2026.10.11 is a plain
  redeploy of `release.previous/`.

## v2026.10.11

- The remaining Roundav patch after an independent review, as it goes
  upstream: errors while listing folders are reported like Roundav's own
  listing errors; nothing visible changes.
- Nothing to configure; no data changes. Rollback to v2026.10.10 is a plain
  redeploy of `release.previous/`.

## v2026.10.10

- Our remaining Roundav patch now has the shape we propose upstream: a
  setting `roundav_folder_count_property` (off by default) instead of
  Nextcloud's property name in Roundav's code. `mailstack_cloudfiles` sets
  it, as before only for a Nextcloud that reports subfolder counts. No
  visible change: one-level folder tree with exact expand arrows.
- Nothing to configure; no data changes. Rollback to v2026.10.9 is a plain
  redeploy of `release.previous/`.

## v2026.10.9

- **Cloud files: names with `+` or `%xx` work** (e.g. `C++`): shown right
  and open; before, `C++` showed as `C` and could not be opened, and "Save
  to cloud" into it went to another folder.
- Roundav 3.2.0, its first release with our contributions (#25): our
  folder-creation fix, the `+`/`%xx` fix, and settings for what our own
  hook did (login with the first request, Nextcloud's session kept);
  `mailstack_cloudfiles` turns them on. One local patch remains: exact
  expand arrows from Nextcloud's subfolder counts (still offered upstream).
- Roundav now keeps its own Nextcloud session beside the one the calendar
  uses: one more Nextcloud login per webmail session (~0.5 s, once).
- Roundav's folder cache is versioned: the first tree after the deploy is
  read fresh.
- Nothing to configure; no data changes. Rollback to v2026.10.8 is a plain
  redeploy of `release.previous/` (it brings the `+`/`%xx` bug back).

## v2026.10.8

- **getmail verifies your providers' certificates** (chain and host name).
  Before, it checked neither: someone on the path to a provider could have
  read the provider password. After the deploy, watch getmail's log for a
  minute: `docker logs --since 5m boring-mailstack-mail-getmail-1`. A
  provider whose certificate is not valid now fails with `certificate verify
  failed` (for that account only); the cure is the provider's certificate,
  not switching the check off.
- **The bridge's duplicate check** (folders other than the Inbox) also
  recognises a mail fetched again with different getmail header lines, and
  looks beyond the 50 newest mails of a folder (200 with the same subject).
- **resieve is much faster:** a dry run over 49k mails took 222 s, now
  about 7 s when the active filter only reads header fields (Roundcube's
  usual filters), about 38 s otherwise. It pauses and retries when Stalwart
  rate-limits it, and applies moves 500 at a time. `RESIEVE_FULL_MESSAGES=1`
  forces whole messages.
- **Automatic resieve after a filter change** (new service
  `resieve-watch`): about a minute after someone saves a filter in
  Roundcube, resieve applies it to that account's existing mail. The first
  start only records the current filters. Logs:
  `docker logs boring-mailstack-resieve-watch-1`. To leave an account out,
  add `auto_resieve: false` to it in `etc/accounts.yaml`.
- **Stalwart's request limit** per account goes from 60,000 to 600,000 per
  minute (set by init on deploy; DECISIONS.md).
- `tools/deploy` gives its commands no terminal input (the "staircase" after
  the first smoke check should be gone).
- Test tooling only: unit tests, browser checks in the acceptance test,
  resieve benchmark.
- Nothing to configure, no data changes. Rollback to v2026.10.7 is a plain
  redeploy of `release.previous/`.

## v2026.10.7

- The Kolab patches after their independent review (the versions offered to
  Kolab): the DAV user is looked up once per request (fewer requests for
  calendars of other users), the folder-info cache entry is also dropped
  after a change, docs and commit messages tidied. Behaviour as in
  v2026.10.6; nothing to configure, no data changes.

## v2026.10.6

- **Invitations and replies in Sent:** invitations, updates and replies sent
  by the calendar (and tasks) now get a copy in the user's Sent folder, like
  any other mail. On by default; each user can switch it off under
  Settings → Preferences → Calendar → Event Invitations.
- Kolab's calendar plugins carry exactly the six changes prepared for Kolab
 . Besides the above: the SQLite schema
  installs and upgrades cleanly; on the first start the plugin-table task
  logs `updating tables for libkolab (at 2026013000)` and adds the index
  that was skipped at install (version 2026100700). The folder-info cache is
  now an option (`dav_cache_folder_info`), on in our defaults as before; it
  matters for calendars shared by other Nextcloud users.
- `tools/demo down` needs `--yes` (lab tooling only).
- Nothing to configure; the only data change is that one index. Rollback to
  v2026.10.5 is a plain redeploy of `release.previous/` (the extra index and
  version stay; harmless).

## v2026.10.5

- **Security fix (regression since v2026.10.3):** the cloud folder tree
  accepted `..` in a folder path, so a logged-in user could list their own
  WebDAV root at the Nextcloud (calendars, address books by name) outside
  "Files". Only with their own Nextcloud login; Nextcloud's permissions
  applied. Now rejected ("Path traversal detected"), as in plain Roundav.
- Creating a folder inside a cloud folder whose name contains a space (or
  another character that needs URL encoding) works; before, it failed with
  "The resource you tried to create already exists".
- Roundav 3.1.0 (its current master, 7000626) with exactly the three changes
  offered upstream. New in 3.1.0: the optional
  `driver_curl_http_version` setting (unset here).
- league/commonmark 2.10.3 (two advisories against 2.10.0).
- Still open, reported upstream: names with `+` or `%xx` (e.g. `C++`) are
  shown wrong, and "Save to cloud" into such a folder lands in another one.
- Nothing to configure; no data changes. Rollback to v2026.10.4 is a plain
  redeploy of `release.previous/` (it brings the `..` regression back).

## v2026.10.4

- Accepting a calendar invitation works when the webmail login differs from
  the Nextcloud user name (e.g. a mail address in webmail, a short name at
  Nextcloud). Before, all calendars counted as someone else's: invitations
  offered no calendar ("No calendar found to save the event") and calendar
  names showed the owner in front. Fixed by a libkolab patch
  (`roundcube/patches/kolab/libkolab-owner-dav-user.patch`).
- The calendar invitations are saved to is chosen per invitation ("save in");
  the preselected one is Settings → Preferences → Calendar → "Create new
  events in".
- Nothing to configure; no data changes.

## v2026.10.3

- Cloud files faster: Roundav sends the Nextcloud login up front and reuses
  Nextcloud's session (shared with the calendar and the identity check), and
  loads the folder tree one level per request. Measured on a Nextcloud 35:
  a folder listing ~0.55 s with a fresh login, ~0.1 s in a
  session; opening "Attach from cloud" lists one folder instead of all
  top-level ones, with each folder's subfolder count from the same request
  (Nextcloud's `nc:contained-folder-count`), so expand arrows appear only
  where there are subfolders. Gated per session: the identity check at the
  start of a Roundcube session asks the Nextcloud whether it reports these
  counts; without them Roundav keeps listing two levels (its default).
- Nothing to configure; no data changes. Rollback to v2026.10.2 is a plain
  redeploy of `release.previous/`.

## v2026.10.2

- **Calendar and cloud files in Roundcube.** For each user who has added
  their Nextcloud under Settings → CardDAV, the Calendar (their Nextcloud
  calendars, read and write) and *Attach from cloud* / *Save to cloud*
  (their Nextcloud files) work with that same login. Users without one see
  no Calendar button; opening the calendar leads to the CardDAV settings
  with a note. Nothing to configure in `etc/`.
- Roundcube asks the Nextcloud once per session who the user is
  (`current-user-principal`). A wrong CardDAV password therefore counts
  as a failed login at the Nextcloud, as the Contacts sync already does.
- The first start creates the calendar's tables in the Roundcube database
  (`40-mailstack-plugin-db`, logged by the container). Rolling back to
  v2026.10.1 leaves them unused; no restore needed.
- Folders the bridge creates are subscribed from now on. Folders it
  created before may still be unsubscribed: tick them once under
  Settings → Folders.

## v2026.10.1

First release in the release layout (DEPLOY.md): Stalwart 0.16.23,
Roundcube 1.7.4 with Filters and Contacts (RCMCardDAV), getmail, bridge,
provenance, resieve and relay; `tools/make-release`, `tools/deploy`,
`tools/uninstall` and the demo.
