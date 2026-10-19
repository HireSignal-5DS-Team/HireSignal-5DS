# T09 report — RAG upgrade, measured step by step

## In plain words
- **Tesseract works now.** The `.env` path had been mangled; after fixing it, all 6 OCR tests that used to be
  skipped pass (reader suite 40/40).
- **Knowledge base:** ESCO only (1,621 ICT/data skill concepts, CC BY 4.0). It is rebuilt from a pinned public source,
  byte-identical to the V2 file, and now also carries the broader/narrower/related links.
- **Finding the right ESCO concept** got much better. On 46 test queries with known answers, BM25 ranked the right
  concept first 33% of the time on dev; dense MiniLM does so 71% of the time (MRR 0.44 -> 0.76; test 0.38 -> 0.59).
  Hybrid search, rerankers, graph expansion and chunking B were all measured, and none beat plain dense.
  Qdrant and Chroma gave identical results; we keep Qdrant (no extra packages, and it is the Locked choice).
- **The Matcher barely changes.** Better knowledge did not change the Matcher's decisions in a measurable way
  (364 real labelled rows). The selection rule picks V6 (dense; skip RAG when the skill is already written in the CV):
  macro-F1 is 0.665 vs 0.651 for the old setup on dev. That is only 2 rows out of 182, i.e. noise. On test, V6 is
  slightly lower (0.644 vs 0.661). The final screening outcome is identical for all variants: 0 false invites, same
  false rejects, same review rate.
- **n8n shows RAG as its own step:** a "RAG lookup" node runs before each /match, and its refs are visible per
  requirement. One real end-to-end run worked.

## 1. Done
- **Part 0 (Tesseract):**
  - fixed `TESSERACT_CMD` in `.env` (the backslashes and the `\t` had been eaten);
  - Tesseract v5.5.3.20260724, languages `eng`, `osd`;
  - the 6 `@needs_tesseract` tests in `tests/test_reader.py` now run.
- **Part A (corpus, chunking):**
  - `rag/build_esco.py` (rule-6 header, adapted from V2): downloads the Tabiya ESCO v1.1.1 CSVs (commit `eb3e5f44`,
    sha256-pinned, no git) into `data/raw/esco_tabiya/`;
  - it rebuilds `rag/data/esco/esco_ict_skills.jsonl` byte-identically (sha256 `8c6a4b3d…`) and writes
    `rag/data/esco/esco_ict_graph.jsonl` (labels, alt labels, description, broader/narrower/related);
  - chunking A (concept = label + alt labels + description, equal to what the LoRA saw) and B (A + broader/related
    labels) are in `rag/retrieval.py`;
  - `rag/RAG_REPORT.md` sections 1-6.
- **Part B (queries):**
  - `rag/eval/make_queries.py` writes `rag/eval/queries.jsonl`: 46 queries, dev 24 / test 22;
  - sources: 14 V2 reviewed, 9 from T06 Matcher errors, 23 from gold requirements;
  - V2 file copied to `rag/eval/v2_queries_reviewed_en.jsonl`; V2 path from env `V2_REPO`.
- **Part C (retrieval benchmark):**
  - `rag/evaluate.py`: 84-configuration grid (chunking A/B x BM25/dense/hybrid x 3 embeddings x 3 rerankers x graph
    on/off) plus the store comparison numpy / Qdrant local / Chroma persistent;
  - results in `eval/results/2026-10-18_rag_retrieval/`;
  - models copied to `models/` with revision, sha256 and licence in `models/MANIFEST.md`:
    all-MiniLM-L6-v2, multilingual-e5-base, bge-small-en-v1.5, ms-marco-MiniLM-L-6-v2, bge-reranker-base.
- **Part D (Matcher effect):**
  - `scripts/add_skill_terms.py` adds `skill_terms` to `data/processed/jobs/J*_requirements.json`: the Job Agent's
    T06 terms, aligned by source sentence, kept if written in the requirement;
  - `scripts/eval_rag_matcher.py`: V1-V6 through /match (+confidence) -> /judge, plus the T08b gate offline;
    V0 = the T08b rows;
  - results in `eval/results/2026-10-18_rag_matcher/`. **Chosen on dev: V6.**
- **Production setup = V6:**
  - code defaults in `services/api.py` `_rag()` and `rag_search` are dense / all-MiniLM-L6-v2 / qdrant /
    RAG_ONLY_WHEN_MISSING=1, documented in `config/.env.example` (RAG_* block);
  - `/match` without `knowledge_refs` keeps the old built-in BM25 (backwards compatible).
- **Part E (n8n):**
  - `POST /rag/search` (contracts `RagSearchIn/Out`); `/match` accepts `knowledge_refs` + `knowledge`;
  - `n8n/hiresignal_v1.json` is now 31 nodes: Loop -> **RAG lookup** -> HTTP /match (refs from the RAG node,
    cv/requirement from the loop item) -> HTTP /judge;
  - imported, published, re-exported and cleaned; `n8n/README.md` has a new "RAG lookup (T09)" section;
  - one real e2e run, saved in `eval/results/2026-10-18_n8n_e2e_rag/`.
- `prompts/PROMPT_LIBRARY.md`: new row `knowledge-matcher-rag-v6`. The knowledge block's content changed; the prompt
  text is unchanged (= matcher-v1), so there is no new `prompts/matcher/v2.md`.
- Tests:
  - `tests/test_rag.py` (12 tests);
  - `tests/test_rag.py::test_rag_search_endpoint_and_skip_rule` now sets the env explicitly;
  - `tests/test_api.py` fake `match()` accepts the new keyword arguments.
- chromadb (+36 packages) was installed only for the benchmark and then uninstalled. `pip freeze` equals the freeze
  taken before the install; `pip check` is clean.

## 2. Evidence (all real-GPU, RTX 4050, unless stated)
- **Tesseract:** `tesseract --version` -> `tesseract v5.5.3.20260724`; `--list-langs` -> `eng osd`;
  `pytest tests/test_reader.py` -> `40 passed` (0 skipped; before T09 the 6 OCR tests were skipped).
- **Corpus:** `rag/build_esco.py` -> 1,621 concepts; sha256 of the rebuilt V2 file equals V2's.
  All 1,621 have broader, 445 have narrower, 603 have related.
- **Retrieval** (`rag/evaluate.py`; choose on dev = MRR@10, then hit@3, then simpler):

  | config | dev hit@1 / hit@3 / MRR@10 | test MRR@10 |
  |---|---|---|
  | BM25 A (V0) | 0.333 / 0.5 / 0.436 | 0.382 |
  | **dense MiniLM A (chosen)** | **0.708 / 0.792 / 0.762** | **0.591** |
  | dense e5-base | 0.583 / 0.792 / 0.686 | 0.542 |
  | dense bge-small | 0.708 / 0.75 / 0.751 | 0.542 |
  | dense MiniLM B | 0.708 / 0.75 / 0.754 | 0.564 |
  | hybrid MiniLM (RRF) | 0.458 / 0.708 / 0.592 | 0.546 |
  | hybrid + ms-marco rerank | 0.583 / 0.75 / 0.669 | 0.574 |
  | hybrid + rerank + graph | 0.583 / 0.75 / 0.672 | 0.553 |
  | dense + bge-reranker-base | 0.458 / 0.667 / 0.605 | 0.532 |

  Full table: `rag/RAG_REPORT.md` section 4.
- **Stores** (same MiniLM vectors, 46 queries):

  | store | top-10 equal to numpy | warm latency | build | disk |
  |---|---|---|---|---|
  | numpy | 46/46 | 4.19 ms | 0.79 s | 2.5 MB |
  | **Qdrant** | 46/46 | 8.23 ms | 4.22 s | 6.7 MB |
  | Chroma | 46/46 | 5.43 ms | 1.75 s | 4.5 MB, +36 packages |

  Qdrant was chosen (reasons in RAG_REPORT section 5).
- **Part D** (`scripts/eval_rag_matcher.py --report-only`; 182 rows / 26 pairs per split):

  | variant | dev mF1 | dev FR | test mF1 | test FR |
  |---|---|---|---|---|
  | V0 BM25 sentence | 0.651 | 6 | 0.661 | 4 |
  | V1 BM25 + terms | 0.579 | 6 | 0.661 | 4 |
  | V2 dense | 0.659 | 6 | 0.653 | 4 |
  | V3 hybrid | 0.632 | 6 | 0.646 | 4 |
  | V4 + rerank | 0.591 | 6 | 0.663 | 4 |
  | V5 + graph | 0.631 | 6 | 0.664 | 4 |
  | **V6 dense, only when missing** | **0.665** | 6 | 0.644 | 4 |

  - Every variant: false invites 0; review rate dev 0.077 / test 0.154.
  - Output line: `chosen on dev: V6`. Per-class F1, false MET, UNCERTAIN recall and latency are in RAG_REPORT
    section 6.
  - Paired V6 vs V0: dev 10 rows fixed / 8 broken (sign test p = 0.81); test 3 fixed / 6 broken (p = 0.51).
  - Alias-type T06 errors fixed: 0/6 for every variant except V4 (1/3 on dev).
  - V6 skipped the knowledge block on 67/364 rows.
- **Tests:** `pytest -q` -> `398 passed, 1 skipped` (the skip is the Chroma store test, since chromadb is
  uninstalled); `tests/test_rag.py` -> `11 passed, 1 skipped`.
- **Workflow check before the import:** the live n8n export equaled `n8n/hiresignal_v1.json` (30 nodes). After the
  import and re-export, the nodes and connections equal the generated 31-node workflow; only n8n metadata
  (versionId, isArchived, nodeGroups) was added.
- **E2E** (`n8n_e2e.py --runs P15 --cards`):
  - exec 28, HTTP 200, valid JSON; outcome `review` (waiting at the recruiter form), score 50;
  - identity values found in the execution 0; LoRA scale 1 on all /match calls;
  - RAG lookup ran 6x, all successful: 20.9 s the first time (model load + Qdrant build), then 4-14 ms; 3/6 skipped;
  - /match received exactly the RAG node's refs (`rag_nodes.json`), e.g. r1 -> "data warehouse",
    "implement data warehousing techniques", ….

## 3. Not done / problems
- **V6's win is not real evidence of improvement.** The rule forced the choice (+0.014 dev macro-F1 = 2 rows), and
  test is lower. We report it as "no measurable Matcher effect; V6 chosen by the rule, mainly for speed and for
  skipping unneeded knowledge".
- The main mechanism behind the spread: a knowledge change shifts label probabilities, and tau_conf 0.72 flips
  MISSING <-> UNCERTAIN (V2 vs V0 on dev: 17 final decision changes, 6 raw model changes).
- The six alias-type rows stay wrong. Knowledge explains a term, but it cannot make the Matcher quote a buried term.
- Gold for the 32 new retrieval queries was drafted by me from exact ESCO labels, not checked by a human.
- ESCO v1.1.1 has no concept for Spark, Kubernetes, AWS, PyTorch, data lake, microservices or AutoML. Those
  requirements only get a broader concept.
- The task says refs ≤ 280 characters; V0 and V2's prompt code use 300. Kept at 300 so the format the LoRA saw does
  not change (RAG_REPORT section 2).
- The first `/rag/search` after an API start takes ~20 s (model load + index build). It is not preloaded at startup
  (keep it simple). In n8n the HTTP timeout is 120 s, so it is not a problem.
- V0 latency (3.2 s per /match) comes from the T08b session and is not timed together with V1-V6.
- A first `pip uninstall` left 4 `~*` temp folders in site-packages (files locked by the running API). I deleted
  them after the API stopped.
- The e2e execution 28 is left waiting at the recruiter form (same as earlier e2e runs).

## 4. Questions for the Brain
1. V6 was picked by the rule, but the gain is noise and test is lower. Keep V6 (faster, RAG visible, skips needless
   knowledge) or go back to V0 for the Matcher? My view: keep V6. The outcome metrics are identical, and dense
   retrieval is clearly better at finding the concept.
2. Should tau_conf (0.72) be re-checked on dev with V6 rows? The knowledge block shifts the probabilities. I did not
   re-tune it, because that was not in the task.
3. Should a human check the 32 Developer-drafted query golds before the final report uses the retrieval numbers?

## 5. Suggested next step
Leave the RAG part as is. For the Matcher, the alias-type misses need a Matcher-side fix rather than better
retrieval: for example, the prompt/LoRA quoting the CV line that contains the term. Otherwise, move on to the next
stations (Bias Auditor / Report Writer).
