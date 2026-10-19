# HireSignal

An AI CV screener for tech and data jobs. An **n8n** workflow runs a chain of small, local agents. They check each job
requirement against **verbatim CV evidence**, and plain code makes the decision: *the LLM judges, code counts*.
Everything runs locally and costs nothing: Qwen3-4B + LoRA on llama.cpp, DeBERTa NLI, qwen2.5vl on Ollama.

Advanced Deep Learning final project (ESPRIT 5DS).

## Architecture (one n8n node per station)

```
Webhook (CV file + job text + optional confirmed requirement card; header X-HireSignal-Token)
 -> 1 Reader          text PDF / DOCX / TXT; photos and scans: Tesseract OCR || qwen2.5vl vision, LATE FUSION in code
 -> 2 Profile         anonymise (code; identity kept apart in private/) -> Bias Auditor guard (masks protected lines)
                      -> parse (Qwen3-4B plain)
 || 3 Job Agent       job text -> must / nice requirements (or the recruiter-confirmed card)
 -> 4 Matcher + RAG   per requirement: ESCO knowledge (dense MiniLM in Qdrant, only when the term is not in the CV)
                      -> Qwen3-4B + Matcher LoRA: MET / MISSING / UNCERTAIN + verbatim quotes (code-verified) + confidence
 -> 6 Judge           DeBERTa NLI: do the quotes support the decision?
 -> 5 Bias Auditor    live identity-swap test when the gate would decide automatically
 -> 8 Outcome gate    plain code: invite / reject / review (target review rate <= 25%)
 -> 7 Report Writer   Qwen3-4B plain writes the recruiter summary + candidate letter; a code fact checker reads it;
                      template fallback
 -> Switch            invite / reject: letter to eval/outbox/ | review: recruiter form -> human decision -> checked letter
```

Station API: FastAPI on `127.0.0.1:8010` (`services/api.py`). Models: llama-server `:8090`, Ollama `:11434`.
n8n: `:5678`.

## Run it

- Install (Windows, from zero): [INSTALL.md](INSTALL.md).
- Start / stop: `scripts\start_all.ps1` / `scripts\stop_all.ps1`.
- Demo (invite PDF, reject PDF, phone photo): [demo/README.md](demo/README.md).
- Tests: `.venv\Scripts\python -m pytest -q`.

## Results and reports

| topic | document |
|---|---|
| final evaluation on the test pairs, and every component's key number | [docs/FINAL_EVAL.md](docs/FINAL_EVAL.md) |
| RAG: corpus, chunking, retrieval benchmark, effect on the Matcher | [rag/RAG_REPORT.md](rag/RAG_REPORT.md) |
| multimodal Reader: OCR vs vision, late vs early fusion | [docs/MULTIMODAL_REPORT.md](docs/MULTIMODAL_REPORT.md) |
| Bias Auditor: counterfactual swap test | [docs/BIAS_REPORT.md](docs/BIAS_REPORT.md) |
| Report Writer: LLM writes, code checks | [docs/REPORT_WRITER.md](docs/REPORT_WRITER.md) |
| security tests | [docs/SECURITY_REPORT.md](docs/SECURITY_REPORT.md) |
| licences of packages and models | [docs/LICENSES.md](docs/LICENSES.md) |
| prompt library (annex) | [prompts/PROMPT_LIBRARY.md](prompts/PROMPT_LIBRARY.md) |
| n8n workflows | [n8n/README.md](n8n/README.md), `n8n/hiresignal_v1.json` |
| task-by-task reports (T01–T13) | `tasks/` |

Measured results live in `eval/results/<date>_<name>/`. Each folder carries the config used, and every result is
labelled real-GPU, real-CPU or mock.

Project rules for the coding agent: [CLAUDE.md](CLAUDE.md).
