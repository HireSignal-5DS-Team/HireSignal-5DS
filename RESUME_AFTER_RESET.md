# Resume the Matcher benchmark (if the cloud session or container expired)

Results are committed and pushed to `claude/kind-albattani-k7qlt9` after every model
(`benchmark/results/<run-id>/`). A run without `metrics.json` is unfinished. Its `predictions.jsonl` holds the
completed requirements, and re-running the same command continues from there.

## In a new cloud session (Linux)

```bash
git fetch origin claude/kind-albattani-k7qlt9 && git checkout claude/kind-albattani-k7qlt9 && git pull
python3 -m venv /home/user/venv && /home/user/venv/bin/pip install -r requirements-matcher.txt
# RAG code, read-only (no merge):
mkdir -p /tmp/ragsrc && git archive origin/claude/gracious-fermi-ncuem4 rag | tar -x -C /tmp/ragsrc
export HIRESIGNAL_RAG_DIR=/tmp/ragsrc/rag HF_HOME=/home/user/hf
# model cache (needs huggingface.co + *.hf.co); same pinned revisions as the runs:
/home/user/venv/bin/python - <<'EOF'
from huggingface_hub import snapshot_download as d
for m, r in [("Qwen/Qwen2.5-0.5B-Instruct","7ae557604adf67be50417f59c2c2f167def9a775"),
             ("Kus-hal/resume-screener-lora","e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6"),
             ("Qwen/Qwen3-0.6B","c1899de289a04d12100db370d81485cdf75e47ca"),
             ("HuggingFaceTB/SmolLM2-360M-Instruct","a10cc1512eabd3dde888204e902eca88bddb4951"),
             ("HuggingFaceTB/SmolLM2-135M-Instruct","12fd25f77366fa6b3b4b768ec3050bf629380bac"),
             ("google/flan-t5-small","0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab"),
             ("HumayunShahzad123/resume-scorer-t5-small","209038761d88a42857749fd2cddcac4add3cdc81"),
             ("Zerflyne/FERMI-0.8B","d21fa5400ff181083f5f8a07d82e6b8097f9cbc8"),
             ("Qwen/Qwen3.5-0.8B","2fc06364715b967f1860aea9cf38778875588b17")]:
    d(m, revision=r, allow_patterns=["*.json","*.safetensors","*.txt","*.jinja","spiece.model","merges.txt","vocab.json",
                                     "checkpoints/final/*","fermi/*"])
EOF
HIRESIGNAL_RAG_DIR=/tmp/ragsrc/rag setsid nohup scripts/continue_benchmark.sh 0 > benchmark/results/continue.log 2>&1 &
```

Then the Kus-hal adapter study (it waits for `continue_benchmark.sh` to finish, never runs two models at once):

```bash
HIRESIGNAL_RAG_DIR=/tmp/ragsrc/rag setsid nohup scripts/kushal_study.sh > benchmark/results/kushal_study.log 2>&1 < /dev/null &
```

`continue_benchmark.sh` skips every run that already has `metrics.json`. It commits and pushes after each model,
and then writes `benchmark/results/CONSOLIDATED_val.md`.

## On the Windows laptop instead

Follow `docs/WINDOWS_LOCAL_BENCHMARK.md`. GPU runs get their own run ids (suffix `-cuda`), so they never mix
with the CPU predictions.

## After all runs

```bash
python -m benchmark.consolidate --split val     # consolidated table
python -m pytest -q matcher benchmark finetune  # tests
```

Then fill §6 of `docs/MATCHER_REPORT.md` from `benchmark/results/CONSOLIDATED_val.md`. Pick the model on val
only. The locked test split is for a single confirmation run of the selected configuration.

## Status at hand-off (2026-10-15 ~09:45 UTC)

| work | state |
|---|---|
| lexical / mock baselines, Qwen2.5-0.5B, Qwen2.5-0.5B + Kus-hal (val) | done, pushed |
| post-hoc `schema_repair` adapter on Kus-hal and Qwen2.5 raw outputs | done, pushed (`*__schema_repair` runs) |
| Qwen3-0.6B, SmolLM2-360M | running / queued: original queue, then `continue_benchmark.sh` |
| SmolLM2-135M, FLAN-T5-small, resume-scorer-t5, FERMI-0.8B, Qwen3.5-0.8B | queued in `continue_benchmark.sh` |
| Kus-hal study: native prompt (+ `kushal_native` adapter), constrained JSON, one-shot, and the same three on the Qwen2.5 base | queued in `scripts/kushal_study.sh` |
| `docs/MATCHER_REPORT.md` §6 results, final recommendation | not written yet: fill from `benchmark/results/CONSOLIDATED_val.md` |
| `gw0/jobfit-model` | not runnable (ONNX-only typed scorer, fixed 17 questions); documented, its base is benchmarked |

Logs in the original container: `/home/user/continue.log`, `/home/user/kushal_study.log`.
