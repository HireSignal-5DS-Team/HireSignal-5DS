"""Shared constants and helpers for the soft prompt experiment.

Pinned identities (verified 2026-10-16 from the Hugging Face metadata and benchmark/results/adapter/):
- base: Qwen/Qwen3-4B-Instruct-2507 @ cdbee75f17c01a7cc42f958dc650907174af0554 (the revision the Matcher LoRA was
  trained on, see the LoRA's train_meta.json)
- Matcher LoRA: HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora @ 0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "prompt_tuning/data"
BENCH = ROOT / "benchmark/data"
RESULTS = ROOT / "benchmark/results/experimental/soft_prompt"

BASE = "Qwen/Qwen3-4B-Instruct-2507"
BASE_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
LORA = "HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora"
LORA_REVISION = "0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a"

SFT_TRAIN = ROOT / "finetune/data/sft_train.jsonl"
SFT_VAL = ROOT / "finetune/data/sft_val.jsonl"
VAL_PROMPTS = DATA / "val_prompts.jsonl"
MANIFEST = DATA / "manifest.json"

# Initial text of the soft prompt (PromptTuningInit.TEXT): its token embeddings are the starting point, then they are
# trained freely. It is a starting point for optimisation, not a prompt that the model reads as text.
INIT_TEXT = ("Check one job requirement against one anonymized CV. Answer with one JSON object: decision MET, MISSING "
             "or UNCERTAIN, basis, verbatim CV evidence, short explanation. Never invent evidence.")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def config_hash(cfg):
    """sha256 of a canonical JSON dump: two runs with the same hash used the same result-affecting settings."""
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def case_ids(rows):
    return {r["case_id"] for r in rows}


class LeakageError(AssertionError):
    pass


def check_no_leakage(train_rows, val_ids, test_ids, train_path=None):
    """Refuse training data that touches the val or the locked test split (by file name, split field or case_id)."""
    if train_path is not None:
        stem = Path(train_path).stem.lower()
        if "test" in stem or "val" in stem:
            raise LeakageError(f"refusing to train on a file named like an evaluation split: {train_path}")
    ids = case_ids(train_rows)
    for name, held in (("val", val_ids), ("test", test_ids)):
        hit = sorted(ids & set(held))
        if hit:
            raise LeakageError(f"refusing: {len(hit)} training case_ids are in the {name} split, e.g. {hit[:3]}")
    bad = [r["case_id"] for r in train_rows if not str(r["case_id"]).startswith("train-")]
    if bad:
        raise LeakageError(f"refusing: case_ids that are not train cases, e.g. {bad[:3]}")
    return len(ids)


def held_out_ids(manifest_path=MANIFEST):
    """val and test case_ids from the committed manifest (the test file itself is never read or bundled)."""
    m = json.loads(Path(manifest_path).read_text())
    return set(m["val_case_ids"]), set(m["test_case_ids"])
