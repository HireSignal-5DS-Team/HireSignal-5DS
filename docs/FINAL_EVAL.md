# Final evaluation (T13 Part B) — the numbers for the report and the slides

**What was run.** The full production chain, end to end through the n8n webhook (`scripts/n8n_e2e.py --cards`), on
every **test** pair (26) from the original files, plus the 5 labelled photo / scan cases:
- Reader (late fusion for images);
- Profile + Bias Auditor guard;
- recruiter-confirmed requirement cards;
- RAG V6;
- Matcher (Qwen3-4B + LoRA, confidence rule tau 0.72);
- Judge (DeBERTa NLI);
- Bias Auditor live swap;
- T08b gate;
- Report Writer (Qwen3-4B plain, prompt v3, fact checker, template fallback).

**Conditions.** Real-GPU, RTX 4050 6 GB; llama-server, the station API, Ollama and n8n all running. Nothing was
tuned here. Results: `eval/results/2026-10-19_final_eval/` (`final_summary.json`, one `*_result.json` and
`*_execution.json` per run, `run.log`, `vram_poll.txt`).

## 1. Test pairs (26 pairs, 182 requirements, original Djinni text files)

**Requirement level** (vs the human gold labels):

| accuracy | macro-F1 | F1 MET | F1 MISSING | F1 UNCERTAIN | false MET |
|---|---|---|---|---|---|
| 0.753 | **0.644** | 0.771 | 0.870 | 0.291 | 13 |

**Outcome level** (rows = gold, columns = system):

| gold \ system | invite | review | reject |
|---|---|---|---|
| invite (1) | 0 | 1 | 0 |
| review (7) | 0 | 3 | **4** |
| reject (18) | 0 | 0 | 18 |

- Agreement: 21/26.
- **False invites: 0.**
- **False rejects: 4.** Gold review, system reject: the Matcher says MISSING with no doubt on a must-have that the
  labellers found unclear (T08b).
- **Review rate: 15.4%** (target ≤ 25%).

**Report Writer:**
- 20/26 reports were written by the LLM and passed the fact checker; 6/26 fell back to the template (checked by
  construction).
- Every report is fact-checked. The 6 fallbacks are quote edits or letters that named non-missing items.

**Bias Auditor:**
- The live swap ran on the 22 pairs the gate decided automatically. All 22 had an identical Matcher input, so there
  was no LLM re-run, and there were **0 swap flips**.
- Counterfactual set (T11 / T11b): 0 / 832 variants change a decision in production.

**Latency per CV** (wall time, webhook → reply): mean **55.2 s**, max 162.2 s. The first run includes the cold
start: the RAG embedder and the Qdrant index load once, 117 s.

| station (mean / max s) | Reader | Profile | RAG | Match (all requirements) | Judge | Bias | Outcome | Report Writer |
|---|---|---|---|---|---|---|---|---|
| text CV | 0.01 / 0.07 | 25.8 / 69.6 | 4.6 / 117.4 (cold start) | 10.7 / 19.5 | 0.24 / 2.2 | 0.01 | 0.01 | 13.7 / 28.1 |

Peak VRAM: llama-server (Qwen3-4B + LoRA) 3.25 GB + Judge + embedder; the Report Writer adds nothing (same server).

## 2. Photo / scan cases (5 labelled CVs, T10's images through the full chain)

| case | pair | gold | system | reads as |
|---|---|---|---|---|
| close photo `K03_photo.jpg` | P02 | reject | reject | correct |
| close photo `K01_photo.jpg` | P15 | invite | review | safe (no wrong decision) |
| close photo `K02_photo.jpg` | P47 | review | review | correct |
| scan `L04_scan.pdf` (2 pages) | P52 | invite | review | safe |
| hard photo `L05_photo.jpg` | P43 | review | reject | false reject (the digital PDF gives the same reject, T10 Part D) |

Summary of the photo / scan cases:
- requirements: macro-F1 0.570, F1 MET 0.842 / MISSING 0.867 / UNCERTAIN 0.0;
- 0 false invites, 1 false reject;
- Report Writer 5/5 LLM;
- latency per CV mean **188 s**, max 238 s (Reader 128 s mean: OCR || vision on a GPU shared with llama-server).

P15 is a dev pair in the gold split; it is here because it is one of the 5 labelled image cases of T10.

**Privacy check of every run** (the identity values of each CV searched in the n8n execution data):
- 0 everywhere except P52, where a false "URL" value `ci` appeared.
- The anonymiser had read "gitlab-ci" as label "gitlab" plus handle "ci" and masked it ("gitlab-[URL]").
- Fixed after the run: a dash separates a profile label only with spaces around it.
- P52 was re-run with the fix (`p52_rerun_after_label_fix/`): identity found 0/0, decisions and outcome identical
  (review, score 78). The tables above keep the as-run result.

## 3. Every component's key number (baseline → final)

These are the numbers for the report and the slides; the source folder is under `eval/results/`.

| component | measure | baseline | final | source |
|---|---|---|---|---|
| Matcher LoRA | macro-F1, synthetic val (202) | base Qwen3-4B 0.703 | LoRA **0.892** | `2026-10-18_val_full/` |
| Matcher, real pairs | macro-F1, test (40-pair set) | 0.608 (T06) | 0.642 with the confidence rule (T07) | `2026-10-18_real_baseline/`, `2026-10-18_judge_confidence/` |
| Matcher, final chain | macro-F1, test (52-pair gold, 26 test) | – | **0.644** (accuracy 0.753) | `2026-10-19_final_eval/` |
| JSON validity | base model, constrained decoding | 0.900 | **1.000** | `2026-10-18_schema_check/` |
| Judge | false MET flagged for review (test) | 3/11 | **9/11** | `2026-10-18_judge_confidence/` |
| Outcome gate | review rate (test) | 96.2% (T05 TEMP rule) | **15.4%**, 0 false invites, 4 false rejects | `2026-10-18_outcome_gate/`, `2026-10-19_final_eval/` |
| RAG retrieval | dev MRR@10 (Approver-checked golds) | BM25 0.520 | dense MiniLM **0.798** (test 0.425 → 0.712) | `2026-10-18_rag_retrieval_checked/` |
| RAG → Matcher | macro-F1 dev / test | V0 0.651 / 0.661 | V6 0.665 / 0.644 (within noise) | `2026-10-18_rag_matcher/` |
| Reader, images | CER (test, 11 pages) | OCR only 0.381 | late fusion **0.036** (vision 0.023) | `2026-10-18_multimodal/` |
| Reader, images | decision = digital version (10 cases) | OCR 7/10 + 1 wrong reject | late fusion **8/10**, 2 safe reviews, 0 wrong | `2026-10-18_multimodal/chain/` |
| Reader speed | s / photo page (late fusion) | sequential 25.4 | parallel **15.7** (×1.62) | `2026-10-18_reader_parallel/` |
| Anonymiser | false "names" on real CVs | 45 on 40 CVs (T06 before) | **0 on 52** (T11b) | `2026-10-18_anonymiser_fix/`, `2026-10-19_name_overmask/` |
| Bias Auditor | Matcher input identical under identity swaps (832) | 0/832 (T10 anonymiser) | **832/832** | `2026-10-18_bias/`, `2026-10-19_name_overmask/` |
| Bias Auditor | requirement flips under swaps | no anonymiser: 5.4% (name) / 11.4% (origin) on dev | **0** | `2026-10-18_bias/` |
| Report Writer | fact-check pass, first try (dev) | v0 0/28 | **v3 22/28** (test 21/28; fallback 6/28) | `2026-10-19_report_writer/`, `2026-10-19_report_writer_t13/` |
| Job Agent prompt | requirement-sentence F1 vs gold cards (test: 5 USAJOBS + J3, J4) | v1 0.700 (must/nice acc. 0.714) | **v2 0.712** (must/nice acc. 0.865); dev 0.721 → 0.810 | `2026-10-19_job_prompts/` |
| Profile prompt | test CVs cut at the token limit / requirement terms found (34 CVs) | v1 14/34, 28/70 | **v3 0/34, 59/70** (9.6 s vs 29.0 s per CV) | `2026-10-19_profile_prompts/` |
| Security | CV injection: decisions changed vs the same file without injection (16 attacks) | detect + review (T13): 6/16 attacks, 8 decisions | + sentences removed (T14): **0/16**; review 16/16 | `2026-10-19_security/`, `2026-10-19_security_t14/` |

## 4. Known limits (honest list)

- **The Matcher misses doubt (false rejects).** 4 of 26 test pairs are rejected where the labellers wanted a review:
  the Matcher says MISSING with high confidence on a requirement that is unclear in the CV. The gate cannot recover a
  doubt the Matcher does not express. UNCERTAIN F1 is only 0.29.
- **Alias errors.** Requirements written with another name than in the CV ("PL/SQL", "Lakehouse") are still missed.
  Better retrieval (MRR 0.52 → 0.80) did not fix them, because knowledge explains a term but cannot become a CV quote.
- **Small test set.** 26 test pairs (1 gold invite) + 5 image cases: every rate has a wide margin.
- **Synthetic counterfactuals.** The bias test injects one header format and only the signals we chose.
- **Prompt injection the detector misses.** Detected injection sentences are removed before every model (T14: 0
  measured effect on 16 attacks), but the detector is pattern-based; a new wording would reach the Matcher. Gate rule
  0, quote verification and the fact checker remain as further layers.
- **ESCO gaps.** There is no concept for Spark, Kubernetes, AWS, PyTorch, data lake, microservices or AutoML.
- **GPU sharing (6 GB).** llama-server, the Judge, the embedder and the vision model share the GPU. A photo CV takes
  ~3 minutes end to end; a text CV ~1 minute.
- **The Report Writer** falls back to the template for about 1 report in 4 (quote edits, letters naming the wrong
  items). The template is correct but less readable.
- **Job Agent v2** (T15) takes a "Tasks:" duties list of a Djinni post as requirements (test J3). The recruiter
  confirms the card before a run, and the final evaluation used confirmed cards.
- **The final evaluation ran with Profile v1.** In 13 of its 31 results the profile was cut at the token limit
  (`profile:partial_extraction_requires_review`, listed only). Profile v3 (T15) removes this, and it cannot change a
  decision: the Matcher reads the CV text, not the profile, and the gate treats the flag as information only.
