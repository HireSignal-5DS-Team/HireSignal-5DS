# How the embedding model and the index run (verified 2026-10-15)

Measured with `runtime_check.py` (each phase a fresh process) and by starting the API twice; numbers in `RUNTIME.md`.
Environment: Intel Xeon @ 2.10 GHz, 4 logical cores, 15 GB RAM, **no GPU**, Python 3.13, torch 2.14 (CPU), cloud container.

| Question | Answer (from the code and the measurements) |
|---|---|
| Is e5-small loaded only when indexing/searching, or does it stay in memory? | It is loaded once when the `Retriever` is created (API start) and stays in the API process for its lifetime. Every dense query needs it to embed the query text, so keeping it loaded is the efficient choice: reloading per request would add several seconds per query. |
| Does RAG need a continuously running model server? | No. There is no separate model server or background process: the model runs **inside** the FastAPI process (or inside whatever Python process imports `retrieval.py`). The only process is the API itself, and only while you run it. |
| Can document embeddings be computed once, saved and reused? | Yes, and this is now an explicit step: `python rag/build_index.py --profile baseline` embeds the 1,818 chunks once and stores them in `rag/index/` (Qdrant local mode, on disk, 7.2 MB). The collection name is a fingerprint of model + corpus, so an unchanged corpus is reused and a changed one is re-embedded automatically. `--prune` removes collections no profile uses. |
| How are new queries embedded? | At request time, by the in-process e5-small (`"query: " + text`, normalised), then an exact cosine search with the job-ID / source filter in Qdrant. Query embedding + search: median 45–141 ms, p95 ≤ 164 ms per query on this CPU (varies between runs; within the 300 ms real-time budget). |
| What happens after restarting the application? | Measured: the API starts in 10–11 s, reports `"index_reused": true` on `/health`, embeds **no** documents, and returns identical results (same sections and character spans) as before the restart. Only a first start (or a corpus/model change) pays the full embedding cost: 46–54 s here (190 s once, right after a container reboot). |
| CPU, RAM and latency implications | e5-small process: ~1.3 GB resident RAM (PyTorch runtime + model + index), ~15 s cold process start, ~0.1 s per query on 4 cores. BM25-only mode (what the Matcher currently uses in-process): 116 MB, < 1 ms per query, no model. Experimental profiles cost more: `async-experimental` loads e5-base + the mmarco reranker (p95 ~1.1 s per query in exp03). |

## Recommended deployment with the Qwen3-4B Matcher

- Build the index once (`build_index.py`) after any corpus change; ship or keep `rag/index/` with the application.
- Run **one** RAG API process (`RAG_PROFILE=baseline uvicorn api:app --app-dir rag`), which keeps e5-small loaded,
  and let the Matcher call `POST /knowledge` (its own `KnowledgeRef` format). This keeps the Qwen3-4B process free of a
  second neural model, which is the reason the Matcher chose in-process BM25.
- Alternative without a service: the Matcher keeps calling `Retriever` in BM25 mode in-process (116 MB, no model),
  at the dense-vs-BM25 quality cost measured in exp02 (ESCO MRR 0.786 vs 0.559, French queries fail with BM25).
- Qdrant local mode allows **one process per index folder**: do not run the API and an evaluation on the same folder
  at the same time (the evaluation scripts use their own `index_eval/`).
- No external embedding API and no GPU are assumed anywhere. GPU latency has not been measured.
