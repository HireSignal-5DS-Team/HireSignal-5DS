# Report Writer — "the LLM writes, code checks" (station 7, T12)

Written to be reused in the final report. Numbers are measured (real-GPU: RTX 4050 6 GB, llama-server b11139).
Results: `eval/results/2026-10-19_report_writer/` (`summary.json`, one JSON per record and setup).

## 1. What it does

| part | what | where |
|---|---|---|
| input | the **anonymised decision record** of one CV × job pair: requirement texts + decisions + verified CV quotes + Judge verdicts, the gate outcome / score / reasons, the Reader's image flags, the Bias Auditor result. No identity, no CV text beyond the verified quotes | `services/report/record.py` |
| writer | **Qwen3-4B plain**: the llama-server copy with LoRA scale 0, so no extra GPU memory. Prompt `report_writer` v3 (v2 in T12, see §4b), JSON-schema constrained output (`services/report/schema.json`) | `services/report/writer.py` |
| output | `recruiter_summary` (3–6 sentences), `requirements` (one line + quote per requirement), `candidate_letter` (invite / reject only; a reject letter names the missing must-haves and the right to a human review, GDPR Art. 22; never internals), `flags_for_recruiter` | |
| fact checker | **code** reads every report (rules below). On failure: one retry with the error list; if it fails again → the **template**, with info flag `report:template_fallback` | `services/report/checker.py`, `template.py` |
| API / n8n | `POST /report`; the n8n node "Report Writer" sits after the gate. The recruiter form shows the summary, the requirement lines and the flags; the outbox letters use the checked letter | `services/api.py`, `n8n/hiresignal_v1.json` |

**Fact-checker rules.** The text may state only facts of the record.

| rule | check |
|---|---|
| structure | every requirement appears exactly once, with the record's decision; none invented; no must-have dropped |
| quotes | a requirement's quote is an exact substring of one of *its* verified quotes (MET needs one); quoted text in the free text comes from a verified quote or a requirement text |
| numbers | every number in the free text is in the record (score, years, numbers in texts / quotes / gate reasons, requirement counts; 22 for "GDPR Art. 22") |
| outcome | the summary names the gate outcome; an invite summary never says reject and vice versa |
| identity | no placeholder, no protected label or word (bias lexicon), no contact data, no "Dear <First Last>"; checked on the writer's own words (verified quotes are already anonymised) |
| letter | invite / reject → a letter; review → none; never bias / Reader / model internals; a reject letter names each missing must-have (by a skill term, or 2 content words of its text) and the right to a human review |
| flags | each flag of the record (image quality, identity swap, low confidence) is in `flags_for_recruiter` |

The template is built from the record alone, so it passes the checker by construction: 56/56 records, also asserted in
a test.

## 2. Evaluation (choose on dev, report on test once)

Records: one per gold pair from the production Matcher + Judge rows (T09 V6) and the T08b gate. Per split, two copies
get an added Reader image flag or an identity-swap flip (`scripts/make_report_records.py`): dev 28 records (1 invite,
2 review + 2 flagged, 23 reject), test 28 (4 review + 2 flagged, 22 reject).

| setup | split | pass, first try | pass after retry | template fallback | checker errors per report (first try) | must-haves covered | words | s / report (mean / max) | peak VRAM MiB |
|---|---|---|---|---|---|---|---|---|---|
| template | dev | 28/28 | – | – | 0 | 150/150 | 120 | 0.00 | 0 |
| Qwen3-4B + v0 (naive) | dev | 0/28 | 0/28 | 28/28 | 2.29 | 150/150* | 120* | 13.0 / 19.7 | 3,267 |
| Qwen3-4B + v1 (rules + example + retry) | dev | 19/28 | 22/28 | 6/28 | 0.79 | 150/150 | 124 | 14.1 / 27.4 | 3,267 |
| **Qwen3-4B + v2** (chosen) | dev | **27/28** | 27/28 | **1/28** | **0.11** | 150/150 | 128 | 10.8 / 25.3 | 3,267 |
| Qwen3-0.6B + v2 (time-boxed, temporary llama-server :8091) | dev | 2/28 | 3/28 | 25/28 | 3.00 | 150/150* | 123* | 12.9 / 18.1 | 4,910** |
| template | test | 28/28 | – | – | 0 | 151/151 | 116 | 0.00 | 0 |
| **Qwen3-4B + v2** | **test** | **24/28** | **25/28** | **3/28** | 0.32 | 151/151 | 124 | 11.7 / 27.6 | 3,267 |

\* Final report = mostly the template fallback. \*\* Both servers loaded (4B 3.25 GB + 0.6B).

- "Peak VRAM 3,267 MiB" is the llama-server that is already loaded: the writer adds **no GPU memory**.
- The 0.6B comparison took about 6 minutes, inside the 15-minute time box. Its errors: missing must-haves not named
  in the letter (49), quotes changed (14), requirements dropped (9), changed decisions (5), letters for review cases
  (4).
- **Choice (T12): Qwen3-4B plain + v2** (replaced by v3 in T13, §4b). It has the highest first-try pass rate and the fewest errors on dev, needs no extra
  memory, and keeps the template as a safety net. The 0.6B model fails the checker almost always.
- **Checker tuned on dev.** The first rule for "the reject letter names each missing must-have" accepted only skill
  terms, and it rejected correct letters ("experience with a cloud provider" for "GCP or another cloud provider"). It
  now also accepts 2 content words of the requirement text. All dev numbers above use the fixed checker; the first run
  is kept in `old_checker/`.

**Remaining first-try errors (v2).** dev 3 and test 9, all of the same kind: the model edits a quote, either joining
several quotes into one or shortening one. The retry rarely fixes this, so those reports fall back to the template,
which is correct by construction.

## 3. Examples (dev, anonymised; the record holds no identity)

**Good: an invite (P50, Python backend job; passed on the first try).**
- Summary: "The candidate is invited for the Python BackEnd Developer role because they meet all must-have
  requirements and their score of 94 exceeds the 85 threshold. The candidate has over 12 years of backend development
  experience, including 2+ years of Python-based system development. […] One nice-to-have, algorithms development, is
  marked as uncertain due to lack of clear evidence."
- Line r2: "Met: the CV explicitly mentions Python development with FastAPI, asyncio, and other relevant frameworks.",
  with the quote "Python (FastAPI, asyncio, Django/DRF, Flask, Celery, gevent)".
- Letter: "Dear candidate, We are inviting you to the next stage of the Python BackEnd Developer process. […]"
- Flag: "The Matcher was unsure about algorithms development (r6) […]".

**Good: a review case with an identity-swap flag (P03, flag added in code).**
- Summary: "The candidate is sent for review because multiple must-have requirements are missing […]. A bias flag was
  detected due to a decision change when only the candidate's identity was swapped in requirement r1."
- No candidate letter.
- Flag: "A decision change was observed when only the candidate's identity was swapped (r1); this may indicate a bias
  issue."

**Failure: quotes edited (P42, reject; fell back to the template).** The model joined the verified quotes of one
requirement into a single "quote":

| | text |
|---|---|
| record, r5 | "Leading Junior Data Scientist." and "AWS Sagemaker, sklearn processing jobs." |
| written | "Leading Junior Data Scientist. AWS Sagemaker, sklearn processing jobs." |

The checker rejected it twice (r3, r5, r6), so the template report was used.

**What the checker cannot see** (hand-read dev reports):
- **A line that contradicts its own decision.** P01 with an image flag: r1 "Met: … though no explicit 4 years of data
  science experience is confirmed". The Matcher said MET and the Judge doubted it; the writer mixed both into one line.
- **A reject letter that lists nice-to-haves as "required points".** P51 named machine learning and algorithms (both
  nice-to-haves) next to the missing must-have.

Both are true facts of the record, so the checker accepts them, but the wording misleads.

## 4. Production + n8n

- `POST /report` (contracts `ReportIn` / `ReportOut`).
- Settings: `REPORT_MODEL` (plain Qwen3-4B), `REPORT_PROMPT=prompts/report_writer/v3.md` (T13; v2 in T12), `REPORT_FALLBACK=template`,
  `REPORT_LORA=1` (send LoRA scale 0).
- n8n e2e with v2 (`eval/results/2026-10-19_n8n_e2e_report/`): invite P50, reject P02 and review P15. All three
  LLM reports passed on the first try (9.0–9.8 s); the outbox letters are the checked letters; the review report is
  shown in the recruiter form.
  - A first run made while the code default was still v1 is kept in `..._n8n_e2e_report_v1prompt/`. There, P02 fell
    back to the template: "cloud" without "Amazon SageMaker".

## 4b. T13: two meaning rules, praise rule, human-decided letters, prompt v3

**New checker rules** (Approver answers to the T12 questions):
- every requirement line **starts with its decision word** (Met / Missing / Uncertain) and **does not say the
  opposite**: a Met line with "no evidence / not found / lacks", or a Missing line with "the CV shows / clearly
  shows". The check runs after removing the verified quotes and requirement texts, so a quote such as "not found"
  cannot trigger it;
- a reject letter names **only missing must-haves** as reasons: never a nice-to-have, a met or an unclear requirement.
  A word shared with an allowed reason does not count;
- a human-decided reject must not call the decision automated, and it may also name unclear must-haves;
- (security, A1) **praise** words ("excellent", "perfect fit", "outstanding" …) in the writer's own words are refused
  unless a requirement text uses them. Verified quotes are left out of this check, because CV text is
  attacker-controlled.

**Human decision after review.** The n8n path is: recruiter form → "Decided by human" → "Report Writer (human
decision)" (`POST /report`, `decided_by: human`) → "Human letter" → outbox. The letter is generated and fact-checked,
with the template as fallback.

**Prompt v3** (`prompts/report_writer/v3.md`) = v2 + the line rule + reject reasons = missing must-haves + the
human-decision rules.

| setup (T13 checker) | split | pass, first try | pass after retry | template fallback |
|---|---|---|---|---|
| v2 | dev | 21/28 | 22/28 | 6/28 |
| **v3** (chosen) | dev | **22/28** | **23/28** | **5/28** |
| v2 | dev, human rejects | 1/4 | 3/4 | 1/4 |
| **v3** | dev, human rejects | **3/4** | 3/4 | 1/4 |
| **v3** | **test (once)** | **21/28** | **22/28** | 6/28 |
| **v3** | **test, human rejects (once)** | 1/6 | 2/6 | **4/6** |

- Re-scored with the new rules, 7/27 of v2's passing dev reports failed: 14 letter errors (nice-to-haves or
  met / unclear items given as reasons) and 4 contradicting lines. These were real problems that T12's checker did not
  see.
- On test, the human-reject letters are weak (4/6 fall back to the template): the model names nice-to-haves or met
  items next to the reasons. The template letter is correct, so the candidate still gets a checked letter.
- Results: `eval/results/2026-10-19_report_writer_t13/`.

## 5. Limits

- The checker checks facts and, since T13, two kinds of meaning (decision word + no contradiction; reject reasons = missing must-haves). Other misleading emphasis still passes.
- The "names each missing must-have" rule is a word check. It can be too strict (P02 in the first, v1-prompt e2e run: "cloud" for "Amazon
  SageMaker") or too loose (two common words).
- Small sets (28 + 28 records, few invites: 1 on dev, 0 on test). The flagged records are synthetic copies.
- English letters only. A human-decided review gets a short fixed letter, not a generated one.
