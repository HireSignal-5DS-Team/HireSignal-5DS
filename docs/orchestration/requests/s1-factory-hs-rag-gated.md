# Request S1 → S2 (owner of `matcher/factory.py`): select the gated knowledge provider

Status: proposed, 2026-10-16. Evidence: `docs/rag/RAG_OPTIMIZATION.md`.

## Ask

1. Add two values to `HS_RAG` in `matcher/factory.py` (no other change):
   ```python
   from .knowledge import GatedKnowledge
   ...
   "gated": GatedKnowledge,                       # rag.gated.v1+bm25, no embedding model
   "gated-qdrant": lambda: _gated_qdrant(),       # same gate/cut-off, Qdrant e5-small candidates (needs sentence-transformers)
   ```
   (`_gated_qdrant` = `GatedKnowledge(retriever=Retriever(build_chunks("structure"), model="e5-small", store_path=<rag>/index),
   mode="dense", dense_tau=<exp03 thresholds, "structure@300 | e5-small", esco>)`, the same construction as
   `rag_opt/run_arm.py:provider_factory`.)
2. Change the production default from `bm25` to `gated` **only after** the window-1 run of
   `rag_opt/e2e_compare.sh` shows, on the LoRA Matcher, that `gated` is not worse than `none` and not worse than
   `bm25` (paired CI and McNemar in `rag_opt/results/e2e/e2e_report.md`). RAG stays enabled either way (merge gate 4).

## Why

- The interface is unchanged (`lookup(req, k=3, job_id=None) -> list[KnowledgeRef]`, empty list = abstention,
  CV text never sent). `GatedKnowledge.uses_job = True`, so `Matcher.match_requirement` already passes `job_id`.
- On the 202 val requirements the legacy BM25 provider injects 1.28 off-target ESCO references per requirement
  (certifications, languages and degrees get unrelated concepts); the gated provider injects 0 off-target and 51
  on-target references, with 57 instead of 379 knowledge characters per requirement (`rag_opt/results/retrieval_metrics.md`).
- A replay estimate from recorded answers (not a model run) puts the base Matcher with gating at no-RAG level
  (Δ macro-F1 +0.004, 95% CI [−0.014, +0.023]) instead of −0.041 for legacy BM25; the live run must confirm it.
