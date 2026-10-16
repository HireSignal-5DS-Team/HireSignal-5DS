"""Build prompt_tuning/dist/hiresignal_soft_prompt_bundle.zip to upload as a PRIVATE Kaggle Dataset.

Contains only what the notebook needs: matcher/ (prompt, schemas, validator), benchmark metrics, the val gold file
(scoring only), finetune/ SFT files + encode/collate helpers, and prompt_tuning/. The locked test split is NOT
included (only its case_ids, inside the manifest, for the leak check). All data is synthetic.

  python -m prompt_tuning.make_bundle
"""
import zipfile
from pathlib import Path

from .common import MANIFEST, ROOT, SFT_TRAIN, SFT_VAL, VAL_PROMPTS, sha256

INCLUDE = ["matcher/*.py", "matcher/json_schemas/*.json", "benchmark/__init__.py", "benchmark/metrics.py",
           "benchmark/data/val.jsonl", "benchmark/data/MANIFEST.json", "finetune/train_lora.py",
           "finetune/build_sft.py", "finetune/data/sft_train.jsonl", "finetune/data/sft_train.meta.json",
           "finetune/data/sft_val.jsonl", "finetune/data/sft_val.meta.json", "requirements-matcher.txt",
           "prompt_tuning/*.py", "prompt_tuning/*.md", "prompt_tuning/*.ipynb", "prompt_tuning/data/*"]


def files():
    out = sorted({p for pat in INCLUDE for p in ROOT.glob(pat) if p.is_file()})
    for p in out:
        rel = p.relative_to(ROOT).as_posix()
        assert "test.jsonl" not in rel and "/tests/" not in rel, f"refusing to bundle {rel}"
    return out


def main(out=ROOT / "prompt_tuning/dist/hiresignal_soft_prompt_bundle.zip"):
    import json

    m = json.loads(MANIFEST.read_text())
    for p, key in ((SFT_TRAIN, "finetune/data/sft_train.jsonl"), (SFT_VAL, "finetune/data/sft_val.jsonl"),
                   (VAL_PROMPTS, "prompt_tuning/data/val_prompts.jsonl")):
        assert sha256(p) == m["files"][key]["sha256"], f"{key} changed since prepare_data; re-run it"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fs = files()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in fs:
            z.write(p, p.relative_to(ROOT).as_posix())
    print(f"{out} ({out.stat().st_size // 1024} KB, {len(fs)} files)")
    return out


if __name__ == "__main__":
    main()
