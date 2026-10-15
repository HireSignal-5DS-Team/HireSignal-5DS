"""Build finetuning/dist/hiresignal_finetune_bundle.zip to upload as a PRIVATE Kaggle Dataset.

Contains only what the notebook needs: matcher/ (prompt, schemas, validator), the benchmark metrics/runner helpers,
the val gold file (evaluation only), and finetuning/ (scripts + SFT data). The sealed test split is NOT included.
All data is synthetic (no real CVs). Keep the Kaggle dataset private anyway (val/test integrity).

  python -m finetuning.make_bundle
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["matcher/*.py", "matcher/json_schemas/*.json", "benchmark/__init__.py", "benchmark/metrics.py",
           "benchmark/run.py", "benchmark/compare.py", "benchmark/data/val.jsonl", "benchmark/data/MANIFEST.json",
           "finetune/__init__.py", "finetune/build_sft.py", "finetune/train_judge.py",
           "finetuning/*.py", "finetuning/*.md", "finetuning/*.ipynb", "finetuning/data/*"]
NEVER = ("benchmark/data/test.jsonl",)


def main():
    out = ROOT / "finetuning/dist/hiresignal_finetune_bundle.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    files = sorted({p for pat in INCLUDE for p in ROOT.glob(pat) if p.is_file()})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            assert rel not in NEVER and "test.jsonl" not in rel, rel
            z.write(p, rel)
    print(f"{out} ({out.stat().st_size // 1024} KB, {len(files)} files)")


if __name__ == "__main__":
    main()
