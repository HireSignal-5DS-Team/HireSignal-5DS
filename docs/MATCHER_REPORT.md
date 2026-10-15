# HireSignal Matcher Agent: architecture, decisions, evaluation

Branch `claude/kind-albattani-k7qlt9`. Written 2026-10-15 for the final project report. Every number
in this document comes from a file in `benchmark/results/` or another file named next to it. Anything
argued but not measured is labelled **reasoned**.

## 1. Task

For each requirement of a job, the Matcher reads an anonymized CV and the requirement and returns:
- a decision `MET`, `MISSING` or `UNCERTAIN`;
- a basis `supported`, `contradicted`, `not_documented` or `ambiguous`;
- verbatim CV evidence with character offsets;
- an explanation;
- the ESCO references used;
- a human-review flag with its reasons.

It never rejects a candidate and never produces a hiring decision (`MatchSummary.note`).

## 2. Architecture

```
anonymized CV (text)      structured job requirements
        │                          │
        │                 knowledge lookup: team RAG, BM25 over 1,621 ESCO concepts
        │                 (query = requirement skill terms only; CV text never sent)
        └──────────┬───────────────┘
                   ▼
       prompt (matcher/prompt.py, one format for inference, benchmark and LoRA)
                   ▼
   ONE generative SLM < 1B params (+ optional LoRA adapter of the same base)
                   ▼
   deterministic Python validation (matcher/validate.py)
     JSON + schema parse │ exact-substring quote check │ decision/basis consistency │
     years-of-experience check │ review flags
                   ▼
   RequirementResult × n  →  MatchReport (strict Pydantic / JSON Schema, matcher/json_schemas/)
```

| Module | Role |
|---|---|
| `matcher/schemas.py` | Data contracts (CV, Job, Requirement, KnowledgeRef, ModelAnswer, RequirementResult, MatchReport); `extra="forbid"` everywhere |
| `matcher/prompt.py` | System + user message; knowledge is labelled "terminology only, NOT evidence" |
| `matcher/knowledge.py` | `RagKnowledge` (team `rag/retrieval.py`, BM25 mode), `FixtureKnowledge`, `NoKnowledge` |
| `matcher/backends.py` | `TransformersBackend` (the SLM; refuses ≥ 1B params; refuses adapters whose `adapter_config.json` names another base), `LexicalBaseline` (non-neural reference), `MockBackend` (tests only) |
| `matcher/validate.py` | The rules in §4 |
| `matcher/agent.py` | Orchestration and summary (counts, must-have coverage ratio) |
| `benchmark/` | Synthetic dataset generator, locked splits, metrics, resumable runner, comparison table, RAG check |
| `finetune/` | SFT builder (refuses test split), resumable LoRA trainer, smoke test |

### One-generative-model constraint (verified)

- Only `TransformersBackend` loads a neural network. Its parameter guard counts `model.parameters()`
  and raises an error at ≥ 1,000,000,000.
- A LoRA adapter only adds low-rank matrices to that same base. The compatibility check
  refuses any other base.
- Retrieval uses `Retriever(chunks)` with `model=None`, which is BM25 only. The RAG branch's optional
  e5 embedder and cross-encoder reranker are never loaded. The test
  `test_end_to_end_with_real_rag_bm25_and_mock_slm` asserts this: `retriever.model is None`, and
  neither `sentence_transformers` nor `qdrant_client` is imported.
- Python does the scoring and validation. Python and the BM25 index are tools, not models.

Measured parameter counts (sum of `model.parameters()` at load time, recorded in each run's `config.json`):
see the results table in §6.

## 3. Decisions and alternatives

| # | Decision | Alternatives considered | Why | Status |
|---|---|---|---|---|
| M1 | One SLM < 1B, CPU-capable | Qwen3-4B via Ollama (cancelled by the project); two-model pipelines (embedder + generator) | Project constraint; runs on a laptop GPU (6 GB) and on CPU | constraint |
| M2 | Lexical BM25 retrieval of ESCO inside the Matcher | e5-small dense (RAG default profile), hybrid RRF, cross-encoder | A dense model would be a second neural model. BM25 found the right ESCO concept for 100 % of the val alias items (§6.3) | measured |
| M3 | One SLM call per requirement | One call per job with all requirements | Short contexts suit 0.5B models (prompt ≤ 605 tokens); a malformed answer affects one requirement only | reasoned |
| M4 | The model proposes, Python decides | Trust model output | Tiny models hallucinate quotes (seen in the first smoke run: the model quoted ESCO text and its own paraphrases as "CV evidence") | measured |
| M5 | Exact substring evidence only (after stripping surrounding whitespace) | Fuzzy matching | Fuzzy matching would accept paraphrases, which are fabricated evidence | reasoned |
| M6 | `MISSING` split into `contradicted` vs `not_documented` | One MISSING class | "Not mentioned" is not proof of absence; must-have `not_documented` always goes to human review | requirement |
| M7 | Review priority low/medium/high from named rules | Model-reported confidence | Model confidences are uncalibrated. Rule reasons are auditable. Never presented as probabilities | reasoned |
| M8 | Greedy decoding, `max_new_tokens=192`, same prompt for every model | Sampling; per-model prompts | Comparability and reproducibility | design |
| M9 | Qwen3 with `enable_thinking=False` | Thinking mode | The JSON-only answer must fit 192 tokens; thinking output would be cut | reasoned |
| M10 | Synthetic benchmark with split-disjoint pools | Real CVs | No private data may be used. Disjoint pools prevent memorising phrasings across splits | design |
| M11 | Test split locked (runner flag, SFT refusal ×3) | Free use | Model selection on val only | design |
| M12 | RAG used read-only from its branch via `HIRESIGNAL_RAG_DIR` | Merge the RAG branch | Merging was not authorised in this environment; the code is not duplicated | constraint |

## 4. Validation rules (`matcher/validate.py`)

| Rule | Effect | Review priority |
|---|---|---|
| Output not parseable as `ModelAnswer` JSON | `UNCERTAIN`/`ambiguous` | high |
| Decision and basis inconsistent (e.g. MET + not_documented) | `UNCERTAIN` | high |
| Quote not an exact CV substring | quote dropped | medium |
| `MET` with no verified quote | `UNCERTAIN` | high |
| `MET` on a `min_years` requirement, years in quotes < minimum | `UNCERTAIN` | high |
| `MET` on `min_years`, no duration parseable | kept, flagged | medium |
| `MISSING`/contradicted without a verified quote | becomes `not_documented` | medium |
| `MET` on a skill whose quote contains no requirement term or ESCO alias | kept, flagged (semantic inference) | medium |
| Any `UNCERTAIN` | flagged | medium |
| Must-have `MISSING` | flagged (no automatic rejection) | medium |

Years parsing covers explicit "N years" and merged date ranges ("2019 - present", reference year 2026).

Because evidence is accepted only after verification, a quote of ESCO text can never count as candidate evidence.
`test_knowledge_text_cannot_be_evidence` checks this.

## 5. Benchmark

### 5.1 Data (`benchmark/make_dataset.py`, version `bench-v1`, seed 20261015)

The data is fully synthetic and anonymized. It contains no names, e-mails or employers. Every gold quote
is asserted to be an exact CV substring. Counts are from `benchmark/data/MANIFEST.json`:

| split | cases | requirements | MET / MISSING / UNCERTAIN | sha256 (prefix) |
|---|---|---|---|---|
| train | 150 | 681 | 305 / 273 / 103 | d0206264f093 |
| val | 45 | 202 | 86 / 77 / 39 | 37c60915f2db |
| test (LOCKED) | 45 | 199 | 92 / 84 / 23 | 0bde3a86cc30 |

The data includes these hard cases, tagged per requirement (counts in the manifest):
- ESCO alias equivalence: the requirement uses the ESCO preferred label and the CV only an alternative label;
- implicit project evidence;
- missing evidence;
- contradiction and negation traps ("Has not worked with X", "preparing for the X exam");
- insufficient experience;
- ambiguous duration;
- partial evidence;
- RAG near-miss: ESCO retrieves the required concept, but the CV shows only a neighbouring activity;
- distractor details;
- multi-requirement jobs (3–6 requirements).

Leakage control: every pool is partitioned by index into the three splits. The pools are skills, ESCO pairs,
project sentences, requirement and CV phrasings, section titles and headers. `benchmark/tests` checks that
no CV text, no requirement sentence and no CV line longer than 25 characters is shared across splits.

**Label policy** (debatable cases; a reviewer may disagree):
- "Some familiarity with X" against "Experience with X" is `UNCERTAIN`.
- "Preparing for certificate X" is `MISSING`/contradicted.
- A bachelor's degree in an unrelated field against a master's requirement is `MISSING`/contradicted.

### 5.2 Metrics (`benchmark/metrics.py`)

- **Final**: macro-F1, accuracy, per-class P/R/F1 and confusion after validation.
- **Raw**: the same metrics on the model's own decision before validation. An unparseable answer counts as wrong.
- **False-MET rate** = predicted MET among items whose gold is not MET, divided by the number of those items.
- **JSON/schema validity** = share of answers that parse as `ModelAnswer`.
- **Raw quote validity** = share of model quotes that are exact CV substrings.
- **Evidence attribution** = share of correctly decided MET/contradicted items whose verified quote overlaps
  the gold span.
- **Other**: basis accuracy, per-tag accuracy, review rate, latency p50/p95, peak RSS and load time.

## 6. Results

RESULTS_PLACEHOLDER

## 7. Limitations

- The benchmark is synthetic and template-based. Real CVs are longer, messier and multilingual.
  Numbers measure behaviour on controlled hard cases, not production accuracy.
- Gold labels were written by the generator's label policy (§5.1) and have not been reviewed by a second person.
- The RAG check queries ESCO labels that occur in the requirement text, which is an easy case. Natural-language
  retrieval quality is covered by the RAG team's own evaluation on its branch (exp02/exp03), not here.
- O*NET is not in the repository. Only the ESCO ICT subset (v1.1.x, CC BY 4.0) is used.
- CPU latency was measured on a shared 4-core cloud container; tokenisation jobs ran in parallel for a
  few minutes during the first run. Treat latency as indicative.
- `review_priority` is a rule signal, not a calibrated probability.
- No HireSignal LoRA adapter has been trained (`finetune/README.md`).
- The existing adapter `Kus-hal/resume-screener-lora` was trained for a different output format, a whole-resume
  verdict. It is measured as-is with our prompt.
- The local components `hiresignal_cv_reader`, `hiresignal_benchmark` and `hiresignal_finetune` were not
  accessible. The integration contract is in `LOCAL_INTEGRATION_HANDOFF.md`.
