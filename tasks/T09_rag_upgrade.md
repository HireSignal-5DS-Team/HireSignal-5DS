# T09 — RAG upgrade, measured step by step (keep the old setup if nothing beats it)

Read `CLAUDE.md` first. Decisions by the Approver: knowledge base = **ESCO only**; **benchmark Qdrant vs Chroma** and pick by results; **test every option and keep what measures best** (including the current setup).

## Part 0 — Tesseract
Tesseract is now installed (`C:\Program Files\Tesseract-OCR`, path in `.env`). Check `tesseract --version` and `--list-langs` (expect `eng`, maybe `osd`), then run the 6 skipped OCR tests and report. The team is making scans/photos in parallel for the multimodal task (not this task).

## Part A — Knowledge base and two chunking strategies
- Corpus: the ESCO ICT/data subset from V2 (`rag/data/esco/`, ~1,621 concepts, CC BY 4.0; rule-6 header on copied code; record the source and hash). Per concept keep: preferred label, alternative labels, description, broader / narrower / related links.
- **Chunking A:** one concept per chunk (label + alt labels + description).
- **Chunking B:** one concept + the labels of its directly related/broader concepts in the same chunk.
- Write `rag/RAG_REPORT.md` as you go: corpus (source, size, format, why it fits), chunking (what, size, why), every choice below with its numbers. It must be reusable in the final report.

## Part B — Retrieval evaluation set (known answers)
- Start from V2's reviewed queries (`rag/eval/queries_reviewed.jsonl`, English only) and add queries from our real errors and gold requirements (e.g. "PL/SQL" → SQL concept, "Lakehouse" → data lake, "AWS RDS" → cloud, "PyTorch" → deep learning frameworks). Each query has the expected ESCO concept id(s). Split dev/test. Document how each query was made.
- Metrics: hit@1, hit@3, MRR@10, latency.

## Part C — Options benchmarked on retrieval (choose on dev, report on test)
1. **Embedding models** (small, free, local): `all-MiniLM-L6-v2` (already on disk), `intfloat/multilingual-e5-small` or `e5-base` (on disk), `BAAI/bge-small-en-v1.5` (download).
2. **Vector store: Qdrant (local mode) vs Chroma (persistent local)**, same embeddings and chunks: retrieval quality, query latency, build time, disk size, metadata filtering, install effort, how n8n can reach it. Pick one and write why.
3. **Search:** BM25 only (current) / dense only / **hybrid** (BM25 + dense, RRF).
4. **Reranker:** none vs one small cross-encoder (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2` or `BAAI/bge-reranker-base`) on the top 20.
5. **ESCO graph expansion:** add broader/related concepts of the top hits (on/off).
6. Chunking A vs B. Top-k: keep k = 3 refs ≤ 280 characters for the Matcher (the LoRA was trained with that format).

## Part D — Effect on the Matcher (the real test), 52 real pairs, real-GPU
- **Fix first:** gold requirements have no `skill_terms`, so today the query is the whole requirement sentence. Derive skill terms per requirement (reuse the Job Agent's term logic or a simple documented extraction) and save them with the job cards.
- Run the Matcher (+ confidence) on all 364 gold rows for each variant, then Judge + the T08b gate offline:
  V0 current (BM25, whole sentence: reuse T08b rows) · V1 BM25 + skill terms · V2 best dense · V3 hybrid · V4 hybrid + reranker · V5 + graph · V6 best + **retrieve only when the requirement's terms are not already in the CV** (otherwise no knowledge block).
- Metrics per variant: Matcher macro-F1, per-class F1, false MET, UNCERTAIN recall, alias-type errors fixed (from the T06 error list), latency; then gate: false invites (must stay 0), false rejects, review rate.
- **Pick on dev only** (Matcher macro-F1, then false rejects, then simpler); report on test. **If no variant beats V0 on dev, keep V0** and say so.

## Part E — Make RAG visible in n8n
Add `POST /rag/search` (returns the knowledge refs) and let `/match` accept refs from the request. In n8n, inside the requirement loop: HTTP `RAG lookup` → HTTP `/match` → `/judge`. Re-export and clean the workflow; one real end-to-end run.

## Rules
Tests for new code. Log the RAG choices in `PROMPT_LIBRARY.md` only where a prompt/knowledge block changes. Label results real-GPU/CPU. Never tune on test. Report in `tasks/T09_report.md` with a plain-language summary at the top. Stop llama-server and the API at the end.
