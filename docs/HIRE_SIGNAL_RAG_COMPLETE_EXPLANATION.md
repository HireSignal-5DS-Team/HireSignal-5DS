# HireSignal V3 — The RAG Component, Explained Completely

*Written 2026-10-19 (task T17). Scope: the V3 repository only (`YD/`). Documentation only: no code, configuration,
dataset or experiment was changed, and no benchmark was re-run.*

**Sources of truth used for every number in this file:**

| Source | What it gives |
|---|---|
| `rag/RAG_REPORT.md` | Corpus, chunking, retrieval benchmark, vector store benchmark, Matcher effect |
| `tasks/T09_report.md`, `tasks/T09b_report.md` | How the experiments were run, test results, the Approver's decisions |
| `rag/retrieval.py`, `rag/bm25_esco.py` | The retriever code |
| `services/api.py` (`/rag/search`, `_rag()`, `_rag_refs()`), `services/contracts.py` | The API and its contract |
| `services/matcher/matcher.py`, `services/matcher/prompt.py`, `prompts/matcher/v1.md` | How the Matcher uses the knowledge |
| `services/judge/judge.py`, `services/bias/auditor.py` (via `services/api.py`) | Who else touches RAG |
| `n8n/hiresignal_v1.json` | The "RAG lookup" node in the workflow |
| `config/.env.example` | The production settings (`RAG_*`) |
| `tests/test_rag.py` | The RAG tests |
| `eval/results/2026-10-18_rag_retrieval*/`, `2026-10-18_rag_matcher/`, `2026-10-18_n8n_e2e_rag/` | Raw results, real captured outputs |
| `docs/FINAL_EVAL.md` | Latency in the full pipeline, final known limits |

**Labels used in this document**

| Label | Meaning |
|---|---|
| ✅ **Deployed** | Runs in production today (the n8n pipeline uses it) |
| 🧪 **Tested, not selected** | Measured in an experiment, then rejected |
| 🔁 **Kept for compatibility** | In the code, but not used by the production n8n flow |
| 💡 **Illustrative** | An example written to explain; not a captured output |
| 📸 **Captured** | Copied from a real saved result file |

---

## Contents

1. RAG explained simply
2. Our complete RAG architecture (and why each part)
3. Exactly when and where RAG is used in the pipeline
4. All RAG experiments and benchmarks
5. Testing and validation
6. How it runs (model execution and deployment)
7. A complete end-to-end example
8. Current status: done, not integrated, limits and future work
9. Presentation scripts, professor questions and glossary

---

## 1. RAG explained simply

### 1.1 What is RAG?

**RAG = Retrieval-Augmented Generation.** Before a language model answers, we **search** a knowledge base and
**add** what we found to the model's prompt. The model then answers with that extra information in front of it.

Think of an exam where you may bring a small dictionary. You still have to answer yourself, but you can look up a word
you don't know.

### 1.2 Why does HireSignal need it?

Our **Matcher** (Qwen3-4B + the team's LoRA) checks **one job requirement against one anonymised CV** and answers
MET / MISSING / UNCERTAIN with exact quotes from the CV.

The problem: a job and a CV often name **the same skill with different words**.

| The job says | The CV says | Same skill? |
|---|---|---|
| "PL/SQL" | "SQL, Oracle databases" | Related (a query language) |
| "TensorFlow" | "deep learning models" | TensorFlow is a deep learning tool |
| "asynchronous programming" | "concurrent programming" | Very close |

A small 4B model doesn't always know these links. RAG gives it a short **definition and the other names** of the
skill, taken from **ESCO**, the European Union's official skills vocabulary.

### 1.3 The one rule that matters most

> **RAG gives knowledge, never evidence.**

- The knowledge explains *what a skill means*. It says nothing about the candidate.
- The search query is built from the **requirement only, never from the CV text** (`rag/retrieval.py`, `query_for`).
- The Matcher must still quote the **CV**. A code validator checks that every quote really exists in the CV text, so an
  ESCO sentence can never pass as evidence.
- The prompt says it in plain words: *"Knowledge entries explain what a skill means and its other names. They are NOT
  evidence about the candidate."* (`prompts/matcher/v1.md`).

### 1.4 A simple example 💡 Illustrative

- **Requirement:** "Experience with TensorFlow" (skill term: `TensorFlow`)
- **CV line:** "Built image classifiers with deep learning (CNNs) in Keras."
- **Without RAG:** the Matcher sees "TensorFlow" in the job and no "TensorFlow" in the CV, and may answer MISSING.
- **With RAG:** the Matcher also sees the ESCO entry
  *"deep learning. The principles, methods and algorithms of deep learning, a subfield of artificial intelligence and
  machine learning…"*. It now understands the requirement is about deep learning, and can decide with that in mind.
  It must still quote the CV line; it cannot quote ESCO.

(📸 For the real query "TensorFlow", our retriever's first result is indeed "deep learning"; see section 4.4.)

### 1.5 Four words people mix up

| Term | Simple meaning | In HireSignal |
|---|---|---|
| **Embedding model** | Turns a text into a list of numbers (a *vector*) so that texts with similar meaning get similar numbers | `all-MiniLM-L6-v2` |
| **Vector database** | Stores those vectors and quickly finds the closest ones to a query vector | **Qdrant** (local mode) |
| **Retriever** | The search step: query in, best matching knowledge entries out | `EscoRetriever` in `rag/retrieval.py` |
| **LLM** | The model that reads the prompt (CV + requirement + knowledge) and writes the answer | Qwen3-4B + LoRA (the Matcher) |

RAG is the **whole pattern**: retriever (embedding model + vector database) → add the results to the prompt → the LLM
answers.

---

## 2. Our complete RAG architecture

### 2.1 The big picture

```
                    ┌────────────────────────────────────────────┐
  BUILD (at start)  │ ESCO v1.1.1 (pinned files, CC BY 4.0)      │
                    │        ↓  rag/build_esco.py (one time)     │
                    │ esco_ict_graph.jsonl : 1,621 concepts      │
                    │        ↓  chunking A (1 concept = 1 chunk) │
                    │ "<label>. Also known as: … . <description>"│
                    │        ↓  all-MiniLM-L6-v2 (embeddings)    │
                    │ 1,621 vectors → Qdrant collection "esco"   │
                    └────────────────────────────────────────────┘

  QUERY (per requirement, in n8n node "RAG lookup" → POST /rag/search)
        requirement {text, skill_terms} + anonymised CV text
                         ↓
        Skip rule: are ALL skill terms already written in the CV?
             ├── yes → no knowledge (skipped = true, refs = [])
             └── no  → query = skill terms (or requirement text)
                         ↓  embed the query (MiniLM)
                         ↓  Qdrant: cosine search
                         ↓  top k = 3 concepts
                         ↓  each ref = chunk-A text cut at 300 characters
        knowledge_refs → HTTP /match (Matcher prompt, "Knowledge" block)
```

### 2.2 Component by component

#### (a) Data source: ESCO ✅ Deployed

| Item | Value |
|---|---|
| What | **ESCO v1.1.1** (European Skills, Competences, Qualifications and Occupations), by the European Commission |
| Licence | **CC BY 4.0**, free to reuse with attribution |
| How we get it | `rag/build_esco.py` downloads the Tabiya CSV mirror (commit `eb3e5f44`), each file **pinned by sha256** |
| Selection | Skills linked to ICT and data jobs (ISCO groups 25, 35, 212, 1330) plus all transversal skills |
| Size | **1,621 concepts**: 1,106 skills/competences, 514 knowledge, 1 untyped |
| Fields kept | URI, label, alternative labels, description, type, reuse level, broader / narrower / related links |
| Links | All 1,621 have a broader link; 445 have narrower; 603 have related |
| Proof it's the same data as V2 | The rebuilt `esco_ict_skills.jsonl` is **byte-identical** to the team V2 file (same sha256 `8c6a4b3d…`) |

**Why ESCO?** It's the EU's official skills vocabulary, with **synonyms and spellings** ("Python3", "Py3K"…) and a
**hierarchy**. That's exactly what the Matcher lacks when the job and the CV use different names. It's free and
licensed for reuse, which fits our zero budget.

**Job postings are not in the knowledge base.** The corpus is **ESCO only** (T09 report: "Knowledge base: ESCO only").
The one-line `rag/README.md` still mentions "job postings"; that line is outdated.

#### (b) Data preparation

- `build_esco.py` reads the CSVs, applies the selection rule and writes two files:
  - `rag/data/esco/esco_ict_skills.jsonl` (the V2 format);
  - `rag/data/esco/esco_ict_graph.jsonl` (sha256 `4602627e…`), which adds the graph links.
- No manual editing. The build is repeatable from pinned public files.

#### (c) Chunking ✅ A deployed · 🧪 B tested

**Chunking** means cutting the knowledge into pieces before indexing. Each piece gets one vector.

Our rule: **one ESCO concept = one chunk. No concept is ever split.** An ESCO entry is short and self-contained, and
splitting it would separate a label from its definition. Because nothing is cut, **overlap is not needed**.

| Strategy | Content of a chunk | Size (characters median / p90 / max) | MiniLM tokens (median / p90 / max) | Status |
|---|---|---|---|---|
| **A** | `<label>. Also known as: <alt labels>. <description>` | 255 / 444 / 1,297 | 48 / 80 / 406 (2 chunks over 256) | ✅ Deployed |
| **B** | A + `Broader: <labels>. Related: <labels (max 10)>.` | 342 / 556 / 1,426 | 63 / 99 / 429 (4 chunks over 256) | 🧪 Rejected |

- MiniLM reads at most 256 tokens. Only 2 of 1,621 A-chunks are longer, so almost nothing is lost.
- **What the Matcher sees is always the A text, cut at 300 characters, 3 refs.** That's the format the LoRA was
  trained on (V2 `format_knowledge`). Chunking only changes *what is indexed*, never what the Matcher reads.
- **Why B lost:** neighbour labels added noise. Dev MRR 0.790 (B) vs 0.798 (A), test 0.680 vs 0.712.

#### (d) Embedding model: all-MiniLM-L6-v2 ✅ Deployed

| Model | Layers | Size on disk | Query prefix needed | Status |
|---|---|---|---|---|
| **all-MiniLM-L6-v2** | 6 | 91 MB | No | ✅ Deployed |
| bge-small-en-v1.5 | 12 | 134 MB | Yes ("Represent this sentence for searching relevant passages: ") | 🧪 Tied on dev, not selected |
| multilingual-e5-base | — | — | Yes ("query: " / "passage: ") | 🧪 Rejected |

- All models are copied into the git-ignored `models/` folder, with revision, sha256 and licence in `models/MANIFEST.md`.
- **Why MiniLM?** See section 4.3. In short: it tied with bge-small on dev (same hit@3; MRR gap of 3 queries out of 24),
  and the tie-break was **the simpler, faster model**: 6 layers vs 12, 91 MB vs 134 MB, no prefix, about 38 vs 57 ms
  per query in the grid. It's also the model the Matcher effect (V6) was measured with.

#### (e) Vector database: Qdrant (local mode) ✅ Deployed

- Collection `esco`, **cosine distance**, one point per concept. The payload holds the URI, label and skill type.
- Folder: `rag/index/qdrant_A_all-MiniLM-L6-v2/`.
- Local mode: Qdrant runs **inside our Python process**. There's no separate server, port or Docker.
- **Why Qdrant** (section 4.5): identical results to the alternatives (top-10 equal on 46/46 queries), no extra
  dependency (`qdrant-client` was already installed; Chroma would add 36 packages), and it's the store named in our
  locked architecture.

#### (f) Retrieval: dense, k = 3 ✅ Deployed · 🧪 BM25 / hybrid tested

| Method | Simple meaning | Status |
|---|---|---|
| **Dense** | Compare meaning vectors (MiniLM + cosine) | ✅ Deployed (`RAG_SEARCH=dense`) |
| BM25 | Classic keyword search: counts shared words | 🧪 Benchmark baseline. 🔁 Also the fallback inside `/match` when no refs are sent (see 3.4) |
| Hybrid (RRF) | Run BM25 and dense, merge the two rankings by Reciprocal Rank Fusion (constant 60) | 🧪 Rejected |

- **Query** = the requirement's `skill_terms` joined with spaces, or the requirement text when there are no terms
  (`query_for`). Never CV text.
- **k = 3** refs per requirement (contract default `k=3`, Matcher env `MATCHER_K=3`), the format the LoRA saw.

#### (g) Reranking 🧪 Tested, not selected

A **reranker** (cross-encoder) re-reads the query and each candidate together and re-orders the top 20.
We tested `ms-marco-MiniLM-L-6-v2` and `bge-reranker-base`. **Both made results worse** (section 4.3): they were
trained on web-search passages, not on short skill labels. Production: `RAG_RERANKER=` (empty).

#### (h) ESCO graph expansion 🧪 Tested, not selected

After each of the top 3 hits, insert its broader and related concepts. It **didn't help**: it only reorders below the
top hit. Production: `RAG_GRAPH=0`.

#### (i) The skip rule ("RAG only when needed", variant V6) ✅ Deployed

```
terms_in_cv(requirement, cv_text) is True
   ⇔ the requirement HAS skill terms, AND
     EVERY term appears in the CV (case-insensitive, whole word)
→ then: no retrieval, knowledge block = "(none retrieved)"
```

- "Whole word" is strict: `C` doesn't match inside `C++` (tested).
- **No skill terms** → always retrieve.
- Setting: `RAG_ONLY_WHEN_MISSING=1`.
- **Why:** if the CV already contains the exact word, a definition adds nothing and can only shift the Matcher's
  probabilities. In the T09 measurement, V6 skipped the knowledge block on **67 of 364 rows (18%)**.

#### (j) Source citation

Every ref carries its **ESCO URI** (`source_id`, `url`), title, aliases and relevance score. In the prompt each line
starts with the last 12 characters of the ESCO id, e.g. `[3a2d5b45-56e] machine learning. Also known as: ML. …`.
The Matcher's result records which refs it was given (`knowledge_refs`: id + title), so every decision can be traced
to the knowledge it saw.

#### (k) The API ✅ Deployed

`POST http://127.0.0.1:8010/rag/search` (station API, FastAPI)

| | Field | Meaning |
|---|---|---|
| **In** (`RagSearchIn`) | `requirement` | `{req_id, text, kind, category, skill_terms, min_years}` |
| | `cv_text` | The **anonymised** CV text, used only for the skip rule, never as a query |
| | `k` | Number of refs, 1–10, default 3 |
| **Out** (`RagSearchOut`) | `knowledge_refs` | List of `{source_id, title, text (≤ 300 chars), url, aliases, relevance_score}` |
| | `retriever` | e.g. `esco/A/dense/all-MiniLM-L6-v2/qdrant +only-when-missing` |
| | `skipped` | `true` when the skip rule fired |
| | `elapsed_s` | Time of this call |

Production settings (`config/.env.example`): `RAG_CHUNKING=A`, `RAG_SEARCH=dense`, `RAG_EMBED=all-MiniLM-L6-v2`,
`RAG_RERANKER=` (none), `RAG_GRAPH=0`, `RAG_STORE=qdrant`, `RAG_ONLY_WHEN_MISSING=1`, `RAG_DEVICE` = cuda when available.

---

## 3. Exactly when and where RAG is used

### 3.1 The full chain, with RAG in place

```
1  Webhook (CV file + job text, token checked)
          ↓
2  Reader (text PDF → text layer; photo/scan → two readers + cross-check)
          ↓
3  Profile Agent (anonymise, injection guard, parse)  ‖  Job Agent (requirements + skill_terms)
          ↓                                            ↓
4  Split requirements → Loop, ONE requirement at a time:
        4a  RAG lookup   → POST /rag/search   (requirement + anonymised CV)
        4b  HTTP /match  → Matcher (CV + requirement + knowledge_refs from 4a)
        4c  HTTP /judge  → Judge (DeBERTa NLI; CV quotes vs requirement)
          ↓
5  Bias Auditor (swap test)  →  6 Outcome gate  →  7 Report Writer  →  letter / recruiter form
```

### 3.2 Step by step

1. **A candidate's CV arrives** through the n8n webhook.
2. **The Reader** turns the file into text.
3. **The Profile Agent** anonymises the CV (names, contact lines and other identity signals removed or masked) and
   removes detected injection sentences. **This anonymised text is what RAG and the Matcher receive.**
4. **The Job Agent** turns the job post into a list of requirements. Each has a `text`, a `kind` (must/nice), a
   `category`, optional `min_years` and **`skill_terms`** (e.g. `["SQL"]`). A recruiter-confirmed requirement card
   can replace this step.
5. **For each requirement**, n8n's **"RAG lookup"** node calls `/rag/search` with
   `{requirement, cv_text}` (`n8n/hiresignal_v1.json`):
   - if every skill term is already in the CV → `skipped: true`, `knowledge_refs: []`;
   - otherwise → query = the skill terms → MiniLM vector → Qdrant top 3 → refs.
6. **"HTTP /match"** sends the Matcher the CV, the requirement and **exactly the refs from step 5**. The Matcher
   prompt has a block *"Knowledge (terminology only, not candidate evidence):"* with one line per ref, or
   `(none retrieved)`.
7. **The Matcher decides** (temperature 0, JSON schema forced by the server):
   `{decision, basis, evidence [CV quotes], explanation}`. Then code guards run:
   - every quote must exist verbatim in the CV;
   - a MET without verified evidence becomes UNCERTAIN;
   - if the model's confidence is below **0.72** → UNCERTAIN.
8. **Who else touches RAG?**

| Agent | Uses RAG? | Detail (verified in code) |
|---|---|---|
| **Matcher** | ✅ Yes, directly | Reads the refs in its prompt |
| **Judge** | ❌ No | `services/judge/judge.py`: *"Premises are CV text only: the Judge never receives RAG knowledge."* |
| **Bias Auditor** | ✅ Indirectly | When the swapped CV's Matcher input differs from the original, it re-runs the Matcher with `_rag_refs()`: the same V6 rule and the same retriever, applied to the swapped text. In the final test all 22 swaps had identical input, so no re-run was needed |
| **Outcome gate** | ❌ No | Uses decisions, confidences and flags only |
| **Report Writer** | ❌ No | Uses decisions and CV quotes only |
| **Profile / Job agents** | ❌ No | The Job Agent produces the `skill_terms` that become the query |

### 3.3 The "deployed vs legacy" question (BM25 vs the dense RAG API)

| Path | What happens | Status |
|---|---|---|
| **n8n → `/rag/search` → `/match` with `knowledge_refs`** | Dense MiniLM + Qdrant + skip rule | ✅ **The production path.** Verified in `n8n/hiresignal_v1.json` (nodes "RAG lookup" → "HTTP /match") |
| `/match` called **without** `knowledge_refs` | The Matcher falls back to the old built-in **BM25** retriever (`rag/bm25_esco.py`) | 🔁 Kept for backward compatibility (old scripts and tests). Not used by the n8n flow |
| `/match` with `knowledge_refs: []` | No knowledge block: `(none retrieved)` | ✅ What happens when the skip rule fires |

The integration was checked end to end: in a real n8n run (execution 28, pair P15), the RAG lookup ran 6 times, and
**`/match` received exactly the RAG node's refs** (`eval/results/2026-10-18_n8n_e2e_rag/rag_nodes.json`).

---

## 4. All RAG experiments and benchmarks

### 4.1 The method (how we avoided fooling ourselves)

- **Dev / test split.** We **choose on dev**, then **report test once**. Test is never used to choose.
- **Real hardware.** Measured on a real GPU (RTX 4050 Laptop) unless stated.
- **Two levels of evaluation:**
  1. **Retrieval quality:** does the search find the right ESCO concept? (46 queries)
  2. **Effect on the Matcher:** does better retrieval give better hiring decisions? (52 real CV/job pairs, 364 labelled rows)

### 4.2 The retrieval evaluation set

- **46 queries** with known correct ESCO answers (any listed concept counts), fixed **before** measuring.
  Split **dev 24 / test 22**.
- Where they come from:
  - 14 queries reviewed in the team's V2 work, e.g. "writing SQL queries against relational databases" → SQL;
  - 9 from **our own Matcher's errors** (T06), e.g. "PL/SQL", "Databricks Lakehouse Fundamentals";
  - 23 from our **gold job requirements**, e.g. "asynchronous programming" → use concurrent programming.
- **Human check:** the gold answers of the 32 new queries were drafted from exact ESCO labels, then **checked by the
  Approver** (2026-10-18, `rag/eval/queries_review.xlsx`): 22 OK, 10 CHANGE (more accepted concepts), 0 DROP.

**Metrics in easy words**

| Metric | Easy meaning | Example |
|---|---|---|
| **hit@1** | % of queries where the **first** result is a correct concept | 0.75 = right on top for 3 queries out of 4 |
| **hit@3** | % of queries where a correct concept is **somewhere in the top 3**. It's our *Recall@3*: it matters because the Matcher sees 3 refs | 0.833 = 20 of 24 dev queries |
| **MRR@10** | Mean Reciprocal Rank: for each query take 1 / (position of the first correct result), 0 if not in the top 10, then average | Correct at position 1 → 1.0; at position 2 → 0.5; at position 3 → 0.33 |
| **macro-F1** | For the Matcher: the F1 score of each class (MET, MISSING, UNCERTAIN) averaged equally, so the rare class counts as much as the common ones | 0.665 |
| **Latency** | Time for one query. *Warm* = model already loaded; *cold* = the first query, which also loads the model and builds the index | 8.23 ms warm |
| **Sign test (p)** | When comparing two systems row by row: how likely the difference is just luck. Above ~0.05 = can't tell them apart | p = 0.81 → no real difference |

Not measured, so not reported: Precision@K, p95 latency, confidence intervals. We used the sign test for the
paired comparison instead.

### 4.3 Experiment 1: the 84-configuration retrieval grid (T09) and its re-score on checked golds (T09b)

**What was tested:** `rag/evaluate.py` ran every combination:
chunking (A, B) × search (BM25 alone, dense with 3 embedding models, hybrid with the same 3 models) × reranker
(none, ms-marco-MiniLM-L-6-v2, bge-reranker-base) × graph expansion (on, off) = **2 × 7 × 3 × 2 = 84 configurations**.

**After the Approver checked the golds**, T09b re-scored the 13 main configurations (`rag/rescore.py`). These are
the numbers we use:

| Configuration (chunking A unless noted) | dev hit@1 | dev hit@3 | **dev MRR@10** | test hit@1 | test hit@3 | test MRR@10 | Status |
|---|---|---|---|---|---|---|---|
| BM25 (old V0 baseline) | 0.417 | 0.583 | 0.520 | 0.318 | 0.455 | 0.425 | 🧪 Baseline |
| BM25, chunking B | 0.417 | 0.583 | 0.516 | 0.318 | 0.455 | 0.412 | 🧪 |
| **dense all-MiniLM-L6-v2** | 0.750 | 0.833 | **0.798** | 0.591 | 0.864 | 0.712 | ✅ **Deployed** |
| dense multilingual-e5-base | 0.625 | 0.833 | 0.723 | 0.318 | 0.773 | 0.556 | 🧪 |
| dense bge-small-en-v1.5 | 0.792 | 0.833 | **0.824** | 0.500 | 0.682 | 0.609 | 🧪 Tie on dev |
| dense MiniLM, chunking B | 0.750 | 0.792 | 0.790 | 0.500 | 0.864 | 0.680 | 🧪 |
| hybrid MiniLM (RRF) | 0.583 | 0.792 | 0.686 | 0.545 | 0.818 | 0.684 | 🧪 |
| hybrid bge-small (RRF) | 0.625 | 0.792 | 0.712 | 0.591 | 0.727 | 0.662 | 🧪 |
| hybrid MiniLM + ms-marco rerank | 0.667 | 0.792 | 0.724 | 0.545 | 0.682 | 0.611 | 🧪 |
| hybrid MiniLM + rerank + graph | 0.667 | 0.792 | 0.732 | 0.545 | 0.636 | 0.583 | 🧪 |
| dense MiniLM + ms-marco rerank | 0.708 | 0.833 | 0.765 | 0.591 | 0.636 | 0.632 | 🧪 |
| dense MiniLM + bge-reranker-base | 0.458 | 0.708 | 0.609 | 0.409 | 0.727 | 0.587 | 🧪 |
| dense MiniLM + graph expansion | 0.750 | 0.792 | 0.798 | 0.591 | 0.773 | 0.692 | 🧪 |

**What won and what lost, and why** (all readings on dev):

| Question | Answer | Why |
|---|---|---|
| Dense or BM25? | **Dense**, clearly: MRR 0.798 vs 0.520 | Queries like "PL/SQL", "Lakehouse", "asynchronous programming" share no word with the ESCO label. Keyword search can't bridge that; meaning vectors can |
| MiniLM or bge-small? | **Tie → MiniLM** | bge-small is ahead on dev MRR (0.824 vs 0.798), but the gap comes from only **3 of 24 queries** (AWS RDS: rank 8 → 3; Docker: 3 → 1; asynchronous programming: 2 → 4 the other way), and **hit@3 is equal** (0.833). The Approver called it a tie (2026-10-18) and broke it with the **simpler, faster** model. On test MiniLM is ahead (0.712 vs 0.609), but that's only reported, not used as the reason |
| e5-base? | Lost (0.723) | Weaker on dev, bigger, needs prefixes |
| Hybrid? | Lost (0.686) | BM25's wrong hits pull the merged ranking down on these short, synonym-heavy queries |
| Rerankers? | Lost (0.765 and 0.609) | Trained on web passage relevance (MS MARCO), not on short skill labels |
| Chunking B? | Lost (0.790) | Neighbour labels add noise to the index |
| Graph expansion? | No gain (0.798) | It only reorders results below the top hit |

**History, for honesty:** on the first (drafted) golds, T09 chose MiniLM with dev MRR 0.762 (BM25 0.436). After the
human check, every score went up, and bge-small moved slightly ahead on dev, hence the tie decision above. Only the 13
table configurations were re-scored, not all 84 (T09b, "Not done").

### 4.4 Real retrieval examples 📸 Captured

From `eval/results/2026-10-18_rag_retrieval/per_query.json` (top 3, chunking A). A ✓ marks a correct concept
(current golds).

| Query | BM25 top 3 | Dense MiniLM top 3 |
|---|---|---|
| "PL/SQL" | SQL Server, **SQL ✓**, database management systems | **SQL ✓**, **query languages ✓**, **Oracle Relational Database ✓** |
| "TensorFlow" | computer vision (only 1 hit) | **deep learning ✓**, computer vision, perform dimensionality reduction |
| "asynchronous programming" | AJAX, develop programming schedule, ICT system programming | AJAX, **use concurrent programming ✓**, real-time computing |
| "Databricks Lakehouse Fundamentals" | biology, project management, Outsourcing model | **Hadoop ✓**, **data warehouse ✓**, Pentaho Data Integration |
| "PyTorch" | (no result) | Python (computer programming), Vyper, **deep learning ✓** |
| "Data Lakes" | process data, gather data, manage quantitative data | manage findable accessible interoperable and reusable data, deliver visual presentation of data, manage data (no ✓) |

The last two rows show the **ESCO gap**: ESCO v1.1.1 has no concept for PyTorch or data lakes, so the best possible
result is a broader concept.

### 4.5 Experiment 2: the vector store (Qdrant vs Chroma vs plain numpy)

Same MiniLM vectors, same chunks, 46 queries:

| | numpy (brute force, reference) | **Qdrant local** ✅ | Chroma persistent 🧪 |
|---|---|---|---|
| Top-10 equal to numpy | 46/46 | **46/46** | 46/46 |
| Warm query latency | 4.19 ms | 8.23 ms | 5.43 ms |
| Build (1,621 vectors, embeddings cached) | 0.79 s | 4.22 s | 1.75 s |
| Disk | 2.5 MB (in memory) | 6.7 MB | 4.5 MB |
| Filtering | in code | payload filters | `where` filters |
| Install | nothing | `qdrant-client` (already installed) | `chromadb` + **36 more packages** |
| n8n | via our API | our API, or n8n's built-in Qdrant node | our API, or n8n's Chroma node |

**Choice: Qdrant.** Quality is identical. The 3–4 ms difference doesn't matter next to a 2–3 s Matcher call. It adds
no dependency, and it's the locked architecture's store. Chroma was installed only for this benchmark and then
uninstalled (`pip freeze` identical before and after).

**Why not just numpy?** It has no index, no filters and no persistence to justify as a "vector store". It's the
reference for checking correctness.

### 4.6 Experiment 3: the effect on the Matcher (the real test)

**Question:** better retrieval finds the right concept far more often. Does it also give **better hiring decisions**?

**Setup:** 52 real CV/job pairs, 364 gold requirement rows (dev 182 / test 182, 26 pairs each), real GPU. Each
variant runs Matcher (LoRA + confidence rule 0.72) → Judge → the gate (offline), through the station API
(`scripts/eval_rag_matcher.py`).

| Variant | dev macro-F1 | dev false MET | dev UNCERTAIN recall | dev gate: false invites / false rejects / review | test macro-F1 | test false MET | RAG ms / match s |
|---|---|---|---|---|---|---|---|
| V0 BM25, whole sentence (old baseline) | 0.651 | 10 | 0.370 | 0 / 6 / 7.7% | 0.661 | 13 | – / 3.2* |
| V1 BM25 + skill terms | 0.579 | 10 | 0.185 | 0 / 6 / 7.7% | 0.661 | 13 | 0.6 / 2.5 |
| V2 dense MiniLM | 0.659 | 11 | 0.370 | 0 / 6 / 7.7% | 0.653 | 13 | 10 / 1.9 |
| V3 hybrid (RRF) | 0.632 | 9 | 0.296 | 0 / 6 / 7.7% | 0.646 | 13 | 24 / 2.9 |
| V4 hybrid + ms-marco rerank | 0.591 | 8 | 0.185 | 0 / 6 / 7.7% | 0.663 | 12 | 65 / 2.7 |
| V5 V4 + graph expansion | 0.631 | 9 | 0.333 | 0 / 6 / 7.7% | 0.664 | 14 | 55 / 2.5 |
| **V6 = V2, only when the terms are not in the CV** ✅ | **0.665** | 9 | **0.407** | 0 / 6 / 7.7% | 0.644 | 13 | 9 / 2.0 |

\* V0's timing comes from an earlier session (T08b). On every split, the gate result is identical for all seven
variants (test: 0 false invites, 4 false rejects, 15.4% review).

**Choice (rule: dev macro-F1, then false rejects, then simpler): V6.**

**The honest reading, which you should say in the presentation:**
- V6 is the only variant above V0 on dev, but **the gain is noise**: vs V0 it fixes 10 dev rows and breaks 8 (net +2
  of 182; sign test **p = 0.81**). On test it's slightly lower (0.644 vs 0.661: 3 fixed, 6 broken, p = 0.51).
- **The final hiring outcome doesn't move**: false invites 0, false rejects and review rate identical for all
  variants.
- **Better retrieval (MRR 0.52 → 0.80) didn't give a measurable Matcher gain.** Why:
  1. The Matcher's errors are mostly **about the CV** (vague evidence, years, "hands-on"), not about vocabulary.
  2. The 6 "alias" error rows stay wrong with every variant except V4 (1 of 3 on dev). Knowledge explains a term; it
     **cannot turn a buried skill into a CV quote**.
  3. Changing the knowledge block shifts the label probabilities a little, and the 0.72 confidence rule then flips
     borderline answers MISSING ↔ UNCERTAIN. V2 vs V0 on dev changed 17 final decisions but only 6 raw model
     decisions. Most of the spread between variants is this flip, i.e. noise around the threshold.
  4. The LoRA was trained with **BM25** knowledge, so dense refs are a small distribution shift.
- **Why keep V6 then?**
  - no knowledge block when it isn't needed (18% of rows);
  - a cheap dense lookup (~9 ms) instead of hybrid or rerank (24–65 ms);
  - a retriever that clearly finds the right concept when the job uses another name;
  - RAG is visible as its own step in n8n.

### 4.7 Experiment 4: re-checking the confidence threshold with V6 (T09b)

The knowledge block shifts the Matcher's probabilities, so we checked whether **tau = 0.72** should move. An offline
sweep from 0.50 to 0.90 on the saved V6 dev rows: **no value gives fewer false rejects** (6 at every tau ≥ 0.54), and
0.72 already keeps review under the 25% cap. **tau stays 0.72.** Test, once, at 0.72: macro-F1 0.644, 0 false
invites, 4 false rejects, 15.4% review.

### 4.8 Latency and resources (measured)

| What | Value | Source |
|---|---|---|
| Warm dense query (Qdrant) | 8.23 ms | RAG_REPORT §5 |
| RAG lookup in the n8n run, after warm-up | 4–14 ms | T09 e2e (P15) |
| First `/rag/search` after an API start (loads MiniLM, embeds 1,621 chunks, builds Qdrant) | ~20.9 s | T09 e2e (P15) |
| Per CV in the final evaluation, RAG station (mean / max) | 4.6 s / 117.4 s (the max is the first cold run) | FINAL_EVAL |
| MiniLM per query in the 84-grid (includes the cold first query) | ~38 ms (bge-small ~57 ms) | RAG_REPORT §4 |
| Index on disk | 6.7 MB (Qdrant) | RAG_REPORT §5 |
| Embedding model on disk | 91 MB | RAG_REPORT §4 |

Not measured separately: RAM, VRAM of the embedder alone (it shares the GPU with llama-server and the Judge), and CPU-only
latency.

---

## 5. Testing and validation

### 5.1 Automated tests (`tests/test_rag.py`)

| Test | What it proves |
|---|---|
| `test_chunk_a_is_exactly_the_v2_text_the_matcher_has_seen` | All 1,621 chunk-A texts equal the V2 texts the LoRA was trained with |
| `test_chunk_b_adds_broader_and_related_labels` | Chunking B = A + graph labels |
| `test_bm25_chunk_a_equals_the_current_provider` (3 cases) | The new retriever's BM25 gives the same refs as the old provider (no regression) |
| `test_refs_keep_the_format_the_lora_saw` | 3 refs, ≤ 300 characters, real ESCO URIs (**source attribution**) |
| `test_graph_expansion_inserts_neighbours_after_the_top_hits` | Graph expansion behaves as designed |
| `test_terms_in_cv_rule` | Skip rule: all terms present → skip; one missing → retrieve; no terms → retrieve; `C` doesn't match `C++` |
| `test_vector_stores_give_the_numpy_ranking` (Qdrant, Chroma) | The stores return exactly the numpy ranking. The Chroma case is **skipped** because chromadb was uninstalled |
| `test_rag_search_endpoint_and_skip_rule` | **API contract:** `/rag/search` returns 3 refs, or `skipped: true` with `[]` when the rule fires |
| `test_match_uses_the_refs_from_the_request` | **Integration:** `/match` uses exactly the refs it receives |

**Results** (T09): `tests/test_rag.py` → **11 passed, 1 skipped** (the Chroma case). The latest full suite, after T15:
`pytest -q` → **514 passed, 1 skipped** (the same Chroma test).

### 5.2 Other validation

| Check | Result |
|---|---|
| **Retrieval quality** | 46 queries, golds checked by a human, dev/test split (section 4) |
| **Matcher effect** | 364 labelled rows, dev/test (section 4.6) |
| **Real end-to-end in n8n** | Execution 28 (P15): RAG lookup ran 6×, all successful, 3 of 6 skipped by the rule; `/match` got exactly the RAG refs |
| **Workflow integrity** | After import and re-export, the n8n nodes and connections equal the generated 31-node workflow (it has since grown with later tasks) |
| **Data integrity** | ESCO file rebuilt byte-identical (sha256) |
| **Dev vs test** | Every choice was made on dev; test was used once to report |

### 5.3 What isn't tested (honest gaps)

- **No "no answer" (abstention) behaviour.** The retriever **always returns k = 3 refs**, even when none is relevant
  (e.g. "Data Lakes" in 4.4). There's no relevance threshold. The safety net is the prompt rule "knowledge is not
  evidence" plus the quote validator.
- **No restart / persistence test.** The Qdrant index is rebuilt at each API start (see 6.3), so there's no
  persisted-index behaviour to test.
- **No dedicated load or p95 latency test.**

---

## 6. How it runs (model execution and deployment)

| Question | Answer (verified in `services/api.py` / `rag/retrieval.py`) |
|---|---|
| Does MiniLM run all the time? | It's loaded **once, on the first `/rag/search` call** after the station API starts (lazy `_rag()`), then stays in memory until the API stops |
| When are the ESCO embeddings made? | At that first call: the 1,621 chunk-A texts are embedded in batches of 64 (normalised vectors) |
| Where are they stored? | In memory (numpy) **and** in the Qdrant local collection `esco` under `rag/index/qdrant_A_all-MiniLM-L6-v2/` |
| What happens on restart? | The collection is **deleted and rebuilt** from the ESCO file (a few seconds for 1,621 vectors; the first call ~20 s in total with the model load). The on-disk index is not reused across restarts. That's a simplicity choice: the corpus is fixed and small |
| How is a new query embedded? | The same MiniLM encodes the query (no prefix needed), and Qdrant returns the closest vectors by cosine |
| GPU or API needed? | **No external API, no internet at run time, zero cost.** It uses the GPU when one is available (`RAG_DEVICE` = cuda), otherwise the CPU (the tests run it on CPU) |
| Measured speed | Warm query 4–14 ms in n8n; Qdrant warm 8.23 ms (section 4.8) |

---

## 7. A complete end-to-end example

> **Part 1 is 📸 captured** from a real n8n run. **Part 2 is 💡 illustrative**: it follows the real code path, but the
> CV and the job are invented.

### 7.1 Captured: execution 28, pair P15 (`eval/results/2026-10-18_n8n_e2e_rag/`)

| Req | Requirement (must) | RAG | Refs given to the Matcher | Matcher decision |
|---|---|---|---|---|
| r1 | "Knowledge of the general principles of Data Warehousing and Data Lakes" | Retrieved (20.9 s, the cold start) | data warehouse · implement data warehousing techniques · manage findable accessible interoperable and reusable data | MISSING |
| r2 | "Hands-on experience with SQL" | **Skipped** (SQL is in the CV), 14 ms | – | MET |
| r3 | "Knowledge of Python" | **Skipped**, 5 ms | – | MET |
| r4 | "Experience with GCP or another cloud provider" | Retrieved, 12 ms | IBM InfoSphere Information Server · deploy cloud resource · develop with cloud services | MISSING |

r4 shows a **known weakness**: "GCP" isn't in ESCO, so the first ref is off-topic. The Matcher still has to quote the
CV, so the wrong ref can't become evidence. The pipeline outcome was **review** (sent to the recruiter form).

### 7.2 Illustrative: Python + FastAPI + Machine Learning 💡

**Job (must-haves), as the Job Agent would produce them:**

| req | text | skill_terms |
|---|---|---|
| r1 | Strong proficiency in Python | `["Python"]` |
| r2 | Experience building APIs with FastAPI | `["FastAPI"]` |
| r3 | Experience with machine learning | `["machine learning"]` |

**Anonymised CV (excerpt):** *"Backend developer. Built REST APIs with FastAPI and PostgreSQL. Python, Docker, Git."*
No machine learning anywhere.

**Step 1: RAG lookup, per requirement**

| req | Skip rule | Query sent to Qdrant | Result |
|---|---|---|---|
| r1 | "Python" is in the CV → **skipped** | – | `knowledge_refs: []` → prompt shows `(none retrieved)` |
| r2 | "FastAPI" is in the CV → **skipped** | – | `[]` |
| r3 | "machine learning" isn't in the CV → **retrieve** | `machine learning` | 3 ESCO refs |

For r3 the Matcher's knowledge block would look like this. The first line is the **real** ESCO chunk-A text; the
exact other two refs weren't captured for this query:

```
Knowledge (terminology only, not candidate evidence):
[3a2d5b45-56e] machine learning. Also known as: ML. The principles, methods and algorithms of machine learning,
a subfield of artificial intelligence. Common machine learning models such as supervised or unsupervised models,
semi- supervised models and reinforcement learning models.
[…] (two more closely related ESCO concepts, e.g. deep learning)
```

**Step 2: what the Matcher receives (r3):** the fenced CV text, then
`Requirement (must-have, skill): Experience with machine learning`, then the knowledge block above.

**Step 3: the Matcher's decisions**

| req | Decision | basis | evidence (must be a CV quote) |
|---|---|---|---|
| r1 | MET | supported | "Python, Docker, Git." |
| r2 | MET | supported | "Built REST APIs with FastAPI and PostgreSQL." |
| r3 | MISSING | not_documented | `[]` (the ESCO text explains ML, but nothing in the CV shows it) |

**Step 4: what if the evidence is missing or unclear?**
- **Missing:** r3 is a must-have and MISSING → the gate's rule 1 → **reject**, with a letter naming the missing
  requirement and the right to ask for a human review.
- **Unclear:** if the CV had said *"worked on a data project"*, the Matcher should say UNCERTAIN. Even if it said MET
  with confidence below 0.72, or MET with no verifiable quote, code turns it into UNCERTAIN → the case goes to
  **review** by a recruiter.
- **Invented evidence:** if the Matcher quoted the ESCO text, the validator wouldn't find the quote in the CV, so it
  would be rejected as evidence.

---

## 8. Current status

### 8.1 Done ✅ (implemented, measured, verified)

| Item | Where | Evidence |
|---|---|---|
| ESCO corpus, 1,621 concepts, pinned and rebuildable | `rag/build_esco.py`, `rag/data/esco/` | sha256 byte-identical to V2 |
| Chunking A (deployed) and B (tested) | `rag/retrieval.py` | RAG_REPORT §2 |
| Dense MiniLM retrieval, k = 3 | `rag/retrieval.py`, `services/api.py` `_rag()` | Dev MRR 0.52 → 0.80 |
| Qdrant local store | `rag/index/` | 46/46 equal to numpy |
| Skip rule (V6) | `terms_in_cv`, `RAG_ONLY_WHEN_MISSING=1` | Skipped 67/364 rows |
| `/rag/search` API + contracts | `services/api.py`, `services/contracts.py` | Tests pass |
| n8n "RAG lookup" node before each `/match` | `n8n/hiresignal_v1.json` | e2e execution 28 |
| Matcher takes refs from the request | `services/matcher/matcher.py` | Test + e2e |
| Bias Auditor uses the same RAG rule in swap re-runs | `services/api.py` `_rag_refs()` | Code |
| Evaluation sets with human-checked golds | `rag/eval/queries.jsonl`, `queries_review.xlsx` | 22 OK / 10 CHANGE / 0 DROP |
| Retrieval, store, Matcher-effect and tau benchmarks | `eval/results/2026-10-18_rag_*`, `2026-10-18_tau_recheck/` | Section 4 |
| Tests | `tests/test_rag.py` | 11 passed, 1 skipped |
| Pushed to the team repo | `HireSignal-5DS-Team/HireSignal-5DS`, branch `v3-final` | First push `b7d1d1a`, latest `a93368d` |

### 8.2 Not integrated / kept outside the production path

| Item | Status |
|---|---|
| BM25 inside `/match` (when no refs are sent) | 🔁 Backward compatibility only; n8n always sends refs |
| Hybrid, rerankers, graph expansion, chunking B, e5-base, bge-small | 🧪 In the code behind `RAG_*` switches, **off** in production |
| Chroma store | 🧪 Code path exists; package uninstalled after the benchmark |
| n8n's built-in Qdrant node | Not used: n8n calls our API, which keeps the skip rule and the ref format in one place |

### 8.3 Limits and future work (nothing is blocked)

| Limit | Why it matters | Possible next step |
|---|---|---|
| **No measurable Matcher gain** from better retrieval | RAG helps find the concept, not the decision | Fix the Matcher side: teach it to quote CV lines that hold a buried skill |
| **ESCO gaps**: no Spark, Kubernetes, AWS, PyTorch, data lake, microservices, AutoML | Those requirements only get a broader, sometimes off-topic concept (e.g. GCP → IBM InfoSphere) | A newer ESCO version or a company's own skills base |
| **No relevance threshold** | 3 refs are always returned, even weak ones | Add a minimum score; measure on dev first |
| **The skip rule needs exact words** | "Postgres" in the CV doesn't skip a "PostgreSQL" requirement (retrieval runs instead, which is safe) | Alias-aware matching using ESCO alt labels |
| **Small eval set** (46 queries, 364 rows) | Wide error margins; MiniLM vs bge-small is a tie | More labelled queries |
| **Only 13 of 84 configs re-scored** on the checked golds | A config outside the table could rank higher on dev | Re-run the full grid if needed (not needed for the current choice) |
| **The index is rebuilt at every start** (~20 s first call) | Slow first CV after a restart | Preload at startup or reuse the on-disk index |
| **The LoRA was trained with BM25 knowledge** | Dense refs are a small distribution shift | Retrain the LoRA with dense refs (future) |
| `rag/README.md` says "ESCO + job postings" | Outdated wording; the corpus is ESCO only | Fix the one-liner (docs) |

---

## 9. Presenting it

### 9.1 30-second version

> "Our Matcher sometimes doesn't know that two words mean the same skill, like PL/SQL and SQL. So before each check,
> a RAG step looks up the requirement in ESCO, the EU's skills vocabulary, and adds the three closest definitions to
> the prompt, as knowledge, never as evidence. We embed 1,621 ESCO concepts with MiniLM and store them in Qdrant.
> Dense search finds the right concept far better than keyword search: MRR 0.52 to 0.80. And if the skill is already
> written in the CV, we skip RAG."

### 9.2 Two-minute technical version

> "RAG in HireSignal has one job: give the Matcher the meaning and other names of a skill. Never evidence about the
> candidate. The query is built only from the requirement's skill terms, never from the CV, and every quote the
> Matcher gives is checked against the CV text by code.
>
> Our knowledge base is ESCO v1.1.1, the European Commission's skills vocabulary, licensed CC BY 4.0. We keep 1,621
> ICT and data concepts. Each concept is one chunk, label plus alternative names plus description, so nothing is cut
> and we don't need overlap.
>
> We benchmarked 84 configurations on 46 queries with human-checked answers, choosing on dev and reporting test once.
> Dense retrieval beat BM25 clearly, MRR 0.80 against 0.52, because queries like 'Lakehouse' share no word with the
> ESCO label. Hybrid search, two rerankers, graph expansion and richer chunks all did worse. MiniLM and bge-small tied
> on dev, so we kept the smaller, faster MiniLM. For the store, Qdrant and Chroma returned identical results, and we
> chose Qdrant because it adds no dependencies.
>
> Then the most important test: does it change hiring decisions? On 364 labelled rows, no variant moved the final
> outcome. Zero false invites for all, the same false rejects. The Matcher's errors are about the CV, not vocabulary.
> We report that honestly. We kept variant V6, dense and skipped when the skill is already in the CV, because it's
> fast, about 9 milliseconds, and it removes unneeded knowledge on 18% of rows.
>
> In production, n8n has a visible 'RAG lookup' node before every Matcher call, using our /rag/search endpoint on
> port 8010."

### 9.3 Ten likely professor questions

| # | Question | Short answer |
|---|---|---|
| 1 | Why RAG at all if the Matcher is fine-tuned? | The LoRA learned the task, not every skill name. RAG adds synonyms and definitions (PL/SQL → SQL) without retraining |
| 2 | Why ESCO and not job postings or Wikipedia? | ESCO is the EU's official skills vocabulary, with synonyms and a hierarchy, free under CC BY 4.0. Job postings describe jobs, not skill meanings |
| 3 | Can RAG make a candidate look qualified? | No. The query never uses CV text, the prompt says knowledge isn't evidence, and code rejects any quote that isn't in the CV |
| 4 | Why dense and not BM25? | Skill queries often share no word with the right label ("Lakehouse" → data warehouse). Dense: dev MRR 0.80 vs 0.52 |
| 5 | Why MiniLM if bge-small scored higher on dev? | The gap was 3 queries out of 24 with equal hit@3, so we called it a tie and chose the simpler, faster model (6 vs 12 layers, 91 vs 134 MB, ~38 vs ~57 ms) |
| 6 | Why k = 3? | It's the format the LoRA was trained on (3 refs, 300 characters). Changing it would shift the model's input |
| 7 | Why didn't rerankers help? | They're trained on web passages (MS MARCO), not on short skill labels. Dev MRR 0.765 and 0.609 vs 0.798 |
| 8 | Did RAG improve the final decisions? | No measurable effect: macro-F1 0.665 vs 0.651 on dev (p = 0.81), and the gate outcome is identical. We say so honestly; RAG mainly fixes concept finding |
| 9 | What is the skip rule and why? | If every skill term is already written in the CV, no knowledge is needed. It avoids noise and saved retrieval on 18% of rows |
| 10 | What are the main limits? | ESCO gaps (no Spark, PyTorch, AWS…), no relevance threshold (always 3 refs), a small eval set, and the index rebuilt at each start |

### 9.4 Glossary

| Term | Simple definition |
|---|---|
| **Alias / alternative label** | Another name for the same skill (Py3K = Python) |
| **BM25** | Classic keyword search: scores documents by shared words, rare words counting more |
| **Chunk / chunking** | A piece of the knowledge base that gets one vector / the act of cutting it. Ours: one ESCO concept per chunk |
| **Cold / warm query** | The first query (loads the model and builds the index) / later queries |
| **Cosine similarity** | How close two vectors point in the same direction; 1 = same meaning |
| **Cross-encoder / reranker** | A model that reads the query and a candidate together to re-score it; slower but finer |
| **Dense retrieval** | Search by meaning vectors instead of words |
| **Dev / test split** | Dev = data to choose on; test = data used once to report honestly |
| **Embedding** | A list of numbers representing a text's meaning |
| **ESCO** | European Skills, Competences, Qualifications and Occupations: the EU skills vocabulary |
| **Graph expansion** | Adding broader / related ESCO concepts after the top hits |
| **Gold** | The correct answer, checked by a human |
| **hit@k (Recall@k)** | Share of queries with a correct answer in the top k |
| **Hybrid search / RRF** | Running keyword and dense search and merging the rankings (Reciprocal Rank Fusion) |
| **k** | Number of results returned (3 for us) |
| **Knowledge ref** | One retrieved ESCO entry given to the Matcher |
| **LoRA** | A small fine-tuning add-on for the LLM; ours was trained by the team for the Matcher task |
| **macro-F1** | The average F1 over the three decision classes, each counting equally |
| **MRR@10** | Mean of 1 / (rank of the first correct answer), 0 if not in the top 10 |
| **Qdrant (local mode)** | A vector database running inside our Python process, saving to a folder |
| **RAG** | Retrieval-Augmented Generation: search, then add the results to the prompt |
| **Sign test** | A simple test of whether a row-by-row difference between two systems is more than luck |
| **Skill terms** | The key skill words the Job Agent extracts from a requirement (e.g. "SQL") |
| **Skip rule (V6)** | No retrieval when every skill term is already written in the CV |
| **tau (0.72)** | The confidence threshold under which a Matcher answer becomes UNCERTAIN |
| **Vector database** | A store that finds the vectors closest to a query vector |
