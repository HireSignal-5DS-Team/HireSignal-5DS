# T06 report — anonymiser fix + evaluation on real labelled CVs (baseline)

Date: 2026-10-18. No git commands were run. The Matcher results are **real-GPU** (RTX 4050 Laptop, llama.cpp b11139, Qwen3-4B Q4_K_M + Matcher LoRA). The anonymiser results are rules only (CPU, no model).

**Summary:**
- **Anonymiser:** on the 40 real CVs, false "names" dropped from 18 to 1 and `[NAME]` replacements from 45 to 1. Synthetic identity leaks stayed at 0/65.
- **Matcher on the 280 real gold rows** (all 40 pairs): accuracy **0.793**, macro-F1 **0.584**.
  - F1 per class: MET 0.739, MISSING 0.883, **UNCERTAIN 0.13**.
  - 18 false MET.
  - Dev and test are close: macro-F1 0.558 vs 0.608.
- The model's confidence is now stored for every row: 280/280, without changing any output.
- **Job Agent:** it found all 28 gold requirements, plus 11 extra; must/nice agrees on 27 of 28.
- Tests: **343 passed, 6 skipped.** The skipped ones are OCR tests (Tesseract is still missing).
- Final state: llama-server and the API are stopped. n8n was left as it was (running).

## 1. Done

**Part 0.1: anonymiser fix** ([services/profile/detect.py](../services/profile/detect.py))
1. When the CV has **no section heading** (no Reader section other than header/contact, and no line in `HEADINGS`), the header-name rule is skipped. The "Name:" label rule and the e-mail fallback still run.
2. Common tech and CV words were added to `NOT_NAME`: tools, bi, api, sql, aws, spark, etl, streaming, certified, award, team, leader, used, implemented, …
- V2's 10 synthetic CVs with gold identity were copied to `tests/fixtures/profile/{cvs,gold}/`. Provenance is in [tests/fixtures/README.md](../tests/fixtures/README.md), because a header line inside a CV would change the anonymiser's input.
- [scripts/eval_anonymiser.py](../scripts/eval_anonymiser.py), adapted from V2 `scripts/eval_privacy.py` (rule-6 header):
  - on the synthetic set it measures leaks, other people still readable, and facts kept;
  - on the 40 real CVs it measures detected names and `[NAME]` replacements.
  - The detected values are written only to `private/anonymiser_eval/` (git-ignored).
- Results are in [eval/results/2026-10-18_anonymiser_fix/](../eval/results/2026-10-18_anonymiser_fix/): `before/`, `after/`, `not_names.txt`, `NOTES.md`.
- [tests/test_anonymiser_fix.py](../tests/test_anonymiser_fix.py) has 17 tests:
  - "BI Tools" in a CV without headings, so "Power BI" is kept;
  - 4 tech headers;
  - a real name is still found when the CV has headings;
  - the e-mail fallback still works without headings;
  - 0 leaks on each of the 10 synthetic CVs.

**Part 0.2: n8n pruning** in [scripts/start_n8n.ps1](../scripts/start_n8n.ps1) (process env only): `EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=336`.
- These are the **same values as n8n 2.43's defaults** (`@n8n/config` `executions.config.js`: `pruneData = true`, `pruneDataMaxAge = 336`). They were already in effect, so I did not restart n8n.
- `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false` is now documented as the accepted known n8n 2.43 + SQLite workaround, in the script and in [n8n/README.md](../n8n/README.md).

**Part A: real-data harness** ([scripts/eval_real.py](../scripts/eval_real.py)). Results in [eval/results/2026-10-18_real_baseline/](../eval/results/2026-10-18_real_baseline/): `rows.jsonl`, `profiles.json`, `jobs.json`, `summary.json`, `ERRORS.md`, `logprobs_check.txt`, `NOTES.md`, `config.json`, `run.log`.
- For each pair: `/reader` → `/profile` on the CV file, then `/match` for every gold requirement.
  - Each requirement takes its text, kind, category and min_years from `requirements_gold.csv`.
  - `skill_terms` is empty, so the ESCO query is the requirement text.
- **Confidence:** `/match` now asks llama-server for `logprobs: true, top_logprobs: 20` and returns a `confidence` block ([services/matcher/matcher.py](../services/matcher/matcher.py) `decision_confidence`, plus a unit test). It holds the probability of each label at the decision token, raw and renormalised over the 3 labels.
- Metrics are reported for dev, test and all. The script also runs the TEMP outcome rule (provisional), the Job Agent check (alignment by source sentence), and writes `ERRORS.md` with a hand-written cause line for each of the 58 errors.

## 2. Evidence

**Anonymiser, before vs after.** "Before" is V2's `detect.py`, which was our code until now except for the header line. The diff shows only my T06 lines.

| | before | after |
|---|---|---|
| synthetic: identity leaks | 0/65 | **0/65** |
| synthetic: other people readable | 0/5 | 0/5 |
| synthetic: facts kept | 65/67 | 65/67 |
| real 40: CVs with a detected "name" | 18 | **1** |
| real 40: `[NAME]` replacements | 45 | **1** |
| real 40: detected values that are obviously not names (hand check) | 18/18 | 1/1 |

- The 18 values before were tech terms, project titles, an award, a bank and "Seasoned Team Leader" (list in `not_names.txt`). None was a person's name.
- The one left after the fix is the project title "Cassava Leaf Disease". I did not add its words: that would fit the list to one CV.
- The 2 facts lost are T04's intended gender neutralisation: gold expects "Ingénieure DevOps" and the text now says "Ingénieur·e DevOps".

**Confidence (logprobs):**
- What b11139 supports: `/v1/chat/completions` follows the OpenAI options (README §`/v1/chat/completions`: "See OpenAI Chat Completions API documentation"). The values are a plain softmax of the logits before sampling (README line 579, `n_probs`), so the JSON-schema grammar does not affect them.
- Probed directly: the response holds `choices[0].logprobs.content[]` with `top_logprobs`, alongside constrained decoding.
- The labels' first tokens are distinct: `/tokenize` gives `MET` / `MISS`+`ING` / `UNC`+`ERT`+`AIN`.
- `logprobs_check.txt`, on 30 bench-v1 items: **the raw output is identical with and without logprobs on 30/30**, and the argmax label equals the model's decision on 30/30.
- My first version agreed on only 21/30, because stripping `' "'` merged variants like `" MET"`. Exact token pieces fixed it.
- In the real run, confidence is present for 280/280 rows, and no label ever fell outside the top 20.

**Matcher on real data** (`summary.json`; gold: MET 52, MISSING 189, UNCERTAIN 39):

| split | n | accuracy | macro-F1 | F1 MET / MISSING / UNCERTAIN | false MET (rate of non-MET gold; share of predicted MET) | MET with a verified quote | mean model latency |
|---|---|---|---|---|---|---|---|
| dev | 140 | 0.786 | 0.558 | 0.708 / 0.880 / 0.087 | 7 (0.060; 0.292) | 1.000 | 1.78 s |
| test | 140 | 0.800 | 0.608 | 0.762 / 0.887 / 0.174 | 11 (0.098; 0.314) | 1.000 | 1.92 s |
| all | 280 | 0.793 | 0.584 | 0.739 / 0.883 / 0.130 | 18 (0.079; 0.305) | 1.000 | 1.85 s |

- Confusion over all 280 rows (gold rows; predicted MET / MISSING / UNCERTAIN): MET 41 / 10 / 1; MISSING 8 / 178 / 3; UNCERTAIN 10 / 26 / 3.
- **The model predicts UNCERTAIN only 7 times, against 39 in gold.**
- "MET with a verified quote = 1.000" holds by construction: validator v1 forbids MET without a quote.
- Every `/match` call used LoRA scale 1. No reply was cut at max_tokens.
- 12 of 280 rows have review reasons.
- **Confidence of the model's own decision** (descriptive only, nothing tuned): median 0.989 when correct vs 0.896 when wrong on dev, and 0.994 vs 0.886 on test.

**TEMP outcome rule vs `pairs_gold.csv`.** This is **PROVISIONAL**: the gold outcomes are not human-checked yet, and there are 0 gold invites.
- Agreement: dev 0.80, test 0.70, all 0.75.
- Review rate: dev 0.25, test 0.40, all 0.325.
- Confusion over all 40 pairs:
  - gold review (5): temp review 4, temp reject 1;
  - gold reject (35): temp review 9, temp reject 26;
  - no invites anywhere.
- Two Profile flags push pairs to review; neither affects the Matcher:
  - 7 pairs have `profile:partial_extraction_requires_review` (P01, P12, P13, P16, P20, P22, P32). It comes from the Profile parse step.
  - 3 pairs have `profile:name_not_found` as a review reason (P02, P21, P31). This happens because the anonymiser found something contact-like (`[ADDRESS]` / `[URL]`, see §3.3), so the T05 info-only rule does not apply.

**Job Agent check** (`/job` on J1–J4, aligned to the 28 gold requirements by source sentence):

| job | gold requirements | agent requirements | gold found | must/nice agree | agent extras |
|---|---|---|---|---|---|
| J1 | 8 | 19 | 8 | 7 | 6 (4 × "data preparation, cleansing, feature engineering, visualization", split per skill; "communication skills"; "global cultures a plus") |
| J2 | 6 | 7 | 6 | 6 | 0 |
| J3 | 8 | 19 | 8 | 8 | 3 ("ML understanding techniques: explainability…", split) |
| J4 | 6 | 13 | 6 | 6 | 2 ("analytical and time management skills", "teamwork skills") |
| total | 28 | 58 | **28** | **27** | 11 |

- The one must/nice disagreement is J1 r7 "Strong working knowledge of SQL, Teradata preferred". Gold says must; the agent says nice, because of the cue word "preferred".
- The 4 J1 extras are the must-have that the AI pass said the draft was missing.
- The agent splits compound lines per skill: 58 requirements against 28.

**Error analysis** ([ERRORS.md](../eval/results/2026-10-18_real_baseline/ERRORS.md)). 58 disagreements: 18 false MET, 10 false MISSING, 26 missed UNCERTAIN, 4 other. Causes, counted from my cause lines:

| cause | count |
|---|---|
| partial or implied evidence that gold calls UNCERTAIN, while the model says MISSING | 26 |
| over-claimed MET (weak inference 4, partial evidence taken as full 4, wrong quote 2, degree read as years 1, "Python" in a list read as "excellent Python" 1) | 12 |
| soft trait (J2 r6 "research business logic") | 7 |
| alias or buried-term gaps (PL/SQL, DWH, Lakehouse, ARIMA/MCMC, AWS RDS, TensorFlow) | 6 |
| MET on a minimum-years requirement with no years in the quote | 3 |
| other ("or other cloud providers" not applied, title-only gold, doubtful gold, quote not verbatim) | 4 |

- **No error comes from anonymiser damage** after the fix: no placeholder sits on a gold line.

**Tests:** 343 passed, 6 skipped (OCR). That is T05's 325, plus 17 anonymiser tests and 1 confidence test.

## 3. Not done / problems

1. **UNCERTAIN is the weak class** (F1 0.13). The LoRA predicts it 7 times against 39 in gold, and 26 errors are gold-UNCERTAIN rows called MISSING. This matches the T03 val finding: the LoRA under-predicts UNCERTAIN. The stored confidence may help (wrong decisions have a lower median p), but **I did not tune anything**; that is T07's job.
2. **The years rule only flags.** 3 false METs sit on min-years requirements where the quote states no years: P01 r1, P31 r2, P34 r2. They carry `duration_not_in_evidence` but stay MET, by T04's design (V2's downgrade overfitted). If T07's gate uses `review_reasons`, these go to review.
3. **Remaining anonymiser over-masking,** none of it on a gold line:
   - course providers as `[URL]` (P06: "Deep Learning Specialization by [URL]");
   - "medium-[URL] websites" (P31);
   - "TWF([PERSONAL] Wealth Fund)" (P12, a nationality word);
   - "City: [ADDRESS]" (P21, intended).
   - Not fixed here, because it is out of scope.
4. **The gold requirement rows have no `skill_terms`,** so the ESCO query is the whole requirement text. The bench-v1 runs used the skill terms. This may weaken the knowledge for the Matcher.
5. **Gold doubts** written in `ERRORS.md`: P23 r8 (a Coursera course as AutoML evidence; its gold quote is not exact), P11 r1 (MET from a job title only), P30 r6 (a bundled requirement marked MET with Docker and Kubernetes not shown). I did not edit gold, as instructed.
6. **Kaggle/Vanetik data and OCR:** not part of this evaluation, because all 40 pairs are text CVs.
7. **The TEMP outcome numbers are provisional** (unchecked outcomes, 0 invites). They should not be used to pick thresholds yet.

## 4. Questions for the Brain

1. **For T07:** should the gate use the stored confidence (for example, low p(model decision) sends the case to review), and `review_reasons`? That should be calibrated on **dev only** and reported on test. I have not touched it.
2. **UNCERTAIN:** should a matcher-v2 prompt or a decision rule be tried on dev for "partial or implied" cases? Note the LoRA was trained on prompt v1; changing the prompt must be measured against the LoRA.
3. **J2 r6 "Willingness to research business logic"** causes 7 errors and is close to unlabelable. Should it be removed or made nice in the gold list? That is your call; I made no change.
4. **Job Agent:** it splits compound requirements per skill (58 vs 28). For the end-to-end evaluation, should alignment count a split group as one requirement, as I did here?

## 5. Suggested next step

T07: the Judge (NLI on the quotes) plus the Outcome gate.
- Use `rows.jsonl` offline: it holds the decisions, quotes, review reasons and label probabilities, so no GPU re-run is needed.
- Fit the thresholds on dev and report on test.
- Target a review rate of at most 25%, without false invites.
