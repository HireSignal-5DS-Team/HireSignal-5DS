"""Convert ContractNLI (Koreeda & Manning 2021, CC BY 4.0, human labels + evidence spans) into Matcher SFT examples.

Source: https://stanfordnlp.github.io/contract-nli/ (contract-nli.zip). Only train.json is read; its dev/test are
not used. Mapping (hypothesis = requirement, contract excerpt = document):
  Entailment    -> MET + supported          evidence = annotated spans (verbatim)
  Contradiction -> MISSING + contradicted   evidence = annotated spans (verbatim)
  NotMentioned  -> MISSING + not_documented evidence = []
Full NDAs are too long for training, so each example uses an excerpt: the evidence spans plus random other spans of
the same contract, in document order, capped at --max-chars. Quotes stay exact substrings of the excerpt.
The prompt is the Matcher prompt (p1) with no knowledge block, so the model learns the grounding rule, not NDA law.

  PYTHONPATH=<deps> python -m finetuning.contractnli_to_sft --src contract-nli/train.json --out contractnli_sft.jsonl
"""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from matcher import prompt
from matcher.schemas import CV, ModelAnswer, Requirement
from matcher.validate import find_span

MAP = {"Entailment": ("MET", "supported"), "Contradiction": ("MISSING", "contradicted"),
       "NotMentioned": ("MISSING", "not_documented")}
EXPLANATIONS = {
    "supported": "The document states this directly; the quote is copied from it.",
    "contradicted": "The document states the opposite; the quote is copied from it.",
    "not_documented": "The document says nothing about this.",
}


def excerpt(doc, keep, rng, max_chars):
    """Text of the kept span ids plus random distractor spans, in order, within max_chars."""
    spans = doc["spans"]
    chosen = set(keep)
    size = sum(spans[i][1] - spans[i][0] for i in chosen)
    for i in rng.sample(range(len(spans)), len(spans)):
        n = spans[i][1] - spans[i][0]
        if i not in chosen and size + n <= max_chars:
            chosen.add(i)
            size += n
    return "\n".join(doc["text"][spans[i][0]:spans[i][1]].strip() for i in sorted(chosen))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-chars", type=int, default=2500)
    ap.add_argument("--max-evidence-chars", type=int, default=1200, help="skip items whose evidence alone is longer")
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args(argv)
    assert Path(a.src).name == "train.json", "use ContractNLI train.json only"
    d = json.loads(Path(a.src).read_text(encoding="utf-8"))
    rng, rows, skipped = random.Random(a.seed), [], Counter()
    for doc in d["documents"]:
        for hid, ann in doc["annotation_sets"][0]["annotations"].items():
            dec, basis = MAP[ann["choice"]]
            ev_ids = ann["spans"][:3]
            quotes = [doc["text"][doc["spans"][i][0]:doc["spans"][i][1]].strip() for i in ev_ids]
            if sum(map(len, quotes)) > a.max_evidence_chars:
                skipped["evidence_too_long"] += 1
                continue
            text = excerpt(doc, ev_ids, rng, a.max_chars)
            assert all(find_span(text, q) for q in quotes)
            cv = CV(cv_id=f"cnli-{doc['id']}", text=text)
            req = Requirement(req_id=hid, text=d["labels"][hid]["hypothesis"], kind="must", category="other")
            ans = ModelAnswer(decision=dec, basis=basis, evidence=quotes, explanation=EXPLANATIONS[basis])
            rows.append({"case_id": f"cnli-{doc['id']}", "req_id": hid, "source": "contractnli",
                         "messages": [*prompt.messages(cv, req, []), {"role": "assistant", "content": prompt.target(ans)}]})
    Path(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"examples": len(rows), "decisions": dict(Counter(json.loads(r["messages"][-1]["content"])["basis"] for r in rows)),
                      "skipped": dict(skipped)}))


if __name__ == "__main__":
    main()
