# Job Agent

Job offer → **requirements card** ([`contracts/job_requirements.py`](../../contracts/job_requirements.py)),
read by the Matcher.

**Model:** NuExtract-2.0-2B (NuMind, MIT, built on Qwen2-VL-2B), 4-bit GGUF, 986 MB.
The vision file (`mmproj`) is **not** needed: the agent only sends text.

## How it works

```
job offer ─► NuExtract fills the template ─► parse JSON ─┬─► checks + safe repairs ─► card
                 ▲                                       │
                 └──── unreadable answer: retry once ◄───┘
```

| File | Role |
|---|---|
| `prompts.py` | the template + solved examples per version (`job-v1` … `job-v4`, **`job-v4` active**: requirement sentences by chunk, then one skill-names call per sentence), documented in [`prompts/PROMPT_LIBRARY.md`](../../prompts/PROMPT_LIBRARY.md) |
| `backend.py` | talks to NuExtract (llama.cpp server, vLLM or an API), plus a fake for tests |
| `validate.py` | the guardrails: quotes really in the offer, years, must/nice, skill terms; splits "Java and Spring Boot" into one requirement per skill |
| `agent.py` | the loop: extract → retry if unreadable → check → build the card → flag for review |

**Guardrails.** A quote not found in the offer → requirement dropped as invented.
Wrong years → taken from the quote. "is a plus" marked `must` → corrected to `nice`.
Every change goes into `warnings`. If more than 30% of the proposals were invented,
the card is marked `needs_human_review`.

## Run it on Windows (RTX 4050)

**1. Get llama.cpp** (runs GGUF models, free)
- Go to github.com/ggml-org/llama.cpp → **Releases** → latest release.
- Download the zip whose name contains **`win-cuda`** and **`x64`**, and the matching
  **`cudart-...win-cuda...`** zip. Unzip both into the same folder, e.g. `C:\llama`.

**2. Get the model**
- Go to huggingface.co/numind/NuExtract-2.0-2B-GGUF → **Files**.
- Download **`NuExtract-2.0-2B-Q4_K_M.gguf`** (986 MB) into `C:\llama`.

**3. Start the model server** (PowerShell, leave this window open)

```
cd C:\llama
.\llama-server.exe -m NuExtract-2.0-2B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --port 8080
```

`--jinja` lets the server use NuExtract's own prompt format; `-ngl 99` puts the model on the GPU.
Wait for `server is listening on http://127.0.0.1:8080`.

**4. Run the agent** (a second PowerShell, in the repo, with the venv active)

```
python scripts\run_job_agent.py examples\job_post.example.txt
```

The card is saved in `out\job_post.example.json`.

**If the result looks wrong or empty**, the server may be ignoring the template sent the
official way. Try the fallback that writes the prompt by hand:

```
python scripts\run_job_agent.py examples\job_post.example.txt --mode inline
```

Note which mode works: it goes in the report.

**With Ollama instead of llama.cpp** (what we use on the laptop):

```
$env:HS_NUEXTRACT_MODEL = "hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M"
python scripts\run_job_agent.py examples\job_post.example.txt --base-url http://127.0.0.1:11434/v1 --mode inline
```

Ollama needs `--mode inline`, and a context of 8192 tokens for long job offers
(set once: `[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "8192", "User")`, then restart Ollama).

**Compare prompt versions** (for the prompt library): add `--prompt job-v1` … `--prompt job-v4`
(default: the active version); on the 10 real offers use `scripts/eval_job_agent.py --prompts job-v3 job-v4`.

## Tests

```
python -m pytest -q tests/test_job_agent.py tests/test_job_contract.py
```

They use a fake NuExtract, so they run without the model or a GPU.

## job-q1: the team's Qwen instead of NuExtract

`job-q1` uses the **plain Qwen3-4B-Instruct-2507** that the Matcher already runs
(`config/matcher_models.json` on the release branch), so on a shared machine it adds **no GPU
memory**. It reads the **same settings as the Matcher**: `HS_LLM_BASE_URL`, `HS_LLM_MODEL`,
`HS_LLM_API_KEY` (local llama.cpp or a hosted API, one switch for the whole team).
It never uses the Matcher's LoRA: a model name containing "lora" is refused.

Same pipeline as job-v4 (sections, chunks, filter, checks). Qwen gets **written instructions**
(`prompts.SYSTEM_Q1`) and gives the skill names in the same answer (no second call per sentence).

**On the laptop with Ollama** (the same file as the team's: unsloth Q4_K_M, ~2.5 GB):

```
ollama pull hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M
$env:HS_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
$env:HS_LLM_MODEL = "hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M"
python scripts\run_job_agent.py examples\job_post.example.txt --prompt job-q1
```

**With the team's llama.cpp server** (plain Qwen on port 8080): the defaults already point there.
**With a hosted API**: set the three `HS_LLM_*` variables as for the Matcher. Job offers are
public, so sending them to an API is fine.

**Compare with job-v4 in one run** (each version gets its own model; Ollama swaps them):

```
$env:HS_NUEXTRACT_MODEL = "hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M"
python scripts\eval_job_agent.py --prompts job-v4 job-q1 --base-url http://127.0.0.1:11434/v1 --mode inline --llm-url http://127.0.0.1:11434/v1 --repeat 2 --name v4-vs-q1
```
