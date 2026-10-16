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
5. **LIVE (window 1, §6.1), LoRA Matcher, val 202:** `rag.gated.v1` vs no-RAG Δ macro-F1 **−0.005 [−0.028, +0.014]**
   (McNemar 2/2, p 1.0); vs a same-container no-RAG repeat −0.002 [−0.028, +0.020]. The run-to-run noise floor
   (no-RAG vs its repeat) is −0.003. Legacy BM25 vs no-RAG is −0.011 [−0.047, +0.021] (4/4). Gated keeps false-MET at
   the no-RAG level (0.026; legacy BM25 0.034) and raises alias accuracy 0.81 → 0.90, with 0 template echoes. None of
   these differences is significant. The honest reading: on the LoRA Matcher, gated RAG is **safe (within noise)**,
   removes BM25's false-MET increase and helps aliases, but it does **not** raise macro-F1 measurably on bench-v1 val.
   It meets the pre-registered rule, so the recommendation is `HS_RAG=gated` as the production default (adopted by
   the orchestrator, integration `e27c461`).
6. **The replay estimates did not hold live.** For the LoRA Matcher the replay predicted gated vs no-RAG +0.012
   [0.000, +0.028]; the live run measured **−0.005 [−0.028, +0.014]**, within the noise floor (−0.003). On the LoRA
   Matcher RAG's measured value is **not macro-F1**. It is (a) alias handling (0.81 → 0.90) and (b) a lower human-review
   load: review rate 0.663 → 0.589, −7.4 points [−11.4, −4.0], McNemar 15/0, p = 0.0001, under validator v1 and v2.
   All 15 dropped reviews are on correct decisions (§6.1).

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

**Outcome (window 1):** these estimates are for the base model. The same replay method on the LoRA Matcher predicted
+0.012 [0.000, +0.028]; the live run gave −0.005 [−0.028, +0.014] (§6.1). The estimate did **not** hold. It assumed
the gated prompt (1 short reference) behaves like the legacy prompt (3 references) on the 51 requirements with a
reference, and that assumption failed on 2 of them (val-021, val-028). The method stays useful for bounding the
effect of abstentions, which reproduced exactly (151/151 byte-identical), and not for predicting the effect of
the references that are injected.

## 6. End-to-end comparison (prepared in window 0, run in window 1: results in §6.1)

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

### 6.1 LIVE results, window 1 (LoRA Matcher; `rag_opt/results/e2e/e2e_report.md`)

Serving: this container reproduced the evaluation's LoRA serving. It ran llama-cpp-python 0.3.16 `llama_cpp.server`
with unsloth GGUF @a06e946b Q4_K_M, adapter `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b`
converted with the vendored `convert_lora_to_gguf.py` (f16, sha256 `083dc860…`), `n_ctx 4096`, 4 threads,
temperature 0, 192 tokens, prompt p1, validator v1. A spot check on 9 requirements gave byte-identical raw outputs to
the evaluation's run, so the evaluation's `none` and `bm25` arms (`claude/kind-albattani-k7qlt9` @ `46d24e1`) are
reused (labelled REUSED in `provenance.json`). Only `gated` and `none-repeat` were run here.

| arm | source | macro-F1 | false-MET | JSON valid | UNCERTAIN | alias acc. (n=21) | refs / req | prompt tokens |
|---|---|---|---|---|---|---|---|---|
| none | LIVE, reused (eval) | 0.908 | 0.026 | 1.000 | 0.178 | 0.81 | 0 | 315 |
| bm25 (legacy) | LIVE, reused (eval) | 0.897 | 0.034 | 1.000 | 0.153 | 0.95 | 1.53 | 401 |
| gated (rag.gated.v1+bm25) | LIVE, S1 | 0.903 | 0.026 | 1.000 | 0.178 | 0.90 | 0.25 | 327 |
| none-repeat | LIVE, S1 | 0.905 | 0.026 | 1.000 | 0.188 | 0.76 | 0 | 315 |

| comparison (paired, 202) | Δ macro-F1 | 95% CI | base-only / cand-only correct | McNemar p |
|---|---|---|---|---|
| none-repeat vs none (noise floor) | −0.003 | [−0.024, +0.018] | 2 / 1 | 1.0 |
| bm25 vs none | −0.011 | [−0.047, +0.021] | 4 / 4 | 1.0 |
| gated vs none | −0.005 | [−0.028, +0.014] | 2 / 2 | 1.0 |
| gated vs none-repeat (same container) | −0.002 | [−0.028, +0.020] | 2 / 3 | 1.0 |
| gated vs bm25 | +0.006 | [−0.032, +0.045] | 4 / 4 | 1.0 |

Per requirement:
- **Gated abstentions:** gated abstained on 151 requirements. All 151 raw outputs are byte-identical to `none-repeat`
  (150/151 to the evaluation's `none`), so the gate is exactly neutral where it abstains.
- **BM25's four losses vs no-RAG:** all are off-target references that gated does not inject: React → "react to
  physical changes or hazards" (×2) and scikit-learn (×2). Gated answers these like no-RAG.
- **Gains vs no-RAG:** the alias items Oracle Warehouse Builder (val-002) and OWASP ZAP (val-018).
- **Losses vs no-RAG:** val-021 ("Angular: 2 years", gold UNCERTAIN; with the Angular concept the model said
  MISSING) and val-006 (FastAPI, identical prompt to no-RAG, so this is server noise).
- **Alias not recovered:** val-028 (Oracle Warehouse Builder; legacy BM25 got it with 3 references, gated with 1
  did not).

Latency (same container, same server): mean 14.0 s gated vs 13.8 s none-repeat (+2 %); on the 51 requirements
with a reference, 15.1 s vs 13.3 s. Server peak RSS 4.24 GB in both arms. (The evaluation's own p50 of 8.9 s ran in a
different container, so latency is compared only within this container.)

Validator v2 (integration `4f38c97`, trial merge in a worktree; replay of the saved raw outputs with each arm's own
references, `rag_opt/replay_validator.py`, `rag_opt/results/e2e/replay_validator_v{1,2}.md`). The v1 replay
reproduces every saved decision (0 changes). Under v2, false-MET is 0.000 in every arm. Macro-F1 is none 0.929,
none-repeat 0.925, bm25 0.926, gated 0.924; gated vs none −0.005 [−0.027, +0.014]; bm25 vs none −0.003
[−0.033, +0.026]. Nothing is significant.

**Human-review load** (paired, same 202 items; `rag_opt/review_rate.py`, `rag_opt/results/e2e/review_rate_v{1,2}.md`):

| comparison | review rate | Δ | 95% CI | reviewed only base / only cand | McNemar p | dropped reviews: correct / wrong |
|---|---|---|---|---|---|---|
| gated vs none (v1) | 0.663 → 0.589 | −0.074 | [−0.114, −0.040] | 15 / 0 | 0.0001 | 15 / 0 |
| gated vs none-repeat (v1) | 0.658 → 0.589 | −0.069 | [−0.104, −0.035] | 14 / 0 | 0.0001 | 14 / 0 |
| bm25 vs none (v1) | 0.663 → 0.574 | −0.089 | [−0.134, −0.050] | 18 / 0 | < 0.0001 | 15 / 3 |
| none-repeat vs none (v1, noise) | 0.663 → 0.658 | −0.005 | [−0.015, +0.000] | 1 / 0 | 1.0 | 0 / 1 |
| gated vs none (v2) | 0.668 → 0.594 | −0.074 | [−0.114, −0.040] | 15 / 0 | 0.0001 | 15 / 0 |
| bm25 vs none (v2) | 0.668 → 0.584 | −0.084 | [−0.124, −0.049] | 17 / 0 | < 0.0001 | 15 / 2 |

Mechanism: the main change is the validator reason `semantic_inference_no_term_in_quote` (−13). When the model
quotes a CV line that names the skill by an ESCO alias it was shown ("Zed Attack Proxy" for OWASP ZAP), the validator
counts the alias as a requirement term and drops the flag. This is a validator rule acting on shown, verified ESCO
aliases, not a model change. Gated drops reviews only on correct decisions (15/0). Legacy BM25 drops 3 reviews on
decisions that are wrong, because its off-target references supply "terms" for unrelated concepts. The reduction
is significant, but its value depends on the validator rule: it is review load saved, not accuracy gained.

**Decision (pre-registered rule above):** gated's CI vs none is not entirely below 0, and gated is not worse than
bm25 (+0.006, p 1.0) → recommend `HS_RAG=gated` as the production default. That RAG "helps" is **not** shown on this
benchmark: macro-F1 is unchanged within noise. What is shown: no off-target knowledge, no false-MET increase
(v1), alias accuracy +0.09/+0.14 vs the two no-RAG runs, and +2 % latency, while legacy BM25 adds +27 % prompt tokens (p50 latency +48 % in the evaluation's container)
Confirmation on the locked test split is the orchestrator's call.

BASE_LIVE_PLACEHOLDER

## 7. Still unmeasured, and limits

- LIVE results exist for the LoRA Matcher only on val (§6.1). The locked test split is not run.
- The base-model E2E rows are in §6.1 only once their arms finish (see that section).
- Constrained JSON decoding (S2's `HS_JSON_SCHEMA`) combined with RAG on the base model is not measured.
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

## 7.1 QA-023 (S1): answer

QA-023 asks that the BM25 provider drop hits that share only a generic token ("Apache Maven" for "Apache Kafka").
The proposed fix, a score ratio ≥ 0.5 × the top hit, was measured on the retrieval benchmark (bench-v1 val, terms
mode). It barely helps: off-target refs per requirement go from 1.28 to 1.19 (0.84 at ratio 0.7, 0.52 at 0.9). It
cannot abstain, because the top hit always passes, and on the team queries recall@3 falls from 0.778 to 0.750 (0.639
at 0.9). The production provider is now `rag.gated.v1` (`HS_RAG=gated`, integration `e27c461`). It solves the case
by construction: a candidate needs a label with the same content words, so "Apache Kafka" never matches "Apache
Maven" (0 off-target refs; test `rag/tests/test_gated_knowledge.py::test_qa023_shared_generic_token_is_not_relevance`).
Legacy `RagKnowledge` stays unchanged on purpose: it is the reproducible "old BM25" arm of every recorded comparison
(B, B′, eval LoRA+BM25). Proposed status: **fixed in the production provider; won't fix in the legacy arm**. The
QA test should target the default provider (S5's file).

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
