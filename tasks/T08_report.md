# T08 report — Outcome gate + n8n approval step (**stopped before tuning: gold not final**)

Date: 2026-10-18. No git commands were run. Model runs are **real-GPU** (RTX 4050; llama.cpp b11139 Qwen3-4B + LoRA; DeBERTa Judge on CUDA).

**Status:**
- Part A is done.
- The Part B gate code and tests are done, with **provisional** settings (`t_invite` 80, pair flags info).
- Part C (n8n) is done: 3 real webhook runs, and the review form was submitted once.
- **Part B tuning and gate numbers were NOT produced.** After a fresh `build_gold.py`, `data/labels/gold/summary.json` still shows `row_sources.unchecked: 84` and `pair_sources.unchecked: 12` (the 12 new pairs). The task says to stop and report until the Approver says the labels are final. [scripts/eval_gate.py](../scripts/eval_gate.py) enforces this: it exits with "gold not final: 96 unchecked rows/pairs … not tuning".
- Tests: **374 passed, 6 skipped** (OCR).
- Final state: llama-server and the API are stopped; n8n is running.

## 1. Done

**Gold:** I ran `build_gold.py` as asked. It rewrites the gold files from the review workbooks; I made no manual edits.
- Gold now has 52 pairs and 364 rows. J2 r6 is nice.
- One old-pair gold change compared with the T06 rows: P06 r7, MET → UNCERTAIN.

**Part A** ([scripts/eval_real.py](../scripts/eval_real.py) gained `--select`, `--judge`, `--no-jobs` and `--run-only`; [scripts/eval_extra_pairs.py](../scripts/eval_extra_pairs.py); results in [eval/results/2026-10-18_extra_pairs/](../eval/results/2026-10-18_extra_pairs/)):
- `new12/`: the 12 new pairs went `/reader` → `/profile` → `/match` (confidence check at 0.72) → `/judge`, 84 rows.
- `j2r6_nice/`: the 10 old J2 r6 rows (P11–P20) were **re-run with kind = nice**. This was needed because the Matcher prompt contains `{kind}-have`.
- `rows_all_52_variant4.jsonl` holds all 364 rows (confidence + Judge):
  - the first 40 pairs come from T07 variant 4, with the 10 J2 r6 rows replaced;
  - gold, kind and split are re-read from the current gold.
- `profiles_all_52.json` and `summary.json` are in the same folder.

**Part B code** (rules written as the task gives them):
- [services/outcome/gate.py](../services/outcome/gate.py) and `POST /outcome` in [services/api.py](../services/api.py), with contracts `OutcomeIn` / `OutcomeOut`.
- The output gives `outcome`, `rule` (which rule fired), `score`, `reasons`, `listed_flags` (non-blocking: nice-to-have flags, must-have flags that are not outcome-relevant, info flags, pair flags in info mode), the must-have counts, and the reject sentence.
- Settings: `OUTCOME_T_INVITE`, `OUTCOME_PAIR_FLAGS` in [config/.env.example](../config/.env.example). Both are marked PROVISIONAL.
- [tests/test_outcome_gate.py](../tests/test_outcome_gate.py), 15 tests:
  - the score formula;
  - each rule;
  - every outcome-relevant flag type;
  - non-blocking flags are listed;
  - reject beats flags on other must-haves;
  - pair flags in block and info mode;
  - bad input;
  - the endpoint.
- [scripts/eval_gate.py](../scripts/eval_gate.py) is ready for when gold is final. It compares the T05 TEMP rule, the gate without the outcome-relevance filter, and the gate (pair flags block/info × `t_invite` ∈ {50…100}). It picks on dev (0 false invites hard, then review rate ≤ 25%, then fewest false rejects) and reports confusion, review rate, false invites, false rejects and agreement on dev and test. It ran only in `--dry-run` mode, which makes no gold comparison.

**Part C, n8n** ([n8n/hiresignal_v1.json](../n8n/hiresignal_v1.json), 27 nodes, exported and cleaned; [n8n/README.md](../n8n/README.md) updated):
- `TEMP outcome` is replaced by: Outcome input → **HTTP /outcome** → Result → Respond to Webhook → **Switch outcome**.
  - **invite / reject:** Decided by gate → Outbox letter → To JSON file → Write `eval/outbox/<decision>/<execution>_<cv_id>.json`. Rejects carry the reasons and "You can request a human review of this decision".
  - **review:** **Wait for recruiter (form)**, with Decision approve-invite/reject and a Note → Decided by human (`decided_by: human`) → the same outbox writer.
  - The webhook reply for a review contains `review_form_url`.
- Before importing, I checked that the live workflow had no UI edits: its nodes and connections were equal to the T07 export.
- [scripts/start_n8n.ps1](../scripts/start_n8n.ps1) and [scripts/n8n_cli.ps1](../scripts/n8n_cli.ps1): file access now includes `eval\outbox`, and the script creates `eval\outbox\invite` and `eval\outbox\reject` (n8n's path check needs the folders to exist). `eval/outbox/` is added to `.gitignore`.
- [scripts/n8n_e2e.py](../scripts/n8n_e2e.py) also reads `pairs_extra.csv` and records the gate fields.

**Docs:**
- [eval/results/2026-10-18_outcome_gate/SUMMARY.md](../eval/results/2026-10-18_outcome_gate/SUMMARY.md) for non-experts, with one example per outcome.
- `n8n_e2e/NOTES.md`.
- A guardrail row `guard-outcome-gate` in [prompts/PROMPT_LIBRARY.md](../prompts/PROMPT_LIBRARY.md). Its numbers are marked *pending*.

## 2. Evidence

**Matcher, variant 4** (`extra_pairs/summary.json`). **The 12 new pairs are scored against unchecked gold**, that is AI pre-labels, so these numbers are provisional.

| set | split | n | accuracy | macro-F1 | F1 MET / MISSING / UNCERTAIN | false MET | UNCERTAIN recall | review load |
|---|---|---|---|---|---|---|---|---|
| 12 new | dev | 42 | 0.714 | 0.580 | 0.857 / 0.615 / 0.267 | 3 | 0.29 | 0.62 |
| 12 new | test | 42 | 0.857 | 0.751 | 0.912 / 0.842 / 0.500 | 2 | 0.40 | 0.71 |
| all 52 | dev | 182 | 0.747 | 0.657 | 0.784 / 0.843 / 0.345 | 9 | 0.38 | 0.39 |
| all 52 | test | 182 | 0.780 | 0.672 | 0.825 / 0.870 / 0.320 | 11 | 0.31 | 0.42 |

- On the new rows the Judge gave PASS 24, **FAIL 48**, UNCERTAIN 1, NOT_APPLICABLE 11. All `/match` calls used LoRA scale 1.

**T07 re-report with J2 r6 = nice** (the first 40 pairs, whose gold is checked; dev macro-F1, baseline without confidence 0.555):

| `tau_conf` | 0.60 | 0.65 | **0.70** | **0.72** | 0.75 | 0.80 | 0.85 | 0.90 | 0.95 |
|---|---|---|---|---|---|---|---|---|---|
| dev macro-F1 | 0.605 | 0.617 | **0.642** | **0.642** | 0.621 | 0.619 | 0.609 | 0.591 | 0.566 |

- 0.70 and 0.72 still tie for best, so **0.72 is kept**, as instructed.

**Gate dry run** (code path only, no gold comparison). The provisional gate (pair flags info, any `t_invite` from 50 to 100) gives **invite 0, review 7, reject 45** of 52. The T05 TEMP rule gives invite 0, review 48, reject 4.
- Without looking at gold, the reason is visible: on only one pair (P50) are more than all-but-one must-haves MET without an outcome-relevant flag.
- The Judge's `judge:disagrees` on list-style MET quotes blocks invites. Examples from the n8n runs:
  - "Hands-on experience with SQL" ← "Relational databases: Oracle, MSSQL, MySQL, PostgreSQL…": FAIL 0.999;
  - "Good spoken English" ← "English level: upper": FAIL 0.98;
  - "asynchronous programming" ← "Python (FastAPI, asyncio, Django/DRF…)": FAIL 0.76.

**n8n real runs** (`eval/results/2026-10-18_outcome_gate/n8n_e2e/`; requirements from the Job Agent, as in production):

| pair | execution | gate | rule | final |
|---|---|---|---|---|
| P35 (J4) | 23 | reject, score 22 | 1: must r1, r3 MISSING | `eval/outbox/reject/23_cv-cb118925.json` (reasons + review sentence), `decided_by: gate` |
| P44 (J2, expected invite) | 24 | **reject**, score 57 | 1: must r2, r3, r6 MISSING | written to `eval/outbox/reject/` |
| P50 (J4, expected invite) | 18 | **review**, score 75 | 2: r1–r3 MET with `judge:disagrees` | form submitted (`approve-invite`, labelled as a Developer test) → execution resumed, **success**, `eval/outbox/invite/18_cv-afa64db6.json` with `decided_by: human` |

- In P44, the Job Agent kept r3 "Wiliness to do research on business logic" as a **must** (gold now says nice). The Matcher answered "GCP or other cloud providers" with MISSING although the CV says "Cloud: AWS(EC2, RDS, S3)", and the Judge only said UNCERTAIN on it. Under rule 1 (only `judge:disagrees` saves a MISSING), that is a clean reject: **a likely false reject** (provisional gold: invite).
- Per-node times (P44): `/profile` 30.2 s, `/job` 6.6 s, 7 × `/match` 20.7 s, 7 × `/judge` 1.1 s, `/outcome` 0.03 s.
- 0 identity values were found in the execution data.

**Superseded attempts** (all in `n8n_e2e/NOTES.md`):
- execution 15: 404, because the API had been started before `/outcome` existed;
- executions 19 and 21: the reject branch failed because `eval/outbox/reject` did not exist;
- each of these was logged by the error workflow (executions 16, 20, 22) to `eval/logs/n8n_errors.log`.

**Tests:** `pytest tests/` gives **374 passed, 6 skipped**. That is T07's 359 plus 15 gate tests.

## 3. Not done / problems

1. **Gate tuning and all gate numbers** (confusion matrices, review rate, false invites/rejects, rule table, block vs info) are **not done**. Gold still has 84 unchecked rows and 12 unchecked pair outcomes. When the Approver confirms, the next run is `build_gold.py`, then `scripts/eval_gate.py --rows eval/results/2026-10-18_extra_pairs --out eval/results/<date>_outcome_gate/gate` (plus `eval_extra_pairs.py` again, if gold rows changed).
2. **No invite is reachable with the current flags.** The Judge (template v2, T07) disagrees with most MET answers that rest on a skills list or a profile field, and the T08 rules make that outcome-relevant on must-haves.
   - With 0 false invites as a hard target, this may still pass. But the review rate and the usefulness of the gate depend on it.
   - The gate tuning (once gold is final) may show that Judge FAILs on MET must be weighted, for example only when the confidence is also below a level, or that the Judge template must be revisited (v1 was less strict, T07).
   - I did **not** change any of this without gold.
3. **"Expected invite" runs:** P44 was rejected and P50 went to review. The only invite file came from the human branch. The gate's own invite branch was not exercised in a real run; the unit tests cover it.
4. **Profile parse bug found** (V2 code, not fixed): `cv_sections` drops all text before the first heading. If the only heading is a skipped one ("Interests:"), nothing is parsed and no flag is raised. Example: P45, profile in 0.06 s with 0 skills. This does not affect the Matcher, which uses the anonymised text.
5. **Execution 17** (an earlier P50 run) is still waiting at the review form. It is pruned after 14 days, or can be cancelled in the n8n UI.
6. The 12 new pairs' Matcher metrics use unchecked gold (see §2).

## 4. Questions for the Brain

1. Please tell me when the 12 new pairs are checked (`unchecked: 0`). Gate tuning and reporting is one command, and no GPU is needed.
2. If the gold-based run confirms that Judge FAILs on list-style MET block all invites: may the gate tuning include **variants of rule 2** on dev? For example, Judge FAIL on MET counts only when `p(MET) < X`, or only when the Judge's entailment is below Y. Or should the Judge template (v1/v2) be revisited first?
3. Should the Job Agent's must/nice be overridden for J2 "research business logic" in production, as it was in gold (the Job Agent says must)?
4. Should I fix the Profile parse bug (§3.4) in a small separate task?

## 5. Suggested next step

1. Once gold is final: run the gate evaluation (dev choice, test report) and fill the guardrail numbers.
2. Then decide on the rule-2 variant if invites stay blocked.
3. Then the Bias Auditor and Report Writer stations.
