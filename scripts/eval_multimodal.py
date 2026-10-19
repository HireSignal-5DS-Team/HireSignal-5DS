r"""T10 Parts A-C: benchmark the Reader setups on the phone photos and scans of data/raw/scans/.

Items come from PHOTO_MAPPING.csv (file names do not match their sources). Split by SOURCE: Kaggle source PDFs
(K0x.pdf, no labels) = dev, our labelled L0x.pdf = test. Ground truth = the text layer of the source PDF page(s), read
with PyMuPDF through the Reader's own text route (same block order + clean_text).
Normalisation for CER/WER: Unicode NFKC, lower case, Markdown marks (* # `) and "[unclear]" removed, all whitespace
collapsed to one space. Hallucination rate = share of output words (punctuation stripped) that are not in the ground
truth (multiset difference = inserted words). Skill terms (test): the gold requirements' skill_terms of the pair's job
that are written in the digital text; share of them also found in the setup's text (whole word, case-insensitive).

Stages (each caches its outputs in --out; rerun = resume):
  ocr                      path 1 on every page
  vision --models a,b --prompts v0,v1 [--split dev|test|all]
  early  --models a --prompts v0,v1 [--split ...]
  report [--vision M:P] [--early M:P] [--min-conf 60]   tables + the late-fusion sweep on dev
Usage: .venv\Scripts\python scripts\eval_multimodal.py --out eval\results\<date>_multimodal --stage ocr
"""
import argparse
import collections
import csv
import io
import json
import re
import string
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

import pymupdf
from PIL import Image
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.reader import multimodal as mm  # noqa: E402
from services.reader.cleaning import clean_text  # noqa: E402
from services.reader.reader import OCR_DPI, _ocr_with_cleanup, _order_blocks, _prepare_photo  # noqa: E402

SCANS = ROOT / "data/raw/scans"
HARD = {"L04_p01_photo.jpg", "L04_p02_photo.jpg", "L05_photo.jpg"}
THRESHOLDS = (0, 20, 40, 50, 60, 70, 80, 90, 101)
PROMPTS = {"vision": {"v0": "prompts/reader/vision_v0.md", "v1": "prompts/reader/vision_v1.md"},
           "early": {"v0": "prompts/reader/early_fusion_v0.md", "v1": "prompts/reader/early_fusion_v1.md"}}


# ------------------------------------------------------------------- items ---

def items():
    out = []
    manifest = {r["file_id"]: r for r in csv.DictReader(open(SCANS / "MANIFEST.csv", encoding="utf-8"))}
    for r in csv.DictReader(open(SCANS / "PHOTO_MAPPING.csv", encoding="utf-8")):
        src = r["source_file"]
        pages = [int(x) for x in re.findall(r"\d+", r["source_page"])]
        pages = list(range(pages[0], pages[-1] + 1))
        f = r["photo_file"]
        cond = "scan" if f.endswith("_scan.pdf") else "hard photo" if f in HARD else "close photo"
        out.append({"id": f.rsplit(".", 1)[0], "file": f, "source": src, "pages": pages, "pair": r["pair_id"] or None,
                    "split": "dev" if src.startswith("K") else "test", "condition": cond,
                    "job": manifest.get(src[:3], {}).get("job") or None})
    return out


def page_images(it):
    if it["file"].endswith(".pdf"):
        doc = pymupdf.open(SCANS / it["file"])
        return [Image.open(io.BytesIO(p.get_pixmap(dpi=OCR_DPI).tobytes("png"))) for p in doc]
    return [Image.open(SCANS / it["file"])]


def ground_truth(it):
    doc = pymupdf.open(SCANS / it["source"])
    parts = []
    for n in it["pages"]:
        page = doc[n - 1]
        blocks, _ = _order_blocks(page.get_text("blocks"), page.rect.width)
        parts.append("\n\n".join(b[4].strip() for b in blocks))
    return clean_text("\n\n".join(parts))


# ----------------------------------------------------------------- metrics ---

def norm_text(t):
    t = unicodedata.normalize("NFKC", t).lower().replace(mm.UNCLEAR, " ")
    t = re.sub(r"[*#`]", " ", t)
    return " ".join(t.split())


def words(t):
    return [w for w in (x.strip(string.punctuation + "•·–—‘’“”") for x in norm_text(t).split()) if w]


def scores(hyp, ref):
    h, r = norm_text(hyp), norm_text(ref)
    hw, rw = words(hyp), words(ref)
    inserted = sum((collections.Counter(hw) - collections.Counter(rw)).values())
    return {"cer": round(Levenshtein.distance(h, r) / max(1, len(r)), 4),
            "wer": round(Levenshtein.distance(h.split(), r.split()) / max(1, len(r.split())), 4),
            "halluc": round(inserted / max(1, len(hw)), 4), "out_words": len(hw), "ref_words": len(rw),
            "unclear": mm.unclear_share(hyp)}


def term_in(term, text):
    return re.search(r"(?<![\w+#])" + re.escape(term.lower()) + r"(?![\w+#])", text.lower()) is not None


def job_terms(job):
    reqs = json.loads((ROOT / f"data/processed/jobs/{job}_requirements.json").read_text(encoding="utf-8"))["requirements"]
    return sorted({t for r in reqs for t in r.get("skill_terms") or []})


# --------------------------------------------------------------- GPU memory ---

class VramPeak:
    """Poll nvidia-smi every 0.2 s while a call runs; peak used MiB on GPU 0."""

    def __enter__(self):
        self.peak, self._stop = 0, threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout
                self.peak = max(self.peak, int(out.split()[0]))
            except Exception:
                pass
            time.sleep(0.2)

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()


# ------------------------------------------------------------------ stages ---

def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def stage_ocr(out, its):
    for it in its:
        p = out / "ocr" / f"{it['id']}.json"
        if p.exists():
            continue
        pages = []
        for im in page_images(it):
            t = time.perf_counter()
            warn = []
            text, conf, layout, wc = _ocr_with_cleanup(_prepare_photo(im), warn)
            pages.append({"text": text, "conf": conf, "layout": layout, "word_confs": wc, "warnings": warn,
                          "latency_s": round(time.perf_counter() - t, 2)})
        save(p, {"item": it, "pages": pages})
        print("ocr", it["id"], [x["conf"] for x in pages], flush=True)


def stage_vision(out, its, kind, models, prompts):
    client = mm.httpx.Client(timeout=900)
    for model in models:
        for pv in prompts:
            template = mm.load_prompt(PROMPTS[kind][pv])
            for it in its:
                p = out / kind / f"{model.replace(':', '_')}__{pv}" / f"{it['id']}.json"
                if p.exists():
                    continue
                ocr = load(out / "ocr" / f"{it['id']}.json")
                pages = []
                for n, im in enumerate(page_images(it)):
                    prompt = template if kind == "vision" else mm.early_prompt(ocr["pages"][n]["text"], template)
                    try:
                        with VramPeak() as vr:
                            v = mm.vision_call(im, prompt, model=model, client=client)
                        v["peak_vram_mib"] = vr.peak
                    except mm.VisionUnavailable as exc:
                        v = {"text": "", "error": str(exc), "latency_s": None, "peak_vram_mib": None}
                    pages.append(v)
                save(p, {"item": it, "model": model, "prompt": pv, "pages": pages})
                print(kind, model, pv, it["id"], [x.get("latency_s") for x in pages], [x.get("peak_vram_mib") for x in pages],
                      flush=True)


def page_text(rec):
    return "\n\n".join(x["text"] for x in rec["pages"])


def fused_text(ocr, vis, min_conf, merge="vision_backbone"):
    fuse = mm.MERGES[merge]
    res = [fuse(o["text"], o["word_confs"], v["text"], min_conf) for o, v in zip(ocr["pages"], vis["pages"])]
    return "\n\n".join(r["text"] for r in res), sum(len(r["low_trust_lines"]) for r in res), res


def row(it, setup, text, gt, latency, vram, extra=None):
    s = scores(text, gt)
    r = {"item": it["id"], "split": it["split"], "condition": it["condition"], "setup": setup, **s,
         "latency_s_per_page": round(latency / len(it["pages"]), 2) if latency is not None else None,
         "peak_vram_mib": vram, **(extra or {})}
    if it["job"]:
        terms = [t for t in job_terms(it["job"]) if term_in(t, gt)]
        r["skill_terms_found"] = f"{sum(term_in(t, text) for t in terms)}/{len(terms)}"
    return r


def mean(rows, k):
    xs = [r[k] for r in rows if r.get(k) is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def table(rows, split):
    by = collections.defaultdict(list)
    for r in rows:
        if r["split"] == split:
            by[r["setup"]].append(r)
    out = {}
    for s, rs in by.items():
        tf = [tuple(map(int, r["skill_terms_found"].split("/"))) for r in rs if "skill_terms_found" in r]
        out[s] = {"n": len(rs), "cer": mean(rs, "cer"), "wer": mean(rs, "wer"), "halluc": mean(rs, "halluc"),
                  "unclear": mean(rs, "unclear"), "latency_s_per_page": mean(rs, "latency_s_per_page"),
                  "peak_vram_mib": max((r["peak_vram_mib"] or 0 for r in rs), default=None),
                  "skill_terms_found": f"{sum(a for a, _ in tf)}/{sum(b for _, b in tf)}" if tf else None}
    return out


def stage_report(out, its, vision_sel, early_sel, min_conf_fixed, merge_fixed=None):
    gts = {it["id"]: ground_truth(it) for it in its}
    rows = []
    ocr = {it["id"]: load(out / "ocr" / f"{it['id']}.json") for it in its}
    for it in its:
        o = ocr[it["id"]]
        rows.append(row(it, "1 OCR only", page_text(o), gts[it["id"]], sum(x["latency_s"] for x in o["pages"]), None,
                        {"ocr_conf": mean(o["pages"], "conf")}))
    # every cached vision / early run (model x prompt), for the Part A choice and the prompt before/after
    for kind in ("vision", "early"):
        for d in sorted((out / kind).glob("*")) if (out / kind).exists() else []:
            for it in its:
                v = load(d / f"{it['id']}.json")
                if v and all("error" not in x for x in v["pages"]):
                    lat = sum(x["latency_s"] for x in v["pages"]) + (
                        sum(x["latency_s"] for x in ocr[it["id"]]["pages"]) if kind == "early" else 0)
                    rows.append(row(it, f"{kind} {d.name}", page_text(v), gts[it["id"]], lat,
                                    max(x["peak_vram_mib"] or 0 for x in v["pages"])))
    # late fusion: threshold sweep on dev with the chosen vision run, then dev + test at the chosen threshold
    sweep, chosen_conf, chosen_merge = [], min_conf_fixed, merge_fixed
    if vision_sel:
        vdir = out / "vision" / vision_sel.replace(":", "_").replace("/", "__")
        for merge in mm.MERGES:
            for thr in THRESHOLDS:
                rs = []
                for it in its:
                    v = load(vdir / f"{it['id']}.json")
                    if it["split"] == "dev" and v:
                        text, lt, _ = fused_text(ocr[it["id"]], v, thr, merge)
                        rs.append(scores(text, gts[it["id"]]) | {"low_trust": lt})
                if rs:
                    sweep.append({"merge": merge, "min_conf": thr, "cer": mean(rs, "cer"), "wer": mean(rs, "wer"),
                                  "halluc": mean(rs, "halluc"), "low_trust_lines": sum(r["low_trust"] for r in rs)})
        if sweep and (min_conf_fixed is None or merge_fixed is None):
            best = min(sweep, key=lambda x: (x["cer"], x["halluc"], x["merge"] != "ocr_backbone", -x["min_conf"]))
            chosen_conf, chosen_merge = best["min_conf"], best["merge"]
        for it in its:
            v = load(vdir / f"{it['id']}.json")
            if v:
                text, lt, res = fused_text(ocr[it["id"]], v, chosen_conf, chosen_merge)
                lat = sum(x["latency_s"] for x in ocr[it["id"]]["pages"]) + sum(x["latency_s"] for x in v["pages"])
                rows.append(row(it, f"3 late fusion ({vision_sel}, {chosen_merge}, min_conf {chosen_conf})", text,
                                gts[it["id"]], lat,
                                max(x["peak_vram_mib"] or 0 for x in v["pages"]),
                                {"low_trust_lines": lt, "fusion": [r["stats"] for r in res]}))
                save(out / "late" / f"{it['id']}.json", {"item": it, "text": text, "pages": res, "min_conf": chosen_conf,
                                                         "merge": chosen_merge, "vision": vision_sel})
    summary = {"label": "real-GPU (Ollama vision models, RTX 4050 6 GB) + real-CPU (Tesseract 5.5.3)",
               "normalisation": "NFKC, lower case, * # ` and [unclear] removed, whitespace collapsed",
               "split": "dev = photos of Kaggle source PDFs; test = photos + scans of L source PDFs (PHOTO_MAPPING.csv)",
               "vision_selected": vision_sel, "early_selected": early_sel, "late_sweep_dev": sweep,
               "late_min_conf": chosen_conf, "late_merge": chosen_merge, "dev": table(rows, "dev"), "test": table(rows, "test"),
               "by_condition_test": {c: table([r for r in rows if r["condition"] == c], "test")
                                     for c in ("close photo", "hard photo", "scan")}}
    save(out / "summary.json", summary)
    with open(out / "rows.csv", "w", newline="", encoding="utf-8") as f:
        keys = sorted({k for r in rows for k in r if k != "fusion"})
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    for sp in ("dev", "test"):
        print(f"== {sp}")
        for s, v in sorted(summary[sp].items()):
            print(f"  {s:60s} {v}")
    for x in sweep:
        print("  late sweep (dev):", x)
    print("chosen merge:", chosen_merge, "min_conf:", chosen_conf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage", required=True, choices=("ocr", "vision", "early", "report"))
    ap.add_argument("--models", default="qwen2.5vl:3b")
    ap.add_argument("--prompts", default="v0,v1")
    ap.add_argument("--split", default="dev", choices=("dev", "test", "all"))
    ap.add_argument("--vision", help="chosen vision run for the report, e.g. qwen2.5vl:3b__v1")
    ap.add_argument("--early", help="chosen early-fusion run for the report")
    ap.add_argument("--min-conf", type=float, help="fixed late-fusion threshold (default: choose on dev)")
    ap.add_argument("--merge", choices=tuple(mm.MERGES), help="fixed late-fusion merge (default: choose on dev)")
    a = ap.parse_args()
    out = Path(a.out)
    its = items()
    sel = [it for it in its if a.split == "all" or it["split"] == a.split]
    if a.stage == "ocr":
        stage_ocr(out, its)
    elif a.stage in ("vision", "early"):
        stage_vision(out, sel, a.stage, a.models.split(","), a.prompts.split(","))
    else:
        stage_report(out, its, a.vision, a.early, a.min_conf, a.merge)


if __name__ == "__main__":
    main()
