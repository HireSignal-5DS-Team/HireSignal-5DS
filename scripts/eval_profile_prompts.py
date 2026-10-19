r"""T15 Part B: Profile Agent parse prompt versions (real-GPU, plain Qwen3-4B on llama-server).

Input = what /profile parses: Reader text -> anonymiser -> leakage check + injection removal (services/api.py
matcher_guard) -> parse_cv(prompt version, chunk size, max tokens).
Sets (split fixed before any run):
  gold  : the 52 gold-pair CVs (dev / test = the pair's split) + the 5 Kaggle IT PDFs (data/raw/scans/K01..K05.pdf,
          CC0; dev = K01, K02, test = K03..K05);
  synth : the 10 synthetic CVs with V2's parse gold (eval/profile_agent/parse_gold; dev = p01-p05, test = p06-p10).
Measures per setting:
  partial   = CVs with a call cut at the token limit or an unreadable answer (= /profile's
              profile:partial_extraction_requires_review);
  cut_calls / json_valid share of all calls;
  skills_precision = raw skill proposals whose name is written in the CV text (case-insensitive) / all raw proposals;
  term_recall = the job card's skill_terms that are literally in the CV and are found among the kept skills
               (case-insensitive containment either way), gold pairs only;
  experience / education items kept; latency per CV;
  synth: skills precision / recall vs the gold (an item counts if it matches one of the gold alternatives;
         `skills_optional` neither help nor hurt).
Usage: .venv\Scripts\python scripts\eval_profile_prompts.py --setting v1 --split dev --out eval\results\<d>_profile_prompts
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.bias.auditor import leakage_check  # noqa: E402
from services.job.injection import sanitise_injection  # noqa: E402
from services.job.qwen_retry import ResilientQwenChatClient  # noqa: E402
from services.job.validate import parse_model_output  # noqa: E402
from services.profile import anonymise_cv  # noqa: E402
from services.profile.parse import _expand_skill_groups, parse_cv  # noqa: E402
from services.reader import read_cv  # noqa: E402

# setting -> (prompt version, chunk characters, max output tokens); v1 = production before T15
SETTINGS = {"v1": ("profile-v1", 800, 768), "v2": ("profile-v2", 800, 768),
            "v3": ("profile-v3", 800, 768), "v2g": ("profile-v2", 800, 768), "v1-1024": ("profile-v1", 800, 1024)}


def cases(split: str) -> list[dict]:
    out = []
    for p in csv.DictReader(open(ROOT / "data/labels/gold/pairs_gold.csv", encoding="utf-8")):
        if p["split"] == split:
            card = json.loads((ROOT / f"data/processed/jobs/{p['job']}_requirements.json").read_text(encoding="utf-8"))
            out.append({"id": p["pair_id"], "set": "gold", "path": ROOT / "data/processed/cvs" / p["cv_file"],
                        "terms": [t for r in card["requirements"] for t in r["skill_terms"]]})
    for k in (["K01", "K02"] if split == "dev" else ["K03", "K04", "K05"]):
        out.append({"id": k, "set": "kaggle", "path": ROOT / f"data/raw/scans/{k}.pdf", "terms": []})
    synth = sorted((ROOT / "tests/fixtures/profile/cvs").glob("*.txt"))
    for f in (synth[:5] if split == "dev" else synth[5:]):
        out.append({"id": f.stem, "set": "synth", "path": f, "terms": [],
                    "gold": json.loads((ROOT / f"eval/profile_agent/parse_gold/{f.stem}.json").read_text("utf-8"))})
    return out


class Recorder:
    def __init__(self, backend):
        self.backend, self.log = backend, []

    @property
    def last_call(self):
        return getattr(self.backend, "last_call", {})

    def extract(self, text, template, examples):
        raw = self.backend.extract(text, template, examples)
        self.log.append({"input": text, "raw": raw, "finish": (self.last_call or {}).get("finish_reason"),
                         "tokens": (self.last_call or {}).get("completion_tokens")})
        return raw


def low(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def run_case(c: dict, version: str, chunk: int, max_tokens: int) -> dict:
    data = c["path"].read_bytes()
    r = read_cv(data, c["path"].name)
    anon = anonymise_cv(r.text, cv_id="cv-00000000", sections=r.sections).text
    anon = sanitise_injection(leakage_check(anon)[0])[0]
    rec = Recorder(ResilientQwenChatClient(max_tokens=max_tokens, lora_scale=0.0))
    t = time.perf_counter()
    prof = parse_cv(anon, "cv-00000000", rec, prompt_version=version, chunk_chars=chunk)
    lat = time.perf_counter() - t
    raws, valid = [], 0
    for call in rec.log:
        try:
            d = parse_model_output(call["raw"])
            valid += 1
            raws += [s for s in _expand_skill_groups([x for x in d.get("skills", []) if isinstance(x, dict)]) if s.get("name")]
        except (ValueError, TypeError):
            pass
    text = low(anon)
    kept = [low(s.name) for s in prof.skills]
    present = [t for t in dict.fromkeys(c["terms"]) if low(t) in text]
    found = [t for t in present if any(low(t) in k or k in low(t) for k in kept if len(k) > 1)]
    row = {"id": c["id"], "set": c["set"], "calls": len(rec.log), "json_valid": valid,
           "cut_calls": sum(x["finish"] == "length" for x in rec.log),
           "partial": any("answer cut off" in n or "unreadable answer" in n for n in prof.uncertain),
           "raw_skills": len(raws), "raw_skills_in_cv": sum(low(str(s["name"])) in text for s in raws),
           "skills_kept": len(prof.skills), "experience": len(prof.experience), "education": len(prof.education),
           "terms_present": len(present), "terms_found": len(found), "terms_missed": [t for t in present if t not in found],
           "latency_s": round(lat, 1), "max_completion_tokens": max([x["tokens"] or 0 for x in rec.log] or [0])}
    if c["set"] == "synth":
        alts = [[low(a) for a in g] for g in c["gold"]["skills"]]
        opt = {low(o) for o in c["gold"].get("skills_optional", [])}
        tp = sum(any(k == a or a in k or k in a for a in g for k in kept) for g in alts)
        fp = sum(not any(k == a or a in k or k in a for g in alts for a in g) and not any(
            k == o or o in k or k in o for o in opt) for k in kept)
        row.update({"synth_tp": tp, "synth_fp": fp, "synth_fn": len(alts) - tp})
    return row, prof


def summarise(rows: list[dict]) -> dict:
    s = lambda k, rs=rows: sum(r.get(k, 0) for r in rs)  # noqa: E731
    syn = [r for r in rows if r["set"] == "synth"]
    tp, fp, fn = s("synth_tp", syn), s("synth_fp", syn), s("synth_fn", syn)
    return {"cvs": len(rows), "partial": s("partial"), "partial_rate": round(s("partial") / len(rows), 3),
            "calls": s("calls"), "cut_calls": s("cut_calls"),
            "json_valid": round(s("json_valid") / s("calls"), 3) if s("calls") else None,
            "skills_precision_raw": round(s("raw_skills_in_cv") / s("raw_skills"), 3) if s("raw_skills") else None,
            "skills_kept": s("skills_kept"), "experience": s("experience"), "education": s("education"),
            "term_recall": f"{s('terms_found')}/{s('terms_present')}",
            "synth_skills_precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "synth_skills_recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "latency_s_mean": round(s("latency_s") / len(rows), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", nargs="+", default=["v1"])
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    path = out / f"summary_{a.split}.json"
    for st in a.settings:
        version, chunk, mt = SETTINGS[st]
        rows = []
        (out / st / a.split).mkdir(parents=True, exist_ok=True)
        for c in cases(a.split):
            row, prof = run_case(c, version, chunk, mt)
            rows.append(row)
            (out / st / a.split / f"{c['id']}.json").write_text(json.dumps(
                {"row": row, "profile": prof.model_dump()}, indent=1, ensure_ascii=False), encoding="utf-8")
            print(st, a.split, c["id"], "partial" if row["partial"] else "ok", "cut", row["cut_calls"], "skills",
                  row["skills_kept"], f"terms {row['terms_found']}/{row['terms_present']}", row["latency_s"],
                  flush=True)
        res = {"setting": {"prompt": version, "chunk_chars": chunk, "max_tokens": mt}, "all": summarise(rows),
               **{k: summarise([r for r in rows if r["set"] == k]) for k in ("gold", "kaggle", "synth")}}
        print(st, a.split, json.dumps(res["all"]), flush=True)
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        path.write_text(json.dumps({**old, st: res, "label": "real-GPU, plain Qwen3-4B (llama-server)"}, indent=1),
                        encoding="utf-8")


if __name__ == "__main__":
    main()
