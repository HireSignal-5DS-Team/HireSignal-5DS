# Job Agent evaluation

Measures the Job Agent on **10 real job offers** (USAJOBS, public domain) against
**hand-made correct answers** (gold cards, 104 requirements).

| Folder / file | What |
|---|---|
| `offers/` | the 10 job offers, verbatim, with [`SOURCES.md`](offers/SOURCES.md) |
| `gold/` | the correct requirements card for each offer, and [`REVIEW.md`](gold/REVIEW.md) to review them |
| [`ANNOTATION_RULES.md`](ANNOTATION_RULES.md) | what counts as a requirement (and what does not) |
| `results/<name>/` | one evaluation run: `summary.md`, `summary.json`, each card and raw model answer |

## Run it (laptop, Ollama running)

```
$env:HS_NUEXTRACT_MODEL = "hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M"
python scripts\eval_job_agent.py --base-url http://127.0.0.1:11434/v1 --mode inline --repeat 2 --name v1-vs-v2
```

It runs every prompt version (`job-v1`, `job-v2`) on every offer, twice each (`--repeat 2`,
to check the answers are stable), and prints a table ready for the prompt library.
About 10 offers × 2 prompts × 2 repeats = 40 model calls (roughly 10 minutes).

## What is measured

- **Precision**: of the requirements the agent kept, how many are correct.
- **Recall**: of the correct requirements, how many the agent found.
- **F1**: both together.
- On matched requirements: accuracy of `kind` (must/nice), `category`, `min_years`.
- Invented quotes the guardrails dropped, cards flagged for review, latency, stability.

Matching rule: see section 4 of the annotation rules.

## Checks on the gold cards themselves

- `python scripts/check_gold.py`: every quote is exact, every skill term is in its quote.
- `tests/test_job_eval.py`: if the model answered exactly the gold card, the agent's
  guardrails must give back the gold card unchanged. This keeps the code consistent with the
  annotation rules. It already caught two bugs while the gold cards were drafted.

## Limits (for the report)

- The gold cards are drafts by one annotator (with AI assistance) until a second team member
  reviews them (`gold/REVIEW.md`).
- All 10 offers are US federal postings in English: long, formal, many administrative
  conditions. Results may differ on short private-sector or French offers.
