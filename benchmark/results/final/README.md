# Final locked-test run (bench-v1 test, 199 requirements): status and resume guide

**Status: PARTIAL.** Stopped on purpose on 2026-10-16 at 16:04:44Z (owner decision: stop Matcher benchmarking and
focus on the Judge and Report Writer). The stop came right after a completed row; every file ends on a whole line.

| arm (LIVE, llama.cpp 0.3.16, Q4_K_M @a06e946b, prompt p1, k = 3) | rows | status |
|---|---|---|
| `lora__gated`: Qwen3-4B + LoRA `0b6925b1` + `rag.gated.v1` (headline config) | 199/199 | complete |
| `lora__none`: same LoRA, no RAG | 199/199 | complete |
| `base__gated`: base Qwen3-4B, no adapter, `rag.gated.v1` | **173/199** | **PARTIAL, do not report as a test result** |
| full-pipeline check on test-000..002 | — | not run |

Checks done at stop: every arm has unique `(case_id, req_id)` keys in exact test-file order, with no partial line.
The LoRA arms are byte-identical to their pre-resume checksums. `SHA256SUMS` covers every file here (the original
copy is in `/home/user/hs_final_run/` in the orchestrator container).

Code: every arm ran pipeline code at commit `852daa4`: validator v2 as pre-registered, **before** the QA-031/QA-032
fixes. The pre-registered plan is in `docs/orchestration/FINAL_RUN_PLAN.md` (`a1f7f6d`).

Incident (disclosed): `base__gated` rows 37–104 were lost on the first attempt (a `git stash`/`pop` in the worktree
replaced the predictions file under the running writer), and then the container restarted. They were recomputed on
resume from a detached worktree pinned to `852daa4`. Only the 36 rows written before the incident were kept.

## Results of the complete arms (LIVE, test, 199 requirements)

| arm | macro-F1 pre-registered (v2 @ `852daa4`) | false-MET | v1 replay (`4f38c97^`) | fixed v2 replay (**POST-HOC**, `309a33f`) |
|---|---|---|---|---|
| lora__gated | 0.678 | 0.131 (14) | 0.862 | 0.862 |
| lora__none | 0.681 | 0.121 (13) | 0.866 | 0.866 |

- The pre-registered numbers are the official ones. QA-031 (a validator bug found by the pre-registered v1/v2 replay)
  moved 36 correct METs per arm to UNCERTAIN. The post-hoc fix was made after seeing test data, so its numbers are
  labelled as such.
- Every false MET (14 / 13) is a `rag_suggests_absent_skill` item, flagged for human review
  (`semantic_inference_no_term_in_quote`); none is an unreviewed MET.
- The paired comparisons, and the base vs LoRA comparison on test, were **not run**.

## Resume (only with the owner's approval; costs about 8 min of CPU for 26 rows, plus the pipeline check)

```bash
cd <detached worktree at 852daa4, with scripts/final_run.sh from cb9c94e>
HS_FINAL_OUT=/home/user/hs_final_run setsid nohup scripts/final_run.sh >> /home/user/hs_final_run/run.log 2>&1 < /dev/null &
```
Finished arms are skipped (metrics.json present), and `base__gated` resumes at row 174. Keep the output outside every
git worktree. Never stash, checkout or reset over a live output path.
