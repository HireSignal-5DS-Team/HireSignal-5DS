# T07 report — Judge (NLI) + confidence check, measured against the T06 baseline

Date: 2026-10-18. No git commands were run.
- The measurements reuse T06's Matcher rows (`eval/results/2026-10-18_real_baseline/rows.jsonl`, real-GPU). **The Matcher was not re-run.**
- NLI scoring is **real-GPU** (RTX 4050, CUDA). The one real-model unit test is **real-CPU**.
- **Every threshold and the hypothesis template were chosen on dev only.** Test was used only for reporting.

**Summary:**
- **Confidence check** (`tau_conf = 0.72`), test results:
  - macro-F1 **0.608 → 0.642**;
  - UNCERTAIN recall 0.10 → 0.30 (gold-UNCERTAIN rows answered UNCERTAIN: 2 → 6 of 20);
  - false MET 11 → 8;
  - accuracy 0.800 → 0.764;
  - review load 4% → 16%.
- **Judge** (DeBERTa-v3-base, template v2, `tau_pass 0.05`, `tau_fail 0.15`), test results:
  - false METs flagged for review **3/11 → 9/11**;
  - all errors flagged 3/28 → 11/28;
  - review load 4% → 28%;
  - decisions unchanged.
- **Both together** (test): macro-F1 0.642, false MET 8 (7 flagged), errors flagged 21/33, review load 35%.
- **End-to-end:** `/judge` is wired into n8n after `/match`. One webhook run (P15) succeeded.
- **Tests:** 359 passed, 6 skipped (OCR).
- **Final state:** llama-server and the API are stopped; n8n is running.

## 1. Done

**Part A: Judge station** ([services/judge/judge.py](../services/judge/judge.py), adapted from V2 `matcher/judge.py`, rule-6 header; `POST /judge` in [services/api.py](../services/api.py)):
- **Logic kept from V2:**
  - the premise is the verified quotes, widened to their CV line (list markers dropped);
  - for MISSING/not_documented, the premise is the whole CV in 1,500-character chunks, and the chunk with the highest entailment decides;
  - UNCERTAIN gives NOT_APPLICABLE;
  - NLI labels are mapped by name (`label_index`);
  - the premise is asserted to be CV text, so RAG knowledge never reaches the NLI;
  - an NLI failure gives UNCERTAIN with an `error`, never a crash.
- **Changes:**
  - it works on plain dicts (our `/match` output);
  - review reasons `judge:disagrees` (FAIL) and `judge:uncertain` (UNCERTAIN);
  - validator numeric reasons are recorded only as `notes`;
  - probabilities and the verdict are separate functions, so thresholds could be chosen offline.
- **Contracts** ([services/contracts.py](../services/contracts.py)): `JudgeIn` (cv_text, requirement, match) and `JudgeOut` = the `/match` result passed through, with the Judge's review reasons added plus a `judge` finding. **The decision is never changed.**
- **Settings** in [config/.env.example](../config/.env.example): `JUDGE_MODEL_DIR`, `JUDGE_DEVICE`, `JUDGE_HYPOTHESIS=v2`, `JUDGE_TAU_PASS=0.05`, `JUDGE_TAU_FAIL=0.15`.
- **Regeneration check:** I rebuilt the anonymised text from `private/<cv_id>.reader.json` with the same anonymiser code. It is identical for **40/40 pairs**, and all **131/131** saved quote spans still match. No mismatches.

**Part B: confidence check** inside `/match` ([services/matcher/matcher.py](../services/matcher/matcher.py) `apply_confidence_rule`):
- If p(model decision) < `MATCHER_TAU_CONF` (default 0.72): the decision becomes UNCERTAIN, `model_decision` is kept, and the review reason `match:low_confidence` is added.
- **Bench-v1 val secondary check:** skipped. T03 did not save probabilities.

**Part C:** [scripts/eval_judge_confidence.py](../scripts/eval_judge_confidence.py), with results in [eval/results/2026-10-18_judge_confidence/](../eval/results/2026-10-18_judge_confidence/):
- `summary.json`: all tables (dev, test, all, and without J2 r6);
- `rows_<variant>.jsonl`, `nli_scores_v1.jsonl` / `nli_scores_v2.jsonl` and their timings;
- `SUMMARY.md` (for non-experts, with 2 real examples per check), `config.json`;
- `n8n_e2e/` (the Part D run).

**Part D:** an `HTTP /judge` node after `HTTP /match` inside "Loop requirements (1 at a time)".
- Its body takes `cv_text` and `requirement` from the loop item and `match` from `$json`. Timeout 300 s, Retry On Fail 2×5 s.
- The TEMP outcome node also returns `confidence` and `judge` per requirement.
- Re-imported (I first checked that the live workflow had no UI edits: its nodes, connections and settings equalled the T05 export), published, re-exported and cleaned into [n8n/hiresignal_v1.json](../n8n/hiresignal_v1.json) (18 nodes). [n8n/README.md](../n8n/README.md) is updated.

**Prompt library** ([prompts/PROMPT_LIBRARY.md](../prompts/PROMPT_LIBRARY.md)): two guardrail rows with before/after numbers, `guard-matcher-confidence` and `guard-judge-nli`.

**Tests** ([tests/test_judge.py](../tests/test_judge.py), 16 tests; mock NLI except one real-model test):
- verdicts per decision type;
- UNCERTAIN gives NOT_APPLICABLE without a model call;
- MET with an unverified quote gives UNCERTAIN without NLI;
- line widening shows a negation ("Never used Kubernetes…");
- the premise is never knowledge text;
- an NLI failure is handled;
- labels are mapped by name, and generic labels are refused;
- hypothesis templates and chunking;
- the confidence rule (lowers a decision, keeps a confident one);
- `/judge` passes the `/match` result through and adds reasons;
- real DeBERTa on two clear cases (real-CPU).

## 2. Evidence

**Choosing `tau_conf` on dev** (dev: 140 rows, 30 errors before; baseline dev macro-F1 0.558). The table shows the change against baseline:

| tau_conf | dev macro-F1 | dev accuracy | made UNCERTAIN | of these, wrong before | of these, now correct | correct answers sent to review |
|---|---|---|---|---|---|---|
| 0.60 | 0.610 | 0.757 | 14 | 10 | 4 | 4 |
| 0.70 | **0.642** | 0.757 | 20 | 13 | 7 | 7 |
| **0.72** | **0.642** | 0.757 | 20 | 13 | 7 | 7 |
| 0.75 | 0.621 | 0.736 | 23 | 16 | 7 | 7 |
| 0.80 | 0.619 | 0.714 | 28 | 20 | 8 | 8 |
| 0.85 | 0.613 | 0.700 | 32 | 24 | 8 | 8 |
| 0.90 | 0.591 | 0.650 | 41 | 32 | 9 | 9 |
| 0.95 | 0.566 | 0.607 | 56 | 44 | 12 | 12 |
| 0.98 | 0.566 | 0.579 | 66 | 51 | 15 | 15 |

- **Why 0.72:** it gives the highest dev macro-F1 (the task's criterion). 0.70 and 0.72 tie and change the same 20 rows; the tie-break takes the higher value.
- Above 0.72, more correct answers become UNCERTAIN than errors become correct UNCERTAINs, so macro-F1 falls.
- **Gold-UNCERTAIN rows recovered:** dev 1 → 8 of 19, test 2 → 6 of 20.

**Choosing the Judge settings on dev** (136 judged dev rows, 27 of them wrong):
- With template v1 and no cap, the best flag-F1 is 0.40, but it flags 83 rows (61%).
- With a cap of ≤ 25% flagged (the Locked review target), I compared templates v1 and v2 over `tau_pass` × `tau_fail` ∈ {0.05…0.95}:

  | template | best F1 under the cap | flagged (share) | precision | recall |
  |---|---|---|---|---|
  | v1 | 0.37 | 27 (20%) | | |
  | **v2** | **0.448** | 31 (22.8%) | 0.419 | 0.481 |

- I chose v2 with `tau_pass 0.05`, `tau_fail 0.15`. This means: **FAIL when the opposing NLI score beats the supporting one** (and is ≥ 0.15); PASS almost otherwise.
- Without the cap, v2's best F1 is 0.466 at 34% flagged; it was rejected for the review load.
- Final verdict counts on all 280 rows: PASS 204, FAIL 56, UNCERTAIN 13, NOT_APPLICABLE 7.
- **NLI speed:** 280 rows in 5.1 s on GPU (`nli_timing_v2.json`). In the n8n run, `/judge` took 0.6–1.3 s per requirement, including the HTTP call.

**Ablation**, from the saved rows. "Errors flagged" = wrong rows with at least one review reason. The Judge never changes decisions, so its decision metrics equal those of its pair without the Judge.

| variant | split | accuracy | macro-F1 | F1 MET / MISSING / UNCERTAIN | false MET (flagged) | UNCERTAIN recall | review load | errors flagged | TEMP outcome: agreement / review rate |
|---|---|---|---|---|---|---|---|---|---|
| 1 baseline | test | 0.800 | 0.608 | 0.762 / 0.887 / 0.174 | 11 (3) | 0.10 | 0.043 | 3/28 | 0.70 / 0.40 |
| 2 + confidence | test | 0.764 | **0.642** | 0.759 / 0.873 / 0.293 | 8 (2) | 0.30 | 0.164 | 16/33 | 0.30 / 0.80 |
| 3 + Judge | test | 0.800 | 0.608 | = baseline | 11 (**9**) | 0.10 | 0.279 | 11/28 | 0.20 / 0.90 |
| 4 + both | test | 0.764 | 0.642 | = row 2 | 8 (7) | 0.30 | 0.350 | 21/33 | 0.15 / 0.95 |
| 1 baseline | dev | 0.786 | 0.558 | 0.708 / 0.880 / 0.087 | 7 (2) | 0.05 | 0.043 | 3/30 | 0.80 / 0.25 |
| 2 + confidence | dev | 0.757 | 0.642 | 0.696 / 0.859 / 0.372 | 6 (2) | 0.42 | 0.186 | 16/34 | 0.35 / 0.70 |
| 3 + Judge | dev | 0.786 | 0.558 | = baseline | 7 (6) | 0.05 | 0.229 | 14/30 | 0.35 / 0.80 |
| 4 + both | dev | 0.757 | 0.642 | = row 2 | 6 (5) | 0.42 | 0.314 | 23/34 | 0.30 / 0.85 |

- **TEMP outcome is provisional:** gold outcomes are not human-checked yet and contain 0 invites, so the agreement column cannot judge an invite/review/reject gate.
- The TEMP rule ("any review reason, anywhere in the pair, sends the pair to review") turns every new flag into a pair-level review. That is why the pair review rate goes up to 0.95.

**Sensitivity without J2 r6** (test: accuracy / macro-F1 / false MET / UNCERTAIN recall / review load):

| variant | accuracy | macro-F1 | false MET | UNCERTAIN recall | review load |
|---|---|---|---|---|---|
| baseline | 0.822 | 0.627 | 9 | 0.11 | 0.044 |
| + confidence | 0.778 | 0.630 | 7 | 0.22 | 0.141 |
| + Judge | 0.822 | 0.627 | 9 | 0.11 | 0.274 |
| + both | 0.778 | 0.630 | 7 | 0.22 | 0.333 |

- Without J2 r6, the confidence gain on test is small (0.627 → 0.630), compared with 0.608 → 0.642 with it.
- Of the 4 gold-UNCERTAIN test rows newly recovered (P04 r3, P12 r6, P18 r6, P22 r1), 2 are J2 r6 rows (P12, P18). That requirement drives a good part of the test gain.
- On dev, the gain stays large without it: 0.538 → 0.636.

**Real-model findings** (real-CPU, from the unit test probe):
- With template v2, "Data analyst with 4 years of experience in SQL reporting" is judged:
  - against "The candidate has experience with SQL": entailment 0.99, **PASS**;
  - against "…hands-on experience with SQL": neutral 0.82, **FAIL**.
- Template v1 passes both (0.97 / 0.68).
- So v2 is strict on qualifiers ("hands-on", "strong", "excellent"). That explains part of the Judge's false alarms, for example P06 "Strong working knowledge of SQL", whose MET came from a language list.

**n8n end-to-end** (`n8n_e2e/P15_*`; real-GPU; n8n execution 14; these requirements come from the Job Agent, not gold):
- HTTP 200, status success, 53.4 s total.
- Node times: `/profile` 28.7 s, `/job` 6.0 s, `/match` 7 × (11.8 s in total), `/judge` 7 × (6.5 s in total).
- All `/match` calls used LoRA scale 1. 0 identity values were found in the execution data (the private file holds 0 values now, after the T06 fix), and the raw CV text is not in it.
- **Judge verdicts:** r7 "Good spoken English" got FAIL (neutral 0.997). This is the false MET known since T04. r1/r2 (Data Warehousing / Data Lakes, MISSING) got FAIL, because the CV entails them (0.93 / 0.92); in T06 the labelers marked r1 MET (from "Databricks Lakehouse"). The other 4 got PASS.
- None of P15's answers fell below 0.72 confidence.
- Outcome: review, with reasons `match:r1/r2/r7:judge:disagrees`.

**Tests:** `pytest tests/` gives **359 passed, 6 skipped** (OCR). That is T06's 343 plus 16 new.

## 3. Not done / problems

1. **Review load vs target:** with both checks, 35% of requirement checks (test) carry a review reason. The TEMP pair rule then sends 95% of pairs to review, far above the Locked target of ≤ 25%.
   - The Judge alone flags 28% (test), and its flag precision is low (dev 0.42).
   - The real gate (T08) has to weigh flags, for example by must-have only, or Judge FAIL only on MET. That cannot be measured until the gold outcomes are final.
2. **The confidence check lowers accuracy** (test 0.800 → 0.764): of the 18 rows it changes on test, 9 were correct before, and only 4 become correct (gold UNCERTAIN). They all go to review. Macro-F1 rises because UNCERTAIN improves. The criterion was macro-F1 on dev, as the task asked.
3. **J2 r6 sensitivity:** much of the test confidence gain comes from the soft-trait requirement (see the table above).
4. **Judge template and thresholds:**
   - `tau_pass 0.05` makes UNCERTAIN verdicts rare, so effectively only FAIL flags (`judge:uncertain` appears mainly for MET without a verified quote).
   - The template choice (v2) was also made on dev. It is strict on qualifiers.
5. **Bench-v1 secondary check:** not done, because T03 saved no probabilities.
6. **GPU:** in the n8n run, the Judge runs on the GPU next to llama-server. I did not record peak VRAM; the measured total was below 6 GB, since no OOM occurred. Set `JUDGE_DEVICE=cpu` if memory is tight.

## 4. Questions for the Brain

1. **For T08:** should the gate count `judge:disagrees` only on MET decisions and on must-haves, and treat MISSING-vs-CV-entailment FAILs as a softer signal? On dev, the not_documented FAILs were mostly right about a real gap (P15 r1, P21 r4/r5).
2. Should the confidence threshold be re-checked once J2 r6 is decided? Without it, the test gain is small.
3. Is a Judge flag precision of about 0.4 acceptable, or should we try the xsmall checkpoint or fine-tuning (V2 lost its fine-tuned Judge)? Both are out of scope here.

## 5. Suggested next step

T08, the Outcome gate:
- once the gold pair outcomes are final, use the variant-4 rows (`rows_4_both.jsonl`) offline to design must-have-weighted rules;
- target ≤ 25% of pairs reviewed and 0 false invites, fitted on dev and reported on test;
- then replace TEMP outcome in n8n with Switch/If nodes and the human-approval step.
