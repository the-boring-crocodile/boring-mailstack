# The story

How boring-mailstack came to be, and how it was built. Both at once,
because that is how it happened: the mail stack, the place where the
AI works, and the server they both run on grew side by side, and each one
shaped the others. The mail stack came in phases, between work on the
other two.

I am Wald, the human here. All of it — the code, the tests, the docs,
this page — was written by AI: by an agent that works on my home server
under the name "The Boring Crocodile" (`<^==>`), driven by OpenAI's
models and Anthropic's Claude, depending on the session. What to build
we worked out together; I tested it, ran it and had the last word. This
document says who did what wherever it matters.

It started with my own mail. For about twenty years I have used a
catch-all address on a domain of my own: every website that wants an email
address gets one of its own. Websites get hacked, dubious ones sell their
lists, services close down and their data ends up somewhere. So a lot of
mail arrives, and a lot of spam with it. To bring order into it, I glued a
mail stack together from ready-made Docker images and a few hacky scripts.
Mail is a pain, and I am a tinkerer: once it worked well enough, it ran.
For years.

What changed were the tools. With AI agents I could finally build it
properly, the mail stack and the rest of my server, which had grown the
same way, and learn the new way of working while doing it.

## A first version, and a philosophy

The first version (`mailstack_v2`) ran on my home server in September
2026, replacing the glued-together stack: getmail fetching from the
providers, Stalwart as the local mail server, Roundcube as webmail, and a
small relay sending through each provider. It was built in long sessions
with heavy AI support, before any of the tooling described below existed.
Two ideas from that time carried through to today:

- **Provenance.** Its design already recorded where a human had put a
  mail, so filters could be re-applied later without undoing anyone's own
  filing.
- **Boring on purpose.** The aim: *prefer the design that will be boring
  to understand at 02:00 five months from now.* The crocodile `<^==>`,
  born as a subject prefix for a mailing list a week earlier, became the
  shorthand for that.

It worked, but it was a working installation, not something anyone else
could install: no releases, no upgrade path, configuration and code mixed
in one directory, knowledge in long design documents and in the AI's
context, which is gone after every session.

## A home for the work

That became [Pond](https://github.com/the-boring-crocodile/boring-pond):
the working environment we built for the Boring Crocodile and its fellow
AI assistants. Pond gives them tools to work on the server and a shared
handbook, project map and written decisions, so a new session can pick up
where the previous one stopped.

The mail stack became one of Pond's projects. We imported its source and
documents into a repository, leaving live mail and credentials in place.
Alongside it, we used Pond to clean up the server's backups, proxy and
service ownership. The release and recovery practices tried there became
part of how we build and deploy the mail stack.

## From an installation to a product

One short, intense phase turned the installation into something with
releases:

- **A demo that is also the acceptance test.** `tools/demo up` runs the real
  stack against a simulated provider, with the mailboxes of Pond Ltd: four
  colleagues, one season of office life, told only in email. Its first
  full run found three bugs that would have reached production: a webhook
  pointing at an old container name, folder names compared in two
  different encodings (no provenance for any folder with an umlaut), and a
  retry that imported a mail twice. Every release since has had to pass
  it.
- **Releases and a deploy tool.** Artifacts built from a tag with a
  manifest of every file; a deploy that verifies, builds, checks, switches,
  smoke-tests and prints the way back.
- **A rehearsed move.** The old installation was copied from the backup
  into an isolated test home, upgraded and rolled back again: 67,417
  messages in 33 folders, identical before and after. Then the real
  cutover took four minutes, one afternoon in early October.

## Living with it

The first days in production were the most productive ones, because
every rough edge was now my own daily mail:

- **Nextcloud** became the centre: the calendar inside the webmail
  (Kolab's plugins, against my own Nextcloud), files through Roundav,
  Files and Talk in the sidebar. Accepting an invitation failed because my
  Nextcloud user name differs from my mail address; a calendar view took
  30 to 45 seconds. Both were dug out, measured and fixed.
- **Upstream instead of forks.** The fixes went back where they belong:
  an issue with tested branches to Roundav (taken into its release 3.2.0
  the next day), six findings for Kolab's calendar plugins.
- **Filters that follow you.** `resieve` re-applies a changed filter to
  old mail and runs automatically about a minute after a filter change.
  Making that practical meant removing unnecessary work: fetch message
  details in batches, reuse one connection for downloads, and skip bodies
  and attachments when the filter only needs headers such as sender and
  subject. On a test copy of a real mailbox with 48,987 messages, those
  changes took a dry run from 222 seconds to 7, with the same filing
  results. Filters needing whole messages took about 38 seconds.

Many small releases, each one deployed by me, checked live, and only then
called final. Reversible releases had a one-command way back; later upgrades
that changed the data required a pre-upgrade backup instead.

## Rethinking the way in

A review found that provenance "failed open": every placement it had not
heard of counted as free to move. The rule was turned around: only what a
human placed is protected, and everything else goes exactly where the
filter says. With that came a cleaner model for how mail enters the
stack ("three ways in"), a Message-ID index for copies and labels, and
accounts that are their real addresses, so vacation replies leave from
the right sender.

## Real providers

Gmail joined, with its labels, its two "Sent" folders and its arrival
dates. Two of my decisions from that phase shape the product:

- **Mirror reality.** The stack shows the provider's mailbox as it is, odd
  folders included. It leans on the structure your provider already has
  instead of inventing a new folder scheme. This makes the starting point
  familiar when switching between local and provider webmail. It is not
  two-way synchronisation: local rules and deliberate filing can make the
  two copies differ.
- **No spam filter of our own.** The question was whether to run
  Stalwart's filter a second time over mail the provider had already
  filtered. Instead of arguing, we measured with real mail: even with the
  sender checks off, 7 of 25 good Inbox mails would have landed in Junk.
  It stays off.

And one of comfort: the installation became a plain Docker Compose
project, `docker compose up -d` and `down` in its directory, like every
other service on the server.

## Ready to share

The whole repository was reviewed against our written engineering
practice, everything found was fixed, and every test suite passed. The
full runs caught one mistake the agent had made in those fixes (a CSS
selector that would have shown every picture as a negative) and one that
had been waiting in the image build (files the web server could not
read, once the build tool changed). Then: a licence
(AGPL-3.0), a review of everything public for private details, and this
document.

## How it was built

**Working together.** Design and architecture are worked out together,
in conversation: I bring the direction, the constraints and what I see
in daily use; the agent brings research, the knowledge of how others
solved it, options and their trade-offs, and objections when an idea of
mine has a hole. Most decisions in DECISIONS.md came out of such an
exchange. It is a colleague to think with, not a tool I point at code.

**Who does what.** Then the work divides. The agent writes the code, the
tests and the documents, runs the test suites, and prepares every step on
the server as a block I run myself. I test in production and do
everything that needs root. Where we disagree, I have the last word, and
I am the one who answers for the result. The agent does not touch
production, and nothing it writes leaves the server without my approval
of the exact text: not an issue, not a mail, not a commit to someone
else's project.

**Memory.** The agent starts every session from what is written down: a
status log, a work list, the decisions with their reasons. "Write it down
where the next one will find it" is the rule that makes the rest work.

**Guardrails that caught real mistakes.**

- *Tests before release.* The acceptance demo caught three bugs before the
  first release, and a trial installation caught an image build that no
  longer worked, though nothing in our code had changed.
- *Measure, then decide.* Calendar speed, resieve speed, the spam filter:
  each decision has a number behind it, recorded in DECISIONS.md.
- *Fresh eyes.* Before anything went upstream, an independent agent that
  had not seen the work reviewed it.
- *Commit only when green.* After the agent once put untested work on the
  main branch, all work moved to branches that are merged only after the
  tests pass.

**Decisions with a name on them.** Some calls were mine alone, on what
the product is for: mirror reality, a plain Compose project like every
other service here, no single sign-on into Nextcloud ("way too heavy for
a little convenience"). Others we reached by measuring first, like the
spam filter. Either way the decision and its reason go into DECISIONS.md.

**Looking back.** What surprised me most was how much we could build
together. The mail stack also helped shape Pond and our working
agreement: the agent wrote down the practices we had developed along the
way, so we could carry them into the next project.

I hadn't expected to find a productive way of working with AI so quickly.
I'm still figuring out what to make of it, but I enjoy it. It feels a bit
like being MacGyver in an Iron Man suit: I bring the ideas and the
willingness to tinker, with far more capability at my disposal than before.

If I started again, I would take a firmer hand earlier. At first I left
too many decisions to the agent. The work improved when I became clearer
about what I wanted, questioned its choices and made the important calls
myself. That, I suppose, is how you learn it.

## In numbers

These figures describe the initial development period, not the current
release.

- About 390 commits, September and October 2026. The public repository
  starts with one: the history holds details of my own server and stays
  private.
- Six test suites, the largest a full acceptance run from nothing back to
  nothing (about 20 minutes).
