"""Zip everything the Kaggle notebook needs into one file to upload as a PRIVATE Kaggle Dataset.

Contents: this folder's scripts + notebook, the built data (--data, from build_real.py: SFT train/dev, eval prompts,
real eval gold, manifest), and read-only snapshots of matcher/, benchmark/ (metrics, runner, val.jsonl) and
finetune/build_sft.py taken from the team branches (--deps). The sealed test split is never included.
The built data holds real (public, anonymised) Djinni CV text: keep the Kaggle dataset Private.

  python -m finetuning.make_bundle --deps <HireSignal-data/deps> --data <HireSignal-data/build/final> --out bundle.zip
"""
import argparse
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPS = ["matcher/*.py", "matcher/json_schemas/*.json", "benchmark/__init__.py", "benchmark/metrics.py", "benchmark/run.py",
        "benchmark/data/val.jsonl", "benchmark/data/MANIFEST.json", "finetune/__init__.py", "finetune/build_sft.py",
        "finetune/train_judge.py", "MATCHER_COMMIT", "RAG_COMMIT"]
DATA = ["sft_train.jsonl", "sft_dev.jsonl", "manifest.json", "eval/*.jsonl"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--deps", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    deps, data, out = Path(a.deps), Path(a.data), Path(a.out)
    files = [(p, p.relative_to(deps).as_posix()) for pat in DEPS for p in deps.glob(pat) if p.is_file()]
    files += [(p, "finetuning/" + p.relative_to(HERE).as_posix()) for pat in ("*.py", "*.ipynb", "README.md")
              for p in HERE.glob(pat)]
    files += [(p, "finetuning/data/" + p.relative_to(data).as_posix()) for pat in DATA for p in data.glob(pat)]
    assert (data / "sft_train.jsonl").exists() and (data / "manifest.json").exists(), f"build the data first: {data}"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, rel in sorted(set(files), key=lambda x: x[1]):
            assert "test.jsonl" not in rel, f"refusing to bundle the sealed test split: {rel}"
            z.write(src, rel)
    print(f"{out} ({out.stat().st_size // 1024} KB, {len(files)} files)")


if __name__ == "__main__":
    main()
