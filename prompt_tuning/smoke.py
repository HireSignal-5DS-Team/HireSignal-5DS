"""CPU SMOKE RUN of the whole pipeline on a TINY RANDOM Qwen3 model (prompt_tuning/tiny.py), with the real data files:
train a soft prompt on sft_train.jsonl (few steps), train one on a tiny random LoRA merged into the tiny base, evaluate
all four arms on the first --limit val prompts, compare. Every output is labelled SMOKE. It proves the plumbing
(data -> training -> save -> load -> generation -> validator -> metrics -> paired stats), NOT matching quality.

  nice -n 19 python -m prompt_tuning.smoke
"""
import argparse
import json
from pathlib import Path

from .common import RESULTS, ROOT, SFT_TRAIN, read_jsonl


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default=str(ROOT / "prompt_tuning/runs/smoke"))
    ap.add_argument("--out-root", default=str(RESULTS / "smoke"))
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--steps", type=int, default=6)
    a = ap.parse_args(argv)
    from . import compare, evaluate, train_soft_prompt
    from .tiny import tiny_lora, tiny_qwen3

    work = Path(a.work)
    texts = [m["content"] for ex in read_jsonl(SFT_TRAIN)[:200] for m in ex["messages"]]
    base = tiny_qwen3(work / "tiny_qwen3", texts, vocab_size=2000)
    lora = tiny_lora(base, work / "tiny_lora")
    common = ["--base", base, "--revision", "", "--runs-dir", str(work / "runs"), "--max-steps", str(a.steps),
              "--grad-accum", "4", "--eval-every", "3", "--eval-limit", "10", "--max-len", "8192",
              "--save-every", "3", "--num-virtual-tokens", "8", "--lr", "3e-2", "--device", "cpu"]
    sp_base = train_soft_prompt.train(train_soft_prompt.parse_args(["--run-id", "sp-base", *common]))
    sp_lora = train_soft_prompt.train(train_soft_prompt.parse_args(["--run-id", "sp-lora", "--lora", lora, *common]))
    ev = ["--base", base, "--revision", "", "--device", "cpu", "--label", "SMOKE", "--limit", str(a.limit),
          "--out-root", a.out_root, "--max-new-tokens", "48"]
    arms = {"base": [], "lora": ["--lora", lora], "soft_prompt": ["--soft-prompt", str(sp_base / "soft_prompt")],
            "lora_soft_prompt": ["--lora", lora, "--soft-prompt", str(sp_lora / "soft_prompt")]}
    for arm, extra in arms.items():
        evaluate.run(evaluate.parse_args(["--arm", arm, "--run-id", f"smoke-{arm}", *ev, *extra]))
    c = compare.main(["--out-root", a.out_root, "--name", "COMPARISON_SMOKE",
                      "--runs", *(f"{arm}=smoke-{arm}" for arm in arms)])
    for run in (sp_base, sp_lora):  # keep the small text artefacts of the smoke training next to the eval results
        dst = Path(a.out_root) / f"train-{run.name}"
        dst.mkdir(parents=True, exist_ok=True)
        for f in ("loss_log.jsonl", "provenance.json", "training_args.json", "environment.json"):
            (dst / f).write_text((run / f).read_text())
    print(json.dumps({"label": "SMOKE", "rows": [(r["arm"], round(r["macro_f1"], 3)) for r in c["rows"]]}))
    return c


if __name__ == "__main__":
    main()
