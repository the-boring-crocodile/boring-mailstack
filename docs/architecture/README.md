# Architecture

![The containers](mailstack.svg)

| Diagram | Kind | Source |
|---|---|---|
| [The containers](mailstack.svg) | C4 container diagram | [mailstack.dot](mailstack.dot) |
| [The way of a mail](way-of-a-mail.svg) | C4 dynamic diagram | [way-of-a-mail.dot](way-of-a-mail.dot), numbers placed by [badges.py](badges.py) |
| [The life of a mail](life-of-a-mail.svg) | dynamic, folders over time | [life-of-a-mail.py](life-of-a-mail.py) |
| [How provenance works](how-provenance-works.svg) | sequence diagram | [how-provenance-works.py](how-provenance-works.py) |
| [Who is trusted](who-is-trusted.svg) | trust boundaries | [who-is-trusted.py](who-is-trusted.py) |

Each `.dot` renders with Graphviz; the `.py` scripts compute fixed positions
and write their `.dot`, rendered with `neato -n2` (the first lines of each
file say how). All five follow one set of rules: C4's notation, a key for
every symbol, no line through any text. Where the five share a symbol,
it means the same: blue boxes are what you see and use, green boxes the
stack's services, grey boxes the outside, dashed green a provenance record.

## The idea

Mail stays with the providers: they receive it from the Internet, keep it
and deliver what you send (with their DKIM). The stack never runs an MX and
never deletes anything at a provider. Locally it keeps one canonical copy in
Stalwart, which all clients use, and remembers where each mail came from.

## Inbound

1. **getmail** polls each account's provider folders over IMAPS (certificates
   verified) and hands each new mail to the bridge. Its state keeps a mail
   from being fetched twice. Before fetching it reads the provider's folder
   list: an "all mail" view (special-use `\All`) is skipped, and each
   folder's special-use role and separator go to the bridge with the mail.
   A stop waits for the mail being handed over.
2. **bridge** delivers into Stalwart, one of three ways, by provider folder
   (DECISIONS.md, "Three ways in"):
   - a folder listed in the account's `inbound_sieve.folders` (default
     INBOX): normal SMTP delivery, so the user's filter runs; no rule →
     INBOX;
   - the provider's Junk, if listed: SMTP on Stalwart's internal second port
     2525, where the spam filter runs and a rule makes it spam: the filter
     still decides, what it leaves in INBOX goes to Junk;
   - any other folder: JMAP import into the folder of the same name (by
     role for special folders), recorded in **mail-provenance** as placed by
     a human before the mail is acknowledged.

   Copies are found through a per-account Message-ID index the bridge keeps
   with JMAP `Email/changes` (Stalwart cannot search Message-IDs) and
   compared exactly (Message-ID, From, Date, Subject, body): an earlier
   attempt is not stored twice; a mail moved at the provider moves here; a
   mail in a second provider folder (labels) gets that folder too; the
   provider's own Sent copy is skipped.

## Provenance and resieve

**mail-provenance** (Python, SQLite) records, per account and stable JMAP
Email ID, the placements a human made: in a provider folder before the
fetch ("human, elsewhere"), and here, reported by Stalwart's webhook — IMAP
MOVE, COPY and APPEND (Roundcube's Sent and Drafts). Deliveries, Sieve and
resieve's own moves are never protected.

Known limit: Stalwart reports an APPEND with the mail's Message-ID, not its
ID, so provenance finds the mail by Message-ID. A mail appended without one
(Roundcube always sets it; some other IMAP clients or import tools may not)
is not recorded: outside `never_move_from` folders a later filter change
may move it. The event is logged and skipped.

**resieve** (Rust, JMAP) applies an account's active Sieve filter to mail
already in the mailbox (DECISIONS.md, "resieve puts unprotected mail where
the filter says"): it skips protected mail and mail in the account's
`never_move_from` folders (default Sent, Drafts, Trash, Junk), computes the filter's full
placement (`:copy`, several `fileinto`, keep), and puts the mail exactly
there. Before writing it looks again (protection
re-read, `ifInState`).
**resieve-watch** runs it by itself about a minute after a filter is saved
in Roundcube (DECISIONS.md).

## Outbound

Clients submit to Stalwart; Stalwart passes all non-local mail to the
**relay** (Postfix), which sends each sender's mail through that sender's own
provider, authenticated and certificate-verified. Only the configured
addresses may send.

## Webmail

**Roundcube** 1.7 talks to Stalwart (IMAP, SMTP, ManageSieve) and adds
Filters and Contacts (RCMCardDAV, each user's own addressbooks). For a user
with a Nextcloud account in Contacts, `mailstack_cloudfiles` hands that login
to Kolab's calendar (CalDAV) and to Roundav (attach from / save to Nextcloud
files) and adds Files and Talk to the left bar. `roundcube/README.md` has the
image's details.

## One-shot services

**prepare** creates the data directories; **init** generates the services'
configuration from `accounts.yaml` and provisions Stalwart (accounts,
passwords, the bridge's login, webhooks, limits) at every start.

## Networks

One Compose project, three networks. `mail-internal` connects the services
and is not marked internal: getmail and the relay reach the providers through
it. `webmail` joins only Roundcube and Stalwart and is not internal either:
Roundcube reaches the users' Nextclouds through it, but not provenance, the
bridge or resieve-watch (deploy checks this). `relay-internal` is internal
and joins only Stalwart and the relay. Only the webmail and Stalwart's admin
UI are published on the host. The demo makes the mail and webmail networks
internal, so a demo cannot reach a real mail server. Inside the stack, clients do not verify
Stalwart's self-signed certificate (DECISIONS.md, TLS).
