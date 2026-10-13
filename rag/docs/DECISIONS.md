# RAG decision log

Status key: **measured** = backed by a run in `eval/results/`; **reasoned** = argued, not yet measured.

## Decisions

| # | Decision | Alternatives considered | Why | Status |
|---|---|---|---|---|
| D1 | Two collections: real job postings (employer requirements) + ESCO skills (terminology) | ESCO only; job postings only; indexing CVs | A taxonomy cannot say what an employer requires; a posting cannot define a skill. CVs fit in the LLM context and must not be indexed (privacy) | reasoned |
| D2 | ESCO subset = skills of 110 ICT/data occupations + transversal skills (1,621 concepts) | Full ESCO (13,896); ESCO digital skills collection | Fits HireSignal's tech/data scope, ~9x less to embed on CPU. Digital collection not in the mirror. Coverage 29/38 probe terms vs 30/38 for full ESCO | measured (`esco_coverage.md`) |
| D3 | ESCO: one concept = one chunk (label + alt labels + description), never split | Splitting descriptions | Entries are short and atomic; splitting would separate a label from its definition | reasoned |
| D4 | Job postings: compare S1 fixed 200 words / 30 overlap vs S2 structure-aware (headings, title/section prefix, split > 300 words at line breaks) | Sentence chunking; semantic chunking | S1 is the standard baseline; S2 tests the hypothesis that keeping must-have and nice-to-have apart improves Hit@1. Semantic chunking needs an embedding model in the loop and is harder to explain | measured: structure adopted (dense models better, n.s.; BM25 prefers fixed); hypothesis on must/nice split untestable on USAJOBS |
| D5 | Retrieval: BM25 + dense fused with RRF (k=60), top-k=5, filters `job_id` / `source_type` | Dense only; BM25 only; reranker | BM25 is strong on exact tool names, dense on paraphrase and French. Filters give precision cheaply; a cross-encoder reranker adds a second model download and latency for a small corpus | measured on ESCO: dense > hybrid > BM25 at Hit@1; job postings pending |
| D6 | **Revised**: no cosine threshold; `no_match` only when nothing is retrieved; Matcher checks the label | Cosine threshold (tested), threshold on RRF/BM25 scores | Tested threshold did no better than always answering (7/9 on held-out ids); unknown in-domain tools score like real matches | measured (negative result) |
| D7 | Embeddings: compare `multilingual-e5-small` (118M) vs `BAAI/bge-m3` (568M); keep the larger one only if it clearly wins | Single model; English-only models | Must handle French queries; CPU inference in the demo | measured: e5-small kept (ESCO 10 vs 9; jobs: bge-m3 ahead 23 vs 19 scoped but p = 0.22; 3x slower) |
| D8 | Vector store: Qdrant local mode (on disk, no server) | FAISS (no payload filters), Chroma, pgvector (needs a server) | Payload filters + persistence; same client API as a Qdrant server if the team deploys one | plumbing tested with stub embedder |
| D9 | Gold evidence = verbatim quote resolved to a character span; hit = chunk covers >= 50% of the span | Gold chunk ids | Chunk ids differ per strategy; spans make the chunking comparison fair | implemented |

## Failed attempts and corrections (chronological)

1. **Official ESCO portal and Hugging Face unreachable** from the cloud build environment (HTTP 403 by network policy).
   Correction: ESCO from a pinned, hash-checked CC BY 4.0 mirror on GitHub; dense models run where Hugging Face is reachable.
2. **ESCO digital skills collection not available** in the mirror. Correction: subset from occupation links; coverage measured.
3. **Heading detector missed "About the role"** (no trailing colon), found by a unit test. Correction: also accept
   short unpunctuated lines that follow a blank line.
4. **Flaky test**: the stub embedder used Python's randomised `hash()`. Correction: `zlib.crc32`.
5. **BM25 fails French queries** against the English ESCO index: E02 "apprentissage automatique" and E08
   "exploration de données" get no correct result in the top 10. Expected for a lexical method; this is the
   measured motivation for a multilingual dense model.
6. **BM25 cannot abstain**: it returned results for 3 of 4 no-answer ESCO queries (Kubernetes, Power BI, truck
   licence). Motivation for the dense-score threshold (D6).
7. **n8n install blocked**: `npm install n8n` fails because one dependency (`xlsx`) is fetched from `cdn.sheetjs.com`
   (403). Correction: npm `overrides` pinning `xlsx` to the npm-registry 0.18.5. n8n 1.123.84 then installed.
8. **n8n end-to-end test passed** (2026-10-13): the exported workflow ran via `n8n execute` (Manual Trigger) and via
   the active Webhook trigger, calling the RAG API and returning evidence. Record: `n8n/test_run_2026-10-13.json`.
9. **Bug found by the webhook test**: a French query with no shared BM25 term returned `status: found` with an
   empty evidence list. Correction: `no_match` whenever nothing is retrieved; covered by a test.
10. **Hugging Face only partly reachable after the first network change** (2026-10-13): `huggingface.co` API and
    config files return 200, but weight files redirect to `us.aws.cdn.hf.co` / `cas-bridge.xethub.hf.co` (403) and
    `cdn-lfs.huggingface.co` (502). Correction: allow `*.hf.co` and `cdn-lfs.huggingface.co` as well.
11. **Weights downloaded after allowing `*.hf.co`** (2026-10-13). Both models loaded and evaluated on CPU.
12. **Qdrant local-mode folder lock**: a second client on the same index folder is refused. Correction: the
    evaluation closes each client before opening the next.
13. **Cosine-threshold abstention failed** (see EVALUATION.md, comment 4). Decision D6 revised.
14. **Hybrid lowered Hit@1 on ESCO** for both models. Kept only as a candidate for job postings.
15. **Job postings sourced from a CC0 Hugging Face mirror of USAJOBS** (public-domain federal announcements) after
    every job site was unreachable from the build environment. Scraped text has collapsed line breaks.
16. **Structure chunker produced 1,300-word chunks** on single-line USAJOBS sections. Correction: long sections are
    split at sentence boundaries, not only line breaks; coverage of every non-space character re-checked.
17. **Gold quotes not unique**: some passages repeat inside a posting. Correction: every verbatim occurrence counts.
18. **Qdrant folder lock between the running API and the evaluation**. Correction: separate `index_eval/` folder.
19. **Preliminary chunking result (5 postings) reversed on the full 20** for dense models; documented in EVALUATION.md.
