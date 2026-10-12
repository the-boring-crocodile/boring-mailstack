# The boring-mailstack demo

The whole stack, running against a simulated mail provider, with four
mailboxes full of three months of office life. Try it without handing
anyone a real password.

```bash
tools/demo up          # first run builds images; prints the URL and logins
tools/demo logins      # print them again
tools/demo reset       # start the story over (same URL and logins)
tools/demo down --yes  # remove everything the demo created
```

Open the printed URL — it shows this machine's LAN address, so it works
from your laptop when the demo runs on a home server — and log in as
`croc@pond.test`, `otter@pond.test`, `tim@pond.test` or `brog@pond.test`
(passwords in `tools/demo logins`).
Each of them sees a different story.

Needs Docker with Compose, `python3` and `openssl`. Rootless Docker works.

## What you are looking at

**Pond Ltd** ("Bespoke Water Features & Digital Solutions") is moving its
email to a new platform. The Management wants it done by Friday. The demo
mailboxes hold one season of what happened next — *Operation Lighthouse*,
an office sitcom told entirely in email, in six episodes and 271 mails.
Every account has its own perspective and its own private life. The canon
is `demo/story/BIBLE.md`; reading it first spoils the story.

## What the demo does

```
 story files ──seed──▶ demo provider (GreenMail, IMAPS/SMTPS)
                          │  ▲
                 getmail  │  │  relay (Postfix)
                          ▼  │
                  bridge ──▶ Stalwart ◀── Roundcube (you) ──▶ Pond Cloud
                     │          │
                     └─▶ provenance ◀─ telemetry (human moves)
```

1. `tools/demo up` creates a demo directory (default
   `~/.local/state/boring-mailstack-demo`): a throwaway CA, the provider's
   certificate, four accounts with random passwords, and the stack's
   `etc/` and `data/` in the same layout as production.
2. **demo-seed** renders the story into real messages — threads,
   attachments, calendar invitations, mailing-list mail, auto-replies,
   spam — and files them at the provider the way each character keeps
   their mailbox (`demo/story/filing.yaml`), before the stack starts.
3. The stack's **first import** brings it all across, folder for folder,
   and provenance records every mail imported outside an Inbox.
   Replies carry the conversation quoted below them, as after *Reply*,
   so an Inbox reads as a whole conversation without visiting Sent.
4. From then on it is a working mail system: what you send leaves through
   the relay, arrives at the provider and is fetched back in.
5. **Pond Cloud** (`demo/cloud`) stands in for the Nextcloud a real
   installation's users bring: each character has a calendar with a few
   routine appointments, an addressbook of colleagues and a few files.
   Roundcube connects everyone to it at first login (a demo-only Contacts
   preset), so **Contacts**, **Calendar** and **Attach from / Save to
   cloud** work at once. In production each user adds their own Nextcloud
   under Settings → CardDAV, and Calendar and cloud files follow from that
   account; without one the Calendar button stays hidden.

**Network:** by default the demo listens on all interfaces, so others on
your network can reach its webmail (plain HTTP, throwaway passwords, no
real mail). That is on purpose: most people run it on a home or office
server, or in Docker Desktop, and open it from another computer. On a
network you do not trust (a café's Wi-Fi), use `--bind 127.0.0.1` to keep
it to this machine.

**Safety:** getmail and the relay trust only the demo's own CA, and the
mail network has no route to the Internet, so a demo cannot reach a real
mail server, even by mistake. Stalwart and Roundcube are also on an
ordinary Docker network each (Stalwart needs DNS to start, Roundcube
publishes its port), so those two can reach the Internet.

## Options

```
tools/demo up --bind 127.0.0.1      # this machine only (default: all interfaces)
tools/demo up --port 18680          # Roundcube port; Stalwart admin on port+1
tools/demo up --tz Europe/Berlin    # time zone of the story's dates
tools/demo --dir PATH up            # demo directory
DEMO_PROJECT=name tools/demo up     # a second demo beside the first
```

`--bind`, `--port` and `--tz` take effect when the demo directory is
created; to change them, `tools/demo down --yes` first.

The story's dates are relative to the moment of seeding, so a demo always
looks recent. The provider (GreenMail) keeps its mail in memory: after
`down`, everything starts fresh.

## The acceptance test

`tests/demo/run.sh` runs the demo from nothing and checks it:

- **first import** (`verify_import.py`): every story mail in exactly its
  owner's folder, no duplicates, provenance for every mail imported outside
  the Inbox;
- **live** (`roundtrip.py`): a mail sent through Stalwart comes back via
  relay and provider; a mail to oneself arrives; webmail, Filters, Contacts
  and the demo cloud work; a human move into a folder with an emoji is
  recorded by provenance; the mail network has no Internet;
- **inbound paths** (`inbound.py`): provider Junk through the filter,
  provider moves and labels, filter changes, the re-sort chute, "not spam";
- **mail Stalwart writes itself** (`vacation.py`): a vacation reply leaves
  from the real address.

It uses its own Compose project, so a demo someone is reading is not
touched. Run it before every release.

## Files

| Path | What |
|---|---|
| `tools/demo` | the command |
| `demo/compose.demo.yaml` | overlay on the production `compose.yaml` |
| `demo/seed/` | renders and seeds the story |
| `demo/cloud/` | Pond Cloud: a small CardDAV/CalDAV/WebDAV server standing in for Nextcloud |
| `demo/story/` | the season: bible, cast, filing habits, episodes, attachments; `story.py check` validates it |
| `tests/demo/` | the acceptance test |
