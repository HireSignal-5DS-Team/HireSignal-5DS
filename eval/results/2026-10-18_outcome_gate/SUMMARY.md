# The Outcome gate — what it decides (T08 / T08b, final labels)

After every requirement of a job has been checked (MET / MISSING / UNCERTAIN, with the confidence check and the
Judge), the **gate** decides for the whole candidate: **invite**, **reject** or **review by a person**. It is plain
code, not a model, so every decision names the rule that fired.

The rules, in order:
1. **Reject** when a *must-have* is MISSING and nothing casts doubt on that answer.
2. **Review** when a *must-have* answer is doubtful in a way that could change the outcome: a MET whose quote the
   Judge does not accept (could be a false invite) — but only when the Matcher itself is not near-certain (below
   99.9%) —, a MISSING where the Judge thinks the CV does show it (could be a false reject), or an UNCERTAIN answer.
3. **Invite** when every must-have is MET without doubt and the overall score is at least 85 out of 100.
4. Otherwise **review**.
Doubts on nice-to-haves are shown but never block. Every rejection says "You can request a human review of this
decision". The recruiter can also confirm the job's requirement list before the run; the demo runs below did.

## How well it works (52 labelled candidate x job pairs; settings chosen on 26 "dev" pairs, measured on 26 "test" pairs)

| | wrong invites | real invites found | wrongly rejected | sent to a person |
|---|---|---|---|---|
| old temporary rule ("any doubt -> review"), test | 0 | 0 of 1 | 0 | 96% |
| **the gate, test** | **0** | 0 of 1 | 4 | **15%** |
| the gate, dev (for reference) | 0 | 1 of 2 | 6 | 8% |

- The gate never invited a candidate the labelers would not invite (the hard rule).
- It sends far fewer candidates to a person (15% instead of 96%), which meets the target of at most 25%.
- The price: 4 test candidates that the labelers would send to review are rejected. In these cases the Matcher said
  a must-have is MISSING, while the labelers said "not sure" (UNCERTAIN). The gate cannot see that doubt.
  Treating every profile-reading warning as a reason for review would remove these false rejects (4 -> 0), but would
  send 46% of candidates to a person, above the target; we chose the target and report the cost.
- The only test invite (P52) went to review: its score, 78, is below 85.

## One real example per outcome (n8n, recruiter-confirmed requirement lists, 2026-10-18)

- **Invite (by the gate)** — pair P50, Python backend job: all three must-haves MET ("More than 12+ years of
  experience", Python big systems, "Python (FastAPI, asyncio, ...)" for asynchronous programming), score 89. The Judge
  doubted the asynchronous-programming quote, but the Matcher was 99.98% sure, so the doubt is only listed. Written to `eval/outbox/invite/`.
- **Reject** — pair P35, same job: two must-haves (5 years of development; asynchronous programming and performance-critical applications)
  MISSING with no doubt; score 11. Written to `eval/outbox/reject/` with the reasons and the review sentence.
- **Review** — pair P15, Data Engineer job: two must-haves MISSING but the Judge says the CV does show them
  (Data Warehousing and Data Lakes; "GCP or another cloud provider" from "Azure and AWS services"), and "Good spoken English" is MET but doubted; score 59. The run waited for the recruiter form; it was submitted
  once as a test ("approve-invite"), and the final decision was recorded with `decided_by: human`.
