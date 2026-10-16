"""Per-requirement error analysis of the committed Matcher predictions. No LLM is run.

    python -m rag_opt.error_analysis            # writes rag_opt/results/error_analysis.{json,md}

Inputs (all committed, 202 bench-v1 val requirements, base Qwen3-4B-Instruct-2507 Q4_K_M, temperature 0, 192 tokens,
prompt p1, k = 3):
  A'  rag/integration/results/qwen3-4b-q4-none-val-rerun   no knowledge          (llama-server, RAG audit)
  B'  rag/integration/results/qwen3-4b-q4-bm25-val-rerun   legacy BM25 ESCO      (llama-server, RAG audit)
  C   rag/integration/results/qwen3-4b-q4-dense-val        dense e5-small ESCO   (llama-server, RAG audit)
  A   benchmark/results/qwen3-4b-q4-none-val               no knowledge          (llama_cpp.server, Matcher session)
  B   benchmark/results/qwen3-4b-q4-rag-val                legacy BM25 ESCO      (llama_cpp.server, Matcher session)
  L   git <LORA_REF>:benchmark/results/qwen3-4b-q4+hslora-rag-val  LoRA + legacy BM25, PARTIAL checkpoint (read-only)

The "replay estimate" of the gated provider is NOT a model result: for requirements where rag.gated.v1 abstains,
the p1 prompt is byte-identical to the no-RAG prompt, so the A' answer is the answer to that exact prompt (up to the
server's run-to-run noise, measured in §4); for the other requirements the legacy run's answer (B' or C) is used as
a proxy although the gated prompt there is shorter. It bounds what gating can do; the live run must confirm it.
"""
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark import metrics as M  # noqa: E402
from matcher.knowledge import GatedKnowledge, surface  # noqa: E402
from matcher.schemas import Requirement  # noqa: E402
from rag.significance import macro_f1, mcnemar_exact, paired_bootstrap_diff  # noqa: E402

RI = "rag/integration/results"
RUNS = {
    "A'": (f"{RI}/qwen3-4b-q4-none-val-rerun", "none"),
    "B'": (f"{RI}/qwen3-4b-q4-bm25-val-rerun", "legacy BM25 ESCO k=3"),
    "C": (f"{RI}/qwen3-4b-q4-dense-val", "dense e5-small ESCO k=3"),
    "A": ("benchmark/results/qwen3-4b-q4-none-val", "none"),
    "B": ("benchmark/results/qwen3-4b-q4-rag-val", "legacy BM25 ESCO k=3"),
}
LORA_REF = "302a424"  # claude/kind-albattani-k7qlt9 checkpoint 138/202 (read with git show, never checked out)
LORA_PATH = "benchmark/results/qwen3-4b-q4+hslora-rag-val/predictions.jsonl"
KEY_TAGS = ("equivalent_skill_alias", "rag_suggests_absent_skill", "certification", "implicit_project_evidence",
            "direct_match", "missing_evidence", "negation_trap", "language", "education")
OUT = ROOT / "rag_opt/results"


def read_jsonl_text(text):
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def load_run(d):
    recs = read_jsonl_text((ROOT / d / "predictions.jsonl").read_text(encoding="utf-8"))
    cfg = json.loads((ROOT / d / "config.json").read_text())
    return {(r["case_id"], r["req_id"]): r for r in recs}, cfg


def load_lora():
    try:
        txt = subprocess.run(["git", "show", f"{LORA_REF}:{LORA_PATH}"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return None
    return {(r["case_id"], r["req_id"]): r for r in read_jsonl_text(txt)}


def requirements(split="val"):
    out = {}
    for line in (ROOT / f"benchmark/data/{split}.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        for r in c["job"]["requirements"]:
            out[(c["case_id"], r["req_id"])] = Requirement(**r)
    return out


def echo(rec):
    """Unparsed answer whose JSON is valid but copies the template enum ('MET|MISSING|UNCERTAIN')."""
    if rec["parsed"]:
        return False
    raw = rec["raw"] or ""
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw[raw.find("{"):])
    except (json.JSONDecodeError, ValueError):
        return False
    return "|" in str(obj.get("decision", "")) or "|" in str(obj.get("basis", ""))


def unparsed_kind(rec):
    if rec["parsed"]:
        return "parsed"
    if echo(rec):
        return "template_echo (valid JSON, enum copied from the prompt)"
    raw = rec["raw"] or ""
    try:
        json.JSONDecoder().raw_decode(raw[raw.find("{"):])
        return "valid JSON, other schema violation"
    except (json.JSONDecodeError, ValueError):
        return "not JSON / truncated"


def ptoks(rec):
    return (rec.get("call") or {}).get("prompt_tokens")


def run_summary(name, recs, cfg, desc):
    rs = list(recs.values())
    m = M.compute(rs)
    pt = [ptoks(r) for r in rs if ptoks(r)]
    return {"run": name, "backend": f"{cfg['backend'].get('model_id')} via {cfg['backend'].get('base_url')}",
            "knowledge": desc, "n": len(rs), "macro_f1": round(m["final"]["macro_f1"], 4),
            "accuracy": round(m["final"]["accuracy"], 4), "json_valid": round(m["json_schema_validity"], 4),
            "unparsed": sum(not r["parsed"] for r in rs), "template_echo": sum(echo(r) for r in rs),
            "mean_prompt_tokens": round(sum(pt) / len(pt), 1) if pt else None,
            "refs_injected": dict(sorted(Counter(len(r["rag_refs"]) for r in rs).items()))}


def transitions(base, cand, reqs, keys):
    """Per group: n, base acc, cand acc, lost because cand unparsed, lost on parsed, gained."""
    groups = defaultdict(list)
    for k in keys:
        groups[f"category={reqs[k].category}"].append(k)
        for t in KEY_TAGS:
            if t in base[k]["tags"]:
                groups[f"tag={t}"].append(k)
        groups["all"].append(k)
    out = {}
    for g, ks in sorted(groups.items()):
        ok_b = [base[k]["decision"] == base[k]["gold_decision"] for k in ks]
        ok_c = [cand[k]["decision"] == cand[k]["gold_decision"] for k in ks]
        out[g] = {"n": len(ks), "acc_base": round(sum(ok_b) / len(ks), 3), "acc_cand": round(sum(ok_c) / len(ks), 3),
                  "lost_unparsed": sum(b and not c and not cand[k]["parsed"] for b, c, k in zip(ok_b, ok_c, ks)),
                  "lost_parsed": sum(b and not c and cand[k]["parsed"] for b, c, k in zip(ok_b, ok_c, ks)),
                  "gained": sum(c and not b for b, c in zip(ok_b, ok_c))}
    return out


def paired(base, cand, keys):
    gold = [base[k]["gold_decision"] for k in keys]
    b = [base[k]["decision"] for k in keys]
    c = [cand[k]["decision"] for k in keys]
    x, y, p = mcnemar_exact([u == g for u, g in zip(b, gold)], [u == g for u, g in zip(c, gold)])
    d, (lo, hi) = paired_bootstrap_diff(gold, b, c)
    return {"n": len(keys), "macro_f1_base": round(macro_f1(gold, b), 4), "macro_f1_cand": round(macro_f1(gold, c), 4),
            "delta": round(d, 4), "ci95": [round(lo, 4), round(hi, 4)], "base_only_correct": x, "cand_only_correct": y,
            "mcnemar_p": round(p, 4)}


def gold_concepts(provider, req):
    """ESCO concept(s) whose preferred or alternative label equals a skill term (bench-v1 alias / absent-skill items
    use ESCO preferred labels by construction, benchmark/make_dataset.py)."""
    return {i for t in req.skill_terms for i in provider.surface_index.get(surface(t), [])}


def ref_relevance(recs, reqs, provider, keys):
    by = defaultdict(lambda: {"n": 0, "with_refs": 0, "refs": 0, "on_target_refs": 0, "gold_at_1": 0, "has_gold": 0})
    for k in keys:
        req, r = reqs[k], recs[k]
        gold = gold_concepts(provider, req)
        s = by[req.category]
        s["n"] += 1
        s["has_gold"] += bool(gold)
        s["with_refs"] += bool(r["rag_refs"])
        s["refs"] += len(r["rag_refs"])
        s["on_target_refs"] += sum(x in gold for x in r["rag_refs"])
        s["gold_at_1"] += bool(r["rag_refs"]) and r["rag_refs"][0] in gold
    for s in by.values():
        s["off_target_refs"] = s["refs"] - s["on_target_refs"]
    return dict(sorted(by.items()))


def replay(base, proxy, gated_refs, keys):
    """Records for the replay estimate: base (no-RAG) answer where gated abstains, proxy answer elsewhere."""
    return {k: (proxy[k] if gated_refs[k] and proxy[k]["rag_refs"] else base[k]) for k in keys}


def analyse():
    reqs = requirements()
    runs = {n: (*load_run(d), desc) for n, (d, desc) in RUNS.items()}
    keys = sorted(set.intersection(*[set(r) for r, _, _ in runs.values()]))
    assert len(keys) == 202, len(keys)
    A, B, C = runs["A'"][0], runs["B'"][0], runs["C"][0]
    res = {"inputs": {n: d for n, (d, _) in RUNS.items()},
           "label": "LIVE predictions recorded earlier (base Qwen3-4B Q4_K_M); replay rows are ESTIMATES, not runs"}
    res["runs"] = [run_summary(n, r, cfg, desc) for n, (r, cfg, desc) in runs.items()]
    res["unparsed_taxonomy"] = {n: dict(Counter(unparsed_kind(x) for x in r.values() if not x["parsed"]))
                                for n, (r, _, _) in runs.items()}
    # echo vs number of injected refs (B') and vs prompt length (A', B', C pooled)
    by_refs = defaultdict(lambda: [0, 0])
    for k in keys:
        by_refs[len(B[k]["rag_refs"])][0] += 1
        by_refs[len(B[k]["rag_refs"])][1] += echo(B[k])
    res["echo_by_refs_Bprime"] = {n: {"n": a, "echo": e, "rate": round(e / a, 3)} for n, (a, e) in sorted(by_refs.items())}
    pooled = sorted((ptoks(r[k]), echo(r[k])) for r in (A, B, C) for k in keys if ptoks(r[k]))
    third = len(pooled) // 3
    bins = [pooled[:third], pooled[third:2 * third], pooled[2 * third:]]
    res["echo_by_prompt_tokens"] = [{"tokens": f"{b[0][0]}-{b[-1][0]}", "n": len(b), "echo": sum(e for _, e in b),
                                     "rate": round(sum(e for _, e in b) / len(b), 3)} for b in bins]
    # noise floor: identical prompts (B' injected nothing) answered twice by the same server build
    z = [k for k in keys if not B[k]["rag_refs"]]
    res["noise_floor_identical_prompts"] = {
        "n": len(z), "same_prompt_tokens": sum(ptoks(A[k]) == ptoks(B[k]) for k in z),
        "identical_raw": sum(A[k]["raw"] == B[k]["raw"] for k in z),
        "same_decision": sum(A[k]["decision"] == B[k]["decision"] for k in z),
        "echo_Aprime": sum(echo(A[k]) for k in z), "echo_Bprime": sum(echo(B[k]) for k in z)}
    all_parsed = [k for k in keys if A[k]["parsed"] and B[k]["parsed"] and C[k]["parsed"]]
    res["parsed_in_all_three"] = {"n": len(all_parsed), **{n: round(sum(r[k]["decision"] == r[k]["gold_decision"]
                                                                       for k in all_parsed) / len(all_parsed), 3)
                                                           for n, r in (("A'", A), ("B'", B), ("C", C))}}
    res["transitions_vs_Aprime"] = {"B'": transitions(A, B, reqs, keys), "C": transitions(A, C, reqs, keys)}
    res["paired_vs_Aprime"] = {"B'": paired(A, B, keys), "C": paired(A, C, keys),
                               "A (server drift)": paired(A, runs["A"][0], keys)}

    gated = GatedKnowledge()
    res["ref_relevance"] = {"B'": ref_relevance(B, reqs, gated, keys), "C": ref_relevance(C, reqs, gated, keys)}
    g_refs = {k: gated.lookup(reqs[k]) for k in keys}
    res["gated_provider"] = {
        "name": gated.name,
        "abstains": sum(not v for v in g_refs.values()),
        "refs_injected": dict(sorted(Counter(len(v) for v in g_refs.values()).items())),
        "mean_text_chars": round(sum(len(x.text) for v in g_refs.values() for x in v) /
                                 max(1, sum(len(v) for v in g_refs.values())), 1),
        "legacy_bm25_mean_text_chars_shown": round(sum(min(300, len(gated.esco[u]["text"])) for k in keys
                                                       for u in B[k]["rag_refs"]) /
                                                   max(1, sum(len(B[k]["rag_refs"]) for k in keys)), 1),
        "on_target_refs": sum(x.source_id in gold_concepts(gated, reqs[k]) for k, v in g_refs.items() for x in v),
        "off_target_refs": sum(x.source_id not in gold_concepts(gated, reqs[k]) for k, v in g_refs.items() for x in v)}
    res["replay_estimate"] = {}
    for proxy_name, proxy in (("B'", B), ("C", C)):
        rp = replay(A, proxy, g_refs, keys)
        res["replay_estimate"][f"gated(abstain->A', else {proxy_name})"] = {
            "label": "ESTIMATE from recorded answers, not a model run",
            "uses_proxy_answer": sum(rp[k] is proxy[k] for k in keys),
            "paired_vs_Aprime": paired(A, rp, keys),
            "unparsed": sum(not rp[k]["parsed"] for k in keys),
            "transitions": {g: v for g, v in transitions(A, rp, reqs, keys).items()
                            if g in ("all", "tag=equivalent_skill_alias", "tag=rag_suggests_absent_skill",
                                     "tag=certification", "category=skill", "category=experience")}}
    lora = load_lora()
    if lora:
        lk = [k for k in keys if k in lora]
        res["lora_partial"] = {
            "label": f"LIVE, PARTIAL ({len(lk)}/202) LoRA + legacy BM25, checkpoint {LORA_REF} (no LoRA no-RAG arm yet)",
            "n": len(lk), "unparsed": sum(not lora[k]["parsed"] for k in lk), "template_echo": sum(echo(lora[k]) for k in lk),
            "accuracy": round(sum(lora[k]["decision"] == lora[k]["gold_decision"] for k in lk) / len(lk), 3),
            "base_B'_accuracy_same_keys": round(sum(B[k]["decision"] == B[k]["gold_decision"] for k in lk) / len(lk), 3),
            "base_A'_accuracy_same_keys": round(sum(A[k]["decision"] == A[k]["gold_decision"] for k in lk) / len(lk), 3),
            "per_tag": {t: {"n": sum(t in lora[k]["tags"] for k in lk),
                            "acc": round(sum(lora[k]["decision"] == lora[k]["gold_decision"] for k in lk if t in lora[k]["tags"])
                                         / max(1, sum(t in lora[k]["tags"] for k in lk)), 3)} for t in KEY_TAGS[:3]}}
    return res


def to_markdown(res):
    L = ["# RAG error analysis (generated by `python -m rag_opt.error_analysis`; no LLM run)", "",
         f"_{res['label']}_", "", "## Runs", "",
         "| run | backend | knowledge | n | macro-F1 | acc | JSON valid | unparsed | template echo | prompt tok | refs injected |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["runs"]:
        L.append(f"| {r['run']} | {r['backend']} | {r['knowledge']} | {r['n']} | {r['macro_f1']:.3f} | {r['accuracy']:.3f} | "
                 f"{r['json_valid']:.3f} | {r['unparsed']} | {r['template_echo']} | {r['mean_prompt_tokens']} | {r['refs_injected']} |")
    L += ["", "## Unparsed outputs by kind", "", "```", json.dumps(res["unparsed_taxonomy"], indent=1), "```", "",
          "## Template echo vs injected references (B′)", "", "| refs | n | echo | rate |", "|---|---|---|---|",
          *(f"| {k} | {v['n']} | {v['echo']} | {v['rate']} |" for k, v in res["echo_by_refs_Bprime"].items()), "",
          "Template echo vs prompt length (A′, B′, C pooled, tertiles):", "", "| prompt tokens | n | echo | rate |",
          "|---|---|---|---|", *(f"| {b['tokens']} | {b['n']} | {b['echo']} | {b['rate']} |" for b in res["echo_by_prompt_tokens"]),
          "", "## Noise floor: identical prompts answered twice (B′ requirements with no reference vs A′)", "",
          "```", json.dumps(res["noise_floor_identical_prompts"]), "```", "",
          f"Accuracy on the {res['parsed_in_all_three']['n']} requirements parsed in A′, B′ and C: "
          + ", ".join(f"{k} {v}" for k, v in res["parsed_in_all_three"].items() if k != "n"), "",
          "## Paired comparisons vs A′ (McNemar on correctness, bootstrap 95% CI of Δ macro-F1)", "",
          "| comparison | Δ macro-F1 | 95% CI | base-only / cand-only correct | McNemar p |", "|---|---|---|---|---|",
          *(f"| {n} vs A′ | {v['delta']:+.3f} | [{v['ci95'][0]:+.3f}, {v['ci95'][1]:+.3f}] | {v['base_only_correct']} / "
            f"{v['cand_only_correct']} | {v['mcnemar_p']} |" for n, v in res["paired_vs_Aprime"].items())]
    for n, tr in res["transitions_vs_Aprime"].items():
        L += ["", f"## Where {n} loses or gains vs A′", "", "| group | n | acc A′ | acc cand | lost (unparsed) | lost (parsed) | gained |",
              "|---|---|---|---|---|---|---|",
              *(f"| {g} | {v['n']} | {v['acc_base']} | {v['acc_cand']} | {v['lost_unparsed']} | {v['lost_parsed']} | {v['gained']} |"
                for g, v in tr.items())]
    for n, rr in res["ref_relevance"].items():
        L += ["", f"## Reference relevance in {n} (gold = ESCO concept whose label/alias equals the skill term)", "",
              "| category | n | has gold concept | reqs with refs | refs | on-target | off-target | gold at rank 1 |",
              "|---|---|---|---|---|---|---|---|",
              *(f"| {c} | {v['n']} | {v['has_gold']} | {v['with_refs']} | {v['refs']} | {v['on_target_refs']} | "
                f"{v['off_target_refs']} | {v['gold_at_1']} |" for c, v in rr.items())]
    g = res["gated_provider"]
    L += ["", f"## {g['name']} on the same 202 requirements (retrieval only)", "", "```", json.dumps(g, indent=1), "```",
          "", "## Replay estimate of gating (NOT a model run; see module docstring)", ""]
    for n, v in res["replay_estimate"].items():
        p = v["paired_vs_Aprime"]
        L += [f"- **{n}**: proxy answers used for {v['uses_proxy_answer']} requirements; macro-F1 {p['macro_f1_cand']:.3f} vs A′ "
              f"{p['macro_f1_base']:.3f} (Δ {p['delta']:+.3f}, 95% CI [{p['ci95'][0]:+.3f}, {p['ci95'][1]:+.3f}], McNemar p "
              f"{p['mcnemar_p']}); unparsed {v['unparsed']}",
              *(f"  - {grp}: acc {t['acc_base']} → {t['acc_cand']} (n={t['n']}, lost {t['lost_unparsed']}+{t['lost_parsed']}, "
                f"gained {t['gained']})" for grp, t in v["transitions"].items())]
    if "lora_partial" in res:
        L += ["", "## LoRA partial checkpoint", "", "```", json.dumps(res["lora_partial"], indent=1), "```"]
    return "\n".join(L) + "\n"


def main():
    res = analyse()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "error_analysis.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    (OUT / "error_analysis.md").write_text(to_markdown(res))
    print(to_markdown(res))


if __name__ == "__main__":
    main()
