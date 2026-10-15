# Qwen3-4B-Instruct-2507 fine-tuning handoff (Kaggle)

Branch `feature/qwen3-4b-finetune-handoff`. This folder is self-contained: data, scripts, notebook, output schema.
**Nothing here has been trained yet.** The training loop was smoke-tested on CPU with a tiny random model only.
The 4-bit GPU path has not been run, because no GPU was available in the cloud build environment.

## 1. What data you may use

| file | split | use |
|---|---|---|
| `data/sft_train.jsonl` | train, case index % 5 ≠ 0 | **training** (539 examples, 120 cases; MET 237 / MISSING 215 / UNCERTAIN 87) |
| `data/sft_dev.jsonl` | train, case index % 5 = 0 | eval loss / early stopping (142 examples, 30 cases) |
| `data/val_prompts.jsonl` | val | **evaluation only** (202 prompts, no targets) |
| sealed test (`benchmark/data/test.jsonl`) | test | **not in this package.** Never train or tune on it |

- **Source.** All three files are built from `benchmark/data/train.jsonl` (bench-v1) by `prepare_data.py`. `val_prompts.jsonl` comes from `val.jsonl`.
- **What the data is.** It is fully synthetic and anonymised by construction: no real person, CV, name, e-mail or employer.
- **Integrity.** sha256 hashes and counts are in `data/manifest.json`. The notebook checks them.
- **Leakage audit** (in `manifest.json`), train against val and against test:
  - 0 exact CV duplicates;
  - 0 shared requirement sentences;
  - 0 shared CV lines;
  - max word 6-gram Jaccard 0.0, max 3-gram Jaccard 0.015, so only generic phrases are shared.
  - The generator partitions every pool by split: skills, ESCO alias pairs, phrasings, section titles.

**Example format.** One line = one requirement:

`{"messages": [system, user, assistant]}`

- The system and user messages are the exact Matcher prompt (`matcher/prompt.py`, version `p1`). The user message includes 3 BM25 ESCO references.
- The assistant message is the gold JSON (schema: `schema/ModelAnswer.schema.json`):

```json
{"decision": "MET|MISSING|UNCERTAIN", "basis": "supported|contradicted|not_documented|ambiguous",
 "evidence": ["exact CV substring"], "explanation": "..."}
```

## 2. Limits of the data (read before training)

- **Size.** Only 539 training examples, template-generated. Expect fast convergence and overfitting to template
  style. The adapter may not transfer to real CVs. Keep 2 epochs maximum and watch `eval_loss` on `sft_dev`.
- **Explanations.** Gold explanations are one fixed sentence per decision/basis, because the generator stores no
  rationales. The adapter will learn decisions, basis and verbatim quotes, not explanation quality.
- **Label imbalance.** UNCERTAIN is the minority class (16 %). The untuned Qwen3-4B already over-predicts it
  (UNCERTAIN precision 0.343 on val), so fine-tuning should mainly help calibrate that.
- **Real data.** None exists that is approved for training. Using real CVs would need an anonymised, consented and
  labelled set (per-requirement gold decisions with verbatim evidence). The team does not have one, and none has been
  invented here.

## 3. Kaggle steps

1. In the repo: `python -m finetuning.make_bundle`. This creates `finetuning/dist/hiresignal_finetune_bundle.zip`
   (225 KB, no test split).
2. Kaggle → Datasets → New Dataset → upload the zip. Name it `hiresignal-finetune` and set it to **Private**.
3. Kaggle → New Notebook → File → Import notebook → `finetuning/kaggle_qwen3_4b_qlora.ipynb`.
   - Add the dataset.
   - Settings: **GPU T4 x2** (or P100), **Internet ON**.
4. Run all cells in order:
   1. integrity check;
   2. **baseline eval of the untuned model**, about 15–25 min;
   3. QLoRA training, about 30–60 min;
   4. adapter eval, about 15–25 min;
   5. comparison print;
   6. zips.

   These times are estimates, not measured.
5. Download `results.zip` (adapter), `eval_results.zip` and `train_meta.json`. Send them to the team or push them to
   your own branch. Do **not** commit the adapter weights to `main`.

**Training config** (`train_qlora.py` defaults):
- base: 4-bit NF4 with double quantisation, fp16 compute;
- LoRA: r=16, alpha=32, dropout 0.05 on q/k/v/o/gate/up/down;
- optimiser: lr 2e-4, linear schedule with 3 % warm-up, batch 1 × grad-accum 16, 2 epochs, paged AdamW 8-bit;
- gradient checkpointing; max length 1024 (no truncation: longer examples are skipped and counted);
- checkpoint every 20 steps; the best checkpoint by `eval_loss` is kept;
- re-running resumes from the last checkpoint.

## 4. How to judge the result (pre-registered)

**Keep the adapter only if**, on the 202 val requirements and under identical conditions (same 4-bit load, prompt,
greedy decoding, `max_new_tokens=192`, validator), it beats the **untuned base run in the same notebook**:
- macro-F1 is higher;
- false-MET rate is not higher.

**Reference number.** The team's current number is untuned Qwen3-4B Q4_K_M through llama.cpp on CPU: macro-F1 0.630,
false-MET 0.9 %, JSON valid 91.6 % (`benchmark/results/qwen3-4b-q4-rag-val`). This is a different quantisation and
runtime, so compare against the Kaggle base run, not against this number.

**Sealed test split:** run it once, by the team, after the choice is made.

## 5. Files

| file | role |
|---|---|
| `prepare_data.py` | rebuilds `data/` from the train split, refuses test, writes the leakage audit |
| `train_qlora.py` | QLoRA trainer (train/dev files only) |
| `eval_val.py` | base vs adapter on val with the project's validator and metrics |
| `make_bundle.py` | private Kaggle dataset zip (excludes test) |
| `kaggle_qwen3_4b_qlora.ipynb` | the notebook |
| `schema/ModelAnswer.schema.json` | required output schema |
