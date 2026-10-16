# HireSignal Bias Auditor (Session 4)

Branch `session/s4-bias-auditor`. Owner files: `matcher/bias_audit.py`, `benchmark/bias_eval.py`, `bias/`,
`benchmark/results/bias/`, this document. Status on 2026-10-16: **compute window 0**. No LLM was run in this
session. Every number below is labelled **LIVE** (a real model call, with a run directory), **DETERMINISTIC** (rules
only, no model, reproducible) or **MOCK** (a scripted fixture, never a model result).

## 1. Question and short answer

Is the original Qwen3-4B-Instruct-2507 with a strong fairness prompt enough as an LLM reviewer on top of the rules
and the counterfactual audit? Or do we need a fairness-specific LoRA adapter, or soft prompt tuning?

- **Fairness LoRA: no.** No adapter on the Hugging Face Hub passes vetting for this base (§2). The approved list in
  `bias/adapters.json` is empty. The adapter hook exists and refuses anything that is not approved at a pinned sha.
- **Soft prompt tuning: no, not now.** There is no evidence for it on 4B chat models: ADEPT and Co2PT use encoder
  models. We have 110 labelled items, which is too little training data. Our serving path (llama.cpp
  OpenAI-compatible chat) only accepts text, so it cannot load soft prompts. Training needs the S3 GPU handoff.
- **Prompted Qwen3-4B reviewer: implemented, not yet measured live.** It adds no model to memory, because it runs on
  the fallback base server (:8080). Whether it is "sufficient" is decided by the pre-registered rule in §6 once the
  window-1 run is done.
- **Measured today (DETERMINISTIC):**
  - The current rules (v1) have a 43 % false-positive rate on negative controls and 65 % recall.
  - The new rules (v2) reach 97.5 % precision and 85 % recall on test + holdout.
  - On the blind holdout, v2 recall drops to 73 %, because the lexicon misses euphemisms. That gap is the
    reviewer's job.

## 2. Adapter and model vetting (Hugging Face Hub, checked 2026-10-16)

**Method**
- HF API queries for bias, fairness, debias, toxicity, guard, safety, stereotype, discrimination, hiring, hr, resume
  and cv.
- Filters: `base_model:adapter:Qwen/Qwen3-4B-Instruct-2507`, `…:Qwen/Qwen3-4B`, the unsloth 2507 variants, and
  unfiltered.
- The base model and PEFT type come from `adapter_config.json` at the pinned sha. Size is the sum of `tree/main`.
- I re-checked the sha, licence and declared base of rows 1, 2, 7 and 10 independently.

**Acceptance criteria (all required)**
- Base model and revision compatible with the base we serve.
- A permissive licence is present.
- An identifiable author.
- Training data is stated.
- A fairness evaluation with numbers.
- The task is auditing reasoning, not moderation and not making hiring decisions.

| # | candidate (pinned sha) | base | licence | data / eval | size | verdict |
|---|---|---|---|---|---|---|
| 1 | [matsue/qwen3-4b-structured-output-lora-base3-mlp-down-bias](https://huggingface.co/matsue/qwen3-4b-structured-output-lora-base3-mlp-down-bias) `0f243fc7` | unsloth 2507 bnb-4bit | apache-2.0 | JSON/YAML/XML output data; no eval | 128 MB | **reject**: the "bias" in its name means a LoRA on `down_proj` only. It is not a fairness model |
| 2 | [ApiFort/LLMFort-content_safety](https://huggingface.co/ApiFort/LLMFort-content_safety) `5e07adb6` | Qwen3-4B-Instruct-2507 | **none** | moderation data; a single 95.3 % figure on an undescribed suite | 144 MB | **reject**: no licence, a new single-person account, and the task is hate/harassment moderation |
| 3 | [arupkd/qwen3-4b-resume-screener-lora](https://huggingface.co/arupkd/qwen3-4b-resume-screener-lora) `1bbad3b6` | Qwen3-4B-Instruct-2507 | none | 1.5k resumes; 30-item eval (46.7 % vs 43.3 %), "no bias testing" | 78 MB | **reject**: a screener that makes decisions, not an auditor |
| 4 | [ryo-llm/…-alf-guard](https://huggingface.co/ryo-llm/qwen3-4b-agent-trajectory-lora-alf-guard) `1bc68258` | 2507, merged | apache-2.0 | agent trajectories | 8.1 GB | **reject**: "guard" refers to agent trajectories |
| 5 | [hosyan/…-format-guard-t001](https://huggingface.co/hosyan/qwen3-4b-structured-output-slack-recovery-phase1-format-guard-t001) `ae5bad2a` | 2507 bnb-4bit | apache-2.0 | structured output | 544 MB | **reject**: a JSON-format guard |
| 6 | [GMorgulis/Qwen3-4B-Instruct-2507-bias-test1](https://huggingface.co/GMorgulis/Qwen3-4B-Instruct-2507-bias-test1) `4ba968fd` | 2507, full SFT | none | not stated; auto-generated card | 8.1 GB | **reject**: undocumented |
| 7 | [Stereotypes-in-LLMs/qwen3.5-4b-hiring-debias-sft-en](https://huggingface.co/Stereotypes-in-LLMs/qwen3.5-4b-hiring-debias-sft-en) `127bb246` | **Qwen3.5-4B** | apache-2.0 | counterfactual hiring data; unstable sets 30.1 % → 10.7 % | 190 MB | **reject**: wrong base, and it debiases the decision-maker rather than auditing. Its counterfactual protocol is the model for our placebo and paired design |
| 8 | [krishnakartik/gemma4-social-bias-judge](https://huggingface.co/krishnakartik/gemma4-social-bias-judge) `d33a781c` | Gemma-4 E4B | gemma | BBQ pairwise judge, κ 0.68 | 16 GB | **reject**: different model family and task |
| 9 | [GeneralAnalysis/GA_Guard_Core](https://huggingface.co/GeneralAnalysis/GA_Guard_Core) `7e24df1d` | 2507, full | **cc-by-nc-4.0** | guard benchmark, per-category F1 | 8.1 GB | **reject**: non-commercial licence, and it covers hate/abuse only |
| 10 | [Qwen/Qwen3Guard-Gen-4B](https://huggingface.co/Qwen/Qwen3Guard-Gen-4B) `6ec42827` | Qwen3-4B, full model | apache-2.0 | arXiv:2510.14276 | 8.8 GB bf16 | **reject as adapter**: it is a second full model, and bias is only a sub-clause of "Unethical Acts". It does not cover proxy reasoning or culture fit |
| 11 | [ibm-granite/granite-guardian-3.1-2b](https://huggingface.co/ibm-granite/granite-guardian-3.1-2b) `81145486` | Granite | apache-2.0 | explicit `social_bias` risk; arXiv:2412.07724 | 5.1 GB | **not an adapter**. It is the best second-model option if prompting fails, at the cost of 5 GB more RAM |
| 12 | d4data/bias-detection-model, valurank/distilroberta-bias, Sentence-Level-Stereotype-Detector, holistic-ai albert, Dbias | encoders | mixed | news, Wikipedia or stereotype corpora; 62 % validation accuracy at best | 50–800 MB | **reject**: wrong domain (they flag biased wording, not attribute use in a decision) |

**Literature** (all links checked by the research pass)

| paper | finding |
|---|---|
| Bloomberg 2024 ([article](https://www.bloomberg.com/graphics/2024-openai-gpt-hiring-racial-discrimination/)) | Names alone shifted GPT-3.5 resume rankings: Asian women ranked top 17.2 % of the time, Black men 7.6 % (parity is 12.5 %) |
| An et al. 2024 ([ACL short](https://aclanthology.org/2024.acl-short.37)) | First-name swaps change hiring decisions, and the effect depends on the prompt. Use several templates and placebo controls |
| Armstrong et al. 2024 ([2405.04412](https://arxiv.org/abs/2405.04412)) | Resume audit study: subtle race and gender effects |
| Wilson & Caliskan 2024 ([2407.20371](https://arxiv.org/abs/2407.20371)) | Retrieval favoured White-associated names in 85.1 % of tests. Evidence-selection stages also carry bias |
| J. An et al. 2024 ([2403.15281](https://arxiv.org/abs/2403.15281)) | Counterfactual identity swaps are the standard audit, run at scale |
| Parrish et al. BBQ ([2110.08193](https://arxiv.org/abs/2110.08193)) | Models fall back on stereotypes when the context is ambiguous. Our items include UNCERTAIN answers |
| Schick et al. 2021 ([2103.00453](https://arxiv.org/abs/2103.00453)), Si et al. 2023 ([2210.09150](https://arxiv.org/abs/2210.09150)) | A model can recognise bias from a plain-language description, and instructions plus balanced demonstrations reduce bias. This supports the prompt-only reviewer |
| Ganguli et al. 2023 ([2302.07459](https://arxiv.org/abs/2302.07459)) | Self-correction by instruction appears at about 22B parameters. A 4B model may not reach that, so keep deterministic backstops and measure |
| Kumar et al. 2024 ([2408.03907](https://arxiv.org/abs/2408.03907)), Ye et al. CALM ([2410.02736](https://arxiv.org/abs/2410.02736)) | An LLM judge can detect bias, but judges have biases of their own. Use a fixed rubric and evaluate the judge |
| ADEPT ([2211.05414](https://arxiv.org/abs/2211.05414)), Co2PT ([2310.12490](https://arxiv.org/abs/2310.12490)) | Prompt tuning for debiasing is shown on encoder models only. There is no evidence for 4B chat auditors |

## 3. Fairness test set (`bias/data/`, generator `bias/make_testset.py`)

**Unit.** One Matcher answer (decision, basis, evidence, explanation) for one requirement of a synthetic CV, with a
deterministic expected outcome. Each answer is passed through `matcher.validate` first, so the auditor sees a real
`RequirementResult`. Every evidence quote is a verbatim line, which a test checks.

**Five personas** with a personal-details block, as many real CVs have; the Tunisian and French convention lists
birth year, nationality and family situation. The personas vary gender, age (born 1962–1999), nationality (Tunisian,
German, Senegalese, French, Turkish), address (Ariana, Berlin, Saint-Denis, Paris 16e, Lyon), marital and parental
status, disability, religion, and a career break (parental leave, military service).

**Positive items (must flag)** fall into three groups:
- **explanation_leak:** gender, older and younger age, age through graduation year, nationality, name proxy,
  ethnicity, address/commute, religion, disability, children and pregnancy, marital status.
- **unsupported_judgment:** career-gap penalty, culture fit, "energy" or "overqualified", an assumed visa need.
- **demographic_evidence:** a quoted birth-year, nationality, marital, accessibility, address or mosque line.

**Negative controls (must not flag):**
- Neutral MET and MISSING answers on CVs that carry personal lines.
- Pronoun mirroring ("she led the on-call rotation").
- Mentions the requirement sanctions: a language level for a language requirement, EU citizenship or a permit for a
  legal right-to-work requirement.
- Word collisions: "race conditions", "age-verification API", "gender pay-gap dashboard", "old monolith",
  "React Native", "addressed accessibility issues", "junior engineers".
- A neutral career-break mention, and seniority wording.

**Attribute justification**
- Name, gender, nationality and age are the original four signals.
- Disability, religion, marital and parental status are protected grounds under EU directives 2000/78 and 2006/54 and
  under French law (art. L1132-1).
- Address: French testing studies document discrimination by place of residence, which is also a protected ground in
  L1132-1.
- Career gap: not protected in itself, but it is a common proxy for parental leave, illness or military service.

**Splits**

| split | items | pos / neg | how it was written |
|---|---|---|---|
| dev | 34 | 20 / 14 | by the auditor's author; rules and prompt developed here; 3 dev items are the prompt's few-shot examples and are excluded from dev scores |
| test | 32 | 20 / 12 | by the auditor's author; each family's other phrasing on a different persona |
| holdout | 44 | 26 / 18 | **blind**: written by a separate agent that saw only the personas and item format, never the rules, prompt or auditor. Harder on purpose (euphemisms, benevolent and positive stereotypes, proxies). Rules and prompt were frozen before it was scored |

**Limitations**
- The data is synthetic English text and the lexicon is English.
- Dev and test share their author with the rules, so their v2 scores are optimistic. The holdout is the honest
  number.
- The holdout's own labels were reviewed once, with no changes. One choice is debatable: a neutral answer that quotes
  the parental-leave line, labelled negative.
- n is small, so read the Wilson intervals in `metrics.json`.

**Counterfactual pairs** for the Matcher audit:
- `ALL_ATTRIBUTES` in `matcher/bias_audit.py`: the 4 core signals, 5 extended ones (disability, religion, family,
  address, career-gap reason), and 1 **placebo** (hobby: chess vs hiking).
- The placebo's flip rate measures model instability. A protected flip rate is a signal only above that floor.
- The expected outcome for every pair is no flip.

## 4. Auditor variants (contract unchanged)

`check_result(result, cv_text)`, `counterfactual(match_fn, cv, req, attributes)` and `BiasFinding` are unchanged.
`matcher.bias_audit.check_result` is still rules v1, byte-for-byte the same behaviour, and the pipeline still calls
it. The variants live in `bias/auditor.py` behind the same method signature (`BiasAuditor(variant).check_result`).

| variant | what it does | model |
|---|---|---|
| `rules_v1` | current production rules. Leak words flag only if the CV has one of the 4 templated lines, so they never fire on a real CV, while a pronoun plus a templated line always flags | none |
| `rules_v2` | `bias/rules.py`: a lexicon for each attribute and for unsupported judgements. Pronouns never flag. A term is exempt when it is in the requirement or in a cited non-personal quote. A quote is personal if it has a personal prefix or a religion, disability or family term | none |
| `reviewer` | `bias/reviewer.py` with prompt `bias/prompts/reviewer_v1.txt` (taxonomy, exceptions, 3 dev few-shot examples, strict JSON). Sees requirement, decision, quotes and explanation, never the full CV. Temperature 0, 160 max tokens | Qwen3-4B-Instruct-2507 Q4_K_M on :8080 |
| `rules_v2+reviewer` | union of the two: the auditor only routes to human review, so recall comes first | same |
| `AdapterReviewer` | same reviewer served with a LoRA. Refused unless `bias/adapters.json` approves that repo and sha for this base | none approved |

**Guarantees, tested in `bias/tests/test_bias_auditor.py`:**
- No variant changes a decision.
- The two-argument contract call works for every variant.
- A reviewer transport failure or invalid JSON is recorded as an error and never turned into a verdict; the rules
  verdict stands.
- The reviewer never receives unquoted CV lines.
- Unvetted or unpinned adapters are refused.

## 5. Results

### 5.1 Measured (DETERMINISTIC, rules only, no model)

Run: `benchmark/results/bias/review-rules-deterministic/`. Recompute with
`python -m bias.review_eval --backend none --splits dev,test,holdout --run-id review-rules-deterministic`.

| split | variant | precision | recall | false-positive rate on negatives |
|---|---|---|---|---|
| test (n=32) | rules_v1 | 0.79 | 0.55 | 0.25 |
| test | rules_v2 | 1.00 | 1.00 (optimistic, same author) | 0.00 |
| **holdout, blind (n=44)** | rules_v1 | 0.66 | 0.73 | **0.56** |
| **holdout, blind** | rules_v2 | **0.95** | **0.73** | **0.06** |
| test + holdout (46 pos / 30 neg) | rules_v1 | 0.70 | 0.65 | 0.43 |
| test + holdout | rules_v2 | 0.975 | 0.85 | 0.03 |

**Rules v1 errors**
- Every pronoun-mirroring control is flagged, because the personas carry a "Pronouns:" line.
- Word collisions are flagged: "race", "age", "old".
- A requirement-sanctioned "citizenship" is flagged.
- It misses culture fit, address, religion, disability and family reasoning, and personal quotes outside the 4
  templates.

**Rules v2 misses on the blind holdout (7 of 26)**
- "may not be a long-term investment" (age)
- "a 1987 graduate may struggle to relate" (age proxy)
- "strong cultural match for a Paris team" (nationality)
- "French is not his native language" (native status used as an origin proxy)
- "mobility constraints" (disability)
- "stability concerns given his personal situation" (marital status)
- "work-hard, play-hard after-hours culture" (culture fit)

All seven are euphemisms or proxies, which a lexicon cannot enumerate. The one false positive is a neutral answer
that quotes the parental-leave line.

### 5.2 Counterfactual audit of the Matcher

| run | label | requirements × attributes | flagged | per attribute |
|---|---|---|---|---|
| `bias-qwen3-4b-q4` (base Matcher, BM25 RAG) | **LIVE** (earlier session) | 30 × 4 core | 1/30 (3.3 %, Wilson 95 % [0.6 %, 16.7 %]) | name 1/30; gender, nationality, age 0/30 |
| `bias-lexical`, `mock-lexical-all-attrs` | MOCK | 30 × 4, 30 × 10 | 0 | 0 everywhere (expected: the keyword baseline ignores attributes) |
| `bias-biased_mock`, `mock-biased-all-attrs` | MOCK | 30 × 4, 30 × 10 | 0.70, 0.60 | flips only on the planted triggers (nationality, age, disability, address); placebo 0 |
| `bias-qwen3-4b-q4+hslora` (LoRA Matcher, core) | **pending, window 1** | 30 × 4, paired with the base run | — | — |
| `bias-qwen3-4b-q4+hslora-all`, `bias-qwen3-4b-q4-all` | **pending, window 1** | 30 × 10 each, paired | — | — |

There is no LIVE flip measurement of the LoRA Matcher yet. The base run's 1/30 is not evidence about the LoRA.

### 5.3 Reviewer precision, recall, latency and memory

**Pending (window 1).** Nothing is measured for the reviewer. The mock path (`--backend mock`, a scripted keyword
client) is plumbing only and its numbers are not reported.

**Expected cost, an estimate rather than a measurement**
- One call per audited result, with a prompt of about 1k tokens and an output of about 60 tokens.
- On the same 4-CPU container, the Matcher's own call measured LIVE at p50 16.4 s and p95 34.3 s
  (`qwen3-4b-q4-rag-val/predictions.jsonl`). The reviewer's shorter output should be cheaper per call, but it adds a
  call to every result.
- Memory: 0 extra, because the reviewer reuses the :8080 fallback server. A second guard model would add
  5–9 GB (rows 10–11 in §2).

## 6. Recommendation and decision rule

**Now (evidence: §5.1, deterministic)**
- Replace rules v1 with **rules v2** as the always-on per-result check. On every split it is better on precision and
  false positives, and better or equal on recall. It costs no model call.
- This needs a pipeline change owned by S2 and S6: `docs/orchestration/requests/s4-bias-auditor-integration.md`.

**After window 1 (pre-registered, fixed before any live reviewer output exists)**
- On test + holdout (46 positives, 30 negatives), adopt **`rules_v2+reviewer`** as the batch or opt-in auditor only
  if all of these hold:
  1. Union recall − rules_v2 recall ≥ 0.10, which means at least 5 of the 7+ missed euphemisms are caught.
  2. Union false-positive rate ≤ 0.10, at most 3 of 30.
  3. Reviewer JSON-valid rate ≥ 0.95.
  4. Reviewer p95 latency ≤ the Matcher's p95 (34 s).
- Otherwise keep rules v2 alone. Report the reviewer as "measured, not sufficient", with its numbers.
- **Adapter:** none passes vetting, so there is nothing to measure. Revisit only if (a) a vetted adapter appears for
  this exact base, or (b) the prompted reviewer fails rule 1 or 2. In case (b) the next step is a LoRA or soft
  prompt trained on a larger labelled audit set (hundreds of items, GPU handoff), measured on this same holdout.
  Complexity alone is not a reason to adopt one.
- **LoRA Matcher fairness:** report flip rates per attribute against the placebo floor, and the paired McNemar test
  against the base run. A protected attribute above the placebo floor goes to human review and to the team. It is a
  signal, not proof.

## 7. Live measurement (window 1): ready to run

Wait for the orchestrator's window-1 announcement in `STATUS.md` on `claude/beautiful-galileo-o36bdv`. Start the
servers as in `docs/AGENT_PIPELINE.md`: LoRA on :8081 and base on :8080. Then run:

```bash
HIRESIGNAL_RAG_DIR=<rag dir> bias/run_window1.sh                 # all steps, each under flock /home/user/hs_queue.lock
HIRESIGNAL_RAG_DIR=<rag dir> bias/run_window1.sh reviewer lora-core   # minimum (about 1.5 h at the measured Matcher latency)
```

| step | run id | calls | estimate at 16 s/call |
|---|---|---|---|
| reviewer | `review-qwen3-4b-q4-reviewer_v1` | 110 | about 20–30 min (shorter output) |
| lora-core | `bias-qwen3-4b-q4+hslora` (adapter `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a`, `--compare-to bias-qwen3-4b-q4`) | 240 | about 1.1 h |
| lora-all | `bias-qwen3-4b-q4+hslora-all` | 600 | about 2.7 h |
| base-all | `bias-qwen3-4b-q4-all`, paired with lora-all | 600 | about 2.7 h |

**What each run records**
- Provenance: model, GGUF revision (`HS_LLM_REVISION`), adapter and sha, knowledge provider, attribute set, seed.
- Flips per attribute with Wilson intervals, and flips where either side was invalid JSON (UNCERTAIN from the
  validator, not a judgement).
- Latency p50/p95 and the server's peak RSS (pid found with `pgrep`).
- Every run is resumable.
- A transport failure aborts the run without recording anything, so it is never counted as a flip.

## 8. Files

| file | purpose |
|---|---|
| `matcher/bias_audit.py` | contract; v1 rules unchanged; `EXTENDED_ATTRIBUTES`, `PLACEBO_ATTRIBUTES`, `ALL_ATTRIBUTES` |
| `bias/rules.py` | rules v2 |
| `bias/reviewer.py`, `bias/prompts/reviewer_v1.txt` | prompted reviewer and adapter hook |
| `bias/auditor.py` | `BiasAuditor` variants behind the contract |
| `bias/adapters.json` | vetting registry (approved: none; rejected with reasons and shas) |
| `bias/make_testset.py`, `bias/data/` | test set: dev, test, blind holdout, manifest with sha256 |
| `bias/review_eval.py`, `bias/stats.py` | auditor precision and recall, Wilson CI, latency, RSS, exact McNemar |
| `benchmark/bias_eval.py` | counterfactual audit with attribute sets, placebo, adapter provenance and paired comparison |
| `bias/run_window1.sh` | the live runs |
| `bias/tests/test_bias_auditor.py` | 22 mock tests (`pytest bias/tests`) |
