# Operation Lighthouse — write-up

Author: Croc. Reviewed by: Otter (two corrections, both his).

## Summary

Pond Ltd's email, including the mail we host for customers, moved to the
new platform on Wednesday evening. The switch-over itself went to plan.
At 03:00 on Thursday a server-wide rule created in 2009 began to divert
every message containing the word "invoice" into management@ / Later.
214 messages were diverted; none were lost. All were delivered to their
intended recipients by 04:12. Featherstonehaugh Koi's invoices were 69
minutes late.

## Timeline (Thursday)

  03:00  scheduled rule run begins on the new server
  03:00  first invoice diverted to management@ / Later
  03:07  incident noticed; status mail sent
  03:41  cause found: rule "DO NOT DELETE" (14 March 2009) is server-wide
  04:05  rule disabled (not deleted)
  04:09  diverted messages redelivered, original order
  04:12  verified; status mail sent

## Cause

The old server never ran server-wide rules. The rule existed for 17 years
and never fired. The new server runs them. Nobody knew what the rule did;
the question was asked four times and not answered (see appendix, item 37).

## Why recovery was possible

The new system records the provenance of every message: where it came
from, and where it was meant to go. That made it possible to put each of
the 214 messages back exactly where it belonged, instead of guessing.

## What we changed

- Rule disabled. Kept, renamed "DO NOT DELETE (2009, disabled)".
- Server-wide rules now need a second person to read them.
- Switch-overs are watched until 04:00, whatever the day.

## Appendix: risk register outcomes

Of 37 items on Otter's register, 34 happened as written. Item 14 ("This
fails on a Thursday at 03:00") happened at 03:00 on a Thursday. Item 32
("Coffee supply interrupted") did not happen, but it was close.

Thank you, Otter, for writing them down before anyone wanted to read
them.
