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

## Sessions (reviewed at 11:00Z; mock tests run by the orchestrator in `/home/user/hs-wt/<session>`)

| session | branch @ head | Claude session | delivered so far | blockers | tests (orchestrator rerun) |
|---|---|---|---|---|---|
| 1 RAG | `session/s1-rag-optimization` @ `f30197a` | `session_013GKCTUT4EiMBH2Q8tVdquw` | merged team `rag/`; gated provider `rag.gated.v1`; per-requirement RAG error analysis; retrieval metrics (BM25 + dense); E2E comparison prepared, not run; `docs/rag/RAG_OPTIMIZATION.md` | none (window 1 open) | MOCK: 105 passed, 8 skipped |
| 2 Matcher LoRA | `session/s2-matcher-lora-integration` @ `03b6431` | `session_01ReP1Qmd3Hq69cVnvLM4RZJ` | pinned LoRA provenance per result, `/v1/models` alias check, strict JSON repair, review routing, fake-server mock tests, live harness + smoke script; `docs/MATCHER_INTEGRATION.md` | none (window 1 open) | MOCK: 71 passed, 6 skipped |
| 3 Soft prompt | `session/s3-matcher-soft-prompt` @ `88e1fb4` | `session_01Uxb7wkSL8FdicKUG7jGBk8` | PEFT prompt-tuning pipeline, 4-arm eval (one backend + dtype enforced), Kaggle bundle + notebook, tiny-model SMOKE run (all arms 0.061: random model, no valid JSON), tokenizer/PEFT compatibility check | **4B training needs a GPU**: CPU estimate about 8.5 h per soft prompt, about 20 h total; fp32 needs 16.1 GB. Not approved on CPU. Waiting on the owner to run `prompt_tuning/kaggle_soft_prompt.ipynb` on Kaggle | fixture defect fixed (`de4bd64`); orchestrator rerun with torch: 64 passed, 2 skipped |
| 4 Bias Auditor | `session/s4-bias-auditor` @ `9173d6d` | `session_01QjD3VUqjjj6hLiUU5LegT1` | extended attributes + placebo floor, rules v2, prompted reviewer, adapter registry, fairness test set (dev/test/blind), paired McNemar, window-1 runner; `docs/BIAS_AUDITOR.md` | the evaluation session has its own LoRA bias re-audit queued: reuse it, do not duplicate | MOCK: 71 passed, 2 skipped |
| 5 QA | `session/s5-qa-contracts` @ `91a88fb` | `session_015KY6nW8NkJuGZ2rB35uZGz` | contract, grounding, false-MET, citation, injection, Judge, bias and fallback tests; Judge fixes QA-017/018/019; live suite; `docs/qa/FAILURES.md` (18 open defects) | none | MOCK: 129 passed, 2 skipped, 26 xfailed |
| 6 Orchestrator | `claude/beautiful-galileo-o36bdv` | `session_01CyLv8Vej3sAYAmPbyrDsJy` | plan, contracts, tracker, reviews | final E2E waits for window 2 | baseline MOCK: 50 passed, 1 skipped |

Ownership check at 11:00Z: no session edited a file outside its ownership or a frozen contract. S2 added new files
(`scripts/check_matcher_lora.py`, `scripts/live_smoke.{py,sh}`, `docs/matcher_integration/`); accepted.

No session branch has been merged into the integration branch yet.

## Log

- 2026-10-16: audit done, branches and worktrees created, contracts frozen (v1).
- 2026-10-16 10:05Z: sessions S1–S5 launched as independent cloud sessions (tag `hiresignal-orchestra`), each on its own branch and container.
- 2026-10-16 11:05Z: LoRA evaluation complete (202/202). Window 1 opened. First review of all branches; S3 test defect found.
- 2026-10-16 11:10Z: S3 fixture defect fixed and verified. S3 4B training waits on a Kaggle GPU run by the owner (not approved on CPU).
