# HireSignal session status

Maintained by Session 6. Plan and rules: `docs/orchestration/ORCHESTRATION.md`.

**Compute window: 1 (opened 2026-10-16 11:05Z).** The 202-requirement LoRA evaluation is complete
(`claude/kind-albattani-k7qlt9` @ `46d24e1`, 202/202 predictions for both arms, `metrics.json` committed).
Live LLM work is allowed: one model job at a time per container (`flock /home/user/hs_queue.lock`). The evaluation
session continues its own follow-up runs in its own container; never touch them.

## LoRA evaluation result (LIVE, val, 202 requirements, Q4_K_M, llama.cpp, prompt p1)

Source: `benchmark/results/CONSOLIDATED_val.md` on `claude/kind-albattani-k7qlt9` @ `46d24e1`.

| arm | macro-F1 | false-MET | JSON valid | UNCERTAIN | expl. on topic | p50 / p95 s |
|---|---|---|---|---|---|---|
| base, no RAG | 0.634 | 0.009 | 0.950 | 0.495 | 0.847 | 12.9 / 20.8 |
| base, BM25 RAG | 0.630 | 0.009 | 0.916 | 0.505 | 0.837 | 16.4 / 34.3 |
| LoRA, no RAG | **0.908** | 0.026 | 1.000 | 0.178 | **0.000** | 8.9 / 13.9 |
| LoRA, BM25 RAG | 0.897 | 0.034 | 1.000 | 0.153 | **0.000** | 13.1 / 21.5 |

Open issues raised by this result:
1. RAG still costs about 0.011 macro-F1 and raises false-MET (0.026 → 0.034) on the LoRA Matcher. Not yet tested
   for significance. Owner: S1.
2. False-MET rose about 3× from base to LoRA (0.009 → 0.026 / 0.034). Owners: S5 (error analysis), S2 (review routing).
3. The LoRA writes fixed template explanations ("The CV directly shows this requirement; ...") that never name the
   requirement (expl. on topic 0.000). This is an explainability gap. Owner: S2, with S5 tests. Any fix must not
   invent claims: it may only use the verified evidence quotes and cited RAG refs.
4. The consolidated table shows adapter `n/a` for the LoRA runs. Provenance belongs in the report. Owner: S2.

## Sessions (reviewed at 11:56Z; mock tests rerun by the orchestrator)

| session | branch @ head | Claude session | state | blockers | tests |
|---|---|---|---|---|---|
| 1 RAG | `session/s1-rag-optimization` @ `864ccf8` | `session_013GKCTUT4EiMBH2Q8tVdquw` | gated provider `rag.gated.v1`; error analysis; retrieval metrics. Paired on reused eval predictions: LoRA BM25 vs none Δ macro-F1 −0.011 [−0.047, +0.021], McNemar p = 1.0 (not significant). **LIVE E2E running:** `lora__gated` 131/202; `lora__none` repeat next | not merged: E2E incomplete; QA-001, QA-023 open; owes S2 `knowledge_version` (QA-014) | MOCK at `f30197a`: 105 passed, 8 skipped |
| 2 Matcher LoRA | merged (`04bac85`, from `598d958`) | `session_01ReP1Qmd3Hq69cVnvLM4RZJ` | LoRA primary + pinned provenance, fallback, strict JSON, review routing, grounded explanation, opt-in bias-auditor wiring (`HS_BIAS_AUDITOR`, default `rules_v1`). **LIVE smoke** `benchmark/results/live_smoke/20261016T113444Z` (ran before validator v2): 4/4 live tests, 14/14 checks | QA-014 (waits on S1), QA-027 (model-level, caught by validator) | merged branch MOCK: 200 passed, 5 skipped, 7 xfailed |
| 3 Soft prompt | `session/s3-matcher-soft-prompt` @ `9c62328` | `session_01Uxb7wkSL8FdicKUG7jGBk8` | pipeline, 4-arm eval, Kaggle bundle + notebook, validating importer (97 checks), SMOKE run only | **owner decision: run the Kaggle notebook on a GPU.** CPU 4B training not approved (about 20 h) | MOCK: 74 passed, 2 skipped (with torch) |
| 4 Bias Auditor | `session/s4-bias-auditor` @ `73bfe8c` | `session_01QjD3VUqjjj6hLiUU5LegT1` | rules v2, prompted reviewer. **LIVE (base Qwen3-4B reviewer):** holdout recall 25/26, FP 0/18 (same-author test set: upper bound). QA-016/020 fixed; QA-029 pre-registered flip analysis added; base-Matcher new-attribute arm running | not merged: LoRA flip-rate arm pending (torch install for adapter conversion) | MOCK at `d025a3d`: 179 passed, 1 skipped, 13 xfailed |
| 5 QA | merged (`115f364`, from `a11296f`) | `session_015KY6nW8NkJuGZ2rB35uZGz` | contract/adversarial suites; validator v2 patch; false-MET analysis; **LIVE suite** `docs/qa/live_runs/20261016T111644Z`: 19 passed, 2 xfailed, 1 skipped; QA-029 found; Judge τ recheck (unchanged); QA-030 fixed | live Judge run needs the fine-tuned Judge checkpoint (not available in any session) | in integration branch |
| 6 Orchestrator | `claude/beautiful-galileo-o36bdv` @ `04bac85` | `session_01CyLv8Vej3sAYAmPbyrDsJy` | S5 and S2 merged; validator v2 + narrow S2 cues; contract decisions QA-010/011 | final real E2E after S1 + S4 merges | integration MOCK: 200 passed, 5 skipped, 7 xfailed |

Evaluation session (read-only): `claude/kind-albattani-k7qlt9` @ `e995669` — its LoRA bias audit is in progress; S4 will reuse it.

## Integration branch

- `e3aa6c8`: merged `session/s5-qa-contracts` @ `a4379ed` (QA suites, Judge fixes QA-017/018/019, failure log).
- `4f38c97`: **validator v2 + prompt fence** (S5 patch to frozen files `matcher/validate.py`, `matcher/prompt.py`).
  Fixes QA-002/003/004/005/007/008/009/012/022/025/026. Decision changes go only MET to UNCERTAIN (human review).
  MOCK: `pytest matcher benchmark/tests tests/qa` gives 154 passed, 1 skipped, 15 xfailed.
  Orchestrator replay of the committed LIVE val raw outputs (no model call; v1 replay reproduces the saved decisions
  with 0 changes):

  | arm | v1 macro-F1 / false-MET | v2 macro-F1 / false-MET | review rate v1 / v2 |
  |---|---|---|---|
  | LoRA, no RAG | 0.908 / 0.026 | 0.929 / 0.000 | 0.663 / 0.668 |
  | LoRA, BM25 RAG | 0.897 / 0.034 | 0.926 / 0.000 | 0.574 / 0.584 |
  | base, no RAG | 0.634 / 0.009 | 0.640 / 0.000 | 0.782 / 0.782 |
  | base, BM25 RAG | 0.630 / 0.009 | 0.635 / 0.000 | 0.743 / 0.743 |

  **In-sample:** the QA-025/026 rules were written after inspecting val errors. Held-out effect is measured once in
  the locked-test final run, with v1 and v2 replays reported side by side.
- All session branches must merge `claude/beautiful-galileo-o36bdv` before their next merge request.

## Log

- 2026-10-16: audit done, branches and worktrees created, contracts frozen (v1).
- 2026-10-16 10:05Z: sessions S1–S5 launched as independent cloud sessions (tag `hiresignal-orchestra`), each on its own branch and container.
- 2026-10-16 11:05Z: LoRA evaluation complete (202/202). Window 1 opened. First review of all branches; S3 test defect found.
- 2026-10-16 11:10Z: S3 fixture defect fixed and verified. S3 4B training waits on a Kaggle GPU run by the owner (not approved on CPU).
- 2026-10-16 11:25Z: S5 merged; validator v2 applied and replay-verified on val (in-sample).
- 2026-10-16 11:35Z: S5 LIVE suite on real models (docs/qa/live_runs/20261016T111644Z on S5 @ eb03c46): 19 passed,
  2 xfailed (QA-014, QA-028 confirmed live), 1 skipped (Judge checkpoint absent). No unreviewed MET on 11 trap probes.
  New LIVE finding QA-029 (name-header counterfactual flip on a borderline item) sent to S4.
  Contract decisions QA-010 (`rag_refs` = knowledge shown to the model) and QA-011 (MISSING reviewed only for must)
  recorded in ORCHESTRATION.md §3; the code already behaves this way.
- 2026-10-16 11:56Z: S2 merged (6281fd8, 04bac85) + narrow intent cues (971f6fd). S1 LIVE gated arm at 131/202. Open owner decision: Kaggle GPU run for S3.
- 2026-10-16 12:55Z: S1 merged (23799f4). LIVE LoRA E2E (val 202): none 0.908, bm25 0.897 (reused), gated 0.903,
  none-repeat 0.905; gated vs none -0.005 [-0.028, +0.014], p=1.0 (noise floor -0.003). v2 replay: 0.929 / 0.926 /
  0.924 / 0.925, false-MET 0 everywhere; review rate lower with RAG (0.59 vs 0.67, untested). **Production default
  switched to HS_RAG=gated.** QA-001 and QA-014 closed. Integration MOCK (with rag/tests): 262 passed, 12 skipped,
  3 xfailed. Eval session's LoRA bias audit: 1/30 flagged (name signal, borderline item), same as base (f22b97f).
  Remaining before the final run: S4 merge (LoRA flip-rate arm), owner decision on the S3 Kaggle run.
- 2026-10-16 13:05Z: S4 merged (013189e, from 95dd5e3; its LoRA new-attribute + placebo arm keeps running, ETA 16:15Z).
  Core-4 LIVE flips: base 1/120, LoRA 1/120 (different borderline items, both name signal), McNemar p=1.0.
  **Production default switched to HS_BIAS_AUDITOR=rules_v2** (orchestrator-verified blind holdout n=44: recall 19/26
  for v1 and v2, FPR 9/18 vs 1/18). Reviewer (`rules_v2+reviewer`) stays opt-in (+11 s p50 per result).
  Integration MOCK (matcher, benchmark, qa, rag, bias): 289 passed, 12 skipped, 1 xfailed.
- 2026-10-16 13:05Z: S1 paired review-rate test (rag_opt/review_rate.py, val 202, LIVE LoRA outputs): gated vs none
  review rate 0.663 -> 0.589, delta -0.074 [-0.114, -0.040], McNemar 15/0, p = 0.0001 (same under validator v2);
  noise floor none-repeat vs none -0.005, p = 1.0. All 15 dropped reviews are on correct decisions. Mechanism: a
  shown ESCO alias counts as a requirement term (semantic_inference_no_term_in_quote -13). **This is RAG's measured,
  significant benefit on the LoRA Matcher: lower human-review load at equal accuracy and false-MET.** QA-023 closed as
  fixed in the production provider (gated), won't-fix in legacy BM25. S1 base-model arms running (~2.5 h, S1 container).
- 13:05Z: final locked-test run plan committed (a1f7f6d) before any test access; serving stack installing in S6.
- 2026-10-16 13:43Z: final run lora__gated 154/199 (~14 s/req). ETA: lora__gated ~13:55Z, lora__none ~14:40Z, base__gated ~15:30Z. S1 base arms and S4 new-attribute arms running in their containers.
- 2026-10-16 14:55Z: final run lora__gated + lora__none done, base__gated running. Pre-registered v1/v2 replay on test exposed **QA-031** (validator v2 clause-scoping bug: 36 correct METs per arm downgraded); fixed in 309a33f, val replay unchanged. Full results after base__gated (FINAL_REPORT.md).
- 2026-10-16 15:27Z: **final run recovered.** Cause of the stall: a `git stash`/`pop` in this worktree (~14:58Z) replaced
  base__gated/predictions.jsonl under the running writer; rows 37-104 went to the unlinked file and were lost, then the
  container restarted (~15:18Z). Recovery: the 36 saved rows verified (unique, test order, clean last line, equal to the
  committed copy); 9 of them are genuine base-model template echoes ("MET|MISSING|UNCERTAIN"), kept. Live output moved
  to /home/user/hs_final_run (outside git), LoRA arms checksummed and unchanged; resumed from a detached worktree pinned
  to 852daa4 so all 3 arms use identical pipeline code (validator fixes QA-031/032 apply only in later replays). Resume
  started at test-008/r1. Monitor: /home/user/hs_final_run_monitor.log, atomic snapshots in /home/user/hs_final_run_snapshots.
- Fine-tuned Judge: trained in the eval session's container at /home/user/judge_runs/deberta-hs-v1/best and never pushed
  (only metrics + train meta are in git). Recipe is committed (finetune/train_judge.py, train split, seed 13).

## Final-delivery phase (deadline 2026-10-17 22:59 UTC)

| component | owner | status | branch | session |
|---|---|---|---|---|
| NLI Judge (xsmall eval, calibration, provenance) | S7 | DONE, merged (default xsmall) | `session/s7-judge-nli` | `session_0162eFFwGNh9LTqytiCUyHWm` |
| Tiny SLM Report Writer (Qwen3-0.6B + deterministic fallback) | S8 | DONE, merged | `session/s8-slm-reporter` | `session_01SgDad1xET9FMM66nr7mdjH` |
| Integration contract v1.1 + adapters + handoffs | S6 | DONE (mock-tested) | `claude/beautiful-galileo-o36bdv` @ `cdd5cc0` | — |
| Deployment (FastAPI/Docker) | Dali | NOT STARTED in repo (no branch yet) | — | local |
| Upstream agents | Ayoub | PARTIAL: reader `2386e14`, job agent `985d14d` (Oct 15); Profile Agent not delivered | `feature/reader-agent`, `feature/job-agent` | local |
- 2026-10-16 17:05Z: S7 + S8 merged; LIVE end-to-end run with all models real (f8e67d7); FINAL_REPORT.md written.
