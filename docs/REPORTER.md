# HireSignal Report Writer (S8): deterministic report + tiny SLM text

Package `reporter/`. It consumes the `Pipeline.run()` output dict (`matcher/pipeline.py`) and writes a versioned
report as JSON, self-contained HTML and Markdown. A tiny SLM (Qwen3-0.6B) may write the natural-language parts only;
every SLM sentence passes a fact check, or it is replaced by a deterministic sentence. Each text section names its
writer. The report is decision support, not a hiring decision, and says so at the top and bottom.

```
Pipeline.run() dict
  -> reporter.build      deterministic Report (schema 1.0.0): decisions, evidence + spans, knowledge shown,
                         validator reasons, bias audit, Judge, review flag + reasons, Matcher provenance, disclaimer
  -> reporter.writer     optional SLM pass: executive summary + one note per requirement
                         facts -> Qwen3-0.6B (JSON grammar, greedy, no thinking) -> reporter.slm_validate
                         reject -> one corrective retry (validator reasons fed back) -> reject -> deterministic text
  -> reporter.render     JSON (reporter/json_schemas/Report.schema.json), HTML (escaped, inline CSS, no script), Markdown
```

## Run

```bash
# with the pipeline (writes report.json + report.md as before, plus report.report.json / report.html / report.slm.md)
HS_REPORTER_SLM=on python scripts/run_pipeline.py --case val-000 --out out/val-000
# from a saved pipeline output
HS_REPORTER_SLM=on python -m reporter out/val-000/report.json --out out/val-000 --job-title "..."
# measurement (val only; real LoRA Matcher outputs replayed, real SLM)
flock /home/user/hs_queue.lock python -m reporter.measure --n 25 --out reporter/results/val_replay
# tests
python -m pytest matcher benchmark/tests tests/qa reporter
```

Python API: `reporter.write(out, slm=None | LlamaCppSLM(), job_title=None) -> Report`, `reporter.to_html(rep)`,
`reporter.to_markdown(rep)`, `reporter.write_files(out, folder, ...)`.

## Environment

| variable | default | meaning |
|---|---|---|
| `HS_REPORTER_SLM` | `off` | `off`: deterministic only. `on`: load the SLM; if it cannot be loaded, the report says `unavailable: <reason>` and stays deterministic. `required`: fail if the SLM cannot be loaded |
| `HS_REPORTER_MODEL_PATH` | (HF cache) | path to the GGUF; otherwise the pinned file is looked up in the Hugging Face cache |
| `HS_REPORTER_DOWNLOAD` | unset | `1` allows downloading the pinned GGUF (otherwise cache only, no network) |
| `HS_REPORTER_THREADS` | `4` | llama.cpp CPU threads |
| `HS_REPORTER_TIMEOUT` | `30` | seconds per SLM call; a call over budget is stopped and counts as a failed attempt |
| `HS_REPORTER_MAX_TOKENS` | `160` | max new tokens per section |

The file's sha256 is checked against the pin before use; a mismatch makes the SLM `unavailable`.

## Why a tiny SLM, and what it is allowed to do

The deterministic report is complete on its own. What it lacks is readable prose: a recruiter-facing summary and a
plain sentence per requirement. A 0.6B model is enough to rephrase a handful of verified facts, runs on the same CPU
container as the rest of the pipeline (about 1.2 GB RSS, a few seconds per section), and needs no GPU or hosted API, so
no CV-derived text leaves the machine. Its job is narrow on purpose: it never sees the CV, the knowledge base or the
model explanations; it receives only the verified facts of one section, and it writes no decision, score or evidence
of its own. Whatever it writes is checked, and the checks are strict enough that a fallback is cheaper than a risk.
It is not fine-tuned.

## Model facts (verified 2026-10-16 from the Hugging Face API and the GGUF metadata)

| item | value |
|---|---|
| model | `Qwen/Qwen3-0.6B` @ `c1899de289a04d12100db370d81485cdf75e47ca`, licence Apache-2.0 |
| weights | official `Qwen/Qwen3-0.6B-GGUF` @ `23749fefcc72300e3a2ad315e1317431b06b590a`, file `Qwen3-0.6B-Q8_0.gguf` (the repo's only file), sha256 `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031` |
| architecture | qwen3, 28 layers, hidden 1024, 16 heads / 8 KV heads, context 40960 (run with n_ctx 4096) |
| runtime | llama-cpp-python 0.3.16, in-process, CPU, 4 threads, seed 0 |
| decoding | greedy (temperature 0, top_k 1), JSON-schema grammar per section, max 160 tokens, 30 s budget |
| thinking | disabled. The GGUF's chat template emits `<think>\n\n</think>\n\n` after the assistant header when `enable_thinking=False`; `reporter/slm_prompt.chatml` renders exactly that. `test_slm_real.py` renders the GGUF's own Jinja template with `enable_thinking=False` and checks the strings are equal |

## Prompt design (`reporter/slm_prompt.py`, id `reporter-slm-p1`)

- System prompt: restricted role ("You are not a recruiter"); facts only from the input JSON; no new skills, tools,
  years, numbers, employers, degrees or sources; keep decision words exactly; quotes only verbatim from
  `evidence_quotes`; `not_documented` means "not mentioned", never "lacks"; never recommend, hire, reject, rank or
  judge the person; reply with one JSON object.
- Output schema: `{"note": str}` (10–300 chars, one sentence) or `{"summary": str}` (20–600 chars), enforced by a
  llama.cpp grammar and checked again by the validator.
- Facts per note: requirement text, must/nice, decision, basis, verified evidence quotes, review flag, and for
  UNCERTAIN the pipeline's own plain-language reason (`why_uncertain`). Facts for the summary: the counts
  (all / MET / MISSING / UNCERTAIN / must met / must total / nice total / need review) and each requirement's text,
  kind and decision. No CV text, no RAG text, no model explanation.
- Few-shot: two note examples and one summary example, written from an invented pastry-chef job (no val or test data).
- Retry is corrective: greedy decoding would repeat the same text, so the retry prompt appends the validator's reasons
  (e.g. `count_mismatch:'2 of 2 must-have requirements are MET' but the facts give must-have MET = 1`).
- Provenance: the report records prompt id + sha256 of the full prompt (system, tasks, retry template, shots), the
  model pins, runtime, decoding, and per section: writer, attempts, rejection reasons and the raw rejected outputs.

## Validation (`reporter/slm_validate.py`)

A section is accepted only if all checks pass:

1. JSON: exactly one key of the right name, a string, within the length limits; a note has at most one sentence.
2. Closed vocabulary: every word is a plain function / report word (an explicit list of about 250 words such as
   "the", "CV", "states", "review", "evidence") or occurs (up to simple inflection) in the facts of that section.
   Any skill, tool, employer, degree, certificate or name not in the facts is rejected, without needing a skill list.
   JSON key names (`evidence_quotes`) in the prose are rejected.
3. Numbers: every number, in digits or words (zero–twenty), occurs in the facts. In a summary, each clause is read
   against its subject: "N must-have ... MET", "N of M must-have", "N need human review", "N are MISSING",
   "of N requirements", "no requirements are uncertain"; each count must equal the fact.
4. Quotes: every quoted string is a verbatim (case/space-insensitive) part of an evidence quote or a requirement text.
5. Decisions: a note contains its own decision word and no other; claims are checked too ("is met" on MISSING,
   "not met"/"does not meet" unless the basis is contradicted, "does not mention" unless the basis is not_documented).
   A review claim must agree with the review flag.
6. Verdicts and judgements: hire/hiring, reject, recommend, shortlist, interview, offer, "move forward", ... are always
   rejected; judgement words about the person (suitable, qualified, strong, weak, fit, lacks, expert, ...) are rejected
   unless the word is itself in the facts (e.g. a requirement "Strong communication skills").

Text inside verified quotes is exempt from checks 2, 3 and 6 (it is CV text, e.g. "Hired to engineer ...").

## Fallback

Per section: attempt 1 -> validator -> attempt 2 with feedback -> validator -> deterministic template. An SLM exception
(model missing, crash, timeout) counts as a failed attempt. The fallback is labelled `deterministic_fallback` with its
rejection reasons; the rendered report shows the names of the failed checks only (the raw rejected text, which may
contain the unsupported words, stays in the JSON provenance for audit). A scripted test double is labelled `slm_mock`
and "MOCK, not a model"; it is never labelled `slm`.

## Measured results

RESULTS_PLACEHOLDER

## Tests (`reporter/tests/`)

| file | what |
|---|---|
| `test_render.py` | report validates against the committed JSON Schema (and the schema is up to date); sections come from the pipeline fields; writer labels; disclaimer; no verdict words; HTML/Markdown escaping (`<script>` in CV text and job title); MOCK Matcher labelled; Judge/bias/backend-down fields rendered |
| `test_slm_validate.py` | 21 hallucinated notes (new skill, number, number word, employer, credential, altered quote, verdicts, judgements, wrong decision, "lacks" on not_documented, wrong review claim, JSON key) and 11 hallucinated summaries (wrong counts, wrong totals, false "no review", verdicts, invented number or skill) are all rejected; faithful texts are accepted; malformed JSON rejected |
| `test_fallback.py` | SLM down, timeout, invalid JSON, hallucination in every section -> deterministic fallback after one retry, recorded; corrective retry succeeds and receives the reasons; scripted output labelled MOCK; `HS_REPORTER_SLM` off / unavailable / required |
| `test_slm_real.py` | skipped unless the pinned GGUF is cached: sha256 pin, chat template equality with thinking disabled, every accepted section re-validates |

The pipeline outputs used by the tests are built by the real `Pipeline` with a scripted Matcher on an invented CV
(MOCK, labelled as such).

## Limitations

- The closed vocabulary is conservative: a harmless word outside the list (e.g. "applicant's background") causes a
  fallback. Safer than the reverse; it lowers the share of SLM-written sections.
- The validator checks facts, not tone or completeness: an accepted note can omit the review flag or the basis.
  The deterministic fields (decision, basis, evidence, review reasons) are always shown next to it.
- Paraphrases of quotes are rejected (e.g. an added comma); the model must copy quotes exactly.
- The summary is the hardest section for a 0.6B model (counting); most summary fallbacks are count mismatches.
- The Judge was not run in the measurement (torch could not be installed in this container: the PyTorch wheel index
  is blocked by the proxy); the renderer's Judge fields are covered by tests with a filled Judge result.
- The pipeline output has no job title, requirement category or minimum years; see
  `docs/orchestration/requests/s8-job-context.md`.
- English only. No PDF export (print the HTML from a browser if needed).
