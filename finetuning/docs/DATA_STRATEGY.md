# Qwen3-4B Matcher fine-tuning: project audit, dataset research and plan

Branch `feature/qwen-lora-finetuning`. Written 2026-10-15. **Nothing has been trained yet.** No code in this
document has been run on a Kaggle GPU yet.

## 1. What the Matcher already does

All paths below are on `origin/feature/qwen3-4b-finetune-handoff`. `matcher/` is identical on
`claude/kind-albattani-k7qlt9`. `main` holds only a README.

### Input contracts (`matcher/schemas.py`, Pydantic v2, `extra="forbid"`)

- **`CV`**: `cv_id`, `text`.
  - `text` is the only source of evidence quotes.
  - It may also carry a `structured` dict, which is never used as evidence.
- **`Requirement`**: `req_id`, `text`, `kind`, `category`, `skill_terms`, `min_years`.
  - `kind` is `must` or `nice`.
  - `category` is one of `skill`, `experience`, `education`, `certification`, `language`, `other`.
- **`Job`**: `job_id`, `title`, `requirements[]`.
- **`KnowledgeRef`**: one RAG item.
  - Fields: `source_type` (esco, onet, job or fixture), `source_id`, `title`, `text`, `aliases`, `relevance_score`, `retrieval`.
  - It is used for terminology only, never as candidate evidence.
- The Job Agent contract that feeds this is `contracts/job_requirements.py` on `feature/job-agent`, owned by Ayoub.
  `to_matcher_job()` converts it to `Job`.

### Model output: `ModelAnswer` (`matcher/json_schemas/ModelAnswer.schema.json`)

The model returns one JSON object per requirement:

```json
{"decision": "MET|MISSING|UNCERTAIN", "basis": "supported|contradicted|not_documented|ambiguous",
 "evidence": ["verbatim CV substring", "... max 3"], "explanation": "<= 600 chars"}
```

The allowed decision and basis pairs are:
- MET + supported;
- MISSING + contradicted, with a quote;
- MISSING + not_documented, with `[]`;
- UNCERTAIN + ambiguous.

### Prompt (`matcher/prompt.py`, version `p1`)

- There is one call per requirement.
- The system prompt contains the rules above. It also says that knowledge entries are not evidence, and never to invent anything.
- The user message is built in this order:
  1. the CV;
  2. the requirement line, e.g. `Requirement (must-have, skill) (minimum 3 years): ...`;
  3. `Knowledge (terminology only, not candidate evidence)`, with k=3 references;
  4. `JSON:`.
- `claude/vigilant-albattani-dmn3pk` has an older `p2` prompt on a different dataset. Do not mix it in.

### After the model (`matcher/validate.py`)

Deterministic rules check every answer:
- JSON parse and schema check;
- each quote must be an exact substring of the CV (offsets are kept);
- years are checked against `min_years`;
- decision and basis must be consistent.

The rules can override the decision and set `needs_human_review`. The final output is a `MatchReport`.

### How RAG enters

`Matcher.match_requirement()` calls `knowledge.lookup(req, k=3)`, and the results go into the user message. In the
benchmark this is `RagKnowledge`, BM25 over an ESCO ICT subset. The team RAG service is on
`claude/gracious-fermi-ncuem4`, under `rag/`. Its `POST /knowledge` returns the same `KnowledgeRef` objects from ESCO
skills and USAJOBS postings. The RAG contract forbids sending CV text to it. **Training examples must therefore
include the same knowledge block,** so that the model learns to ignore it as evidence. The "C/D" comparisons below
run both with and without it.

### Current Qwen3-4B baseline

These numbers are on val: synthetic bench-v1, 202 requirements. The model is untuned, served as Q4_K_M GGUF by
llama.cpp on CPU, with greedy decoding and max 192 tokens.

| run | macro-F1 | false-MET | JSON valid | UNCERTAIN P / R | needs review | p50 latency |
|---|---|---|---|---|---|---|
| no RAG (`benchmark/results/qwen3-4b-q4-none-val`, kind-albattani) | 0.634 | 0.9 % | 95.0 % | 0.340 / 0.872 | 78 % | 12.9 s |
| BM25 RAG (`benchmark/results/qwen3-4b-q4-rag-val`) | 0.630 | 0.9 % | 91.6 % | 0.343 / 0.897 | 74 % | 16.4 s |

- Quotes are excellent: 100 % are exact substrings, and 85 % are attributed to the right span.
- The weaknesses are:
  - over-predicting UNCERTAIN;
  - certifications, with 23–38 % accuracy;
  - date ranges, 12.5 %;
  - missing evidence, 28 %;
  - skill aliases without RAG, 29 %.

### Datasets that already exist (`benchmark/data/`, bench-v1, generator `benchmark/make_dataset.py`)

| split | size | status |
|---|---|---|
| train | 150 cases / 681 requirements | synthetic; packaged as `finetuning/data/sft_train.jsonl` (539) + `sft_dev.jsonl` (142) on the handoff branch |
| val | 45 cases / 202 requirements | **never train**; the comparison set |
| test | 45 cases / 199 requirements | **sealed**; not scored yet on bench-v1; only with explicit approval |

**Important.** val and test are synthetic too. A model trained on real CVs can be judged on val, but real-data gains
may not show there. That is why a small real, human-labelled eval split is part of the plan (section 3).

### Existing fine-tuning code (handoff branch, `finetuning/`)

- `train_qlora.py`:
  - NF4 4-bit with double quantisation, fp16;
  - LoRA r16 / α32 on all linear layers;
  - loss on assistant tokens only (prompt labels set to -100);
  - Qwen chat template;
  - checkpoints with resume;
  - best checkpoint chosen by eval loss.
- `eval_val.py` compares base and adapter with the project validator.
- There is also a Kaggle notebook and a bundle script.
- None of it has run on a GPU.
- It reads the generic `{"messages": [...]}` format, so it does not depend on the dataset. **Plan:** copy it into this
  branch's `finetuning/`, crediting the source commit `2b7d42e`, and feed it the new data. The teammate branch stays
  untouched.

## 2. Dataset research (verified 2026-10-15)

The sources were Hugging Face cards and API, GitHub READMEs and official project pages. I checked the licences and
the provenance of the key rows against the source directly. Kaggle licence fields could not be read because the pages
need JavaScript, so they are marked "not verified".

**Headline: no public dataset has real CVs with genuine, human, per-requirement MET/MISSING/UNCERTAIN labels and
evidence spans.** Every resume dataset with per-requirement labels or rationales that I found is LLM-generated or
LLM-labelled.

### Ranked by usefulness

| # | dataset | link | size | real? | labels | licence | role |
|---|---|---|---|---|---|---|---|
| 1 | **Djinni candidate profiles (EN)** | https://huggingface.co/datasets/lang-uk/recruitment-dataset-candidate-profiles-english | 210,250 | real, anonymised IT CVs (Djinni, 2020–23) | metadata only (position, years, English level) | MIT | **main source of real CVs to label** |
| 2 | **Djinni job descriptions (EN)** | https://huggingface.co/datasets/lang-uk/recruitment-dataset-job-descriptions-english | 141,897 | real postings | exp years, keyword, English level | MIT | **real requirements**, paired with the CVs |
| 3 | **ContractNLI** | https://stanfordnlp.github.io/contract-nli/ | 607 NDAs × 17 hypotheses | real, human-labelled | entailed / contradicting / not mentioned **+ evidence spans** | CC BY 4.0 | same structure as the Matcher: teaches "quote or say not documented" |
| 4 | FEVER | https://huggingface.co/datasets/fever/fever | 311,431 train | real (Wikipedia), human | SUPPORTS / REFUTES / NEI + evidence sentences | CC BY-SA 3.0 (+ GPL tag) | three-way label with evidence; ShareAlike |
| 5 | TechWolf skill-extraction graded (House / Tech / TechWolf) | https://huggingface.co/datasets/TechWolf/Skill-extraction-House-graded | 261 queries × 13,891 ESCO skills | real job-ad sentences | 0–4 grade: 4 explicit, 3 implied, 0–1 not mentioned | CC BY 4.0 | maps to supported / ambiguous / not_documented; the "judge" method is not stated, so treat it as **weak** |
| 6 | SkillSpan | https://huggingface.co/datasets/jjzha/skillspan | 11,543 sentences | real postings, human | skill / knowledge spans | CC BY 4.0 | splitting JDs into atomic requirements |
| 7 | Green | https://huggingface.co/datasets/jjzha/green | 9,968 sentences | real UK postings | SKILL / QUALIFICATION / EXPERIENCE / … spans | CC BY 4.0 | requirement `category` typing |
| 8 | TechWolf anonymous working histories | https://huggingface.co/datasets/TechWolf/anonymous-working-histories | 2,164 careers | real, from resumes | ESCO occupation per job | CC BY 4.0 | title / occupation requirements |
| 9 | Vanetik & Kogan vacancy–resume | https://github.com/NataliaVanetik/vacancy-resume-matching-dataset | 65 CVs, 5 vacancies | real, 2 human annotators | whole-CV rankings | not stated | sanity eval only (licence unclear) |
| 10 | SNLI / MultiNLI | https://huggingface.co/datasets/stanfordnlp/snli · https://huggingface.co/datasets/nyu-mll/multi_nli | 550k / 393k | real, crowd | e / n / c | CC BY-SA 4.0 / mixed | label semantics only; no spans |

### Rejected as training gold

These may be used for format bootstrapping at most.

- **netsol/resume-score-details**: it has per-requirement booleans plus justifications, but the card says the JDs
  and the scores were generated by GPT-4o.
- **AzharAli05/Resume-Screening-Dataset**: synthetic. The resumes start "Here's a professional resume for…".
- **med2425/resume-job-fit-merged-v1** (labels by Qwen2.5-32B) and **Divyanandh/resume-matching-dataset-v2**
  (GPT-4o-mini): LLM labels.
- **cnamuangtoun/resume-job-description-fit**: it has no card, no provenance and no licence, and only 642 unique
  resumes. The origin of the labels is unknown.
- **Kaggle snehaanbhawal "Resume Dataset"**, **ResumeAtlas**, **InferencePrince555**: scraped LiveCareer or OCR
  resumes with category labels only. Copyright and PII are doubtful, and the licences are uploader claims.
- **ANLI**: CC BY-NC (non-commercial).
- **TechWolf Synthetic-ESCO-skill-sentences**: synthetic by its own card.

## 3. Recommended strategy

Real data is used for the CVs and the requirements, and human verification is used for the labels:

1. **Main set: Djinni CV × JD, human-labelled.** Pair CVs with JDs that share the same primary keyword. Run
   `prepare_real.py` (to be written) to:
   - scrub residual PII (e-mails, phones, URLs, names) from the CV text;
   - split each JD into 3–8 atomic requirements, setting `kind`, `category` and `min_years`;
   - attach the same BM25 ESCO knowledge block the Matcher uses;
   - write a **review file** in which a human labels decision, basis and exact evidence spans.

   Target: about 150 CV × JD pairs and about 750 requirements, as a minimum viable set. About 300 pairs and
   1,500 requirements is better.

   Labels are only "gold" once a human confirms them. Any pre-label is stored separately and marked `weak`. About 20 %
   of items are double-labelled, and agreement (Cohen's κ) is reported.
2. **Supplementary genuine labels: ContractNLI**, CC BY 4.0. The mapping is:

   | ContractNLI | Matcher |
   |---|---|
   | entailed | MET / supported |
   | contradicting | MISSING / contradicted |
   | not mentioned | MISSING / not_documented |
   | evidence spans | `evidence` |

   This is capped at about 25 % of the training mix so that the model stays in the HR domain.
3. **Optional weak signal: TechWolf graded.** The mapping is 4 → MET, 3 → UNCERTAIN, 0–1 → MISSING. This set is only
   kept if an ablation shows that it helps.
4. **Synthetic bench-v1 train:** at most a minority share (≤ 25 %). It is the only source of the date-range and
   certification patterns the team benchmarks.
5. **Splits** are grouped by CV and by JD, so that no CV or posting appears in both train and dev. A leakage check is
   run against val and test: exact matches plus 6-gram Jaccard, the same as the handoff audit.
6. **Evaluation:**
   - the team's val (202, synthetic), for comparability;
   - a held-out **real, human-labelled** Djinni eval split of about 30 pairs, never trained on.

   The four runs A–D are base/fine-tuned × no-RAG/RAG, with identical settings.

**Cost:** the labelling is the work. At about 45 s per requirement, 750 requirements take about 9–10 hours of human
time. That can be split across teammates.

## 4. Kaggle training plan (summary)

- **Model:** `Qwen/Qwen3-4B-Instruct-2507`, the original safetensors, not GGUF. The base revision is pinned in
  `train_meta.json`.
- **GPU:** prefer **T4** (16 GB). P100 is untested with current bitsandbytes. The notebook prints the GPU and the
  free VRAM before choosing settings. 4-bit Qwen3-4B needs about 3 GB, and LoRA training at 2,048 tokens with batch 1
  should fit in 16 GB. Real CVs are longer than synthetic ones, so `max_len` rises to 2,048, with a fallback to 1,536
  on OOM.
- **Config:**
  - NF4 with double quantisation, fp16 (T4 and P100 have no bf16);
  - LoRA r=16, α=32, dropout 0.05 on q/k/v/o/gate/up/down;
  - lr 2e-4, 3 % warm-up, batch 1 × grad-accum 16, 2–3 epochs;
  - eval every N steps on dev, keeping the best checkpoint by eval loss;
  - seed 13.
- **Loss:** assistant JSON only, with prompt tokens masked to -100.
- **Accept the adapter only if** it beats the untuned base run in the same notebook:
  - macro-F1 is higher on val **and** on the real eval split;
  - false-MET is not higher;
  - JSON validity is not lower.

  Otherwise investigate the cause and report it as a negative result.
- **After training**, upload the adapter to a private HF repo. Its model card records the base revision, the config,
  the data provenance and the metrics. No CV text is uploaded.

## 5. What you must do yourself

1. Verify your Kaggle phone number. This is needed for GPU and Internet in notebooks.
2. Create a Hugging Face account and a fine-grained **write** token. Store it only in Kaggle → Add-ons → Secrets as
   `HF_TOKEN`.
3. Approve the labelling plan, decide who labels, and validate the review file.
