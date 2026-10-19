# Notes — real-data baseline 2026-10-18 (real-GPU; 40 real Djinni CV x job pairs, 280 requirement rows)

Files: `rows.jsonl` (one row per pair x gold requirement: gold, prediction, model decision, verified quotes, review
reasons, label probabilities, latency), `profiles.json` (Reader metadata + anonymised CV + parsed profile per pair; no
identity, no raw text), `jobs.json` (`/job` on J1-J4), `summary.json` (all metrics), `ERRORS.md` (every disagreement,
with a hand-written cause), `logprobs_check.txt`, `config.json`, `run.log`.

- Gold = `gold_decision` (AI pre-labels checked row by row by a teammate, 10/280 changed). Gold quotes are not used
  for scoring. Pair outcomes in `pairs_gold.csv` are NOT human-checked and have 0 invites: the TEMP outcome comparison is
  provisional.
- Requirements come from `requirements_gold.csv` (the labelers' list), not from the Job Agent.
- Confidence: llama-server b11139 `logprobs: true, top_logprobs: 20` in `/v1/chat/completions` (OpenAI form; values are
  the pre-sampling softmax, README line 579 `n_probs`). Probability of each label = its first token (MET / MISS / UNC)
  at the decision position. `logprobs_check.txt`: on 30 bench-v1 items the raw output is identical with and without
  logprobs (30/30), and the argmax label equals the model decision (30/30). Here: present for 280/280 rows.
- Nothing was tuned: no setting was changed after seeing dev or test.
