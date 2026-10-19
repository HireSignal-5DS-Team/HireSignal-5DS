# T17 report — Complete RAG technical explanation (documentation only)

Done directly by the Brain (Claude, chat) on 2026-10-19 at the Approver's request; Claude Code was busy with T16.

## Done
- New file: `docs/HIRE_SIGNAL_RAG_COMPLETE_EXPLANATION.md` (9 sections: simple explanation, architecture, when/where RAG
  runs, all experiments with tables, tests, deployment, end-to-end example, status, presentation scripts + 10 Q&A +
  glossary).
- Sources: `rag/RAG_REPORT.md`, `tasks/T09_report.md`, `tasks/T09b_report.md`, `rag/retrieval.py`, `services/api.py`,
  `services/contracts.py`, `services/matcher/*`, `services/judge/judge.py`, `n8n/hiresignal_v1.json`,
  `config/.env.example`, `tests/test_rag.py`, `docs/FINAL_EVAL.md`, `eval/results/2026-10-18_rag_*` and
  `2026-10-18_n8n_e2e_rag/`.
- Captured examples (top-3 per query, P15 e2e refs) were read from saved result files; nothing was re-run.

## Not changed
No code, configuration, dataset, experiment or result file was modified. V1/V2 not touched. No git command.

## Findings worth a fix later (docs only)
- `rag/README.md` says "ESCO + job postings"; the corpus is ESCO only (T09 report). Suggest fixing the one-liner.
