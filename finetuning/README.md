# Qwen3-4B Matcher fine-tuning (real data)

Branch `feature/qwen-lora-finetuning`.

- This folder is the only place this work lives.
- It reads, but never changes, the Matcher code (`feature/qwen3-4b-finetune-handoff@2b7d42e`) and the RAG code
  (`claude/gracious-fermi-ncuem4`).
- Background, dataset research and the plan are in [docs/DATA_STRATEGY.md](docs/DATA_STRATEGY.md).

**Status:** the pipeline is tested end to end on fake labels, and the notebook cells parse. Nothing has run on a
Kaggle GPU yet, and nothing has been trained.

## Pipeline

| step | script | output (outside git: holds CV text) |
|---|---|---|
| 1. sample real pairs | `sample_djinni.py` | `djinni_review.xlsx` (150 pairs, 876 candidate requirements) |
| 2. **humans label** | Excel | labelled copies of `djinni_review.xlsx` |
| 3. support set | `contractnli_to_sft.py` | `contractnli_sft.jsonl` (7,069 examples from ContractNLI train) |
| 4. build data | `build_real.py` | `sft_train/dev.jsonl`, `eval/*`, `manifest.json`, `label_errors.csv` |
| 5. bundle | `make_bundle.py` | zip for a **private** Kaggle dataset |
| 6. train + evaluate | `kaggle_qwen3_4b_qlora.ipynb` (`train_qlora.py`, `eval_matcher.py`) | adapter, A–D metrics |

## How to label (step 2)

1. Open `djinni_review.xlsx`. For each `pair_id`, read the CV and the job on the **pairs** sheet.
2. On the **requirements** sheet, set `keep_requirement`:
   - `yes` to keep the row as it is;
   - `edit` after fixing the text, the kind or the category in place;
   - `no` to drop the row, for example when it is vague, not checkable, or a duty rather than a requirement.
3. Choose a `decision` and `basis` with the dropdowns. Only these pairs are valid:

   | decision | basis | when |
   |---|---|---|
   | MET | supported | the CV clearly shows it |
   | MISSING | contradicted | the CV shows it is not met (e.g. 2 years when 5 are required) |
   | MISSING | not_documented | the CV says nothing about it |
   | UNCERTAIN | ambiguous | partial, implied, or the duration cannot be confirmed |

4. Fill `evidence` with 1–3 pieces copied **character for character** from `cv_text`, separated by ` || `.
   - Leave it empty for `not_documented`.
   - Do not quote the job text or the metadata columns.
5. Fill `explanation` with one short sentence, and `labeller` with your initials.
6. If you find contact details or a real name in the CV, write `PII` in `notes`.
7. **Double labelling:** about 20 % of the pairs (e.g. `dj-001`…`dj-030`) should be labelled by a second person in
   their own copy of the file. `build_real.py` reports Cohen's kappa and drops any requirement where the two
   labellers disagree.
8. Run step 4. Fix every row listed in `label_errors.csv`, then run it again until it reports 0 errors.

**Budget:** about 45 s per requirement, so 876 requirements take about 11 hours. That time can be split by
`keyword`. A partial set still builds, and the splits stay stable because they are hashed by `pair_id`.

## Commands (Windows, from the repo root)

```bash
# once: read-only snapshots of the Matcher and RAG code, outside the repo
git archive 2b7d42e matcher benchmark/__init__.py benchmark/run.py benchmark/metrics.py benchmark/data/val.jsonl benchmark/data/MANIFEST.json finetune | tar -x -C ../HireSignal-data/deps
git archive origin/claude/gracious-fermi-ncuem4 rag | tar -x -C ../HireSignal-data/deps
# step 4 (add --test <test.jsonl> only for the leakage audit; it is never trained on)
PYTHONPATH=../HireSignal-data/deps HIRESIGNAL_RAG_DIR=../HireSignal-data/deps/rag python -m finetuning.build_real \
  --labels label_A.xlsx label_B.xlsx --val ../HireSignal-data/deps/benchmark/data/val.jsonl --out ../HireSignal-data/build/final \
  --extra ../HireSignal-data/build/contractnli_sft.jsonl:0.25 ../HireSignal-data/build/bench_synthetic_sft.jsonl:0.15
# step 5
PYTHONPATH=../HireSignal-data/deps python -m finetuning.make_bundle --deps ../HireSignal-data/deps --data ../HireSignal-data/build/final --out ../HireSignal-data/hiresignal_finetune_bundle.zip
```

## Rules this code enforces

- **Train only on** `sft_train.jsonl`, with `sft_dev.jsonl` for eval loss. The trainer refuses any other file.
- **Never trained on:**
  - the 202 val requirements;
  - the real eval split (20 % of pairs, hashed by `pair_id`);
  - the sealed test. It is read only by the leakage audit, and `make_bundle` refuses to include it.
- **Gold labels are human labels only.** Rows a human did not fill are ignored.
- Requirement texts made from job metadata ("English level … or higher", "At least N years …") are shared templates.
  The leakage audit therefore counts some requirement-text overlap with `eval_real`. The CVs and jobs themselves never
  overlap.
- **Adapter acceptance**, under identical settings: on both val and the real eval split,
  - macro-F1 is higher than the base;
  - false-MET is not higher;
  - JSON validity is not lower.
