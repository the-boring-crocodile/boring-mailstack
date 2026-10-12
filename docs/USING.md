# Using boring-mailstack

What happens to your mail, and what you can do with it. For the people who
read mail here; the operator's side is in DEPLOY.md, the settings per
mailbox in `accounts.example.yaml`.

## Logging in

Open the webmail address your operator gave you and log in with your **full
email address** and the password of your mailbox at your provider. When you
change that password at the provider, tell your operator: the mailstack
needs it too (it is the same password here, set again at every start).

Your mail stays at your provider: boring-mailstack fetches a copy and never
deletes anything there. Sending goes through your provider as well, so your
mail looks exactly as if you had sent it from there.

## Where arriving mail goes

- **Your provider's Inbox goes through your filter.** Filters are under
  Settings → Filters. A mail no rule matches lands in your Inbox.
- **What you sorted at your provider stays sorted.** Mail in any other folder
  at your provider arrives in the folder of the same name here, and your
  filter never touches it.
- **Spam stays spam unless your filter says otherwise.** If your operator
  lets your filter see your provider's Junk folder, a rule can rescue a mail
  from it; everything else lands in Junk, marked as junk.
- **A new mailbox brings its whole history**, folder by folder, the first
  time. Large mailboxes take a while.
- **Mail you send to yourself arrives** in your Inbox, and your Sent copy
  stays in Sent.

## Things your provider does

- **Moving a mail at your provider moves it here** (once fetched again), and
  from then on it counts as sorted by you.
- **Gmail labels:** a mail with two labels is one mail in two folders here,
  not two copies.
- **Spam and trash at your provider are places, not labels:** marking a mail
  as spam (or deleting it) at Gmail moves it here into Junk (or Trash), out
  of every other folder; "not spam" or restoring it there brings it back.
- **Gmail's "All Mail" is not fetched** (it would only duplicate every other
  folder).
- **Your provider's copy of what you sent** (many providers keep one) does
  not appear a second time next to the webmail's Sent copy.
- **Only what arrives somewhere is seen.** A mail that leaves a folder at your
  provider *without* landing in another one stays where it is here: deleted
  for good at the provider, or **archived in Gmail** (Gmail's archive only
  removes the Inbox label; the mail is then in "All Mail" alone, which is not
  fetched). Archive and sort in this webmail, and it is always right; in
  Gmail's own app or web page, archive leaves the mail in this Inbox.

Nothing is fetched twice by a restart or an update. After a crash or a
power cut a mail may, rarely, arrive twice; none is ever lost.

## When you change your filter

About a minute after you save a filter, mail it placed earlier is sorted
again by the new rules ("resieve"). It never moves:

- mail **you** placed: moved or copied by hand here, or sorted at your
  provider before it was fetched;
- mail in **Sent, Drafts, Trash and Junk** (your operator can let your
  filter pull mail out of Junk; a mail it files elsewhere then loses its
  junk mark).

Your filter's actions run only for new mail: re-sorting old mail moves it,
but sends no vacation reply, no redirect and no copy anywhere.

If the re-sorting cannot be finished (a very busy mailbox), a notice arrives
in your Inbox; saving the filter again tries again.

**Re-sort single mails, or reorganise your folders:** move mail into your
Inbox. It forgets that you placed it, and after about a minute your filter
sorts it; if no rule matches, it stays in the Inbox. So: create the new
folders, write the rules, move the old folder's mail into the Inbox, done.
Read and unread stay as they were.

![The life of a mail: your filter files two newsletters, A and B, into News. You move B to Keep: from now on the filter leaves it alone. You change the filter to file newsletters into Reading: A moves there, B stays in Keep. You move B to the Inbox: the filter takes it back and files it into Reading.](architecture/life-of-a-mail.svg)

**"Not spam":** moving a mail from Junk to your Inbox keeps it there (unless
a rule files it elsewhere), whatever the spam check said.

## Dark mode

In dark mode the webmail shows HTML mail dark too: mail that sets no colours
of its own (most personal mail) gets a dark background and light text;
designed mail (newsletters, receipts) stays white, as its colours would not
work on dark. Settings > Preferences > Displaying Messages > "HTML mail in
dark mode" also offers inverting every HTML mail, or always white.

## Good to know

- **Vacation replies answer spam too:** the vacation rule does not skip mail
  the spam check marked (mailing lists, bulk mail and automatic messages are
  skipped).
- **Filters and old mail:** when mail is imported into a mailbox that
  already has a filter with a vacation reply or a redirect, those run for
  the imported mail as well. Switch them off before a mailbox is imported
  or re-imported, and on again afterwards.
- **A "reject" rule discards silently:** the sender gets no bounce, because
  the mail was accepted by your provider long before it reached your
  filter. Use "discard" or a Trash folder to say what you mean.
- **Contacts, Calendar and cloud files** appear once you add your own
  Nextcloud under Settings → CardDAV (ideally with a Nextcloud app
  password).
- The **Files** and **Talk** links open your Nextcloud in a new tab with
  its own login: the webmail's connection to Nextcloud cannot log your
  browser in. Tick "Stay logged in" there once, and the links open
  straight into Nextcloud while you keep using it.
- Moves made with a **JMAP** mail client are not noticed as "placed by you"
  (IMAP clients and the webmail are). Neither is a mail an IMAP client
  stores without a Message-ID (the webmail always sets one).
- Your provider's Inbox mail does not go through this server's own spam
  check (your provider checked it already).
