# What the graders get, and where it is

| deliverable (exam brief) | where | status |
|---|---|---|
| n8n workflow JSON | `n8n/hiresignal_v1.json` (main chain, 37 nodes) and `n8n/hiresignal_errors.json` (error workflow, 4 nodes). Both are exported from n8n and cleaned: no credentials, no pinned data. The webhook token is read from the environment (`$env.WEBHOOK_TOKEN`) and is not in the file. | done |
| Repository with install / run instructions | `README.md` (overview, architecture, how to run), `INSTALL.md` (Windows, from zero), `scripts/start_all.ps1` / `scripts/stop_all.ps1` | done; not tested on a clean machine (`INSTALL.md`, last section) |
| Technical report (max 8 pages) | to be written from `docs/FINAL_EVAL.md` (§3 is the one source of numbers) and the component reports: `docs/MULTIMODAL_REPORT.md`, `rag/RAG_REPORT.md`, `docs/BIAS_REPORT.md`, `docs/REPORT_WRITER.md`, `docs/SECURITY_REPORT.md`; figures in `docs/figures/` | sources ready; the report itself is not in the repo yet |
| Prompt library annex | `prompts/PROMPT_LIBRARY.md` (role, technique, failure, fix, before / after per prompt) and the versioned prompts in `prompts/<station>/v<N>.md` | done |
| PowerPoint | to be made from the same sources and `docs/figures/` | not in the repo yet |
| Demo video (max 5 min) | script and inputs: `demo/README.md` (invite PDF, reject PDF, phone photo, with their jobs, confirmed cards and the exact `curl.exe` commands) | inputs ready; the video is not in the repo yet |

**Evidence.** Every number in the docs comes from a result folder under `eval/results/<date>_<name>/` with the config
used. Labels: mock / real-CPU / real-GPU. The figures are rebuilt from those files by `scripts/make_figures.py`.

**Data and licences.** `data/DATA_CARD.md` and `docs/LICENSES.md`. Large or non-redistributable data and the model
files are not in the repo; `docs/PUSH_CHECKLIST.md` lists what is excluded and how to get it back.
