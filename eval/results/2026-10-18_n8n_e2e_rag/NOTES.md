# T09 Part E: one real end-to-end run with the RAG lookup node (real-GPU)

- Workflow: `n8n/hiresignal_v1.json` (31 nodes; new node `RAG lookup` -> `POST /rag/search` inside the requirement loop).
- Stack: llama-server :8090 (Qwen3-4B Q4_K_M + Matcher LoRA), station API :8010 with the T09 defaults
  (RAG_SEARCH=dense, RAG_EMBED=all-MiniLM-L6-v2, RAG_STORE=qdrant, RAG_ONLY_WHEN_MISSING=1), n8n 2.43.7 :5678.
- Command: `.venv\Scripts\python scripts\n8n_e2e.py --out eval\results\2026-10-18_n8n_e2e_rag --runs P15 --cards`
- Result: execution 28, HTTP 200, valid JSON, outcome `review` (waiting at the recruiter form), score 50,
  identity values found in execution data 0, all /match calls with LoRA scale 1, 4 quotes with verified positions.
- RAG lookup ran 6 times (one per requirement), all success: 20.9 s for the first (model load + Qdrant index build),
  then 4-14 ms. 3 of 6 skipped (all skill terms already in the CV); `HTTP /match` received exactly the refs the RAG
  node returned (`rag_nodes.json`).
