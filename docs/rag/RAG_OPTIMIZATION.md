# RAG optimisation for the Matcher (Session 1)

Branch `session/s1-rag-optimization`. Plan and rules: `docs/orchestration/ORCHESTRATION.md`. Compute window 0 while
this was written: **no LLM was run in this session.** Every number below names its source and backend:

- **LIVE (recorded)**: predictions produced earlier by real models and committed (base Qwen3-4B-Instruct-2507 Q4_K_M,
  llama.cpp, temperature 0, 192 new tokens, prompt p1, k = 3, 202 bench-v1 **val** requirements). Not re-run here.
- **RETRIEVAL**: retrieval-only measurements made in this session on CPU (BM25; e5-small dense under `nice -n 19`).
- **REPLAY ESTIMATE**: recombination of recorded answers, not a model run (§5). It bounds an effect; it is not a result.
- **MOCK**: plumbing checks with scripted backends; never a model result.

## 0. Summary

1. RAG lowered the base Matcher's macro-F1 (BM25 −0.041, dense −0.050; LIVE recorded, RAG audit §11) for three
   reasons, in order of size: (a) **template echo**: every "invalid JSON" answer is valid JSON that copies the p1
   enum template `"MET|MISSING|UNCERTAIN"`, and it gets more frequent with longer prompts; (b) **off-target
   references**: the legacy BM25 provider injected 1.28 unrelated ESCO concepts per requirement on average. Every
   reference it gave for certifications, languages and degrees was unrelated (e.g. "SQL Server, Microsoft Access,
   Microsoft Visio" for an Azure certification); (c) **neighbouring concepts** on absent-skill traps (the right
   concept plus 2 near neighbours).
2. New provider **`rag.gated.v1`** (`matcher/knowledge.py:GatedKnowledge`, same frozen interface): it skips
   requirement types that ESCO cannot inform, matches the exact ESCO label or alias first, applies a strict relevance
   cut-off, returns one concept per skill term, removes duplicates, and keeps each knowledge text at 280 characters
   or less, so the prompt shows every cited reference in full. The legacy `RagKnowledge` (old BM25 arm) is unchanged.
3. RETRIEVAL on the 202 val requirements: the same recall as legacy BM25 on every requirement that has an ESCO concept
   (alias and absent-skill items: recall@1 1.0 for both). Off-target references per requirement drop from 1.28 to 0,
   knowledge text from 379 to 57 characters, and abstention precision is 0.907 (abstention recall 1.0).
4. REPLAY ESTIMATE for the base Matcher: Δ macro-F1 vs no-RAG **+0.004 [−0.014, +0.023]** (legacy BM25: −0.041
   [−0.083, −0.000]). The alias gain is kept (0.29 → 0.43), and certifications go back to their no-RAG level.
   This is not a measured gain: the live comparison is prepared and waits for window 1 (§6).
5. The fine-tuned (LoRA) Matcher produced **0** template echoes in 138/202 recorded answers (partial checkpoint).
   For that model the cost of RAG is mostly latency and decision quality, not JSON validity. Whether RAG helps it is
   **unmeasured** until the window-1 run.

## 1. Reproduce (no LLM needed)

```bash
pip install -r rag/requirements.txt          # bm25s, qdrant-client, pytest, ... (sentence-transformers only for --dense)
python -m rag_opt.error_analysis             # §2, §5  -> rag_opt/results/error_analysis.{md,json}
python -m rag_opt.retrieval_eval             # §4      -> rag_opt/results/retrieval_metrics.{md,json}
nice -n 19 python -m rag_opt.retrieval_eval --dense   # §4 dense rows (downloads intfloat/multilingual-e5-small)
python -m pytest -q matcher benchmark/tests rag/tests # tests (MOCK / recorded data only)
```

Inputs of the error analysis (all committed, read-only): A′ `rag/integration/results/qwen3-4b-q4-none-val-rerun`,
B′ `…/qwen3-4b-q4-bm25-val-rerun`, C `…/qwen3-4b-q4-dense-val` (llama-server, RAG audit), A
`benchmark/results/qwen3-4b-q4-none-val`, B `benchmark/results/qwen3-4b-q4-rag-val` (llama_cpp.server, Matcher
session), and the partial LoRA predictions read with `git show 302a424:benchmark/results/qwen3-4b-q4+hslora-rag-val/predictions.jsonl`
(evaluation branch, never checked out or modified).

## 2. Diagnosis (LIVE recorded predictions, base Qwen3-4B Q4; `rag_opt/results/error_analysis.md`)

### 2.1 The "invalid JSON" is template echo

| run | knowledge | macro-F1 | unparsed | of which template echo | mean prompt tokens |
|---|---|---|---|---|---|
| A′ | none | 0.649 | 14 | 14 | 315 |
| B′ | legacy BM25 k=3 | 0.608 | 27 | 27 | 401 |
| C | dense e5-small k=3 | 0.599 | 25 | 24 (+1 other schema violation) | 501 |
| A | none (llama_cpp.server) | 0.634 | 10 | 10 | 315 |
| B | legacy BM25 (llama_cpp.server) | 0.630 | 17 | 17 | 401 |

None of the unparsed answers is truncated (64–104 of 192 completion tokens). The model writes
`{"decision": "MET|MISSING|UNCERTAIN", "basis": "supported|contradicted|not_documented|ambiguous", ...}`, which is
the format line of the p1 system prompt. The rate grows with the prompt length: 6.4 % / 15.8 % / 9.9 % by
prompt-length tertile (A′, B′, C pooled), and in B′ 8 % with no reference vs 17 % with three references.
`rag.gated.v1` attacks this through length only (57 vs 379 knowledge characters per requirement). The direct fix is
outside S1's files and is filed as a request: `docs/orchestration/requests/s1-template-echo-json.md` (JSON-schema
constrained decoding in the backend; the prompt stays p1).

### 2.2 Noise floor of the recorded runs

B′ injected nothing for 87 requirements, so its prompt was **byte-identical** to A′ for those (same prompt token
counts). The same server answered them differently: 72/87 identical raw outputs, 84/87 identical decisions, 6 vs 7
echoes. Server drift between the two serving stacks (A vs A′) is −0.015 [−0.045, +0.016]. Any live difference of
about ±0.02 macro-F1 is therefore within noise; the E2E script repeats the no-RAG arm to measure this floor (§6).

### 2.3 Where accuracy was lost (paired vs A′, 202 requirements)

| group | n | acc A′ | acc B′ | lost: unparsed / parsed | gained | acc C |
|---|---|---|---|---|---|---|
| all | 202 | 0.649 | 0.604 | 9 / 7 | 7 | 0.594 |
| certification | 13 | 0.538 | 0.231 | 3 / 2 | 1 | 0.385 |
| absent-skill trap | 11 | 0.455 | 0.364 | 0 / 1 | 0 | 0.091 |
| alias | 21 | 0.286 | 0.429 | 0 / 0 | 3 | 0.429 |
| implicit project evidence | 15 | 0.400 | 0.267 | 3 / 0 | 1 | 0.400 |
| language | 14 | 1.000 | 0.929 | 0 / 1 | 0 | 0.857 |

On the 167 requirements parsed in A′, B′ and C, accuracy is 0.689 / 0.683 / 0.671: most of the loss is unparsed
output, the rest sits in the categories where the references were irrelevant.

### 2.4 The references were mostly off-target

Gold concept = the ESCO concept whose preferred or alternative label equals the requirement's skill term (for alias
and absent-skill items this is the generator's ground truth: `benchmark/make_dataset.py` builds them from ESCO
preferred labels).

| category | n | has an ESCO concept | B′ refs: on-target / off-target | C refs: on-target / off-target |
|---|---|---|---|---|
| skill | 102 | 40 | 40 / 132 | 40 / 266 |
| experience | 63 | 11 | 11 / 30 | 11 / 178 |
| certification | 13 | 0 | 0 / 24 | 0 / 39 |
| language | 14 | 14 | 0 / 42 | 14 / 28 |
| education | 10 | 0 | 0 / 30 | 0 / 30 |

Examples (val): "Microsoft Azure Administrator Associate certification" → SQL Server, Microsoft Access, Microsoft Visio
(BM25) / manage flight data communications programme, OWASP ZAP, Microsoft Access (dense). "Ability to maintain
information network hardware" (CV: "Maintained the team's information wiki", gold MISSING) → the right concept plus
"maintain ICT server" and "ICT networking hardware" (dense: absent-skill accuracy 0.45 → 0.09). Where the concept
exists, BM25 and dense both rank it first (65/65), so the problem is not recall. The problem is everything else that
gets injected.

### 2.5 LoRA Matcher (LIVE recorded, PARTIAL: 138/202, checkpoint `302a424`, LoRA + legacy BM25)

0 unparsed, 0 template echo; accuracy 0.906 on these 138 (base B′ 0.601, base A′ 0.659 on the same keys); alias
0.93 (n=14), absent-skill 1.00 (n=6), certification 1.00 (n=13) **with** the legacy off-target references. No LoRA
no-RAG arm exists yet, so the effect of RAG on the LoRA Matcher is unknown. The fine-tuned model looks robust to
off-target references, so gating may matter less for it than for the base/fallback model.

## 3. Changes (`matcher/knowledge.py`, interface unchanged)

`lookup(req, k=3, job_id=None) -> list[KnowledgeRef]`; `[]` = abstention. Every provider in the module now accepts
`job_id` (the frozen signature); legacy providers ignore it. CV text is never a query (tested with a spy retriever).

| step | rule | addresses |
|---|---|---|
| gate | `category ∈ {certification, language, education}` → `[]`; the prompt is then byte-identical to the no-RAG prompt (tested) | §2.3–2.4: the ESCO ICT subset has no credentials, CEFR levels or degrees |
| query | the requirement's `skill_terms`; the sentence only when there are none | exact skill wording, no template words |
| exact match | ESCO preferred or alternative label equal to the term (case, spacing and hyphens ignored); ambiguous forms prefer the concept whose preferred label it is | alias items keep their concept |
| cut-off | otherwise BM25 (or dense) candidates pass only if one label holds the same content words, any order, no extra word (`max_extra=0`); dense candidates may pass on cosine ≥ τ (exp03 calibrated ESCO threshold 0.8438) | "React" → "react to physical changes or hazards" and "database design" → "design database in the cloud" are rejected |
| one per term | `per_term=1`: neighbouring concepts are dropped | §2.4 absent-skill traps |
| de-dup | by `source_id` and by the 12-character prompt tag (citations stay unambiguous); aliases that repeat the title or another alias up to inflection are dropped | shorter text, unambiguous `[tag]` |
| compact text | `title. Also known as: <distinct aliases, ≤190 chars>. <start of the description>`, ≤ 280 characters for all 1,621 ESCO entries (tested) | §2.1 prompt length; p1 shows 300 chars, so nothing cited is cut |
| citations | `KnowledgeRef.aliases` = the aliases shown, so the validator's term check uses only text the model saw; `rag_refs` = the refs shown, each in full (tested end to end through `Matcher`) | `rag_refs` cite only shown text |
| job posting | when `job_id` is an indexed posting: one passage (the best-matching sentence, ≤ 280 chars) that shares a content word with the requirement, within the k budget | the legacy dense provider added 2 full 300-word chunks |
| Qdrant | `GatedKnowledge(retriever=Retriever(..., model="e5-small", store_path=rag/index), mode="dense", dense_tau=τ)`: the team's persisted Qdrant index provides the candidates, and the same gate and cut-off apply | dense recall for synonyms and French, with the same precision rules |

Name in provenance: `rag.gated.v1+bm25` or `rag.gated.v1+qdrant.<collection>`; each ref's `retrieval` field ends
with `:exact`, `:cutoff` or `:job`. `GatedKnowledge.last_trace` records the gate and term decisions for debugging.

Not changed: `RagKnowledge` (legacy BM25, the B/B′ arm) and `QdrantKnowledge` (legacy dense, the C arm), so the old
arms stay reproducible. Selecting the new provider in production needs `matcher/factory.py` (S2):
`docs/orchestration/requests/s1-factory-hs-rag-gated.md`.

Chunking: ESCO entries are one entry per chunk (no split needed once the text is compacted); job postings keep
the team's structure-aware 300-word chunks for retrieval, and only the shown passage is trimmed to one sentence.

## 4. Retrieval results (RETRIEVAL; `rag_opt/results/retrieval_metrics.md`)

bench-v1 val, 202 requirements, `lookup(req, k=3)` as the Matcher calls it (skill terms present):

| provider | recall@1 on reqs with a concept (n=65) | MRR | abstention precision | abstention recall | off-target refs / req | knowledge chars / req | p95 ms |
|---|---|---|---|---|---|---|---|
| legacy rag.bm25 k=3 | 0.785 | 0.785 | 1.000 | 0.635 | 1.277 | 379 | ~0.4 |
| rag.gated.v1+bm25 | 0.785 | 0.785 | 0.907 | 1.000 | 0.000 | 57 | ~0.4 |

The 0.785 is 51/65 for both: the 14 language requirements have an ESCO language concept that legacy BM25 never
retrieves (off-target only) and that the gate withholds by design (a CEFR level is not in ESCO). On skill and
experience requirements with a concept, recall@1 = 1.0 for both. Gated abstention precision 0.907 = 137/151 (the 14
withheld languages). This set is easy for exact matching (gold labels are the skill terms), which is why two harder
views follow.

Sentence only (skill terms removed; 202 requirements): legacy BM25 injects 2.67 off-target refs / requirement (671
chars); gated with `sentence_min_cover=1.0` keeps recall@1 0.785 on concept requirements with 0.000 off-target
refs, abstention precision 0.907 and abstention recall 1.0. With `sentence_min_cover=0.5` (ablation), abstention recall
drops to 0.912 and off-target refs rise to 0.059.

Team-reviewed natural-language ESCO queries (62 queries: `rag/eval/queries_reviewed.jsonl`, exp02 holdout, exp03
calibration; 36 with a gold concept, 26 "none"; the sealed final test was not read):

| provider | recall@1 | recall@3 | MRR | false abstention | abstention precision | abstention recall | off-target refs / q |
|---|---|---|---|---|---|---|---|
| legacy rag.bm25 k=3 | 0.583 | 0.778 | 0.667 | 0.056 | 0.833 | 0.385 | 1.774 |
| rag.gated.v1+bm25 (default) | 0.278 | 0.278 | 0.278 | 0.722 | 0.500 | 1.000 | 0.000 |
| rag.gated.v1+bm25, sentence_min_cover=0.5 | 0.417 | 0.417 | 0.417 | 0.583 | 0.533 | 0.923 | 0.032 |

On free text the gated BM25 provider trades recall for precision: it abstains on paraphrases ("writing SQL queries
against relational databases") and on French. For the Matcher an abstention is cheap (the prompt equals the no-RAG
prompt) and an off-target reference is costly (§2). Gated BM25 vs legacy BM25 on this set: ΔMRR −0.389
[−0.537, −0.255], McNemar p 0.001. This is a real recall loss on free text, and the reason for the dense variant in
§4.1. Free-text search (`/retrieve`, n8n) keeps using the team's
`Retriever`, which is unchanged. Dense rows: §4.1.

### 4.1 Dense / Qdrant (RETRIEVAL, e5-small under `nice -n 19`)

`rag_opt/results/retrieval_metrics_dense.md` (`nice -n 19 python -m rag_opt.retrieval_eval --dense`; e5-small
index built once in `rag/index`, 1,818 vectors; τ = 0.8438 is the RAG team's calibrated ESCO threshold for
`structure@300 | e5-small`, `rag/experiments/exp03_optimization/thresholds.json`).

| set | provider | recall@1 | recall@3 | MRR | abstention precision | abstention recall | off-target refs / q | p95 ms |
|---|---|---|---|---|---|---|---|---|
| bench val, terms | legacy rag.qdrant.e5-small k=3 | 1.000 | 1.000 | 1.000 | n/a (never abstains) | 0.000 | 2.678 | 158 |
| bench val, terms | rag.gated.v1+qdrant (τ) | 0.785 | 0.785 | 0.785 | 0.880 | 0.752 | 0.168 | 158 |
| bench val, terms | rag.gated.v1+bm25 | 0.785 | 0.785 | 0.785 | 0.907 | 1.000 | 0.000 | < 1 |
| team NL queries | legacy rag.bm25 k=3 | 0.583 | 0.778 | 0.667 | 0.833 | 0.385 | 1.774 | < 1 |
| team NL queries | legacy rag.qdrant.e5-small k=3 | 0.778 | 0.944 | 0.847 | n/a | 0.000 | 2.387 | 171 |
| team NL queries | rag.gated.v1+qdrant (τ) | **0.722** | 0.722 | 0.722 | **0.862** | **0.962** | **0.113** | 156 |
| team NL queries | rag.gated.v1+bm25 | 0.278 | 0.278 | 0.278 | 0.500 | 1.000 | 0.000 | < 1 |

(The legacy dense provider's 1.000 on bench includes the 14 language concepts, which the gate withholds by design.)
Gated Qdrant vs legacy BM25 on the team queries: ΔMRR +0.056 [−0.032, +0.148], hit@1 0 lost / 5 gained, McNemar
p 0.063. Gated BM25 vs legacy BM25 there: ΔMRR −0.389 [−0.537, −0.255], p 0.001 (the precision/recall trade-off).
French (5 queries): legacy dense 0.4 recall@1, gated Qdrant 0.2, BM25 providers ≤ 0.2.

On the Matcher's own requirements (terms mode) the dense τ lets through 34 references outside the gold mapping:
"React → react to physical changes or hazards" (12, wrong), "Node.js → JavaScript" (10, related),
"database design → design database in the cloud" (6, wrong), "agile methodology → Agile development" (6, arguably
right; the bench gold has no concept for this term). τ was calibrated for abstention on question-like queries, not
for single skill terms.

**Recommendation:** use `rag.gated.v1+bm25` for the Matcher (production path, skill terms always present, 0
off-target, no embedding model, < 1 ms). Use `rag.gated.v1+qdrant` for free text without skill terms: it gives the
best precision/recall balance measured here (recall@1 0.722, abstention precision 0.862, off-target 0.113). The
E2E script runs the dense arm with `ARMS="... gated-qdrant"`; a stricter τ for term queries is unmeasured.

## 5. Replay estimate (NOT a model run)

When `rag.gated.v1` abstains (151/202 requirements), the p1 prompt is byte-identical to the no-RAG prompt, so the
recorded A′ answer is an answer to exactly that prompt (subject to the §2.2 noise). For the other 51, the recorded
legacy answer (B′ or C, which had 3 longer references) stands in for the gated prompt (1 shorter reference).

| estimate | Δ macro-F1 vs A′ | 95% CI | McNemar p | alias | absent-skill | certification |
|---|---|---|---|---|---|---|
| gated, else B′ | +0.004 | [−0.014, +0.023] | 1.0 | 0.29 → 0.43 | 0.45 → 0.36 | 0.54 → 0.54 |
| gated, else C | −0.001 | [−0.026, +0.024] | 1.0 | 0.29 → 0.43 | 0.45 → 0.09 | 0.54 → 0.54 |
| legacy BM25 (B′, LIVE recorded) | −0.041 | [−0.083, −0.000] | 0.093 | 0.29 → 0.43 | 0.45 → 0.36 | 0.54 → 0.23 |

The absent-skill rows still use the old 3-reference answers. The gated prompt carries only the concept itself, so
its effect on absent-skill items is unmeasured.

## 6. End-to-end comparison: ready to run in window 1 (NOT RUN)

```bash
# after the orchestrator opens window 1 (the script checks STATUS.md and holds /home/user/hs_queue.lock)
LORA_DIR=<pinned adapter snapshot, see scripts/eval_hs_lora.sh> \
  setsid nohup rag_opt/e2e_compare.sh >> /home/user/s1_e2e.log 2>&1 < /dev/null &
# report only (any time, no model):  python -m rag_opt.e2e_report --root rag_opt/results/e2e
```

- Models, in order: **LoRA** Matcher (Qwen3-4B Q4_K_M + `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora`,
  `scripts/serve_qwen4b_lora.sh`, :8081), then the **base** model (same GGUF, `llama_cpp.server`, :8080). Both
  use the same llama.cpp runtime, `n_ctx 4096`, 4 threads, temperature 0, 192 new tokens, prompt p1 and k = 3.
- Arms per model: `none`, `bm25` (legacy, the B/B′ arm), `gated` (rag.gated.v1+bm25), and `none-repeat` (noise
  floor). Add `ARMS="none bm25 gated gated-qdrant"` for the dense gated arm.
- Each arm runs through the frozen `benchmark/run.py` loop (`rag_opt/run_arm.py` only swaps the provider
  constructor). Each run keeps `config.json`, `predictions.jsonl`, `metrics.json`, `metrics.md` and
  `provenance.json` (provider, ESCO SHA-256, server `/v1/models`, adapter provenance, server and client peak RSS).
- Report (`rag_opt/e2e_report.py`): macro-F1, false-MET, JSON-valid, template echo, UNCERTAIN rate, latency p50/p95,
  peak RSS, refs per requirement and per-tag accuracy, plus paired McNemar and bootstrap 95% CI for every arm vs
  `none`, for `gated` vs `bm25`, and for `none-repeat` vs `none`. The test split is refused.
- Cost estimate (CPU, 4 threads, from the recorded p50 latencies of 10.6–16.4 s): about 40–55 min per arm. That is
  4 arms × 2 models ≈ 6–7 h, with the LoRA model first. If time is short: `MODELS=lora ARMS="none gated bm25" REPEAT_NONE=0`.
- Checked without a model: the window gate refuses in window 0, and the full pipeline runs end to end with MOCK
  backends (`rag/tests/test_rag_opt_scripts.py`). The report reproduces the audit's recorded B′ vs A′ numbers
  exactly (−0.041 [−0.083, −0.000], p 0.093).

Decision rule (pre-registered here, before any live run): `gated` becomes the production default (request to S2)
if, on the LoRA Matcher, its paired CI vs `none` does not lie entirely below 0 and it is not significantly worse
than `bm25` (McNemar p ≥ 0.05 or better point estimate). RAG stays enabled in every case (merge gate 4). If
`gated` is not better than `none` on val, the honest reading is "RAG is safe but not helpful on bench-v1". The
alias and terminology cases it was designed for are 21 of 202 requirements.

## 7. Still unmeasured, and limits

- **No live result of rag.gated.v1 exists.** §4 is retrieval-only and §5 is a replay estimate.
- The LoRA Matcher with no RAG and with gated RAG: not run (window 1). The partial LoRA run is 138/202.
- Absent-skill traps with a single reference (the gated prompt): not measured.
- All design choices were made from **val** error analysis, and the comparison is on val too, so there is a
  selection-on-val risk. Confirmation belongs to the orchestrator's single locked-test run of already-selected
  configurations.
- bench-v1 is synthetic. Its ESCO gold for alias and absent-skill items comes from the generator, so terms-mode
  recall of an exact-match provider is high by construction (hence the sentence-only and team-query views).
- The job-posting path is unit-tested only: the bench jobs are not indexed USAJOBS postings.
- Template echo on the base/fallback model needs the S2/S6 fix (request filed); retrieval can only shorten the prompt.
- French and paraphrased free-text queries: gated BM25 abstains on all 5 French queries (recall@1 0.0; legacy
  BM25 0.2). Gated Qdrant reaches 0.2 and legacy dense 0.4 (§4.1); 5 queries are too few for a conclusion.
- Latency and peak RSS of the Matcher with each arm: measured only in window 1. Retrieval itself takes < 1 ms (BM25).

## 8. Tests

`python -m pytest -q matcher benchmark/tests rag/tests`: **105 passed, 8 skipped** (MOCK / recorded data / BM25
only; the skips are the team's real-model tests `RAG_REAL=1` and one matcher test that expects an external RAG checkout
at `/home/user/ragsrc-latest`). New: `rag/tests/test_gated_knowledge.py` (21: gate, prompt identical to no-RAG,
exact match, absent-skill neighbours dropped, cut-off cases, de-dup and k budget, compact text for all 1,621 entries,
`rag_refs` equal to the refs shown in full, abstention cites nothing, no CV text in queries, job passage, dense τ)
and `rag/tests/test_rag_opt_scripts.py` (4: MOCK arm runs with no leaking patch, test split refused, echo detector,
audit numbers reproduced).

## 9. S1 status (copy; the orchestrator's STATUS.md is not edited)

| session | branch | deliverable | blockers | tests |
|---|---|---|---|---|
| 1 RAG | `session/s1-rag-optimization` | team `rag/` merged; diagnosis (template echo, off-target refs, neighbours); `rag.gated.v1` provider; retrieval metrics (BM25 + dense); replay estimate; window-1 E2E script ready | live E2E (LoRA + base, 4 arms) waits for window 1; factory default needs S2; template-echo fix needs S2/S6 | 105 passed, 8 skipped (MOCK/recorded; no live model) |
