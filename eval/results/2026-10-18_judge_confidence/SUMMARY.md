# Two extra checks on the Matcher — what they catch (T07)

The Matcher reads one CV and one job requirement and answers **MET**, **MISSING** or **UNCERTAIN**, with quotes
from the CV. On our 40 real labelled CV x job pairs (280 requirement checks) it is right 79% of the time, but it has two
habits that matter for hiring:

1. it almost never says "I am not sure" (UNCERTAIN), even when the CV only hints at the skill;
2. sometimes it says MET with quotes that do not actually prove the requirement.

We added two checks. Both were set up on one half of the pairs (**dev**) and then measured on the other half
(**test**), which was not used for any choice. Numbers below are on **test** (140 checks, 20 pairs).

## Check 1 — "Is the model sure?" (confidence check, inside the Matcher)

The model gives a probability for each answer. If its own answer gets less than **72%**, we turn it into UNCERTAIN and
send it to a human (reason `match:low_confidence`). The model's original answer is kept for the reviewer.

Real examples (test and dev):
- P12, "Willingness to research business logic": the model said MISSING, but only with 53% (UNCERTAIN 46%). Now
  UNCERTAIN, which is what the human labelers said.
- P27, "Proficiency with ML libraries (TensorFlow, PyTorch, ...)": the CV only mentions one training project with
  the fastai library. The model said MISSING with 53% (UNCERTAIN 42%). Now UNCERTAIN, as the labelers said.

Effect on test: correct "not sure" answers 2 -> 6 of 20; balanced score (macro-F1) 0.61 -> 0.64; wrong MET 11 -> 8;
share of checks sent to a human 4% -> 16%. Plain accuracy drops a little (0.80 -> 0.76), because some answers that were
right become "not sure".

## Check 2 — "Does the quote really say that?" (the Judge, a separate station)

A second, independent model (an NLI model, DeBERTa) reads the quote the Matcher gave and asks: does this text
support "The candidate has <requirement>"? It never changes the answer; when it disagrees it adds the review reason
`judge:disagrees`. For a MISSING answer it reads the whole CV and disagrees if the CV does seem to show the skill.

Real examples:
- P23, "Excellent Python coding skills": the Matcher said MET, quoting only the list "R, Vba, C/C++, STL, Python".
  The Judge: the list does not show *excellent* Python (neutral 99.8%) -> sent to review. Labelers: UNCERTAIN.
- P13, "Willingness to research business logic": the Matcher said MET, quoting "Proactive and continuously growing..."
  and a list of soft skills. The Judge: not supported (neutral 97.7%) -> review. Labelers: MISSING.

Effect on test: wrong MET answers that reach a human 3 of 11 -> 9 of 11; all wrong answers that reach a human 3 of 28 ->
11 of 28; but the share of checks sent to a human rises from 4% to 28%, because the Judge also doubts some correct
answers (e.g. P06 "Strong working knowledge of SQL", MET from "Languages: C++, Python, SQL, R(basic)": the Judge reads
"strong" strictly and disagrees).

## Both together (test)

Balanced score 0.64 (same as check 1 alone, the Judge does not change answers); wrong MET 8, of which 7 reach a human;
21 of 33 wrong answers reach a human; 35% of checks go to a human. The temporary pair-level rule ("any doubt -> the whole
pair goes to review") then sends almost every pair to review: the real Outcome gate (T08) must weigh which doubts matter
(e.g. must-haves only) to reach the target of <= 25% of pairs reviewed. Gold pair outcomes are not final yet.

Details: `summary.json` (all tables, dev and test), `rows_<variant>.jsonl`, `../../../tasks/T07_report.md`.
