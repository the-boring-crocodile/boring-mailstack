# Episode 5 — "Thursday, 03:00"

Days -24 to -14. Migration week. The switch-over goes perfectly on
Wednesday evening. Prediction #14 falls due. Item 37 is finally explained.
Croc does not sleep. TIM keeps his Friday guarantee, twice.

Additional header key used here:

- `auto_reply: true` marks an automatic reply (`Auto-Submitted:
  auto-replied`).

Background, as it emerges in the mails: Pond Ltd's "digital solutions" are
hosting a few customers' email, Featherstonehaugh Koi among them. Her
invoices are sent by a batch every Thursday at 03:00.

===
---
id: e5-01
day: -24 09:00
from: croc
to: [management]
cc: [otter, tim]
subject: "Lighthouse: switch-over plan"
---
Hi,

The migration is ready. Proposal for the switch-over:

  When:     Wednesday evening, 20:00–24:00 (quiet, and not a Thursday)
  How:      final copy, verify, switch, verify again
  Way back: the old system stays as it is until I've checked a full week

Still open: the 2009 filter on your mailbox. I've copied it unchanged,
because I don't know what it does and it says DO NOT DELETE.

If that's OK, I'll go ahead.

Croc
Development | Pond Ltd
☕ 6 today

===
---
id: e5-02
day: -24 11:00
from: management
to: [croc, otter, tim]
subject: "Lighthouse goes LIVE on Wednesday 🚀"
---
Team,

I am thrilled to announce that Operation Lighthouse goes live this
Wednesday.

When we set this north star, some said it couldn't be done. And yet here
we are, exactly on schedule. A special thank-you to TIM for driving this
from day one.

The Management
Office of Strategic Vision | Pond Ltd
"Together, we are the pond."

===
---
id: e5-03
day: -24 11:04
from: otter
to: [croc]
subject: "Re: Lighthouse goes LIVE on Wednesday 🚀"
reply_to: e5-02
---
"Exactly on schedule." The schedule was Friday, twelve weeks ago.

On your plan: Wednesday evening, not a Thursday. Correct. Note that
Thursday 03:00 is the first hour after a Wednesday evening at which
everybody has stopped watching.

Prediction #14 is still open.

Otter
Quality Assurance | It is not fine.

===
---
id: e5-04
day: -24 11:20
from: croc
to: [otter]
subject: "Re: Lighthouse goes LIVE on Wednesday 🚀"
reply_to: e5-03
---
Then I'll watch until 04:00 on Thursday.

Croc
Development | Pond Ltd
☕ 6 today

===
---
id: e5-05
day: -23 10:12
from: tim
to: [croc]
cc: [brog]
subject: "Fwd: Thursday invoices"
---
Quick one!! Mrs F asked if her Thursday invoices will be fine with the
new system. Told her 100% yes!! 🙌 (Basically 99.999%, which is 100%.)

TIM 🌟 Director of Yes, Again | Pond Ltd | "Every pond is an opportunity"

---------- Forwarded message ----------
From: Mrs H. Featherstonehaugh <h.featherstonehaugh@featherstonehaugh-koi.test>
Subject: Thursday invoices

Mr Mudskipper,

I understand your firm is changing the system on which you host our
email. My invoices go out at 03:00 on Thursdays, as they have since we
first engaged you. I trust I shall not notice.

H. Featherstonehaugh

===
---
id: e5-06
day: -18 19:55
from: croc
to: [management]
cc: [otter, tim, brog]
subject: "Lighthouse: starting now"
---
Hi all,

Starting the switch-over now. You don't need to do anything. I'll send a
short note when it's done.

(Brog — I've added you, so you're in the loop.)

Croc
Development | Pond Ltd
☕ 8 today

===
---
id: e5-07
day: -18 23:48
from: croc
to: [management]
cc: [otter, tim, brog]
subject: "Lighthouse: done ✅"
reply_to: e5-06
---
Hi all,

Done. Everything is on the new system:

  - all mailboxes copied and checked, message counts match
  - all folders where they were
  - all filters moved unchanged (including the 2009 one)
  - the old system is still there, untouched, as the way back

I'll keep an eye on it overnight.

Croc
Development | Pond Ltd
☕ 9 today

===
---
id: e5-08
day: -18 23:51
from: tim
to: [croc]
cc: [management, otter, brog]
subject: "Re: Lighthouse: done ✅"
reply_to: e5-07
---
LEGEND!!! 🚀🚀🚀 Telling Mrs F first thing!!

TIM 🌟 Director of Yes, Again | Pond Ltd | "Every pond is an opportunity"

===
---
id: e5-09
day: -18 23:55
from: management
to: [croc, otter, tim]
subject: "Re: Lighthouse: done ✅"
reply_to: e5-07
---
Proud moment. 🙌

Sent from The Management's phone

===
---
id: e5-10
day: -18 23:58
from: otter
to: [croc]
subject: "Re: Lighthouse: done ✅"
reply_to: e5-07
---
It is Wednesday for two more minutes.

Otter
Quality Assurance | It is not fine.

===
---
id: e5-11
day: -17 03:07
from: croc
to: [management]
cc: [otter, tim, brog]
subject: "Lighthouse: incident — some mail is not arriving"
reply_to: e5-07
---
Hi all,

Since 03:00, mail containing invoices is not reaching its recipients.
This includes Featherstonehaugh Koi's Thursday invoice run. Nothing
appears to be lost; it is going somewhere. I'm finding out where.

Next update within the hour.

Croc
Development | Pond Ltd
☕ 11 today

===
---
id: e5-12
day: -17 03:09
from: otter
to: [croc]
subject: "Re: Lighthouse: incident — some mail is not arriving"
reply_to: e5-11
---
Item 37.

I am awake. I set an alarm for 02:55 in March.

Otter
Quality Assurance | It is not fine.

===
---
id: e5-13
day: -17 03:41
from: croc
to: [management]
cc: [otter, tim, brog]
subject: "Lighthouse: incident — found it"
reply_to: e5-11
---
Hi all,

Found it. The 2009 filter "DO NOT DELETE" on management@ is not a
personal filter. It is a server-wide rule:

  If any message contains the word "invoice",
  move it to the folder "Later" in management@.

The old server never ran server-wide rules, so in seventeen years it
never once fired. The new server does, and runs them at 03:00.

Since 03:00, 214 messages — including every Featherstonehaugh Koi invoice
— have been filed in management@ / Later. Nothing is lost. Also nothing is
where it should be.

Fixing now.

Croc
Development | Pond Ltd
☕ 13 today

===
---
id: e5-14
day: -17 04:12
from: croc
to: [management]
cc: [otter, tim, brog]
subject: "Lighthouse: incident — fixed"
reply_to: e5-13
---
Hi all,

Status: fixed. Cause: below. Coffee: see signature.

- The rule is disabled. Not deleted: it says DO NOT DELETE, and I am too
  tired to argue with 2009.
- All 214 messages have been delivered to their intended recipients, in
  their original order. Because the new system records the provenance of
  every message — where each one came from and where it was meant to go —
  I could put every single one back exactly.
- Featherstonehaugh Koi's invoices reached her customers at 04:09 instead
  of 03:00. Delay: 69 minutes.

Write-up to follow after some sleep.

Croc
Development | Pond Ltd
☕ 14 today (it is 04:12)

===
---
id: e5-15
day: -17 04:14
from: otter
to: [croc]
subject: "Re: Lighthouse: incident — fixed"
reply_to: e5-14
---
Prediction #14: fulfilled. Thursday, 03:00. The worst one.

Good work. Go to bed.

Otter
Quality Assurance | It is not fine.

===
---
id: e5-16
day: -17 04:20
from: brog
to: [croc]
cc: [management, otter, tim]
subject: "Re: Lighthouse: incident — fixed"
reply_to: e5-14
---
"the new system records the provenance of every message — where each one
came from"

i looked up provenance. it means where something comes from.

so it does know

brog

===
---
id: e5-17
day: -17 08:30
from: tim
to: [croc]
cc: [brog]
subject: "Fwd: Re: Thursday invoices"
---
Morning!! 😴 Did I miss something?? Anyway — told Mrs F the little delay
was a planned resilience exercise 💪 She replied, see below, I think she's
happy??

TIM 🌟 Director of Yes, Again | Pond Ltd | "Every pond is an opportunity"

---------- Forwarded message ----------
From: Mrs H. Featherstonehaugh <h.featherstonehaugh@featherstonehaugh-koi.test>
Subject: Re: Thursday invoices

Mr Mudskipper,

If it was planned, you will be able to tell me now when the next one is.

H. Featherstonehaugh

===
---
id: e5-18
day: -17 08:52
from: croc
to: [tim]
cc: [brog]
subject: "Re: Fwd: Re: Thursday invoices"
reply_to: e5-17
---
Tim, she isn't happy.

For the contract: 69 minutes on a Thursday counts double (7.4), which is
2 hours 18 minutes. Under 7.3 that's one koi per hour; 7.5 rounds up.

We owe Mrs Featherstonehaugh three koi of no less than Grade A quality.

Croc
Development | Pond Ltd
☕ 3 today (it is a new day, technically)

===
---
id: e5-19
day: -17 08:55
from: tim
to: [croc]
cc: [brog]
subject: "Re: Fwd: Re: Thursday invoices"
reply_to: e5-18
---
Brenda has friends!! 🐟🐟🐟 On it!!

TIM 🌟 Director of Yes, Again | Pond Ltd | "Every pond is an opportunity"

===
---
id: e5-20
day: -17 07:58
from: beanthere
to: [croc]
subject: "Express order received at 03:33 ☕ — and a small offer"
---
Hello Croc,

We received an express order from you at 03:33 this morning. It is on
its way.

We'd also like to offer you something we have never offered a customer
before: a free, fifteen-minute **wellness call** with a member of our
team. We won't talk about coffee. We'll just ask how you are, and wait
for the answer.

Reply "YES" and we'll be in touch.

With genuine concern,
The BeanThere Coffee Co.
"There's always a reason. We're the reason."

===
---
id: e5-21
day: -17 09:10
from: croc
to: [beanthere]
subject: "Re: Express order received at 03:33 ☕ — and a small offer"
reply_to: e5-20
---
YES

(Thank you. Nobody has asked that this week.)

Croc

===
---
id: e5-22
day: -16 10:00
from: synergycloud
to: [croc, otter, tim]
subject: "Did your migration go smoothly? 🤔 (Only 3 seats left)"
---
DID YOUR EMAIL MIGRATION GO SMOOTHLY?

If you're reading this, it probably did. But did it go SYNERGISTICALLY?

Join our post-migration webinar, "Lessons Unlearned: Thriving After
Change", and turn your Thursday into a Thrive-day.

  ✔ Only 3 seats left!

SynergyCloud Ltd. — "Everything, aligned."

===
---
id: e5-p01
day: -17 03:30
from: brog
to: [ihm]
subject: "it is 3:30"
---
dear dr hartley-moss

it is 3:30. i am awake because croc is sending emails about the emails.
otter is also awake. i do not think otter sleeps.

the emails with invoices went into a folder called later. it has been
there since 2009 and nobody knew. i think the management has been putting
things in later for a long time

i am not upset. i am interested

brog

===
---
id: e5-p02
day: -17 03:30
from: ihm_auto
to: [brog]
subject: "Automatic reply: it is 3:30"
reply_to: e5-p01
auto_reply: true
---
Thank you for your email.

I am currently away from my desk. If your message concerns plants,
headers, or where emails come from, please bring it to our Tuesday
session. If it is an emergency, please call 999.

If it is about the ficus, it is not an emergency.

Dr Imogen Hartley-Moss
Hartley-Moss Practice | Counselling & Psychotherapy

===
---
id: e5-p03
day: -17 06:15
from: fog_rt
to: [fog]
list: fog
subject: "Fog arrived 03:00 last night — on schedule"
footer: |
  The Fog Inquiry · Asking the Questions Weather Won't
  This message was brought to you by PondPulse Analytics.
  Your engagement is measured to improve your experience.
  https://track.pondpulse.test/o/fog-inquiry/r?s=brog%40pond.test&co=pond-ltd
---
Friends,

Fog arrived at precisely 03:00 last night. Not 02:58. Not 03:04. 03:00.

Something happens at 03:00. Note it.

R.T. ☁ (moderator)

===
---
id: e5-p04
day: -17 06:40
from: brog
to: [fog]
list: fog
subject: "Re: Fog arrived 03:00 last night — on schedule"
reply_to: e5-p03
footer: |
  The Fog Inquiry · Asking the Questions Weather Won't
  This message was brought to you by PondPulse Analytics.
  Your engagement is measured to improve your experience.
  https://track.pondpulse.test/o/fog-inquiry/r?s=brog%40pond.test&co=pond-ltd
---
r.t.

at work something also happened at exactly 03:00. a rule from 2009 woke
up and moved all the invoices to a folder called later.

i do not think it was the fog. but i am noting it

brog

===
---
id: e5-p05
day: -17 04:30
from: otter
to: [mags]
subject: "(no subject)"
---
Croc is still up. Someone should tell him to stop.

===
---
id: e5-p06
day: -17 07:20
from: mags
to: [otter]
subject: "Re: (no subject)"
reply_to: e5-p05
---
Dear O.,

You are someone. Tell him. Use words, not a numbered list.

Mags

===
---
id: e5-p07
day: -17 09:30
from: otter
to: [otter]
subject: "Predictions log"
---
#14  Lighthouse fails Thursday 03:00.              FULFILLED (day 75)
#15  "Friday" will not appear again.              FULFILLED
#19  There will be a sixth nine.                  OPEN
#23  The meeting will never take place.           FULFILLED
#26  Exactly one will reply to a phish: Brog.     FULFILLED
#28  The rfc-pedants thread will be closed by the
     moderator, who will quote my first post as
     the resolution, without attribution.         OPEN
#29  Nobody will thank Croc by name.              OPEN

===
---
id: e5-p08
day: -21 05:50
from: ferrante
to: [rfc-pedants]
list: rfc-pedants
subject: "Re: Two-digit years in Date: are fine, actually (part 6 of 7: on the nature of agreement)"
reply_to: e4-p11
---
Parts 4 and 5 were lost in a mail outage. Part 6 assumes you have read
them.

D. Ferrante

===
---
id: e5-p09
day: -17 03:22
from: mum
to: [croc]
subject: "are you awake"
---
Are you awake? I saw on the family thing that you were online.

Is it the printer?

Love, Mum (Mum)

===
---
id: e5-p10
day: -17 03:25
from: croc
to: [mum]
subject: "Re: are you awake"
reply_to: e5-p09
---
Hi Mum,

Not the printer, for once. It's work. All under control.

Why are YOU awake?

Love you,
Croc
☕ 12 today

===
---
id: e5-p11
day: -17 03:27
from: mum
to: [croc]
subject: "Re: are you awake"
reply_to: e5-p10
---
I can't sleep before big things. Gran's party is in two weeks.

Go to bed when the work lets you. Not when it says you can — when it
lets you. Those are different.

Love, Mum (Mum)

===
---
id: e5-p12
day: -17 07:40
from: charlotte
to: [croc, mum]
subject: "Re: Gran is turning 90 🎉"
reply_to: e1-p14
---
Why were you BOTH online at 3am?? I have a family of owls.

Chairs: confirmed, 40. Website: Gran has looked at it "on the
computer". She asked who the handsome young man in the marrow picture
is. It's Grandad. She knows. She just likes saying it.

C x

===
---
id: e5-p13
day: -16 20:41
from: tim
to: [brog]
subject: "It's going GREAT 😅"
---
Brog!! Lucetta's is lovely, Priya is lovely, going to the "bathroom"
now (ramen) 🍜 back by 9:30!!

TIM

===
---
id: e5-p14
day: -16 20:44
from: brog
to: [tim]
subject: "Re: It's going GREAT 😅"
reply_to: e5-p13
---
one dinner tim

brog

===
---
id: e5-p15
day: -15 09:10
from: priya
to: [tim]
subject: "Last night"
---
Tim,

You went to the bathroom at 8:40 and came back at 9:50 smelling of
ramen.

While you were gone, a woman came in and sat at the bar and asked the
waiter whether a man called Tim had been "going to the bathroom a lot".
We worked it out together. We shared the tiramisu. (It is excellent; the
koi lady was right.)

Her name is Sam. I think we're both done with you, Tim. But honestly,
thank you for introducing us.

Priya

===
---
id: e5-p16
day: -15 09:12
from: sam
to: [tim]
subject: "Last night"
---
Tim.

Priya says hi.

Sam

===
---
id: e5-p17
day: -15 11:30
from: ramen_ichigo
to: [tim]
subject: "Thank you for dining with us"
---
Thank you for dining with us last night.

You left a half-finished bowl and a jacket. The jacket is now at
Lucetta's. Lucetta's called us. We have never been called by Lucetta's
before.

Ramen Ichigo

===
---
id: e5-p18
day: -15 12:02
from: tim
to: [brog]
subject: "One dinner"
---
Brog. You were right. One dinner.

Priya and Sam left together. They seemed really, really happy?? Like,
laughing on the canal happy. So that's sort of a win?? 🥲

TIM

===
---
id: e5-p19
day: -15 12:40
from: brog
to: [tim]
subject: "Re: One dinner"
reply_to: e5-p18
---
it is a win for them

are you ok

brog

===
---
id: e5-p20
day: -15 12:44
from: tim
to: [brog]
subject: "Re: One dinner"
reply_to: e5-p19
---
Yeah. Honestly yeah. Brenda and I are going to have a quiet weekend 🐟

Thanks for asking mate. Nobody else did.

TIM

===
---
id: e5-s1
day: -21 14:20
from: spam_koi
to: [brog, otter]
subject: "Teach your koi to REMEMBER YOUR FACE - by post!"
folder: { otter: Junk }
---
IS YOUR KOI INDIFFERENT TO YOU?

Science has long suspected it: the koi REMEMBERS. Now the Koi
Mesmerism Society brings you the secret, in six illustrated lessons
by post.

  Lesson 1  -  The Gaze
  Lesson 2  -  The Second Gaze
  Lesson 3  -  Hats: help or hindrance?
  Lesson 6  -  When your koi remembers too much

"Within a fortnight my koi knew my face. Within a month it knew my
address. I have moved."  - Mr G. of the Midlands

Send no money. The koi will know if you meant to.

The Koi Mesmerism Society
Est. 1931 (by the koi)

===
---
id: e5-s2
day: -17 03:58
from: spam_somno
to: [croc]
subject: "STILL AWAKE? We noticed. SLEEP, delivered by telegram!"
folder: { croc: Junk }
---
STOP. ARE YOU READING THIS AT FOUR IN THE MORNING STOP. WE THOUGHT SO STOP.

SOMNO-GRAM delivers a full eight hours of restful sleep to your door,
by telegram, in under an hour. Simply sign for it and lie down.

  * No pills, no potions, no counting of sheep
  * Each telegram hand-yawned by trained operators
  * Now with optional lullaby (2/6 extra)

"I ordered one at 03:41. I woke up on Tuesday."  - a developer

SOMNO-GRAM, the Night Desk
"Goodnight, by Wire"

===
---
id: e5-s3
day: -16 09:30
from: spam_lozenge
to: [tim]
subject: "GUARANTEED: 100.000% UPTIME LOZENGES (basically the same as 99.9!)"
folder: { tim: Junk }
---
GEE! MODERN BUSINESSMEN AGREE:

You promised the customer. Now KEEP that promise, with
FEATHERBRIGHT'S UPTIME LOZENGES!

Just one lozenge before every promise and your guarantee gains a whole
NINE - or your money back!*

  99.9 %      ...  one lozenge
  99.99 %     ...  two lozenges
  99.999 %    ...  ask your doctor
  100.000 %   ...  basically the same

Cherry, Menthol and NEW Sales Ninja flavour.

Featherbright & Sons, Purveyors of Confidence since 1924

*Money back takes 5-7 business years.
