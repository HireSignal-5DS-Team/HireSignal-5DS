# T08b report — gate tuning on final gold, recruiter-confirmed requirements, parse fix

Date: 2026-10-18. No git commands were run. Matcher and Judge rows are **real-GPU** (T06/T07/T08 runs plus fresh NLI scores on CUDA). The gate itself is plain code.

**Summary:**
- **Gold:** `build_gold.py` reports 0 unchecked rows and 0 unchecked pairs (52 pairs; outcomes invite 3, review 14, reject 35).
- **Gate, chosen on dev (family b):**
  - a Judge doubt on a MET must-have counts only if p(MET) < 0.999;
  - `t_invite` 85;
  - pair flags info only.
- **Test results:** 0 false invites, review rate **15.4%** (was 96.2% with the T05 TEMP rule), 4 false rejects, agreement 0.808.
- **Recruiter-confirmed requirement cards** are wired into the webhook.
- **The Profile parse bug is fixed.**
- **Three real n8n runs**, one per outcome: P50 **invite by the gate's own branch**, P35 reject, P15 review → form submitted → human decision.
- Tests: **381 passed, 6 skipped** (OCR).
- llama-server and the API are stopped; n8n is running.

## 1. Done

- **Re-ran [scripts/eval_extra_pairs.py](../scripts/eval_extra_pairs.py) on final gold.** Results: `eval/results/2026-10-18_extra_pairs/`, with `rows_all_52_variant4.jsonl` (364 rows) and `summary.json`.
- **Gate options** in [services/outcome/gate.py](../services/outcome/gate.py) (`judge_counts`). The default behaviour is unchanged.
  - `judge` (all | none), `judge_met_max_conf` (X), `judge_max_support` (Y), `judge_skip_proven`.
  - Validator flags always count.
  - Judge doubts that do not count are still listed (`listed_flags`).
- **`/outcome`** reads the chosen settings from env: `OUTCOME_T_INVITE=85`, `OUTCOME_PAIR_FLAGS=info`, `OUTCOME_JUDGE=all`, `OUTCOME_JUDGE_MET_MAX_CONF=0.999`, `OUTCOME_JUDGE_MAX_SUPPORT` empty, `OUTCOME_JUDGE_SKIP_PROVEN=0`. They are documented in [config/.env.example](../config/.env.example).
  - `OutcomeRequirement` accepts `category`, `confidence`, `judge`, `min_years` and `evidence_years`.
- **[scripts/eval_gate.py](../scripts/eval_gate.py)** (rewritten):
  - It refuses to run while gold has unchecked labels.
  - It recomputes Judge NLI scores for all 364 rows on their final decisions, with templates v1 and v2 (cached in `gate/nli_v1.jsonl`, `gate/nli_v2.jsonl`). The v2 recomputation equals the saved station verdicts on **364/364** rows.
  - It tunes each family (a)–(f) on dev over pair flags (info | block) × `t_invite` {50…100} (× X or Y).
  - Results: `eval/results/2026-10-18_outcome_gate/gate/summary.json` and `all_configs.json`.
- **Recruiter-confirmed requirements:**
  - [scripts/make_job_cards.py](../scripts/make_job_cards.py) writes `data/processed/jobs/J1..J4_requirements.json` from gold. J2 r6 is nice; each requirement's `evidence` is its verbatim job sentence (asserted).
  - In n8n, the webhook accepts an optional `requirements` field (the card as JSON).
    - `Confirmed requirements?` (IF) → `Confirmed job card` (Code; checks each `req_id`/`text`/`kind`; info flag `job:requirements confirmed by recruiter`) **or** `HTTP /job`. Both lead to `Job card`, then Merge.
    - Downstream nodes read `$('Job card')`.
  - `Outcome input` now also passes category, min_years, evidence_years, confidence and judge.
  - [scripts/n8n_e2e.py](../scripts/n8n_e2e.py) gained `--cards`.
- **Profile parse fix** ([services/profile/parse.py](../services/profile/parse.py) `cv_sections`):
  - text before the first heading is kept as section "CV" when it has ≥ 200 characters (more than a header);
  - if nothing would be parsed, the whole text is used;
  - a short header (`[NAME]`, `[EMAIL]` lines) is still skipped, so the V2 test is unchanged;
  - 2 tests added, including a P45-like case. On P45 itself it now gives one 1,214-character section (before: none).
- **n8n:**
  - Before importing, I checked that the live workflow had no UI edits (nodes and connections equal to the T08 export).
  - Imported, published, re-exported and cleaned: [n8n/hiresignal_v1.json](../n8n/hiresignal_v1.json), 30 nodes. [n8n/README.md](../n8n/README.md) is updated with the `requirements` field.
- **Docs:** [eval/results/2026-10-18_outcome_gate/SUMMARY.md](../eval/results/2026-10-18_outcome_gate/SUMMARY.md) (non-expert, final numbers, one example per outcome) and the `guard-outcome-gate` row in [prompts/PROMPT_LIBRARY.md](../prompts/PROMPT_LIBRARY.md), both updated.
- **Tests:** 5 new gate tests (variants b, c, d and f, and the endpoint defaults) and 2 parse tests.

## 2. Evidence

**Matcher, variant 4, final gold** (real-GPU): all 52 pairs, dev macro-F1 0.651 and test 0.661; false MET dev 10, test 13.

**Rule-2 families, each tuned on dev.** FI = false invites, FR = false rejects (gold invite/review, gate reject), Inv = gold invites the gate also invited.

| family | dev: best setting | dev FI | dev FR | dev Inv | dev review | test FI | test FR | test Inv | test review | test agreement |
|---|---|---|---|---|---|---|---|---|---|---|
| TEMP rule (T05) | - | 0 | 0 | 0/2 | 0.885 | 0 | 0 | 0/1 | 0.962 | 0.308 |
| (a) Judge counts as in T08 | t 100, info | 0 | 6 | 0/2 | 0.115 | 0 | 4 | 0/1 | 0.154 | 0.808 |
| **(b) Judge on MET only if p(MET) < X** | **X 0.999, t 85, info** | 0 | 6 | **1/2** | **0.077** | **0** | 4 | 0/1 | **0.154** | **0.808** |
| (c) only if entailment < Y | Y 0.5, t 100, info | 0 | 6 | 0/2 | 0.115 | 0 | 4 | 0/1 | 0.154 | 0.808 |
| (d) not for language / proven years | t 100, info | 0 | 6 | 0/2 | 0.115 | 0 | 4 | 0/1 | 0.154 | 0.808 |
| (e) template v1 | t 100, info | 0 | 7 | 0/2 | 0.077 | 0 | 5 | 0/1 | 0.115 | 0.769 |
| (f) no Judge in the gate | t 85, info | 0 | 7 | 1/2 | 0.038 | 0 | 5 | 0/1 | 0.115 | 0.769 |

**Why (b), in plain words:**
- All families meet the hard rule (0 false invites) on dev.
- (b) is the only Judge variant that finds a real invite on dev (P50): the Judge doubted one of P50's quotes, but the Matcher was 99.98% sure.
- (b) also has one fewer false reject than the no-Judge fallback (f), 6 vs 7: the Judge's "the CV does show it" on a MISSING must-have rescues one pair into review.
- So a Judge variant beats (f) on the dev criteria, and (f) is not used. On test, (b) also has fewer false rejects than (f) (4 vs 5), at a slightly higher review rate (15.4% vs 11.5%).

**Tie-breaks** (written in the script):
- On dev, X ∈ {0.80…0.999} and `t_invite` ∈ {50…85} give identical results. I took the more careful values, 0.999 and 85.
- Consequence on test: the only gold invite, P52, goes to review. Its score is 78 < 85, and one must-have has p(MET) 0.9985 < 0.999.
- With `t_invite` 50 and X < 0.9985 it would have been invited. Dev cannot separate these settings. I did not change them after seeing test.

**Confusion matrices for the chosen gate** (rows = gold; columns = gate invite / review / reject):

| gold | dev invite | dev review | dev reject | test invite | test review | test reject |
|---|---|---|---|---|---|---|
| invite | 1 | 1 | 0 | 0 | 1 | 0 |
| review | 0 | 1 | 6 | 0 | 3 | 4 |
| reject | 0 | 0 | 17 | 0 | 0 | 18 |

**Pair flags block vs info** (chosen settings):

| pair flags | dev review | test review | dev FR | test FR |
|---|---|---|---|---|
| info (chosen) | 0.077 | 0.154 | 6 | 4 |
| block | 0.385 | 0.462 | 1 | 0 |

- **Trade-off:** block nearly removes the false rejects, but breaks the ≤ 25% review target. I chose the target. The false rejects are pairs the labelers sent to review because a must-have is UNCERTAIN in gold, for example P44–P46, locked as review by the Approver, while the Matcher said MISSING with no doubt flag. The gate cannot recover a doubt the Matcher did not express.

**What each rule changes (test):**
1. TEMP → the gate's outcome-relevance filter (rule 2 as in T08, family a): review rate 0.962 → 0.154, false rejects 0 → 4, agreement 0.308 → 0.808.
2. Adding the p(MET) condition (b): the same on test. On dev it adds 1 invite found and lowers review 0.115 → 0.077.
3. Pair flags block instead of info: test review 0.154 → 0.462, false rejects 4 → 0.

**n8n runs** (real-GPU, confirmed cards; `eval/results/2026-10-18_outcome_gate/n8n_e2e_T08b/`):

| pair | execution | outcome | rule | file |
|---|---|---|---|---|
| P50 (J4) | 25 | **invite** (score 89), `decided_by: gate` | 3 | `eval/outbox/invite/25_cv-48c47c41.json` |
| P35 (J4) | 26 | reject (score 11) | 1: r1, r3 MISSING | `eval/outbox/reject/26_cv-094fa696.json`, with the reasons and the review sentence |
| P15 (J2) | 27 | review (score 59) | 2: r1, r4 MISSING doubted by the Judge; r5 MET doubted | form submitted (`approve-invite`, labelled a Developer test) → resumed, success, `eval/outbox/invite/27_cv-7c53c25e.json`, `decided_by: human` |

- In P50, the Judge's `judge:disagrees` on r3 is listed but does not count (p(MET) 0.9998).
- All `/match` calls used LoRA scale 1; 0 identity values in the execution data.
- Copies of the outbox files are in the results folder.

**Tests:** `pytest tests/` gives **381 passed, 6 skipped** (T08: 374, plus 7 new).

## 3. Not done / problems

1. **False rejects remain:** 4 on test and 6 on dev. They come from the Matcher saying MISSING where the labelers say UNCERTAIN; T06/T07 showed the LoRA rarely says UNCERTAIN. The gate cannot fix this without breaking the review target (see block vs info).
2. **The test invite (P52) was missed:** it went to review because of the careful tie-break (`t_invite` 85). With only 3 gold invites (2 dev, 1 test), the invite side is barely measurable.
3. Variants (c) and (d) gave the same dev result as (a). On this data, neither the support score nor the language/years exception changes any pair's outcome.
4. **Confirmed cards in the demo come from gold** (sample cards). There is no recruiter UI yet: the card is posted as JSON in the webhook field.

## 4. Questions for the Brain

1. Should the false rejects (must-have MISSING where the CV has partial evidence) get a soft rule? For example, a must-have MISSING whose p(MISSING) is below some level goes to review. That rule would act on the Matcher's confidence and would have to be tuned on dev with the review cap.
2. With only 3 gold invites: should more invite-type pairs be added before the final evaluation, so that false-invite safety and invite recall are measurable?

## 5. Suggested next step

The Bias Auditor (station 5: counterfactual swap test on must-haves and borderline cases), then the Report Writer (station 7). After that, a final end-to-end evaluation on all 52 pairs through n8n with confirmed cards.
