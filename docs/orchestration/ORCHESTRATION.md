# HireSignal: six-session parallel execution plan

Owner: Session 6 (orchestrator). Created 2026-10-16. Live status is in `docs/orchestration/STATUS.md`.

## 0. Audit at kick-off (2026-10-16, verified)

- `main` holds the initial commit only. The most integrated line is `feature/matcher-agent-pipeline` (`3f51c97`).
  It contains the evaluation line `claude/kind-albattani-k7qlt9` up to `4cfcc7d`, plus the agent pipeline
  (LoRA primary, base fallback, Qdrant provider, citations, counterfactual audit, Judge, integration tests).
- The **202-requirement LoRA evaluation** runs in a separate cloud session (`session_015pC4cWnLapLopyiUgf8VmG`,
  branch `claude/kind-albattani-k7qlt9`, last checkpoint `302a424`: 138/202, LoRA + BM25 RAG). It runs in its own
  container. **No session touches that branch, its container, its lock file or its result directories.**
- The orchestrator container: 4 vCPU, 15 GiB RAM, no GPU, no model server running. The other session containers are
  expected to have the same shape (not verified).
- Mock-only baseline on `3f51c97`: `pytest matcher benchmark/tests` gives 50 passed, 1 skipped. No live model ran.
- RAG audit (`claude/gracious-fermi-ncuem4`, `rag/audit/COMPLETE_RAG_AUDIT.md` §11): on the base Qwen3-4B Q4
  Matcher, BM25 RAG gives Δ macro-F1 −0.041 (95 % CI [−0.083, −0.000]); dense e5 gives −0.050. Most of the loss is
  invalid JSON from longer prompts (14 → 27 unparsed of 202). On parsed outputs, accuracy is nearly equal. RAG helps
  aliases (0.29 → 0.43) and hurts absent-skill traps and certifications.

## 1. Branches

| session | branch | base |
|---|---|---|
| 6 orchestrator / integration | `claude/beautiful-galileo-o36bdv` | `feature/matcher-agent-pipeline` |
| 1 RAG optimisation | `session/s1-rag-optimization` | integration branch |
| 2 fine-tuned Matcher integration | `session/s2-matcher-lora-integration` | integration branch |
| 3 Matcher soft prompt tuning (experimental) | `session/s3-matcher-soft-prompt` | integration branch |
| 4 Bias Auditor | `session/s4-bias-auditor` | integration branch |
| 5 independent QA | `session/s5-qa-contracts` | integration branch |

Rules: every session pushes only to its own branch. Nobody pushes to `main`, `claude/kind-albattani-k7qlt9` or a
teammate branch (`feature/*`, `claude/gracious-fermi-ncuem4`, `claude/vigilant-albattani-dmn3pk`, ...). No rebase or
force-push on a shared branch. To use a teammate branch, merge it into your session branch (a merge keeps their
history) or check it out read-only.

## 2. File ownership

A session edits only the files it owns. To change a file owned by someone else, write the request in
`docs/orchestration/requests/<session>-<topic>.md` on your own branch; the orchestrator decides.

| owner | files |
|---|---|
| S1 | `matcher/knowledge.py`, `benchmark/rag_check.py`, `rag/` (imported from `claude/gracious-fermi-ncuem4` by merge), new `rag_opt/`, `docs/rag/` |
| S2 | `matcher/agent.py`, `matcher/pipeline.py`, `matcher/factory.py`, `matcher/backends_api.py`, `matcher/output_adapters.py`, `scripts/run_pipeline.py`, `scripts/serve_qwen4b_lora.sh`, `config/`, `docs/AGENT_PIPELINE.md` |
| S3 | new `prompt_tuning/` only; results in `benchmark/results/experimental/soft_prompt/` |
| S4 | `matcher/bias_audit.py`, `benchmark/bias_eval.py`, new `bias/`, `benchmark/results/bias/`, `docs/BIAS_AUDITOR.md` |
| S5 | new `tests/qa/`, new `tests/live/`, `matcher/judge.py`, `benchmark/judge_eval.py` (fixes only, each with a failing test first), new `docs/qa/` |
| S6 | frozen contracts: `matcher/schemas.py`, `matcher/json_schemas/`, `matcher/validate.py`, `matcher/prompt.py` (production prompt p1), `benchmark/data/`, `benchmark/metrics.py`, `benchmark/run.py`, `docs/orchestration/` |
| eval session (read-only for all) | `scripts/eval_hs_lora.sh`, `scripts/hs_queue.sh`, `benchmark/results/qwen3-4b-q4+hslora-*` |

Existing tests (`matcher/tests/`, `benchmark/tests/`) must keep passing. Add tests; do not weaken existing ones.

## 3. Shared interfaces (frozen v1)

Change only through the orchestrator. S5 owns contract tests that pin these.

1. **Knowledge provider** (S1 implements, S2 consumes):
   `lookup(req: Requirement, k: int = 3, job_id: str | None = None) -> list[KnowledgeRef]`.
   It never receives CV text. Every `KnowledgeRef` has `source_type`, `source_id`, `retrieval` and may return an empty
   list (abstention). Selected by `HS_RAG` in `matcher/factory.py`.
2. **Generation backend** (S2): `generate(task: Task) -> str` (raw model text). Live models are served
   OpenAI-compatible by llama.cpp: primary LoRA on `:8081`, fallback base on `:8080`.
3. **Matcher output**: `ModelAnswer` → validator → `RequirementResult` → `MatchReport`
   (`matcher/json_schemas/*.schema.json`). Evidence quotes are verbatim CV substrings with spans; `rag_refs` are the
   cited `source_id`s; missing evidence is UNCERTAIN + review, never NOT_MET by inference.
4. **Provenance** (S2): `MatchReport.backend` records, for the model that answered each result: model id, base
   revision, adapter repo + sha (or none), primary/fallback, knowledge provider + its version, prompt id. A result
   produced by the fallback is routed to human review.
5. **Bias Auditor** (S4): `check_result(result, cv_text)` and `counterfactual(match_fn, cv, req, attributes)`
   → `BiasFinding`. It never changes a Matcher decision.
6. **Judge** (S5 tests): adds findings only; never overwrites a decision.

## 4. Evaluation protocol (everyone)

- Data: `benchmark/data` (bench-v1). Comparisons use the same **202 val requirements**. The test split stays
  locked; only the orchestrator unlocks it, once, for configurations already selected on val.
- Serving for any live comparison: Qwen3-4B-Instruct-2507 Q4_K_M (`unsloth/...-GGUF@a06e946b`), llama.cpp server,
  temperature 0, max 192 new tokens, prompt p1, same build for all arms of one comparison.
- Report: macro-F1, false-MET rate, JSON-valid rate, UNCERTAIN rate, latency p50/p95, peak RSS; paired McNemar and a
  bootstrap 95 % CI of the macro-F1 difference (`rag/significance.py`).
- **Every number names its backend.** A mock or fixture result is labelled `MOCK` and is never presented as a model
  result. Live results include the run directory with `metrics.json`, `predictions.jsonl` and provenance.

## 5. Compute schedule

The evaluation is the priority. Until it reports 202/202 (`metrics.json` committed on `claude/kind-albattani-k7qlt9`):

- **Window 0 (now):** code, research, mock tests, retrieval-only metrics with small encoders run under `nice -n 19`.
  No LLM server starts, no model training.
- **Window 1 (after the evaluation finishes):** live LLM work, one model job at a time per container
  (`flock /home/user/hs_queue.lock`, the existing convention). Order of priority: S2 smoke test → S1 RAG ablations on
  the LoRA Matcher → S4 counterfactual audit of the LoRA Matcher → S3 soft-prompt runs → S5 live suite.
- **Window 2:** orchestrator final end-to-end run of the merged integration branch with the real models.
- Training that does not fit a 4-CPU/15 GiB container (S3) goes to a GPU notebook handoff (Kaggle, same pattern as
  `finetune/`), not to the shared containers.

The orchestrator announces window changes in `STATUS.md`.

## 6. Merge gates (into the integration branch)

1. The session branch merges the current integration branch first; no conflicts.
2. `pytest matcher benchmark/tests tests/qa` passes (mock). S5 contract tests pass.
3. Any claim of a live result points to committed run artefacts with provenance. Mock success is reported as mock.
4. RAG stays enabled in the default architecture (`HS_RAG` is never `none` in the production default).
5. Experimental models (S3, unvalidated adapters) never become a production default. They merge only as isolated
   experiment code, behind an explicit opt-in flag.
6. Orchestrator review. `main` changes only through a pull request the project owner approves.
