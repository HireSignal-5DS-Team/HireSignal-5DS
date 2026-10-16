# HireSignal NLI Judge

Owner: S7 (`session/s7-judge-nli`). Code: `matcher/judge.py`, `matcher/factory.py` (`judge_config`, `JUDGE_MODELS`),
`benchmark/judge_eval.py`, `judge/experiment.py`, `finetune/train_judge.py`. Tests: `matcher/tests/test_judge_nli.py`,
`tests/qa/test_qa_judge.py`, `matcher/tests/test_pipeline.py`. Results: `benchmark/results/judge/s7/experiment.{json,md}`.

The Judge is the stage after the validator and the Bias Auditor. For every validated requirement result it asks an NLI
cross-encoder whether the **CV text** supports the Matcher decision. It **only adds findings**. It never changes a
decision, and it never removes a validator or bias review reason. In the pipeline, a Judge `FAIL` adds
`judge:disagrees` and a Judge `UNCERTAIN` adds `judge:uncertain` to the review reasons.

## 1. Why NLI and not a generative judge

- **The task is NLI.** The question is "does this CV passage entail, contradict, or say nothing about this
  requirement?". A 3-way NLI cross-encoder answers exactly that, deterministically, in one forward pass.
- **It is independent of the Matcher.** A second Qwen call would share the Matcher's failure modes: the same base model,
  the same prompt sensitivity, and the same year arithmetic (QA-027). An encoder trained on MNLI/SNLI fails in different
  ways.
- **It cannot invent anything.** It outputs three scores. It writes no free text that could add claims to a report.
- **It is cheap.** Per requirement it takes 0.04 s (xsmall) or 0.09 s (base) on 4 CPU threads, against 9–13 s for the
  Matcher LLM call (§5). It needs no server and no GPU.
- **Its limits are known.** NLI models are weak on numbers and durations (§6). For that reason the duration checks stay
  in the validator.

## 2. Supported checkpoints (model-card facts, verified 2026-10-16)

| | `cross-encoder/nli-deberta-v3-xsmall` | `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` |
|---|---|---|
| pinned revision | `a150876415327c80daeff35ca6f68f5ed8cf5c24` | `6f5cf0a2b59cabb106aca4c287eed12e357e90eb` |
| licence | Apache-2.0 | MIT |
| base | `microsoft/deberta-v3-xsmall` | `microsoft/deberta-v3-base` |
| NLI training data (card) | SNLI, MultiNLI | MultiNLI, FEVER-NLI, ANLI |
| card accuracy | SNLI-test 91.64, MNLI-mismatched 87.77 | see card |
| parameters (measured) | 70.8 M (most of it is the 128k-token embedding matrix) | 184.4 M |
| weights file | `model.safetensors` 283 MB (fp32) | `model.safetensors` 369 MB |
| `id2label` | `0 contradiction, 1 entailment, 2 neutral` | `0 entailment, 1 neutral, 2 contradiction` |
| dtype | loaded in **fp32** on CPU (explicit `dtype=torch.float32`) | fp32 (its config says fp16, which would be wrong on CPU) |

**Label mapping.** The two checkpoints order their labels differently. Logits are therefore never read by position.
`label_index(id2label)` maps `entailment` / `neutral` / `contradiction` by **name**, either the exact name or its
4-letter prefix. It **raises** if the names are generic (`LABEL_0/1/2`), ambiguous or incomplete, so a checkpoint
whose labels it cannot map fails at load time. Verified with the real checkpoint: xsmall maps to
`{entailment: 1, neutral: 2, contradiction: 0}`. In the same test, "A man is eating pizza" / "A man eats something" is
entailment (0.94), and "Never used Kubernetes in production." / "The candidate has used Kubernetes in production." is
contradiction (0.995) (`test_real_xsmall_label_mapping_entailment_and_contradiction`).

## 3. What the Judge does

The premise is always taken from `CV.text`. The hypothesis is built from the requirement.

| validated decision | premise | supports the decision | opposes the decision |
|---|---|---|---|
| MET / supported | the verified quotes, each widened to its CV line (QA-017; list marker dropped, QA-030) | entailment | max(neutral, contradiction) |
| MISSING / contradicted | same | contradiction | entailment |
| MISSING / not_documented | the whole CV in ≤ 1500-character chunks; the chunk with the highest entailment decides (QA-018) | 1 − entailment | entailment |
| UNCERTAIN | none | none (verdict `NOT_APPLICABLE`; already sent to review) | none |

Verdict:
- `FAIL` if s(opp) ≥ τ_fail and s(opp) > s(sup);
- otherwise `PASS` if s(sup) ≥ τ_pass;
- otherwise `UNCERTAIN`.

If the NLI call fails, every item becomes `UNCERTAIN` with `error` set, and the pipeline does not crash (QA-019).

**Deterministic pre-checks (before any NLI call, `precheck`).**
- Every quote must be an exact CV substring. This reuses `matcher.validate.find_span`, the validator's own check, so
  the logic is not duplicated. A stored span is trusted only if it points at the same text. A quote that is not in the
  CV is dropped from the premise and recorded as `evidence_not_in_cv`, and the finding recommends review.
- A MET or MISSING/contradicted decision with no verified quote gives verdict `UNCERTAIN` with support status
  `missing_evidence`, a review recommendation, and **no NLI call**. Missing evidence is never read as support or as
  disproof.
- RAG text is never a premise. `judge_many(items)` never receives the knowledge refs, and every quote premise is
  asserted to be CV text. A quote copied from a KnowledgeRef is dropped (`test_rag_text_is_never_a_premise`).
- Numeric and duration checks stay in the validator. If the result carries `years_below_minimum_in_evidence`,
  `duration_not_verified` or `contradiction_refuted_by_evidence`, the finding records `validator:<reason>` in
  `prechecks` and recommends review whatever the NLI says. A Judge `PASS` never clears a validator flag
  (`test_judge_pass_never_clears_a_validator_numeric_check`).

**Output: `JudgeFinding`.** Every finding has these fields:
- `judge_verdict`, `judge_score`, `judge_disagrees`, `requires_human_review`;
- `nli_probs = {entailment, neutral, contradiction}`;
- `premise_kind`, `model`, `error`;
- `support_status`: `supports_decision | opposes_decision | inconclusive | missing_evidence | not_checked`;
- `recommendation`: `review | no_judge_concern`;
- `prechecks`;
- `provenance = {model_id, revision, tau_pass, tau_fail, hypothesis, premise_policy, scores}`.

For a local fine-tuned directory, `revision` is `local:<path>#sha256:<16 hex of the weights>`.

> **The scores are not probabilities of correctness.** `nli_probs` and `judge_score` are the softmax outputs of an NLI
> head trained on SNLI/MNLI-style data. They are not the probability that the Matcher decision is right. Measured
> ECE when they are read that way is 0.52–0.58 for the pretrained models on val (`experiment.json`, field `ece`).
> `no_judge_concern` is not an approval: the validator and bias reasons still apply.

**Hypothesis templates.**
- `v1`: "The candidate meets this job requirement: {text} (at least N years)." This is the original template.
- `v2`: "The candidate has {text}." This is closer to an SNLI hypothesis.

Each model's template is chosen on train-dev (§4). On a pure-NLI model the template matters a lot. For example,
pretrained xsmall scores "5 years of professional Python development" vs the v1 hypothesis for "Python development"
as neutral 0.96, but scores it as entailment 0.97 for "The person has experience with Python development."

## 4. Calibration (train-dev only) and validation protocol

The protocol below is implemented in `judge/experiment.py` and was fixed before any val number was read.

1. **Calibration items.** `benchmark/results/lexical-rag-train` (lexical baseline outputs on TRAIN), restricted to
   train-dev (train case index % 5 == 0, as in `train_judge.py`): 142 items, 37 Matcher errors. The raw outputs are
   re-validated by the current validator. These are the only Matcher predictions on train in the repo. No LoRA
   predictions on train exist.
2. **Template selection.** For each model, the template with the higher train-dev AUROC of the wrongness score
   (1 − s(sup)) is kept.
3. **τ_fail** = argmax of strict-FAIL F1 on train-dev (grid 0.30…0.95, step 0.05; ties go to the lower value). This is
   the legacy S5 protocol, and it reproduces τ = 0.65 for the base model.
4. **τ_pass** = argmin of `5·(errors judged PASS) + (correct items judged FAIL/UNCERTAIN)`, with τ_fail fixed. This
   treats one unflagged Matcher error as costing as much as five unnecessary reviews. That weight is a policy choice
   the owner can change. Sensitivity is in `calibration.tau_pass_if_w_miss`.
5. **Validation.** Saved LIVE outputs of the LoRA Matcher on val (`rag_opt/results/e2e/lora__{gated,none,bm25}`, 202
   requirements each). All Judges score the same pairs. Two views:
   - `replay-v2`: the raw outputs re-validated by the current validator, i.e. what the pipeline Judge sees;
   - `saved-v1`: the decisions as saved by the live run (validator v1). This view still contains the wrong METs, so
     it shows the Judge as defence in depth if the validator rules miss something.

   The test split is never read.

Calibrated thresholds:

| Judge | hypothesis (train-dev AUROC v1 / v2) | τ_pass | τ_fail | τ_pass if w = 2 / 10 |
|---|---|---|---|---|
| xsmall, pretrained | v2 (0.570 / 0.648) | 0.75 | 0.85 | 0.55 / 0.95 |
| base, pretrained | v1 (0.851 / 0.803) | 0.40 | 0.65 | 0.30 / 0.40 |
| xsmall-ft2 (fine-tuned, §5.1, not published) | v1 (0.854 / 0.829) | 0.30 | 0.30 | (grid floor) |

## 5. Results on val (measured, LIVE Matcher outputs, Judge on CPU)

The Matcher is Qwen3-4B-Instruct-2507 Q4_K_M + `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1`
(llama.cpp, prompt p1), from saved live runs. Split: val. Main arm: `gated` (the production RAG default).
The full table, including the `bm25` arm, is in `benchmark/results/judge/s7/experiment.md`.

| Judge (revision) | view | FAIL precision | FAIL recall | TP/FP/FN | false approvals / wrong MET | Judge review rate | validator → validator+Judge review | AUROC |
|---|---|---|---|---|---|---|---|---|
| xsmall `a1508764` | gated replay-v2 | 0.000 | 0.000 | 0/46/8 | 0 / 0 | 0.748 | 0.594 → 0.901 | 0.746 |
| xsmall `a1508764` | gated saved-v1 | 0.042 | 0.182 | 2/46/9 | 0 / 3 | 0.748 | 0.589 → 0.901 | 0.781 |
| xsmall `a1508764` | none replay-v2 | 0.000 | 0.000 | 0/45/9 | 0 / 0 | 0.733 | 0.668 → 0.921 | 0.593 |
| base `6f5cf0a2` | gated replay-v2 | 0.016 | 0.125 | 1/63/7 | 0 / 0 | 0.698 | 0.594 → 0.876 | 0.936 |
| base `6f5cf0a2` | gated saved-v1 | 0.045 | 0.273 | 3/63/8 | 0 / 3 | 0.698 | 0.589 → 0.876 | 0.802 |
| base `6f5cf0a2` | none replay-v2 | 0.016 | 0.111 | 1/61/8 | 0 / 0 | 0.688 | 0.668 → 0.871 | 0.777 |
| xsmall-ft2 (local) | gated replay-v2 | 0.105 | 0.250 | 2/17/6 | 0 / 0 | 0.356 | 0.594 → 0.658 | 0.971 |
| xsmall-ft2 (local) | gated saved-v1 | 0.190 | 0.364 | 4/17/7 | **1 / 3** | 0.351 | 0.589 → 0.653 | 0.962 |
| xsmall-ft2 (local) | none replay-v2 | 0.118 | 0.222 | 2/15/7 | 0 / 0 | 0.327 | 0.668 → 0.678 | 0.770 |

Column notes:
- FAIL precision/recall are computed over the applicable items, i.e. those whose decision is not UNCERTAIN (161–167
  per arm).
- "False approvals" means a wrong MET judged PASS.
- The review rates count all 202 items. The bias reasons are not included.

Latency per requirement (batch size 1, fp32, CPU, 4 torch threads, the 163 gated val items that need NLI):

| Judge | p50 s | p95 s | load s |
|---|---|---|---|
| xsmall | 0.038 | 0.062 | 1–5 |
| base | 0.092 | 0.136 | 1 |
| xsmall fine-tuned | 0.034–0.038 | 0.049–0.058 | 1.5 |

What the numbers say:
- **After validator v2, the LoRA Matcher has no wrong METs on val** (0/0 in every replay-v2 row). The validator rules
  were partly written on val (STATUS.md, in-sample), so the held-out effect is unknown. False approvals can only be
  measured on the saved-v1 view. There, the 3–4 wrong METs per arm are 2 "applied … in side projects over time"
  items with no stated duration and 1–2 "watched tutorials" items. **Both pretrained Judges approve none of them.**
- **The pretrained Judges are poor error detectors on these outputs.** Their FAIL precision is ≤ 0.06. Most of their
  FAILs are on correct METs that a generic NLI model calls "neutral", e.g. "Spoken languages: Portuguese (C2)" for
  "Portuguese at C1 level or above", or "Led the migration of reporting jobs to Vue.js" for "Working knowledge of
  Vue.js". As a result they raise the review rate by about 0.2–0.3 (gated: 0.594 → 0.876 with base, → 0.901 with
  xsmall). Base ranks errors much better than xsmall (AUROC 0.94 vs 0.75 on gated replay-v2), has 0 false approvals,
  and adds less review than xsmall.
- **Pretrained xsmall vs base on the same pairs:** xsmall is 2.4× faster (0.038 vs 0.092 s p50) and 2.6× smaller.
  It is worse on every quality metric: AUROC on train-dev 0.65 vs 0.85, FAIL recall 0.00 on replay-v2, and a higher
  review rate. The speed gain does not matter, because the Matcher call takes 9–13 s.

### 5.1 Fine-tuned xsmall (optional item, measured)

Recipe: `finetune/train_judge.py` with `--base cross-encoder/nli-deberta-v3-xsmall --base-rev a1508764...`. Data:
train split only. Train-dev is used for early stopping. Seed 13.

| run | epochs / lr | best train-dev acc | wall time (4 CPU) | where |
|---|---|---|---|---|
| xsmall-ft1 | 2 / 2e-5 (the recipe as is) | 0.9375 | 3.6 min | `/home/user/judge_runs/xsmall-hs-v1/best` (outside git) |
| xsmall-ft2 | 4 / 5e-5 (one variant, selected on train-dev acc) | 0.9952 | 6.1 min | `/home/user/judge_runs/xsmall-hs-v2/best` (outside git) |

Results of ft2:
- **What it gains (measured on val).** About half the Judge review rate (0.36 vs 0.70), 3–6× the FAIL precision, and
  the best AUROC.
- **What disqualifies it as a default:**
  1. It **approves the weak-exposure false METs** that QA-025/QA-030 were about: `val-029/r4` "Watched tutorials about
     Angular in spare time" in all three arms, and also `val-017/r1` in the bm25 arm. The training pairs contain no
     weak-exposure negatives, so the model learned that "skill named in the quote" means entailment. Validator v2
     (`weak_evidence_cue`) catches both items, so in the current pipeline they are reviewed anyway. As defence in
     depth, however, ft2 is worse than the pretrained models on exactly the error type that matters.
  2. Its thresholds sit at the grid floor (0.30). They were calibrated on the same train-dev used for early stopping,
     where it is near-perfect (FAIL precision 1.00). They are therefore not a reliable estimate.
  3. It is not published. A pinned production default must be reproducible from a Hub revision.

How to publish (not done; it needs an owner decision and a write token):
1. Add weak-exposure and no-duration negatives (`neutral`) to `train_judge.pairs` from **train** only, and retrain.
2. Calibrate τ on a train-dev that was not used for early stopping, e.g. split it again by case index % 10.
3. `huggingface-cli upload HireSignal-5DS-Team/hiresignal-judge-xsmall <dir>` with `judge_meta.json` and
   `judge_calibration.json`. Then add the repo + commit sha to `JUDGE_MODELS`.
4. Re-run `python -m judge.experiment` and compare with base on the same pairs.

## 6. Limitations

- **The calibration set does not match the deployed Matcher.** Train-dev holds lexical-baseline errors, which are
  different from LoRA errors. Thresholds carried over to the LoRA outputs give many FAILs on correct METs. No LoRA
  predictions on train exist to calibrate on.
- **Val has few errors.** Each arm has 8–9 applicable Matcher errors (replay-v2) and 3–4 wrong METs (saved-v1). Every
  precision/recall above has a wide uncertainty (one item moves recall by 0.11–0.14). None of these differences was
  tested for significance.
- **NLI is weak on numbers and durations** ("4 years" vs "at least 3 years") and on CEFR levels. That is why the
  validator owns these checks and the Judge never overrides them.
- **"Neutral" counts as FAIL for a MET.** This makes the pretrained Judges strict. Every such FAIL adds review and
  never rejects anyone, so the cost is reviewer time.
- **English only.** Long CVs cost one NLI pair per 1500-character chunk for not_documented items.

## 7. Deployment

**Production default (owner decision): `cross-encoder/nli-deberta-v3-xsmall@a1508764`, hypothesis v2, τ_pass 0.75,
τ_fail 0.85** (`JUDGE_DEFAULT` in `matcher/factory.py`, set by the orchestrator in `e3bca19`). It is pinned,
Apache-2.0, the smallest supported checkpoint, and approved 0 wrong METs on val.

**Measured-better alternative: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli@6f5cf0a2`, hypothesis v1, τ_pass 0.40,
τ_fail 0.65**, selectable with `HS_JUDGE_MODEL`. On the same val pairs (gated arm, replay-v2) it ranks Matcher errors
better (AUROC 0.94 vs 0.75), also approved 0 wrong METs, and adds slightly less review (validator+Judge 0.876 vs 0.901).
Both pretrained Judges add about +0.28–0.31 review rate. Latency (0.09 vs 0.04 s per requirement) is negligible next to
the Matcher call.

```bash
HS_JUDGE=on                                                  # off disables the Judge
HS_JUDGE_MODEL=cross-encoder/nli-deberta-v3-xsmall           # Hub id or local dir (HS_JUDGE_DIR is the old name)
HS_JUDGE_REVISION=a150876415327c80daeff35ca6f68f5ed8cf5c24    # defaults to the JUDGE_MODELS pin
HS_JUDGE_TAU_PASS=0.75                                        # defaults to the calibrated value
HS_JUDGE_TAU_FAIL=0.85                                        # HS_JUDGE_TAU sets both
HS_JUDGE_HYPOTHESIS=v2                                        # v1 | v2, defaults to the calibrated template
# measured-better alternative:
# HS_JUDGE_MODEL=MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (pins 6f5cf0a2..., τ_pass 0.40, τ_fail 0.65, v1 applied automatically)
HF_HOME=<model cache>  HF_HUB_OFFLINE=1                      # after a first download, run offline
```

A local fine-tuned directory may carry `judge_calibration.json` (`tau_pass`, `tau_fail`, `hypothesis`), which
`judge_config` reads. If HS_JUDGE_MODEL names a local directory that is missing, the factory falls back to
`JUDGE_DEFAULT` and says so in the Judge name.

Reproduce:

```bash
HF_HOME=/home/user/hf python -m judge.experiment \
  --model xsmall=cross-encoder/nli-deberta-v3-xsmall@a150876415327c80daeff35ca6f68f5ed8cf5c24 \
  --model base=MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli@6f5cf0a2b59cabb106aca4c287eed12e357e90eb \
  --out benchmark/results/judge/s7          # about 3 min on 4 CPUs; NLI scores cached in /home/user/judge_runs/s7_cache
```
