r"""T15: before/after example for the Profile prompt: one CV chunk, v1 vs v3 (real-GPU, raw model answers kept).

Finds the first chunk of the pair's CV where v1's answer is cut at the token limit, then sends the same chunk with v3.
Usage: .venv\Scripts\python scripts\profile_example.py --pair P44 --out eval\results\2026-10-19_profile_prompts\example_P44.json
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.bias.auditor import leakage_check  # noqa: E402
from services.job.injection import sanitise_injection  # noqa: E402
from services.job.qwen_retry import ResilientQwenChatClient  # noqa: E402
from services.profile import anonymise_cv  # noqa: E402
from services.profile.parse import CHUNK_CHARS, chunk_sections, cv_sections  # noqa: E402
from services.profile.prompts import get_prompt  # noqa: E402
from services.reader import read_cv  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pair = next(p for p in csv.DictReader(open(ROOT / "data/labels/gold/pairs_gold.csv", encoding="utf-8"))
                if p["pair_id"] == a.pair)
    r = read_cv((ROOT / "data/processed/cvs" / pair["cv_file"]).read_bytes(), "cv.txt")
    anon = sanitise_injection(leakage_check(anonymise_cv(r.text, cv_id="cv-00000000", sections=r.sections).text)[0])[0]
    client = ResilientQwenChatClient(max_tokens=768, lora_scale=0.0)
    for chunk in chunk_sections(cv_sections(anon), size=CHUNK_CHARS):
        system, ex = get_prompt("profile-v1")
        raw1 = client.extract(chunk, system, ex)
        call1 = dict(client.last_call)
        if call1.get("finish_reason") != "length":
            continue
        system, ex = get_prompt("profile-v3")
        raw3 = client.extract(chunk, system, ex)
        call3 = dict(client.last_call)
        res = {"pair": a.pair, "label": "real-GPU, plain Qwen3-4B, max_tokens 768", "chunk": chunk,
               "v1": {"finish_reason": call1.get("finish_reason"), "completion_tokens": call1.get("completion_tokens"),
                      "raw": raw1},
               "v3": {"finish_reason": call3.get("finish_reason"), "completion_tokens": call3.get("completion_tokens"),
                      "raw": raw3}}
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: (v if k != "chunk" else v[:300]) for k, v in res.items() if k not in ("v1", "v3")},
                         ensure_ascii=False))
        print("v1", call1.get("finish_reason"), call1.get("completion_tokens"), raw1[-200:])
        print("v3", call3.get("finish_reason"), call3.get("completion_tokens"), raw3[:400])
        return
    print("no cut chunk found")


if __name__ == "__main__":
    main()
