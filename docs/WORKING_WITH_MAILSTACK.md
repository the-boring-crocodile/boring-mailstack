# Working with mailstack

You already have mail providers. You want a place of your own to read their
mail, connect your Nextcloud, and make filing rules useful for messages
that accumulated before you wrote them.

boring-mailstack keeps a local mail store for that work. Providers still
receive internet mail and send outgoing mail for your addresses. This guide
explains choices and everyday use; [deployment](../DEPLOY.md) owns installation
commands and [Using mailstack](USING.md) owns the behaviour reference.

## Choose your starting point

| Your situation | What helps | What you still own |
|---|---|---|
| You want self-hosted webmail for existing addresses | Roundcube over local copies, sending through each provider | Provider accounts and a trusted operator |
| Years of mail need new filing rules | Re-filter old mail while respecting deliberate placements | The rules and the decision to hand manually filed mail back |
| Contacts and files already live in Nextcloud | Connect each user's own account inside Roundcube | Nextcloud and its browser sign-in |
| You are bringing history from an old system | Retain a local copy without age-based expiry | A reviewed import route, source archives and backups |

The last row is an operating responsibility, not a general migration wizard.
An old private import script is not a supported deployment command.

## Read and send from your own webmail

After the operator adds an account, the stack fetches its selected provider
folders. Log in at the webmail URL with the full mail address and its inbound
provider password. Each address remains its own account; multiple configured
accounts do not imply one combined Inbox.

The first fetch can take time. Mail then arrives through the provider as
before. When you send from Roundcube, the local relay submits through that
address's configured provider. You do not need to take over internet mail
delivery or run an MX server.

Your operator has those provider credentials and can read local mail.
Choose this arrangement for people who trust that operator.

## What travels where

A local copy is useful, but “mirror” can suggest more synchronisation
than the stack provides.

| Action | What happens here |
|---|---|
| Mail arrives in a fetched provider folder | It is fetched and receives the configured delivery/filing treatment |
| A provider-side move is encountered in its destination folder | Its placement is reflected locally, subject to provider rules |
| You file mail in Roundcube | The local mailbox changes; supported human placements are recorded |
| You send mail locally | The account's provider sends it |
| Mail disappears at the provider without a fetched destination | The absence does not request a local deletion |
| The provider expires its own copy | The stack's no-delete policy at the provider cannot reverse that |

Gmail adds a wrinkle: labels can give one message several folder memberships.
The stack skips its All Mail view. Archiving only at Gmail can therefore leave
a message in the local Inbox, because no new fetched destination tells the
stack where it went. [Provider behaviour](USING.md#provider-changes) has the details.

Use local webmail as your daily filing place if you want its rules and
provenance to govern that filing. Keep provider access for when you need it,
but do not expect every action on either side to be replayed on the other.

## Reorganise mail you already have

A rule that only handles future arrivals leaves yesterday's work to you.
Mailstack also applies changed rules to eligible existing mail.

For a small demonstration in the fictional demo mailbox:

1. Create a folder called Reading.
2. Add a filing rule for a recognisable newsletter sender.
3. Save the rule and allow about a minute for re-filtering.
4. Check that eligible matching messages moved to Reading.

A mail you previously moved into Keep should remain there: provenance records
your placement. Rules can evolve without undoing individual decisions.

To deliberately re-filter manually filed messages, move a small selection
into Inbox. That is the hand-back operation: after a quiet period the filter
can file them again. With no matching rule they stay in Inbox. Read/unread
flags are retained.

Start with a small selection so you can check the result before reorganising
a large folder. Moving mail into Junk can also hand it back to the filter,
depending on whether that account allows Junk to be re-sorted. By default the
filter never takes mail out of Sent, Drafts, Trash and Junk.

Re-sorting old mail changes placement. It does not send vacation replies or
redirect those old messages. **Initial fetching or re-import is different:**
active delivery rules can have those effects. Disable vacation and redirect
rules before bringing historical mail through such a route.

Supported human-placement signals come from IMAP clients and Roundcube.
JMAP-client moves and IMAP APPEND without a Message-ID have limitations.
Read [the exact rules](USING.md#filing-and-filter-changes) before relying on
another client or import tool.

## Bring your Nextcloud along

You already maintain contacts, calendars and files in Nextcloud. Keeping
another independent set in the mail stack would create another thing to
synchronise.

In Roundcube, add your own Nextcloud under Settings → CardDAV, preferably
using a Nextcloud app password. The integration uses that connection for
contacts, calendar and file access. Try reading a contact and opening your
calendar before relying on it for daily work.

Files and Talk open Nextcloud in a new browser tab. They use Nextcloud's own
browser session; signing in through the contact connection does not sign that
tab in. “Stay logged in” in Nextcloud can make subsequent visits seamless,
but this is not single sign-on.

Nextcloud remains separate. Other CardDAV or CalDAV servers may partly work;
only Nextcloud is tested for the combined integration.

## Keep history deliberately

A provider login is not a backup plan. Providers can expire mail, and an old
archive may contain messages that no longer exist there.

Updated mailstack provisioning disables automatic age-based expiry of
stored Junk and Trash. Explicit deletion and your own discard rules still
apply. Releases through v2026.10.15 need the
[immediate retention mitigation](../DEPLOY.md#mail-retention).

Before importing history, retain the original archive. Check account identity,
folder mapping, dates, flags and duplicate handling on a small sample before
a bulk run. A count alone cannot establish that the same messages survived.

Back up the local installation, including configuration, credentials and
service data, consistently. Restoring a backup is not the same operation as
re-fetching what happens to remain at a provider.
[Backups and recovery](../DEPLOY.md#backups) explains the boundary.

## Your first useful check

Use the demo to try a rule change and a manual placement. If that behaviour
fits your daily mail, follow [deployment](../DEPLOY.md), add a real account
with its side effects reviewed, and verify fetching and sending before
bringing more accounts or historical archives into the stack.
