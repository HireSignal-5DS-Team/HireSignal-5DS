# HireSignal: final technical report (orchestrator, 2026-10-16)

Release candidate: branch `claude/beautiful-galileo-o36bdv` (never `main` without the owner's approval). Every
number below is measured and names its split. bench-v1 is a **synthetic** benchmark (`benchmark/data/MANIFEST.json`):
train 681, val 202, test 199 requirements. LIVE = real model inference; MOCK = scripted backends (tests only).

## 1. System (downstream of Ayoub's agents)

```
CV + Job JSON (integration/contract.py v1.1; adapters for the CV Reader and the Job Agent)
 -> Matcher: Qwen3-4B-Instruct-2507 Q4_K_M + LoRA HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1 (base fallback)
    with mandatory RAG: rag.gated.v1 over ESCO (BM25), knowledge shown to the model, never used as candidate evidence
 -> Deterministic validator v2 (verbatim quotes and spans, durations, negation, certification, prompt injection)
 -> Bias Auditor rules_v2 (+ opt-in prompted Qwen reviewer)
 -> NLI Judge cross-encoder/nli-deberta-v3-xsmall@a1508764 (base DeBERTa via HS_JUDGE_MODEL)
 -> Report Writer: deterministic JSON/HTML/MD + Qwen3-0.6B Q8_0 (fact-validated, deterministic fallback)
```

The system never makes a hiring decision. Every review reason from every stage is kept, and the report shows
**HUMAN REVIEW REQUIRED** whenever one applies.

## 2. Verified results

| component | result | split / source |
|---|---|---|
| Matcher LoRA vs base | macro-F1 0.908 vs 0.634; JSON-valid 1.000 vs 0.950 | LIVE val 202 (eval session, `46d24e1`) |
| Matcher LoRA + gated RAG, **pre-registered** | macro-F1 **0.678**, false-MET 0.131 (14) | LIVE **test** 199, `benchmark/results/final` |
| same outputs, validator v1 replay / post-hoc fixed v2 | 0.862 / 0.862 (POST-HOC, QA-031 fix made after seeing test) | test 199 |
| LoRA no RAG (pre-registered / v1 / post-hoc) | 0.681 / 0.866 / 0.866, false-MET 0.121 (13) | test 199 |
| test false METs | all on `rag_suggests_absent_skill` items, **all flagged for review** (0 unreviewed) | test |
| base + gated RAG on test | **PARTIAL 173/199, not reported** (stopped by owner decision) | — |
| RAG (gated vs none), LoRA | Δ macro-F1 −0.005 [−0.028, +0.014], p 1.0 (noise floor −0.003); review rate 0.663→0.589, McNemar 15/0, **p 0.0001**; alias accuracy 0.81→0.90 | LIVE val 202 (S1) |
| RAG, base model | Δ −0.014 [−0.038, +0.008], p 0.45; review rate −3.5 pts, p 0.039 | LIVE val 202 (S1) |
| Bias Auditor rules_v2 vs v1 | same recall 19/26; false positives 1/18 vs 9/18 | blind holdout n 44 (S4, orchestrator-verified) |
| Counterfactual flips | base 2/253, LoRA 4/270 protected cells; placebo 0/27, 0/30; base vs LoRA McNemar p 0.69 (low power: rates < ~4 % not excluded) | LIVE val 30 reqs, 9 attributes (S4) |
| Judge xsmall vs base (pretrained) | AUROC 0.75 vs 0.94; false approvals 0 vs 0; review rate +0.28; latency p50 0.04 vs 0.09 s | LIVE LoRA val outputs (S7) |
| Report Writer SLM | 71.6 % of sections accepted (notes 93/123, summaries 13/25), the rest deterministic; 0 unsupported claims in 25 audited reports; 527/530 injected corruptions rejected; p50 30 s per report | LIVE SLM on val-005..029 (S8) |
| End-to-end, all models real | contract valid, spans exact, Judge FAIL/UNCERTAIN shown as HUMAN REVIEW REQUIRED, SLM 3/4 sections + 1 recorded fallback, 73 s for 3 requirements | `integration/e2e_evidence/20261016-real-ex1/` |
| Tests | 404 passed, 12 skipped (MOCK suite); real-model tests: xsmall Judge, SLM, live Matcher suite (S5: 20 passed) | integration branch |

## 3. Honest findings

- **Validator v2 overfitted val.** Its decision rules (QA-025/026) were written after inspecting val errors. On test,
  a scoping bug (QA-031) cost 0.184 macro-F1 until it was fixed post-hoc. With the fix, v2 equals v1 on test: the
  extra rules gave no held-out gain.
- **RAG's measured value is review load and alias handling, not accuracy.**
- **Pretrained NLI judges mostly add review** (FAIL precision ≤ 0.06). They cannot do year arithmetic
  ("2019 - present" vs "3+ years" is scored neutral). Their value is defence in depth: no wrong MET passed.
- **The xsmall Judge is the default by owner decision**; base measured better.
- Validation and test data are synthetic; nothing here measures real recruiting data.

## 4. Not done / blockers

| item | status |
|---|---|
| Deployment (Dali) | handoff ready (`docs/integration/DALI_DEPLOYMENT_HANDOFF.md`); no deployment branch in the repo yet |
| Upstream agents (Ayoub) | Reader + Job Agent exist (Oct 15) with adapters tested on synthetic samples; Profile Agent not delivered; not merged |
| Real-CV document-to-report test | not run (needs Ayoub's agents) |
| Fine-tuned DeBERTa Judge (Oct 15) | lost (never pushed); pretrained Judges used |
| Soft prompt tuning (S3) | code + Kaggle handoff ready; no GPU run (owner decision pending) |
| Port clash | Job Agent NuExtract and the Matcher fallback both default to `:8080`: remap in Compose |
| Bias mitigation proposal (S4) | low-priority review flag for nice-to-have MISSING/contradicted: recommended, not applied |
| PDF export | not done (HTML is print-ready) |
