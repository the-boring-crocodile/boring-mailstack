# Operation Lighthouse — story bible

The demo mailboxes of boring-mailstack are filled with one season of an
office sitcom, told entirely through email. This file is the canon: who
these people are, how they write, what happens, and which running gags must
land where. Episodes live in `episodes/`, one file per episode, in the
format at the end of this file.

## The form

An **epistolary sitcom** (the lineage: *Les Liaisons dangereuses*,
*Dracula*, and closest of all Matt Beaumont's *e*, a London agency told only
through internal email). One rule above all others:

> **The reader knows only what is in the mails.**

Nothing is narrated. Gaps, unanswered questions, a reply that ignores the
question, the attachment nobody opened — that is where the comedy lives.

**Genre:** a British workplace sitcom season (*The IT Crowd*, *The Office*,
*Fawlty Towers*) with a mystery running underneath. Each episode is closed
and follows the story circle — someone wants something, goes after it, gets
it, pays for it, comes back — and, British rule, **nobody learns anything.**
The status quo returns. The mystery spine is the only thing that moves
across episodes.

### Tone rules

- Deadpan. Failure with dignity. No hugs, no lessons.
- Punch up, never down: the institution and its jargon are the target, not
  people. Every character is fond of the others in their own way, even if
  only Brog would say so.
- Mails must read like real mails: subjects with `Re:` and `Fwd:`, quoted
  text, signatures, the occasional typo where the character would make one.
- Mild language only. No real companies, products or people.
- Short beats real. Most mails are three to eight lines. A long mail is a
  character beat (Croc explaining, Management announcing).

## Four perspectives

There are four mailboxes, so there are **four books.** Each account sees
only its own mail: whoever logs in as Brog reads a different season than
whoever logs in as Otter. The office plot is shared, but every perspective
holds only its slice of it — Brog never sees the mails he is not CC'd on,
nobody but Otter sees Otter's predictions being ignored in full — plus a
**private life nobody else at Pond Ltd knows about.** Each private thread
mirrors the office plot in a smaller key.

| Mailbox | Office slice | Private life (never CC'd, never mentioned at work) |
|---|---|---|
| tim | sales, Mrs Featherstonehaugh, Management | a romantic farce: two dates, one guarantee |
| brog | only what Tim CCs him on | letters to his therapist, who has given up on him; a conspiracy mailing list |
| otter | QA, risk, being right | a deep-tech mailing list flame war; venting about his colleagues to an old friend |
| croc | everything, at all hours | his family: Mum, his sister, a group chat about Gran's birthday |

A reader who logs in to all four can assemble the whole season — like
*Dracula*, where only the stack of documents tells the full story.

## The company

**Pond Ltd** — "Bespoke Water Features & Digital Solutions". Founded to
build garden ponds; "pivoted to digital" two years ago, which nobody can
explain, including the website. Domain `pond.test`. Small: four people with
mailboxes, one Management, and a growing number of companies that want to
sell them things.

## The cast

### TIM — The Inquisitive Mudskipper · `tim@pond.test`

Sales. Title changes every episode (Senior Sales Ninja, Head of Customer
Delight, Chief Possibility Officer…). Happy, optimistic, fast. Exclamation
marks, emoji, "Quick one!", "Huge news!!". Promises things before asking
whether they exist. Genuinely kind: he CCs **Brog** on almost everything
because Brog is his friend and "should be in the loop".

- Voice: `Quick one! 🙌` · `Love this!!` · `Already told them yes 😅`
- Signature: `TIM 🌟 <title of the week> | Pond Ltd | "Every pond is an opportunity"`
- Running gag: **the guarantee.** Each episode his uptime promise to a
  customer gains a nine (99.9 → 99.99 → … → "100.000 %, which is basically
  the same").
- His customer: **Mrs Featherstonehaugh** of Featherstonehaugh Koi
  (pronounced "Fanshaw"). Appears only in mails Tim forwards. Formal,
  terrifying, always correct.

### Brog — The Unassuming Brog · `brog@pond.test`

Facilities, Plants & General. A bit simple, a bit outside, entirely
sincere. Receives mail almost only because Tim CCs him. **Always replies to
all.** Low volume — one or two mails per episode — and every one is a gem:
an odd question, an observation nobody asked for, a quiet conspiracy.

- Voice: all lowercase, no greeting, short. `does the new server know where
  our emails go. asking because of the plants`
- Signature: `brog` (sometimes `brog (plants)`)
- **The mystery spine is his** (see below).

### Otter — The Methodical Otter · `otter@pond.test`

Quality Assurance. Overworked, unfriendly, a doomsday prophet — and,
unfortunately, always right. Numbered lists. Attachments (risk registers,
test reports) that nobody opens. Never says "I told you so": he cites the
**prediction number** instead.

- Voice: `No.` · `Per my previous email.` · `See attached. Nobody will read it.`
- Signature: `Otter | Quality Assurance | It is not fine.`
- Running gag: **predictions.** `Prediction #14: this fails Thursday, 03:00.`
  Every prediction comes true, in a later episode, exactly.

### Croc — The Boring Crocodile · `croc@pond.test`

Developer. Polite, careful, overworked, holds everything together. Answers
the question that was asked *and* the three that should have been. Gives
honest estimates, which are ignored. Writes calm status mails at 03:00.

- Voice: `Happy to help!` · `Three quick questions before we commit:` ·
  `Status: fixed. Cause: below. Coffee: see signature.`
- Signature: `Croc | Development | Pond Ltd` plus `☕ <n> today` — the count
  is a **running gag** and tracks the season's stress level.
- His coffee subscription (BeanThere, see Services) is the subplot that
  tells you how bad things are.

### The Management · `management@pond.test`

Not a person: an office. "The Management — Office of Strategic Vision."
Unrealistic timelines, stupid ideas, delivered in passive-aggressive
marketing bingo. Schedules progress meetings, renames them, cancels them —
and then **never mentions the timeline or the idea again.** Thanks "the
whole team", always the wrong part of it.

- Voice: `As per our alignment` · `north star` · `let's take this offline` ·
  `circle back` · `a quick reminder that we are all owners here` ·
  `Friday is a mindset`
- Calendar: real invitations and cancellations (`.ics`), titles escalating:
  *Lighthouse Sync → Alignment Huddle → Lighthouse Sync (v2) → Vision
  Moment → (cancelled)*
- Signature: `The Management | Office of Strategic Vision | Pond Ltd |
  "Together, we are the pond."`

### The Services (various senders, `*.test`)

Companies that want something. Written as **1920s–1940s magazine
advertisements** (`Gee! Modern businessmen agree…`, `Is YOUR inbox letting
you down?`, `Ask your administrator about…`). Some legitimate, some spam;
the spam lands in **Junk**.

- **BeanThere Coffee Co.** — Croc's subscription. Order confirmations,
  then concern: *"We noticed you ordered 14 kg this month. Are you alright?"*
- **SynergyCloud Ltd.** — webinars, "only 3 seats left!", forever.
- **PondPulse Analytics** — sells dashboards to a pond company.
- **LinkedOut** — "4 people viewed your profile (one of them was a duck)".
- **Pure spam** (Junk): miracle uptime tonic, a prince with koi, a parcel
  that is always waiting, a correspondence course in cheerful replying
  (for Otter), an atomic desk fern (for Brog, who writes back about the
  plants), koi that remember faces, sleep by telegram (for Croc, at 03:58),
  uptime lozenges (for TIM), and **Dr. Mallard's Electro-Tonic Inbox
  Tablets**, the season's one HTML advert, to everyone. Brog keeps no
  filters, so his spam simply sits in his Inbox with everything else.

### The Pirate — Mademoiselle Em · `em@boring-pirates.test`

An external contractor hired by The Management for a **security awareness
campaign**. Impeccable, formal, faintly sinister pirate English. Runs
phishing tests from look-alike domains (`p0nd.test`, `pond-ltd.test`).
Invoices in doubloons. Treats the whole company as a ship to be inspected.

- Voice: `Ahoy. Your mailbox has been selected for inspection.` ·
  `I have boarded your systems with the utmost courtesy.`
- Signature: `Mlle Em | Privateer, Security Awareness | Boring Pirates |
  "We find what you forgot."`
- Her phishing mails go to Junk — except one, which Brog finds, reads as
  confirmation of his theory, and replies to all.
- Final verdict on Pond Ltd: **"seaworthy, barely."**

## The private lives

Only the owner of the mailbox ever sees these. They are never CC'd, never
forwarded, never mentioned at work.

### Brog and Dr Hartley-Moss

**Dr Imogen Hartley-Moss**, `ihm@hartley-moss-practice.test`, Brog's
therapist. She has, professionally and warmly, given up. Brog writes to her
between sessions ("i know we said only urgent things") about the plants,
the headers, the feeling that someone knows where his emails come from. Her
replies grow shorter: from paragraphs with gentle reframing, to
"Thank you, Brog. Let's discuss on Tuesday.", to an auto-reply she seems to
have set up only for him. **The season's only apology is hers:** in the
finale, after Brog forwards her proof, she writes back herself — one
paragraph, no reframing: she read about provenance; he was right; she is
sorry. Brog: `thank you. the plants knew`.

### Brog and the Fog Inquiry

`truth@lists.the-fog-inquiry.test` — "The Fog Inquiry: Asking the
Questions Weather Won't". A small, earnest, entirely harmless conspiracy
list: koi that remember faces, fog that arrives "on schedule", houseplants
that lean towards Wi-Fi routers. **Only invented conspiracies, never real
ones.** Members sign with initials and a weather symbol. Brog is the most
reasonable person on it, which says a lot about the list. He shares his
theory about the new mail server; it is received with great respect.

The twist, built across the season: the list's footer slowly changes —
"Supported by friends of the Inquiry", then "Insights powered by
PondPulse", then, in ep. 5, a footer that is plainly **PondPulse
Analytics'** marketing tracker. The Fog Inquiry is a lead-generation funnel.
Someone *was* harvesting where Brog's emails come from. In the finale
PondPulse sends Brog a cheerful "We noticed your interest in mail
provenance!" offer. Brog unsubscribes, from the list and possibly from
everything. `they were the fog`.

### Otter and Mags

**Margaret "Mags" Pell**, `mags@pell-apiary.test`, Otter's old QA lead,
retired, now keeps bees. The only person Otter writes to without a
numbered list. He vents about his colleagues — Management, Tim, "the
phishing pirate", the meeting — with real venom and perfect accuracy. Mags
answers with bee metaphors, gentle mockery, and occasionally a defence of
the colleagues he is being unfair to. What the vents reveal, never said
out loud: Otter respects Croc ("the only one who reads my attachments — I
suspect he doesn't either, but he pretends better than anyone") and is
fond of Brog ("he asked the only correct question in the building. By
accident. Do not tell him."). Finale: Mags sends a jar of honey to the
office, addressed to "whoever is making him predict things".

### TIM and the double booking

A PG romantic farce, mirroring his guarantees. TIM is single and
optimistic, so he says yes twice: **Priya**, `priya.n@mail.test`, whom he
met at a koi auction, and **Sam**, `sam.r@mail.test`, from a dating app
called *Plenty* ("plenty of fish — but make it ponds"). Same Friday, two
restaurants, a guarantee to each. Farce peak: a message meant for Priya
goes to **Mrs Featherstonehaugh** (autocomplete). Her reply is the best
mail she writes all season. Resolution, British rule: both dates go
badly, in different ways; Priya and Sam meet each other and get on
brilliantly; TIM is CC'd on their wedding invitation in the finale and is
genuinely delighted.

### Otter and the mailing list

`rfc-pedants@lists.deep-tech.test` ("Discussion of correctness. Off-topic:
nothing."). A nine-week flame war over whether the `Date:` header of an
email may use a two-digit year, started by someone called **J. Thornbury**
who is wrong, and sustained by everyone else who is also wrong in different
ways. Otter posts four times, each time citing the RFC section, each time
ignored. Real mailing-list headers (`List-Id`, `List-Unsubscribe`,
`[rfc-pedants]` subject tags), so the demo shows list mail. Finale: the
list moderator closes the thread "as it has stopped being productive",
quoting Otter's first post without attribution as the resolution. Otter
does not reply. His prediction log, which only he sees, gains an entry.

### Croc and his family

The warm one. **Mum** (`mum.crocodile@family.test`) has a printer that is
always the problem; she signs every mail "Love, Mum (Mum)". His sister
**Charlotte** (`charlotte@family.test`) organises **Gran's 90th birthday**
in a family group mail that runs all season (venue, cake, who brings the
chairs, who tells Uncle Desmond). Croc says yes to everything, at all
hours. Mirror of the office: in ep. 5, at 03:22, Mum writes "Are you
awake? I saw on the family thing that you were online. Is it the
printer?" Finale: the birthday happens; Gran's thank-you note, dictated to
Charlotte, is the last private mail of the season.

## Filing habits

How each character keeps their mailbox at the provider, before the stack
ever sees it (rules in `filing.yaml`). The first import must bring every
mail across into the same folder and record it, so this is also the
demo's test of first-import provenance.

- **Otter**: meticulous. `Predictions/Log`, `Lists/rfc-pedants`,
  `Personal/Mags`, `Lighthouse/Risk`, `Lighthouse/Incident`,
  `Security/Pirate`, `Vendors/Unsolicited`, and for The Management both
  `Management/Calendar (not attended)` and
  `Management/Announcements (unread on principle)`.
- **TIM**: `Clients/Featherstonehaugh Koi 🐟`, `Learning & Development 🎓`
  (the webinars), and `Networking 🤝`, an unsuspicious name for his entire
  romantic life.
- **Brog**: none. "everything comes in. i think that is more honest" —
  which is also why he has no Junk, and why Mlle Em's phishing reaches him.
- **Croc**: work stays in the Inbox, where he can see it. `Family`,
  `Family/Gran's 90th 🎂`, and `Receipts/Coffee`, which tells its own story.

## Running gags (where they must land)

| Gag | Rule | Payoff |
|---|---|---|
| Tim's guarantee | one more nine per episode | ep. 6: "100.000 %, basically the same" |
| Croc's coffee count | rises with the stress, 2 → 14 | ep. 5, 04:12: `☕ 14 today (it is 04:12)` |
| Otter's predictions | numbered, specific, timestamped | each comes true later, cited by number |
| The meeting | scheduled, renamed, cancelled | ep. 3 is entirely about it; never held |
| Brog's reply-all | every Brog mail goes to everyone | ep. 4: his reply-all to Em's phish |
| Management never mentions it again | each initiative vanishes after launch | ep. 6: quantum email, never again |
| BeanThere's concern | grows with Croc's orders | ep. 5: they offer a wellness call |

## The mystery spine: "someone reads where our emails come from"

Brog's quiet theory, started in the pilot as a throwaway question. Clues
build across the season:

1. **Pilot:** `does the new email server know where our emails come from.
   just wondering`. Ignored.
2. **Ep. 2:** he notices a mail "has more lines on top than it used to"
   (headers). Asks if that is normal. Croc: "Yes, that's normal!" Otter:
   "Mostly."
3. **Ep. 3:** he asks why a mail he moved to a folder "went back". (It
   didn't. Or did it?) Nobody answers.
4. **Ep. 4:** Em's phishing mail asks him to "verify where your mail comes
   from". He replies to all: `SEE.`
5. **Ep. 5:** during the night of the outage, Croc's status mail mentions
   in passing that the new system "records the provenance of every
   message". Nobody notices. Except Brog.
6. **Finale:** it is confirmed, in a technical aside, that the system does
   exactly what Brog said. Nobody apologises. Otter: *"Technically correct.
   Irrelevant."* Brog: `ok. i will tell the plants`.

(For anyone who knows the project: provenance is boring-mailstack's own
feature. For anyone who does not: Brog was right, which is enough.)

## The season — six episodes, about three months of mail

Dates are relative to the moment the demo is seeded (`day -92` is about
three months ago), so the demo always looks recent.

### 1. Pilot — "Operation Lighthouse" (days -92 to -84)

*Want:* The Management wants the company mail moved to a new platform
"by Friday". *Story:* the announcement; Croc's three polite questions and a
six-week estimate (unanswered); Tim already told Mrs Featherstonehaugh it's
done (99.9 %); Otter's first prediction; Brog's first question (mystery
clue 1); the first meeting invite. *Ends:* nothing has moved, Friday comes,
Management sends "great energy this week, team!" and never mentions Friday
again. Croc quietly starts the actual work. ☕ 2 → 5.

### 2. The Guarantee (days -78 to -66)

*Farce engine:* Tim's 99.99 % promise to Mrs Featherstonehaugh, with a
penalty clause he didn't read. Escalates through forwards, a "quick call?",
Otter's risk register (item 37: "someone has a mail filter from 2009"),
Croc trying to find out what was actually promised. Brog: clue 2 (headers).
*Ends:* Mrs Featherstonehaugh renegotiates — she wants 99.999 %. Tim:
"Already said yes!!" ☕ 6.

### 3. Alignment Huddle (days -60 to -48)

*Bureaucratic satire:* the meeting. Invited, moved, renamed, a pre-meeting
for the meeting, an agenda nobody writes, cancelled, re-invited as
"Lighthouse Sync (v2)", cancelled. The Services pile up (SynergyCloud
webinar on "async alignment"). Brog: clue 3. Otter's prediction #23: "this
meeting will never take place". *Ends:* it never takes place. Management
thanks everyone for "a really productive huddle". ☕ 7.

### 4. Ahoy (days -44 to -30)

*Caper:* Mademoiselle Em boards. Formal announcement, her phishing tests
(most in Junk), the company falling for exactly one — Brog, whose
reply-all is clue 4 and the funniest mail of the season. Otter had
predicted the click. Em's interim findings, an invoice in doubloons.
Croc's coffee subscription starts asking questions. ☕ 9.

### 5. Thursday, 03:00 (days -24 to -14)

*Disaster episode:* migration week. Otter's prediction #14 from the pilot,
now due. Wednesday optimism, Thursday 03:00 failure — the 2009 mail filter
(item 37) — Croc's night of calm status mails (03:07, 03:41, 04:12 with
☕ 14), clue 5 buried in a status line. Tim tells Mrs Featherstonehaugh it
was "a planned resilience exercise"; she replies with one devastating
sentence. BeanThere offers a wellness call.

### 6. Finale — "Quantum Email" (days -10 to -1)

*Status quo returns:* Management congratulates "the whole team" on an
on-time delivery (thanking Tim and SynergyCloud), announces the next
initiative — quantum email — and never mentions it again. Em's final
report: seaworthy, barely. Clue 6: Brog was right; nobody apologises. Tim's
guarantee reaches 100.000 %. Otter files prediction #31 about quantum
email. The last mail of the season is Croc's: one line, a coffee count of
1, and a quiet "Thanks, everyone."

### Private beats per episode

| Ep. | Brog ↔ Dr Hartley-Moss | TIM ↔ Priya / Sam | Otter ↔ rfc-pedants | Croc ↔ family |
|---|---|---|---|---|
| 1 | first letter: the plants, the new server; her warm, long reply | meets Priya at a koi auction; matches with Sam on *Plenty* | Thornbury opens the two-digit-year thread; Otter's first post (correct, ignored) | Mum's printer; Charlotte announces Gran's 90th |
| 2 | "more lines on top" (headers); her reply, shorter | says yes to both for the same Friday, "guaranteed" | the thread forks into a sub-war about time zones | venue debate; Croc offers to make a website for the party |
| 3 | the mail that "went back"; "Let's discuss on Tuesday." | logistics of two restaurants; the farce tightens | Otter cites the RFC section; a reply calls him "aggressively correct" | Uncle Desmond must not be told; Desmond is CC'd |
| 4 | forwards her Em's phishing as evidence; her auto-reply, made for him | the autocomplete disaster: Priya's message reaches Mrs Featherstonehaugh | list moderator asks everyone to "cool down"; Otter does not | cake decision by family vote; Croc's vote arrives at 01:40 |
| 5 | writes at 03:30 during the outage; auto-reply | Friday: both dates go wrong, separately | Otter's prediction about the thread, filed privately | 03:22 Mum: "Are you awake? Is it the printer?" |
| 6 | forwards proof; her only apology of the season | Priya and Sam's wedding invitation, TIM delighted | moderator closes the thread, quotes Otter unattributed | the party happens; Gran's dictated thank-you note |

| Ep. | Brog ↔ The Fog Inquiry | Otter ↔ Mags |
|---|---|---|
| 1 | joins; introduces himself and the plants; a warm welcome | first vent: "by Friday"; Mags on bees and deadlines |
| 2 | posts the headers theory; footer: "Supported by friends of the Inquiry" | on Tim's guarantee; Mags defends Tim, a little |
| 3 | a member's koi theory; Brog gently disagrees | on the meeting; Mags: "the hive also has meetings, they are called swarming" |
| 4 | forwards Em's phish to the list as evidence; great respect; footer: "Insights powered by PondPulse" | on the pirate; admits the pirate is competent; hates that |
| 5 | footer is now plainly PondPulse's tracker; Brog notices nothing yet | 04:30, one line: "Croc is still up. Someone should tell him to stop." |
| 6 | PondPulse's "We noticed your interest in mail provenance!"; Brog unsubscribes from everything | the honey; Otter's shortest mail of the season: "Thank you." |

## What the story must exercise (and why it is the demo)

| Feature | Where |
|---|---|
| Threads (`In-Reply-To`, `References`) | every episode |
| CC and reply-all | Brog, always; Tim's CCs |
| Junk folder placement | Services spam; Em's phishing (ep. 4) |
| Sent folders | each persona's own mails |
| Calendar invites and cancellations (`.ics`) | Management, ep. 1–3 |
| Attachments | Otter's risk register (CSV), Management's deck, Em's invoice |
| Forwards with quoted original | Tim forwarding Mrs Featherstonehaugh |
| Non-ASCII and emoji | Tim, Management, Mrs Featherstonehaugh's name |
| Mailing-list headers (`List-Id`, `List-Unsubscribe`) | Otter's rfc-pedants |
| Auto-replies | Dr Hartley-Moss's, set up only for Brog |
| Per-mailbox content (each account sees only its own) | the four perspectives |
| Personal folders, nested, with emoji, before first import | filing habits |
| Several days apart, late-night times | ep. 5 |

## File format

One Markdown file per episode in `episodes/`, readable top to bottom like
a chapter. Each mail is a block: a YAML header between `---` lines, then
the body. Blocks are separated by a line containing only `===`.

```
---
id: e1-03                 # unique; used for threading
day: -91 09:14            # relative day and local time
from: croc
to: [management]
cc: [otter, tim]
subject: "Re: Operation Lighthouse 🚀"
reply_to: e1-01           # optional; sets In-Reply-To/References
folder: { otter: Junk }   # optional; default INBOX for recipients
attach: [risk-register-v1.csv]   # optional; files in attachments/
html: mallard-tablets.html       # optional; an HTML part from html/
---
Body text. Write only the new text: on seeding, a reply quotes its parent
below it ("On … wrote:"), as a mail client does on Reply, nested up to four
levels. To quote selectively instead, write the "> " lines yourself; then
nothing is added.
```

With `html:`, the body is the plain-text part and the file in `html/`
the HTML part (a designed mail, for the Services' adverts). Such a mail
stands alone: no `reply_to`, list or invite.

Short names (`croc`, `otter`, `tim`, `brog`, `management`, `em`, the
Services by key) map to display names and addresses in
`characters.yaml`. The sender's copy lands in their own Sent folder when
the sender has a mailbox. Mail from senders without a mailbox (The
Management, the Services, Em) appears only in recipients' folders.
