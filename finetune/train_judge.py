"""Fine-tune the NLI Judge (MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli) on NLI pairs built from the TRAIN split.

Pairs (hypothesis = matcher.judge.hypothesis(requirement)):
  MET/supported          premise = gold CV quote                         -> entailment
  MISSING/contradicted   premise = gold CV quote                         -> contradiction
  MISSING/not_documented premise = whole CV                              -> neutral
  UNCERTAIN/ambiguous    premise = CV line(s) naming the skill (if any)  -> neutral
  wrong-evidence negative: a MET requirement paired with another requirement's quote of the same CV -> neutral
Split: train cases with index % 5 == 0 form `train-dev` (early stopping + Judge threshold calibration); the rest
train. val and test are never read. Checkpoint is written outside git (size ~0.7 GB); metrics/config are in git.

  python -m finetune.train_judge --out /home/user/judge_runs/deberta-hs-v1
"""
import argparse
import json
import random
import time
from pathlib import Path

from benchmark.run import DATA, read_jsonl
from matcher.judge import LABELS, hypothesis
from matcher.schemas import Requirement

BASE = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
BASE_REV = "6f5cf0a2b59cabb106aca4c287eed12e357e90eb"


def is_dev(case_id):
    return int(case_id.rsplit("-", 1)[1]) % 5 == 0


def pairs(cases):
    out = []
    for c in cases:
        cv, reqs = c["cv"]["text"], {r["req_id"]: Requirement(**r) for r in c["job"]["requirements"]}
        quotes = {rid: g["evidence"] for rid, g in c["gold"].items() if g["evidence"]}
        for rid, g in c["gold"].items():
            req, h = reqs[rid], hypothesis(reqs[rid])
            if g["basis"] == "supported":
                out.append((" ".join(g["evidence"]), h, "entailment", "met"))
                other = [q for r2, q in quotes.items() if r2 != rid]
                if other:
                    out.append((" ".join(other[0]), h, "neutral", "wrong_evidence"))
            elif g["basis"] == "contradicted":
                out.append((" ".join(g["evidence"]), h, "contradiction", "contradicted"))
            elif g["basis"] == "not_documented":
                out.append((cv, h, "neutral", "not_documented"))
            else:
                lines = [ln.lstrip("-•*– ") for ln in cv.splitlines() if any(t.casefold() in ln.casefold() for t in req.skill_terms)]
                if lines:
                    out.append((" ".join(lines), h, "neutral", "ambiguous"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=320)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    random.seed(a.seed)
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = read_jsonl(DATA / "train.jsonl")
    assert all(c["split"] == "train" for c in cases)
    tr = pairs([c for c in cases if not is_dev(c["case_id"])])
    dev = pairs([c for c in cases if is_dev(c["case_id"])])
    tok = AutoTokenizer.from_pretrained(BASE, revision=BASE_REV)
    model = AutoModelForSequenceClassification.from_pretrained(BASE, revision=BASE_REV)
    id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
    lab2id = {lab: next(i for i, v in id2label.items() if v.startswith(lab[:4])) for lab in LABELS}

    def batches(data, shuffle):
        idx = list(range(len(data)))
        if shuffle:
            random.shuffle(idx)
        for i in range(0, len(idx), a.batch):
            b = [data[j] for j in idx[i:i + a.batch]]
            enc = tok([x[0] for x in b], [x[1] for x in b], truncation="only_first", max_length=a.max_len,
                      padding=True, return_tensors="pt")
            enc["labels"] = torch.tensor([lab2id[x[2]] for x in b])
            yield enc, b

    def evaluate():
        model.eval()
        correct, per = 0, {}
        with torch.no_grad():
            for enc, b in batches(dev, False):
                pred = model(**{k: v for k, v in enc.items() if k != "labels"}).logits.argmax(-1).tolist()
                for p, x, y in zip(pred, b, enc["labels"].tolist()):
                    correct += p == y
                    s = per.setdefault(x[3], [0, 0])
                    s[0] += p == y
                    s[1] += 1
        model.train()
        return correct / len(dev), {k: round(c / n, 3) for k, (c, n) in per.items()}

    acc0, per0 = evaluate()
    log = [{"epoch": 0, "dev_acc": acc0, "dev_per_type": per0}]
    print(json.dumps(log[-1]), flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = a.epochs * ((len(tr) + a.batch - 1) // a.batch)
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
    best, t0 = -1, time.perf_counter()
    model.train()
    for ep in range(1, a.epochs + 1):
        tot = n = 0
        for enc, _ in batches(tr, True):
            loss = model(**enc).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            tot, n = tot + loss.item(), n + 1
        acc, per = evaluate()
        log.append({"epoch": ep, "train_loss": tot / n, "dev_acc": acc, "dev_per_type": per,
                    "elapsed_s": round(time.perf_counter() - t0, 1)})
        print(json.dumps(log[-1]), flush=True)
        if acc > best:
            best = acc
            model.save_pretrained(out / "best")
            tok.save_pretrained(out / "best")
    meta = {"base": BASE, "base_revision": BASE_REV, "args": vars(a), "n_train_pairs": len(tr), "n_dev_pairs": len(dev),
            "train_pair_types": {t: sum(x[3] == t for x in tr) for t in {x[3] for x in tr}},
            "dataset_sha256": json.loads((DATA / "MANIFEST.json").read_text())["splits"]["train"]["sha256"],
            "splits_used": ["train (index % 5 != 0) for training", "train (index % 5 == 0) for dev"],
            "log": log, "best_dev_acc": best}
    (out / "train_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"best_dev_acc": best, "out": str(out)}))


if __name__ == "__main__":
    main()
