r"""T14 Part B: figures for the report and the slides, made from the result files (no typed numbers).

Every figure is written as PNG (200 dpi) and SVG to docs/figures/. Grey shades + hatches, so they read in black and
white. Sources (one per figure) are listed in docs/figures/README.md and in SOURCES below.

Usage: .venv\Scripts\python scripts\make_figures.py [--out docs\figures]
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
R = ROOT / "eval/results"
SOURCES = {
    "1_pipeline": "n8n/hiresignal_v1.json",
    "2_rag_retrieval": "eval/results/2026-10-18_rag_retrieval_checked/summary.json",
    "3_multimodal_cer": "eval/results/2026-10-18_multimodal/summary.json",
    "4_bias": "eval/results/2026-10-18_bias/summary.json + data/processed/counterfactuals/ (recomputed with the "
              "current anonymiser and guard)",
    "5_final_outcomes": "eval/results/2026-10-19_final_eval/final_summary.json",
    "6_report_writer": "eval/results/2026-10-19_report_writer/summary.json + "
                       "eval/results/2026-10-19_report_writer_t13/summary.json",
    "7_gate_variants": "eval/results/2026-10-18_outcome_gate/gate/summary.json",
    "8_latency": "eval/results/2026-10-19_final_eval/final_summary.json",
}
GREYS = ["#222222", "#777777", "#bbbbbb", "#eeeeee", "#555555", "#999999"]
HATCH = ["", "//", "..", "xx", "\\\\", "--"]
plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans", "axes.spines.top": False,
                     "axes.spines.right": False, "svg.fonttype": "none"})


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def save(fig, out: Path, name: str):
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(out / f"{name}.{ext}", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


def bars(ax, groups: list[str], series: dict[str, list[float]], fmt="{:.2f}", width=0.8):
    n = len(series)
    w = width / n
    for i, (label, vals) in enumerate(series.items()):
        xs = [g + (i - (n - 1) / 2) * w for g in range(len(groups))]
        b = ax.bar(xs, vals, w, label=label, color=GREYS[i % len(GREYS)], hatch=HATCH[i % len(HATCH)],
                   edgecolor="black", linewidth=0.6)
        ax.bar_label(b, [fmt.format(v) for v in vals], fontsize=7, padding=1)
    ax.set_xticks(range(len(groups)), groups)


# 1. pipeline ---------------------------------------------------------------------------------------------------------
def fig_pipeline(out: Path):
    wf = load(SOURCES["1_pipeline"])
    names = {n["name"] for n in wf["nodes"]}
    steps = [  # (n8n node that must exist, station label, model / method)
        ("Check token", "Webhook + token", "n8n, X-HireSignal-Token"),
        ("HTTP /reader", "1 Reader", "Tesseract OCR + qwen2.5vl:3b,\nlate fusion"),
        ("HTTP /profile", "2 Profile", "anonymise (code) + leakage /\ninjection guard, parse (Qwen3-4B)"),
        ("HTTP /job", "3 Job Agent", "Qwen3-4B -> must / nice card,\nrecruiter confirms"),
        ("RAG lookup", "4a RAG", "ESCO, MiniLM dense in Qdrant,\nonly if no literal match"),
        ("HTTP /match", "4b Matcher", "Qwen3-4B + LoRA, verified\nquote, confidence"),
        ("HTTP /judge", "6 Judge", "DeBERTa NLI: quote\nsupports decision?"),
        ("Bias Auditor", "5 Bias Auditor", "counterfactual swap\n(identical input -> skip)"),
        ("HTTP /outcome", "8 Outcome gate", "code rules: invite /\nreject / review"),
        ("Report Writer", "7 Report Writer", "Qwen3-4B v3 + fact checker,\ntemplate fallback"),
    ]
    missing = [s[0] for s in steps if not any(s[0].lower() in n.lower() for n in names)]
    if missing:
        print("note: n8n nodes not found by name:", missing)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 4.6)
    ax.axis("off")
    pos = [(0.15 + (i % 5) * 2.2, 3.2 if i < 5 else 1.55) for i in range(len(steps))]
    for (node, label, model), (x, y) in zip(steps, pos):
        human = node == "HTTP /job"
        ax.add_patch(FancyBboxPatch((x, y), 1.85, 1.0, boxstyle="round,pad=0.03", facecolor="#eeeeee" if not human
                                    else "white", edgecolor="black", linewidth=1.0, linestyle="-" if not human else "--"))
        ax.text(x + 0.925, y + 0.74, label, ha="center", va="center", fontweight="bold", fontsize=8.5)
        ax.text(x + 0.925, y + 0.33, model, ha="center", va="center", fontsize=6.6)
    for i in range(len(steps) - 1):
        (x0, y0), (x1, y1) = pos[i], pos[i + 1]
        if y0 == y1:
            ax.annotate("", (x1, y1 + 0.5), (x0 + 1.85, y0 + 0.5), arrowprops=dict(arrowstyle="->", lw=1))
        else:
            ym = (y0 + y1 + 1.0) / 2  # route between the two rows
            ax.plot([x0 + 0.925, x0 + 0.925, x1 + 0.925], [y0, ym, ym], color="black", lw=1)
            ax.annotate("", (x1 + 0.925, y1 + 1.0), (x1 + 0.925, ym), arrowprops=dict(arrowstyle="->", lw=1))
    # outcomes
    ox = pos[-1][0] + 1.85
    ax.text(0.15, 0.95, "Outcome (n8n Switch):", fontweight="bold", fontsize=8.5)
    outs = [("invite (automatic)", "#eeeeee", "-"), ("reject + reasons +\n\"request human review\"", "#eeeeee", "-"),
            ("REVIEW: n8n human-approval\nform -> person decides", "white", "--")]
    for i, (t, c, ls) in enumerate(outs):
        ax.add_patch(FancyBboxPatch((0.15 + i * 3.0, 0.1), 2.7, 0.65, boxstyle="round,pad=0.03", facecolor=c,
                                    edgecolor="black", linestyle=ls))
        ax.text(1.5 + i * 3.0, 0.43, t, ha="center", va="center", fontsize=7.5)
    ax.text(9.3, 0.3, "dashed = a person\nacts here", fontsize=7.5, ha="left", style="italic")
    ax.annotate("", (ox - 6.2, 0.78), (pos[-1][0] + 0.925, pos[-1][1]), arrowprops=dict(arrowstyle="->", lw=1))
    ax.set_title(f"HireSignal: one n8n workflow ({len(wf['nodes'])} nodes), one node per station", fontsize=10)
    save(fig, out, "1_pipeline")


# 2. RAG retrieval ----------------------------------------------------------------------------------------------------
def fig_rag(out: Path):
    d = load(SOURCES["2_rag_retrieval"])
    keep = ["BM25 (current V0)", "dense all-MiniLM-L6-v2", "dense bge-small-en-v1.5", "dense multilingual-e5-base",
            "hybrid MiniLM (RRF)", "hybrid MiniLM + ms-marco rerank", "hybrid MiniLM + rerank + graph",
            "BM25, chunking B", "dense MiniLM, chunking B"]
    rows = {r["name"]: r for r in d["results"]}
    rows = [rows[k] for k in keep]
    labels = [r["name"].replace(" (current V0)", "").replace("dense ", "dense\n").replace("hybrid MiniLM", "hybrid")
              .replace(" + ", "\n+ ").replace(", chunking B", "\nchunking B") for r in rows]
    fig, ax = plt.subplots(figsize=(11, 3.8))
    bars(ax, labels, {f"dev ({d['queries']['dev']} queries)": [r["dev"]["mrr@10"] for r in rows],
                      f"test ({d['queries']['test']} queries)": [r["test"]["mrr@10"] for r in rows]})
    ax.set_ylabel("MRR@10")
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, loc="upper right")
    ax.tick_params(axis="x", labelsize=7)
    ax.set_title("RAG retrieval on ESCO (checked golds): dense MiniLM is the production setting (V6)", fontsize=10)
    save(fig, out, "2_rag_retrieval")


# 3. multimodal -------------------------------------------------------------------------------------------------------
def fig_multimodal(out: Path):
    d = load(SOURCES["3_multimodal_cer"])
    setups = [("1 OCR only", "OCR only"), ("vision qwen2.5vl_3b__v1", "vision"),
              ("3 late fusion (qwen2.5vl_3b__v1, vision_backbone, min_conf 101)", "late fusion (prod.)"),
              ("early qwen2.5vl_3b__v1", "early fusion")]
    conds = ["close photo", "hard photo", "scan"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [1, 1.6]})
    bars(a1, [lab for _, lab in setups], {"dev (10 photos)": [d["dev"][k]["cer"] for k, _ in setups],
                                          f"test ({d['test'][setups[0][0]]['n']} photos + scans)":
                                              [d["test"][k]["cer"] for k, _ in setups]}, fmt="{:.3f}")
    a1.set_ylabel("character error rate (lower is better)")
    a1.set_title("CER by reader setup", fontsize=9.5)
    a1.legend(frameon=False)
    a1.tick_params(axis="x", labelsize=7.5)
    bt = d["by_condition_test"]
    bars(a2, [f"{c} (n={bt[c][setups[0][0]]['n']})" for c in conds],
         {lab: [bt[c][k]["cer"] for c in conds] for k, lab in setups}, fmt="{:.3f}")
    a2.set_title("CER by condition (test)", fontsize=9.5)
    a2.legend(frameon=False, fontsize=7.5)
    save(fig, out, "3_multimodal_cer")


# 4. bias -------------------------------------------------------------------------------------------------------------
def identical_now() -> dict:
    """Share of counterfactual variants whose Matcher input is byte-identical to the base, with the current code:
    anonymiser only, and anonymiser + guard (= production, scripts/eval_bias.py matcher_input)."""
    from services.bias.auditor import leakage_check
    from services.job.injection import sanitise_injection
    from services.profile.anonymise import anonymise_cv
    from services.reader import read_cv

    cf = ROOT / "data/processed/counterfactuals"
    man = load("data/processed/counterfactuals/manifest.json")

    def anon(p):
        r = read_cv(p.read_bytes(), "cv.txt")
        return anonymise_cv(r.text, cv_id="cv-00000000", sections=r.sections).text

    res = {}
    for pid, info in man["pairs"].items():
        a0 = anon(cf / pid / "base.txt")
        g0 = sanitise_injection(leakage_check(a0)[0])[0]
        for vid, v in info["variants"].items():
            a = anon(cf / pid / f"{vid}.txt")
            g = sanitise_injection(leakage_check(a)[0])[0]
            f = res.setdefault(v["family"], [0, 0, 0])
            f[0] += 1
            f[1] += a == a0
            f[2] += g == g0
    return res


def fig_bias(out: Path):
    d = load("eval/results/2026-10-18_bias/summary.json")
    raw, prod = d["raw"]["all"]["families"], d["prod"]["all"]["families"]
    fams = ["name-gender", "origin", "age", "family", "language"]
    now = identical_now()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [1, 1.8]})
    two = [f for f in fams if f in raw]
    bars(a1, two, {"no protection (raw text)": [raw[f]["req_flip_rate"] * 100 for f in two],
                   "anonymiser + guard (prod.)": [prod[f]["req_flip_rate"] * 100 for f in two]}, fmt="{:.1f}%")
    a1.set_ylabel("requirement decisions flipped (%)")
    a1.set_title(f"Swap test: flips (raw: reduced subset,\n{sum(raw[f]['variants_run'] for f in two)} variants; "
                 f"prod.: {sum(prod[f]['variants_run'] for f in two)})", fontsize=9)
    a1.set_ylim(0, max(raw[f]["req_flip_rate"] for f in two) * 100 * 1.6)
    a1.legend(frameon=False, fontsize=7.5, loc="upper left")
    bars(a2, fams, {"anonymiser only (no leakage check)": [100 * now[f][1] / now[f][0] for f in fams],
                    "T11 prod. (+ leakage check)": [100 * prod[f]["matcher_input_identical"] /
                                                    prod[f]["variants_run"] for f in fams],
                    "T11b prod. (+ over-mask fix)": [100 * now[f][2] / now[f][0] for f in fams]}, fmt="{:.0f}")
    a2.set_ylabel("Matcher input identical to base (%)")
    a2.set_ylim(0, 115)
    a2.set_title(f"Signal neutralised? ({sum(v[0] for v in now.values())} counterfactual variants, 52 pairs)",
                 fontsize=9)
    a2.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    save(fig, out, "4_bias")


# 5. final outcomes ---------------------------------------------------------------------------------------------------
def fig_outcomes(out: Path):
    d = load(SOURCES["5_final_outcomes"])["groups"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    order = ["invite", "review", "reject"]
    for ax, (name, g) in zip(axes, d.items()):
        cm = g["outcome_confusion_gold_rows_pred_cols"]
        m = [[cm[r][c] for c in order] for r in order]
        ax.imshow(m, cmap="Greys", vmin=0, vmax=max(max(r) for r in m) * 1.6)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, m[i][j], ha="center", va="center", fontsize=12,
                        fontweight="bold" if i == j else "normal")
        ax.set_xticks(range(3), order)
        ax.set_yticks(range(3), order)
        ax.set_xlabel("HireSignal outcome")
        ax.set_ylabel("human gold outcome")
        ax.spines[:].set_visible(True)
        ax.set_title(f"{name}: {g['pairs']} pairs\nreview rate {g['review_rate']:.1%}, false invites "
                     f"{g['false_invites']}, false rejects {g['false_rejects']}", fontsize=9)
    save(fig, out, "5_final_outcomes")


# 6. report writer ----------------------------------------------------------------------------------------------------
def frac(s: str) -> float:
    a, b = s.split("/")
    return int(a) / int(b)


def fig_report_writer(out: Path):
    t12, t13 = load(SOURCES["6_report_writer"].split(" + ")[0]), load(SOURCES["6_report_writer"].split(" + ")[1])
    runs = [("4B v0\n(T12 checker)", t12["4b-v0/dev"]), ("4B v1\n(T12)", t12["4b-v1/dev"]),
            ("4B v2\n(T12)", t12["4b-v2/dev"]), ("0.6B v2\n(T12)", t12["0.6b-v2/dev"]),
            ("4B v2\n(T13 checker)", t13["4b-v2/dev"]), ("4B v3\n(T13, prod.)", t13["4b-v3/dev"])]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    first = [frac(r["pass_first_try"]) * 100 for _, r in runs]
    retry = [(frac(r["pass_after_retry_llm"]) - frac(r["pass_first_try"])) * 100 for _, r in runs]
    fb = [frac(r["template_fallback"]) * 100 for _, r in runs]
    xs = range(len(runs))
    b1 = ax.bar(xs, first, color=GREYS[0], edgecolor="black", label="LLM report passes first try")
    ax.bar(xs, retry, bottom=first, color=GREYS[2], hatch="//", edgecolor="black", label="passes after 1 retry")
    b3 = ax.bar(xs, fb, bottom=[a + b for a, b in zip(first, retry)], color="white", hatch="..", edgecolor="black",
                label="template fallback (checked)")
    box = dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none")
    for b, key in ((b1, "pass_first_try"), (b3, "template_fallback")):
        for t in ax.bar_label(b, [r[key] if frac(r[key]) else "" for _, r in runs], label_type="center", fontsize=7.5):
            t.set_bbox(box)
    ax.axvline(3.5, color="black", lw=0.8, ls=":")
    ax.set_xticks(list(xs), [n for n, _ in runs], fontsize=7.5)
    ax.set_ylabel("dev reports (%)")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3)
    ax.set_title("Report Writer: fact-checker pass rate by prompt version and model (dev, 28 records)", fontsize=10)
    save(fig, out, "6_report_writer")


# 7. gate variants ----------------------------------------------------------------------------------------------------
def fig_gate(out: Path):
    d = load(SOURCES["7_gate_variants"])
    names = {"a": "(a) Judge\nas T08", "b": "(b) Judge if\np(MET)<0.999", "c": "(c) entail.\n< 0.5",
             "d": "(d) not lang./\nyears", "e": "(e) template\nv1", "f": "(f) no Judge"}
    fams = list(d["best_per_family"])
    m = [d["best_per_family"][f]["metrics"]["dev"] for f in fams]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    bars(ax, ["TEMP rule"] + [names.get(f, f) + (" *" if f == d["chosen_family"] else "") for f in fams],
         {"false invites": [d["temp_rule"]["dev"]["false_invites"]] + [x["false_invites"] for x in m],
          "false rejects": [d["temp_rule"]["dev"]["false_rejects"]] + [x["false_rejects"] for x in m],
          "review rate (%)": [d["temp_rule"]["dev"]["review_rate"] * 100] + [x["review_rate"] * 100 for x in m]},
         fmt="{:.0f}")
    ax.tick_params(axis="x", labelsize=7.5)
    ax.set_ylabel("count (of 26) / %")
    ax.legend(frameon=False)
    ax.set_title("Outcome gate variants on dev (26 pairs); * = chosen (b)", fontsize=10)
    save(fig, out, "7_gate_variants")


# 8. latency ----------------------------------------------------------------------------------------------------------
def fig_latency(out: Path):
    d = load(SOURCES["8_latency"])["groups"]
    st = ["reader", "profile", "rag", "match", "judge", "bias", "outcome", "report"]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    bars(ax, st, {f"{n} (mean {g['latency_s_per_cv_mean']:.0f} s / CV)": [g["station_s_mean"][s] for s in st]
                  for n, g in d.items()}, fmt="{:.1f}")
    ax.set_ylabel("mean seconds per CV (all requirements)")
    ax.legend(frameon=False)
    ax.set_title("Latency per station, final evaluation through n8n (real-GPU, RTX 4050 6 GB)", fontsize=10)
    save(fig, out, "8_latency")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs/figures"))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    for f in (fig_pipeline, fig_rag, fig_multimodal, fig_bias, fig_outcomes, fig_report_writer, fig_gate,
              fig_latency):
        f(out)
    (out / "sources.json").write_text(json.dumps(SOURCES, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
